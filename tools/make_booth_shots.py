"""BOOTH 掲載用のスクショ（配布用/booth/*.png）を、自分の戦績の日時だけずらして撮る

    python tools/make_booth_shots.py

本物の DB は読み取り専用で開き、一時フォルダの DB に写してから日時を変える。本物の戦績・設定には書き込まず、
ゲームの画面も写さない。ウィンドウは画面に出さずに描く（ゲーム中に実行してもフォーカスを奪わない）
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["QT_SCALE_FACTOR"] = "2"  # 掲載しても粗く見えないよう2倍で描く

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from svwb.config import Settings  # noqa: E402
from svwb.db import Database  # noqa: E402
from svwb.gui import main_window as main_window_module  # noqa: E402
from svwb.gui import stats as stats_module  # noqa: E402
from svwb.gui import theme  # noqa: E402
from svwb.gui.history import MatchDialog  # noqa: E402
from svwb.gui.main_window import MainWindow  # noqa: E402
from svwb.gui.settings_dialog import SettingsDialog  # noqa: E402

REAL_DB = ROOT / "app" / "data" / "matches.db"
OUT = ROOT / "配布用" / "booth"
SHIFT = timedelta(days=-3, hours=-4)  # 全試合を同じだけずらす（順番と間隔はそのまま）。最後の試合が 11-01 になる
CUTOFF = "2026-11-05 02:38:41"  # 撮り直しても写る試合が変わらないよう、ここまでの戦績だけ使う
FMT = "%Y-%m-%d %H:%M:%S"


def load_real_matches():
    conn = sqlite3.connect(f"file:{REAL_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM matches WHERE played_at <= ? ORDER BY played_at", (CUTOFF,))]
    conn.close()
    for r in rows:
        r["played_at"] = (datetime.strptime(r["played_at"], FMT) + SHIFT).strftime(FMT)
        del r["id"], r["screenshot"]  # スクショのパスは画面に出さない
    return rows


def freeze_today(now):
    """「今日」の集計を、ずらした後の最後の試合の日で数える（stats.period_start と同じ区切り）"""
    def period_start(days):
        if days is None:
            return None
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now.hour < 5:
            base -= timedelta(days=1)
        return (base.replace(hour=5) - timedelta(days=max(days - 1, 0))).strftime(FMT)
    stats_module.period_start = period_start
    main_window_module.period_start = period_start


def shoot(widget, name, size=None):
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    if size:
        widget.resize(*size)
    widget.show()
    QApplication.processEvents()
    QApplication.processEvents()
    widget.grab().save(str(OUT / name))
    print("saved", name)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.STYLE)
    QSystemTrayIcon.show = lambda self: None  # トレイにアイコンを出さない
    Settings.save = lambda self: None  # 本物の設定ファイルに書かない
    OUT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "shots.db")
        rows = load_real_matches()
        for r in rows:
            db.add(**r)
        freeze_today(datetime.strptime(rows[-1]["played_at"], FMT))
        settings = Settings()  # 設定画面は配布時の初期値で撮る
        win = MainWindow(db, settings)
        win._set_status(True, "記録済み（画面遷移待ち）")
        win.window_label.setText("ゲーム画面: ShadowverseWB")
        win.toggle_btn.setText("監視を停止")
        win.toggle_btn.setObjectName("")
        win.toggle_btn.setStyle(win.toggle_btn.style())

        tabs = win.stats.parentWidget().parentWidget()
        tabs.setCurrentWidget(win.stats)
        shoot(win, "1_統計.png", (1100, 900))
        tabs.setCurrentWidget(win.history)
        shoot(win, "2_履歴.png", (1100, 860))

        dlg = MatchDialog(win, win.known_decks(), db.matches()[0])
        shoot(dlg, "3_編集.png", (460, 0))
        dlg.reject()

        sd = SettingsDialog(win, settings, db)
        shoot(sd, "4_設定.png", (620, 0))
        sd.reject()

        wins = sum(r["result"] == "win" for r in rows)
        print(f"{len(rows)} matches, {wins} wins, {rows[0]['played_at']} - {rows[-1]['played_at']}")
        win.tray.hide()
        db.conn.close()
    app.quit()


if __name__ == "__main__":
    main()
