"""デッキ整理ダイアログ（名前の変更・統合と、使わなくなったデッキを隠す）"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..db import deck_class
from . import theme

log = logging.getLogger(__name__)
HEADERS = ["デッキ", "クラス", "試合", "勝率", "最後に使った日", "状態"]
CLASS_AUTO = "（名前から自動）"


class DeckDialog(QDialog):
    def __init__(self, parent, db, settings):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.setWindowTitle("デッキ整理")
        self.resize(720, 520)
        lay = QVBoxLayout(self)

        note = QLabel("隠したデッキは選択肢と読み取りの候補から外れます。戦績と統計には残ります。\n"
                      "隠したデッキをまた使うと、自動で表示に戻ります。\n"
                      "CR のグラフはクラスごとに出ます。クラスが「-」のデッキは「クラスを指定」で選んでください。")
        note.setObjectName("muted")
        lay.addWidget(note)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)

        bar = QHBoxLayout()
        rename = QPushButton("名前の変更・統合")
        klass = QPushButton("クラスを指定")
        klass.clicked.connect(self.set_class)
        hide = QPushButton("隠す")
        show = QPushButton("表示に戻す")
        close = QPushButton("閉じる")
        rename.clicked.connect(self.rename)
        hide.clicked.connect(lambda: self._set_hidden(True))
        show.clicked.connect(lambda: self._set_hidden(False))
        close.clicked.connect(self.accept)
        for b in (rename, klass, hide, show):
            bar.addWidget(b)
        bar.addStretch()
        bar.addWidget(close)
        lay.addLayout(bar)
        self.refresh()

    def refresh(self):
        rows = self.db.deck_summary()
        self.table.setRowCount(len(rows))
        for i, d in enumerate(rows):
            hidden = d["deck"] in self.settings.hidden_decks
            cells = [d["deck"], deck_class(d["deck"], self.settings.deck_classes) or "-", str(d["n"]),
                     f"{d['wins'] / d['n'] * 100:.1f}%", d["last"][:10], "非表示" if hidden else ""]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if j:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if hidden:
                    it.setForeground(QColor(theme.MUTED))
                self.table.setItem(i, j, it)

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).text() for r in rows]

    def _set_hidden(self, hidden):
        names = self._selected()
        if not names:
            return
        current = [d for d in self.settings.hidden_decks if d not in names]
        self.settings.hidden_decks = current + names if hidden else current
        self.settings.save()
        self.refresh()

    def set_class(self):
        names = self._selected()
        if not names:
            QMessageBox.information(self, "デッキ整理", "クラスを指定するデッキを選んでください（複数選べます）。")
            return
        choices = [CLASS_AUTO] + theme.CLASSES
        cur = self.settings.deck_classes.get(names[0], CLASS_AUTO)
        c, ok = QInputDialog.getItem(self, "クラスを指定", "、".join(names) + " のクラス",
                                     choices, choices.index(cur) if cur in choices else 0, False)
        if not ok:
            return
        for n in names:
            self.settings.deck_classes.pop(n, None)
            if c != CLASS_AUTO:
                self.settings.deck_classes[n] = c
        self.settings.save()
        self.refresh()

    def rename(self):
        names = self._selected()
        if not names:
            QMessageBox.information(self, "デッキ整理", "変更するデッキを選んでください（複数選ぶと1つに統合します）。")
            return
        others = [d["deck"] for d in self.db.deck_summary() if d["deck"] not in names]
        new, ok = QInputDialog.getItem(self, "名前の変更・統合", f"{len(names)} 個のデッキの新しい名前（既存の名前を選ぶと統合します）",
                                       names[:1] + others, 0, True)
        new = new.strip()
        if not ok or not new:
            return
        targets = [n for n in names if n != new]
        if not targets:
            return
        n = sum(d["n"] for d in self.db.deck_summary() if d["deck"] in targets)
        msg = "\n".join(targets) + f"\n\n↓ {n} 試合の記録を「{new}」に変更します。\nデータの控えを作ってから変更します。"
        if QMessageBox.question(self, "名前の変更・統合", msg) != QMessageBox.StandardButton.Yes:
            return
        backup = self.db.backup()
        log.info("デッキ名を変更: %s → %s (%d 試合, 控え %s)", targets, new, n, backup)
        for old in targets:
            self.db.rename_deck(old, new)
        s = self.settings
        s.deck_names = list(dict.fromkeys(new if d in targets else d for d in s.deck_names))
        s.hidden_decks = [d for d in s.hidden_decks if d not in targets]
        classes = [s.deck_classes.pop(d) for d in targets if d in s.deck_classes]
        if classes:  # 指定したクラスは新しい名前に引き継ぐ（新しい名前に指定があればそちら）
            s.deck_classes.setdefault(new, classes[0])
        if s.deck_override in targets:
            s.deck_override = new
        s.save()
        self.refresh()
