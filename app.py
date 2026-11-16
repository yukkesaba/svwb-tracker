"""SVWB Tracker - Shadowverse: Worlds Beyond の戦績を自動で記録する

    python app.py              # 起動するとすぐ監視を始める
    python app.py --no-start   # 監視を止めた状態で起動
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from svwb.config import DATA_DIR, LOG_PATH, Settings
from svwb.db import Database
from svwb.gui.main_window import MainWindow
from svwb.gui.theme import STYLE


def setup_logging():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


SERVER_NAME = "svwb-tracker-single-instance"


def notify_running_instance():
    """すでに起動していればウィンドウを出すよう頼んで True を返す"""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(500):
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True
    return False


def listen_for_second_launch(win):
    QLocalServer.removeServer(SERVER_NAME)  # 前回異常終了したときの残骸を消す
    server = QLocalServer(win)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win._show_window()))
    server.listen(SERVER_NAME)
    return server


def main():
    setup_logging()
    app = QApplication(sys.argv)
    # 2つ同時に動くと1試合が2回記録されるので、2つ目は既存のウィンドウを出して終わる
    if notify_running_instance():
        logging.info("すでに起動しているので終了します")
        return
    app.setApplicationName("SVWB Tracker")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)  # トレイに隠れても動き続ける

    settings = Settings.load()
    db = Database()
    win = MainWindow(db, settings)
    app._single_instance = listen_for_second_launch(win)
    app.aboutToQuit.connect(win.stop)
    if not settings.start_minimized:
        win.show()
    if "--no-start" not in sys.argv:
        win.start()
    code = app.exec()
    db.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
