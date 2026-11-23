"""履歴タブと編集ダイアログ"""
import logging
import os
import time
from datetime import datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme

log = logging.getLogger(__name__)

RESULT_TEXT = {"win": "勝ち", "loss": "負け"}
TURN_TEXT = {"first": "先攻", "second": "後攻", None: "-"}
COLS = [("played_at", "日時"), ("result", "結果"), ("turn_order", "先後"), ("deck", "デッキ"),
        ("opponent", "相手"), ("cr", "CR"), ("cr_change", "変動"), ("rank", "ランク"), ("notes", "メモ")]


def _int_or_none(text):
    text = text.strip().replace("+", "")
    try:
        return int(text) if text else None
    except ValueError:
        return None


class MatchDialog(QDialog):
    def __init__(self, parent, decks, match=None):
        super().__init__(parent)
        self.setWindowTitle("戦績を編集" if match else "戦績を手動で追加")
        m = match or {}
        form = QFormLayout(self)

        self.played_at = QDateTimeEdit()
        self.played_at.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.played_at.setCalendarPopup(True)
        self.played_at.setDateTime(QDateTime.fromString(m["played_at"], "yyyy-MM-dd HH:mm:ss")
                                   if m.get("played_at") else QDateTime.currentDateTime())
        self.result = QComboBox()
        for k, v in RESULT_TEXT.items():
            self.result.addItem(v, k)
        self.result.setCurrentIndex(max(self.result.findData(m.get("result", "win")), 0))
        self.turn = QComboBox()
        for k in (None, "first", "second"):
            self.turn.addItem("不明" if k is None else TURN_TEXT[k], k)
        self.turn.setCurrentIndex(max(self.turn.findData(m.get("turn_order")), 0))
        self.deck = QComboBox()
        self.deck.setEditable(True)
        self.deck.setMaxVisibleItems(15)
        self.deck.addItems(decks)
        self.deck.setCurrentText(m.get("deck") or (decks[0] if decks and not match else ""))
        self.my_class = QComboBox()
        self.my_class.addItem("", None)
        for c in theme.CLASSES:
            self.my_class.addItem(c, c)
        self.my_class.setCurrentIndex(max(self.my_class.findData(m.get("my_class")), 0))
        self.my_class.setToolTip("対戦開始の画面から読んだクラスです。CR のグラフを分けるのに使います。\n"
                                 "空のときはデッキから判断します")
        self.opponent = QComboBox()
        self.opponent.setEditable(True)
        self.opponent.addItems([""] + theme.CLASSES)
        self.opponent.setCurrentText(m.get("opponent") or "")
        self.cr = QLineEdit("" if m.get("cr") is None else str(m["cr"]))
        self.cr_change = QLineEdit("" if m.get("cr_change") is None else f"{m['cr_change']:+d}")
        self.notes = QLineEdit(m.get("notes") or "")

        form.addRow("日時", self.played_at)
        form.addRow("結果", self.result)
        form.addRow("先攻/後攻", self.turn)
        form.addRow("使用デッキ", self.deck)
        form.addRow("自分のクラス", self.my_class)
        form.addRow("相手クラス", self.opponent)
        form.addRow("CR", self.cr)
        form.addRow("変動CR", self.cr_change)
        form.addRow("メモ", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.resize(420, 0)

    def values(self):
        return {
            "played_at": self.played_at.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "result": self.result.currentData(),
            "turn_order": self.turn.currentData(),
            "deck": self.deck.currentText().strip() or None,
            "my_class": self.my_class.currentData(),
            "opponent": self.opponent.currentText().strip() or None,
            "cr": _int_or_none(self.cr.text()),
            "cr_change": _int_or_none(self.cr_change.text()),
            "notes": self.notes.text().strip() or None,
        }


class HistoryTab(QWidget):
    def __init__(self, db, on_changed, known_decks):
        super().__init__()
        self.db = db
        self.known_decks = known_decks
        self.on_changed = on_changed
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)

        bar = QHBoxLayout()
        add = QPushButton("＋ 手動で追加")
        edit = QPushButton("編集")
        shot = QPushButton("スクショを開く")
        delete = QPushButton("削除")
        delete.setObjectName("danger")
        export = QPushButton("CSV に書き出し")
        add.clicked.connect(self.add)
        edit.clicked.connect(self.edit)
        shot.clicked.connect(self.open_screenshot)
        delete.clicked.connect(self.delete)
        export.clicked.connect(self.export)
        for b in (add, edit, shot, delete):
            bar.addWidget(b)
        bar.addStretch()
        bar.addWidget(export)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([h for _, h in COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self._fit_columns(True)
        self.table.doubleClicked.connect(self.edit)
        lay.addWidget(self.table)

    def _fit_columns(self, auto):
        # ResizeToContents のまま表示中に書き込むと、1マス入れるたびに全列の幅を測り直して数秒かかる。
        # 書き込む間だけ Interactive にして、終わったら戻す（戻したときに1回だけ測る）
        hh = self.table.horizontalHeader()
        mode = QHeaderView.ResizeMode.ResizeToContents if auto else QHeaderView.ResizeMode.Interactive
        hh.setSectionResizeMode(mode)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def refresh(self):
        rows = self.db.matches()
        self.table.setUpdatesEnabled(False)  # 全行を入れ終わってから1回だけ描き直す
        self._fit_columns(False)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, (key, _) in enumerate(COLS):
                v = r[key]
                if key == "played_at":
                    text = v[:16]
                elif key == "result":
                    text = RESULT_TEXT.get(v, v)
                elif key == "turn_order":
                    text = TURN_TEXT.get(v, "-")
                elif key == "cr_change":
                    text = "" if v is None else f"{v:+d}"
                else:
                    text = "" if v is None else str(v)
                it = QTableWidgetItem(text)
                if key == "played_at":
                    it.setData(Qt.ItemDataRole.UserRole, r["id"])
                if key in ("result", "cr_change") and v is not None:
                    good = v == "win" if key == "result" else v >= 0
                    it.setForeground(QColor(theme.WIN if good else theme.LOSS))
                if key == "turn_order" and v:
                    it.setForeground(QColor(theme.FIRST if v == "first" else theme.SECOND))
                if key not in ("deck", "notes", "rank"):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, j, it)
        self._fit_columns(True)
        self.table.setUpdatesEnabled(True)

    def _selected_ids(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def add(self):
        dlg = MatchDialog(self, self.known_decks())
        if dlg.exec():
            self.db.add(source="manual", **dlg.values())
            self.on_changed()

    def edit(self):
        ids = self._selected_ids()
        if not ids:
            return
        dlg = MatchDialog(self, self.known_decks(), self.db.get(ids[0]))
        if dlg.exec():
            t0 = time.perf_counter()
            self.db.update(ids[0], **dlg.values())
            t1 = time.perf_counter()
            self.on_changed()
            t2 = time.perf_counter()
            # 「OK から反映まで遅い」という報告の調査用
            if t2 - t0 > 0.3:
                log.warning("編集の反映に %.2f 秒（DB 保存 %.2f / 画面更新 %.2f）", t2 - t0, t1 - t0, t2 - t1)

    def delete(self):
        ids = self._selected_ids()
        if not ids:
            return
        if QMessageBox.question(self, "削除", f"{len(ids)} 件の戦績を削除しますか？（元に戻せません）") \
                == QMessageBox.StandardButton.Yes:
            self.db.delete(ids)
            self.on_changed()

    def open_screenshot(self):
        ids = self._selected_ids()
        m = self.db.get(ids[0]) if ids else None
        if m and m.get("screenshot") and os.path.exists(m["screenshot"]):
            os.startfile(m["screenshot"])
        elif m:
            QMessageBox.information(self, "スクショ", "この試合のスクリーンショットはありません。")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "CSV に書き出し", f"svwb_matches_{datetime.now():%Y%m%d}.csv",
                                              "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:  # Excel で文字化けしないよう BOM 付き
                f.write(self.db.export_csv())
