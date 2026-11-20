"""メインウィンドウ"""
import logging
from dataclasses import asdict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__, obs
from ..config import ASSET_DIR
from ..db import summarize
from ..worker import TrackerWorker
from . import theme
from .deck_dialog import DeckDialog
from .history import RESULT_TEXT, TURN_TEXT, HistoryTab
from .matchup import MatchupTab
from .settings_dialog import SettingsDialog
from .stats import StatsTab, period_start
from .widgets import panel

log = logging.getLogger(__name__)
AUTO_DECK = "（自動：画面から読み取り）"
# 変えても監視を止めなくてよい設定（監視を止めると試合中の先攻後攻・相手クラスが消える）
LIVE_SETTINGS = {"notify", "screenshot_limit", "obs_enabled", "obs_template"}


def app_icon():
    # tools/make_icon.py で作ったもの。ico にはトレイ用の小さい絵も入っているので ico を優先する
    path = next((p for p in (ASSET_DIR / "icon.ico", ASSET_DIR / "icon.png") if p.exists()), None)
    if path:
        return QIcon(str(path))
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(theme.ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("#0b1320"))
    f = p.font()
    f.setPointSize(22)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "SV")
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self, db, settings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.worker = None
        self.last_id = None
        self._quitting = False
        self.setWindowTitle("SVWB Tracker")
        self.setWindowIcon(app_icon())
        self.resize(1080, 760)

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # 上段: 状態と操作
        top = QHBoxLayout()
        title = QLabel("SVWB Tracker")
        title.setObjectName("h1")
        self.dot = QLabel("●")
        self.status = QLabel("停止中")
        self.window_label = QLabel("")
        self.window_label.setObjectName("muted")
        self.toggle_btn = QPushButton("監視を開始")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.clicked.connect(self.toggle)
        settings_btn = QPushButton("設定")
        settings_btn.clicked.connect(self.open_settings)
        top.addWidget(title)
        version = QLabel(f"v{__version__}")
        version.setObjectName("muted")
        top.addWidget(version)
        top.addSpacing(16)
        top.addWidget(self.dot)
        top.addWidget(self.status)
        top.addSpacing(8)
        top.addWidget(self.window_label)
        top.addStretch()
        quit_btn = QPushButton("終了")
        quit_btn.setToolTip("トラッカーを終了します（ウィンドウを閉じるだけならトレイで記録を続けます）")
        quit_btn.clicked.connect(self._confirm_quit)
        top.addWidget(settings_btn)
        top.addWidget(self.toggle_btn)
        top.addWidget(quit_btn)
        lay.addLayout(top)

        # 使用デッキと今日の成績
        row = QHBoxLayout()
        row.addWidget(QLabel("使用デッキ"))
        self.deck_combo = QComboBox()
        self.deck_combo.setMinimumWidth(280)
        self.deck_combo.setMaxVisibleItems(15)
        self.deck_combo.setToolTip("通常は自動。OCR がうまく読めないときだけ固定してください")
        self.deck_combo.currentTextChanged.connect(self._deck_changed)
        row.addWidget(self.deck_combo)
        add_deck = QPushButton("＋ 登録")
        add_deck.setToolTip("デッキ名を登録します。登録した名前は選択肢に出て、画面の読み取り結果もこの名前に寄せます")
        add_deck.clicked.connect(self._register_deck)
        row.addWidget(add_deck)
        manage_decks = QPushButton("デッキ整理")
        manage_decks.setToolTip("デッキ名の変更・統合と、使わなくなったデッキを隠す操作ができます")
        manage_decks.clicked.connect(self._manage_decks)
        row.addWidget(manage_decks)
        row.addStretch()
        self.today = QLabel("")
        self.today.setStyleSheet("font-size: 11pt;")
        row.addWidget(self.today)
        lay.addLayout(row)

        # 直前の試合（相手クラスと先後をワンクリックで直せる）
        last = panel()
        ll = QVBoxLayout(last)
        ll.setContentsMargins(14, 10, 14, 10)
        self.last_label = QLabel("まだ記録がありません")
        ll.addWidget(self.last_label)
        chips = QHBoxLayout()
        lab = QLabel("相手")
        lab.setObjectName("muted")
        chips.addWidget(lab)
        self.opp_group = QButtonGroup(self)
        self.opp_group.setExclusive(False)
        for c in theme.CLASSES:
            b = QPushButton(c)
            b.setObjectName("chip")
            b.setCheckable(True)
            self.opp_group.addButton(b)
            chips.addWidget(b)
        self.opp_group.buttonClicked.connect(self._set_opponent)
        chips.addSpacing(20)
        lab2 = QLabel("先後")
        lab2.setObjectName("muted")
        chips.addWidget(lab2)
        self.turn_group = QButtonGroup(self)
        self.turn_group.setExclusive(False)
        for key in ("first", "second"):
            b = QPushButton(TURN_TEXT[key])
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setProperty("turn", key)
            self.turn_group.addButton(b)
            chips.addWidget(b)
        self.turn_group.buttonClicked.connect(self._set_turn)
        chips.addStretch()
        ll.addLayout(chips)
        lay.addWidget(last)

        tabs = QTabWidget()
        self.stats = StatsTab(db, lambda: self.settings.hidden_decks)
        self.history = HistoryTab(db, self.reload, self.known_decks)
        self.matchup = MatchupTab(db)
        tabs.addTab(self.stats, "統計")
        tabs.addTab(self.matchup, "相性")
        tabs.addTab(self.history, "履歴")
        lay.addWidget(tabs, 1)

        self._init_tray()
        self.reload()
        self._obs_timer = QTimer(self)  # 日付が変わったら試合がなくても「今日」を更新する
        self._obs_timer.timeout.connect(self._write_obs)
        self._obs_timer.start(60_000)
        self._set_status(False, "停止中")

    # ---------- 表示の更新 ----------

    def reload(self):
        decks = self.known_decks()
        self.deck_combo.blockSignals(True)
        self.deck_combo.clear()
        self.deck_combo.addItem(AUTO_DECK)
        self.deck_combo.addItems(decks)
        if self.settings.deck_override and self.settings.deck_override not in decks:
            self.deck_combo.addItem(self.settings.deck_override)
        self.deck_combo.setCurrentText(self.settings.deck_override or AUTO_DECK)
        self.deck_combo.blockSignals(False)
        if self.worker:
            self.worker.known_decks = decks
            self.worker.last_cr = self.db.last_cr()

        s = summarize(self.db.matches(since=period_start(0)))
        a = s["all"]
        if a["total"]:
            cr = "" if s["cr_net"] is None else f"　CR {s['cr_net']:+d}"
            self.today.setText(f"今日 <b>{a['wins']}勝 {a['losses']}敗</b>（{a['win_rate']:.0f}%）{cr}")
        else:
            self.today.setText("今日はまだ対戦なし")

        rows = self.db.matches()
        self._show_last(rows[0] if rows else None)
        self.stats.reload_decks()
        self.stats.refresh()
        self.matchup.refresh()
        self.history.refresh()
        self._write_obs()

    def _write_obs(self):
        if self.settings.obs_enabled:
            rows = self.db.matches(since=period_start(0))
            obs.write(obs.render(self.settings.obs_template, rows))
            obs.write_overlay(rows)

    def _show_last(self, m):
        self.last_id = m["id"] if m else None
        for b in self.opp_group.buttons() + self.turn_group.buttons():
            b.setEnabled(m is not None)
            b.setChecked(False)
        if not m:
            self.last_label.setText("まだ記録がありません")
            return
        color = theme.WIN if m["result"] == "win" else theme.LOSS
        parts = [f"<span style='color:{color}; font-weight:600'>{RESULT_TEXT[m['result']]}</span>",
                 m["played_at"][5:16], TURN_TEXT.get(m["turn_order"], "-"), m["deck"] or "デッキ不明"]
        if m["cr"] is not None:
            parts.append(f"CR {m['cr']}" + ("" if m["cr_change"] is None else f"（{m['cr_change']:+d}）"))
        self.last_label.setText("直前の試合　" + "　".join(parts))
        for b in self.opp_group.buttons():
            b.setChecked(b.text() == m["opponent"])
        for b in self.turn_group.buttons():
            b.setChecked(b.property("turn") == m["turn_order"])

    def _set_opponent(self, btn):
        if self.last_id is None:
            return
        self.db.update(self.last_id, opponent=btn.text() if btn.isChecked() else None)
        self.reload()

    def _set_turn(self, btn):
        if self.last_id is None:
            return
        self.db.update(self.last_id, turn_order=btn.property("turn") if btn.isChecked() else None)
        self.reload()

    def known_decks(self):
        """登録したデッキ名 → 戦績にあるデッキ名（最近使った順）。隠したデッキは除く"""
        names = list(self.settings.deck_names)
        names += [d for d in self.db.decks() if d not in names]
        return [d for d in names if d not in self.settings.hidden_decks]

    def _register_deck(self):
        name, ok = QInputDialog.getText(self, "デッキ名を登録", "デッキ名（ゲーム内で付けた名前と同じにすると自動で寄せられます）")
        name = name.strip()
        if not ok or not name:
            return
        if name not in self.settings.deck_names:
            self.settings.deck_names.append(name)
        self.settings.save()
        self.reload()

    def _manage_decks(self):
        DeckDialog(self, self.db, self.settings).exec()
        self.reload()

    def _deck_changed(self, text):
        self.settings.deck_override = "" if text in ("", AUTO_DECK) else text.strip()
        self.settings.save()

    def _set_status(self, running, text):
        self.status.setText(text)
        self.dot.setStyleSheet(f"color: {theme.WIN if running else theme.MUTED};")

    # ---------- 監視 ----------

    def toggle(self):
        if self.worker:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.worker:
            return
        self.worker = TrackerWorker(self.settings)
        self.worker.known_decks = self.known_decks()
        self.worker.last_cr = self.db.last_cr()
        self.worker.status.connect(lambda t: self._set_status(True, t))
        self.worker.window.connect(self._on_window)
        self.worker.recorded.connect(self._on_recorded)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self.toggle_btn.setText("監視を停止")
        self.toggle_btn.setObjectName("")
        self.toggle_btn.setStyle(self.toggle_btn.style())
        self._tray_toggle.setText("監視を停止")

    def stop(self):
        if not self.worker:
            return
        self.worker.stop()
        self.worker = None
        self._set_status(False, "停止中")
        self.window_label.setText("")
        self.toggle_btn.setText("監視を開始")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.setStyle(self.toggle_btn.style())
        self._tray_toggle.setText("監視を開始")

    def _on_window(self, found, title):
        self.window_label.setText(f"ゲーム画面: {title}" if found else
                                  f"ゲーム画面が見つかりません（「{self.settings.window_title}」を探しています）")

    def _on_recorded(self, rec):
        same = self.db.find_same_match(rec)
        if same is not None:
            # 再起動をまたいだ / 同じリザルト画面を見直した → 新しい記録は作らず空欄だけ補う
            filled = self.db.fill_missing(same, rec)
            log.info("同じ試合の記録があるので追加しません (id=%s, 補完 %s)", same, filled)
            if filled:
                self.reload()
            return
        self.db.add(**rec)
        if rec.get("deck") in self.settings.hidden_decks:  # 隠したデッキをまた使い始めたら表示に戻す
            self.settings.hidden_decks.remove(rec["deck"])
            self.settings.save()
        self.reload()
        msg = f"{RESULT_TEXT[rec['result']]}　{rec.get('deck') or ''}"
        if rec.get("cr_change") is not None:
            msg += f"　CR {rec['cr_change']:+d}"
        self._notify("戦績を記録しました", msg, 4000)

    def _on_failed(self, err):
        self.stop()
        QMessageBox.critical(self, "監視を開始できません", err)

    def open_settings(self):
        before = asdict(self.settings)
        dlg = SettingsDialog(self, self.settings, self.db)
        if dlg.exec():
            after = asdict(self.settings)
            if {k for k in after if after[k] != before[k]} - LIVE_SETTINGS:
                was_running = self.worker is not None
                self.stop()
                if was_running:
                    self.start()
            self.reload()

    # ---------- トレイ ----------

    def _init_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("SVWB Tracker")
        menu = QMenu()
        show = QAction("表示", self)
        show.triggered.connect(self._show_window)
        self._tray_toggle = QAction("監視を開始", self)
        self._tray_toggle.triggered.connect(self.toggle)
        quit_ = QAction("終了", self)
        quit_.triggered.connect(self.quit)
        for a in (show, self._tray_toggle, quit_):
            menu.addAction(a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self._show_window()
                                    if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _notify(self, title, msg, msec):
        if self.settings.notify:
            self.tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, msec)

    def _show_window(self):
        self.showNormal()
        self.activateWindow()

    def closeEvent(self, event):
        if self._quitting or not self.worker:
            self.stop()
            self.tray.hide()
            event.accept()
            QApplication.instance().quit()
            return
        # 監視中はトレイに隠れて記録を続ける
        event.ignore()
        self.hide()
        self._notify("SVWB Tracker", "バックグラウンドで記録を続けます（終了はトレイのメニューから）", 3000)

    def _confirm_quit(self):
        # 監視中に終了すると、試合中の先攻後攻・相手クラスが記録されない
        if self.worker and QMessageBox.question(
                self, "終了", "トラッカーを終了しますか？\n対戦中に終了すると、その試合は正しく記録されません。") \
                != QMessageBox.StandardButton.Yes:
            return
        self.quit()

    def quit(self):
        self._quitting = True
        self.close()
