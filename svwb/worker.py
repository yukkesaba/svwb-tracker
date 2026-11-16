"""キャプチャ → 判定を別スレッドで回し、結果を Qt シグナルで GUI に渡す"""
import logging
import time
from datetime import datetime

import cv2
from PySide6.QtCore import QThread, Signal

from .capture import WindowCapture
from .config import DATA_DIR, SCREENSHOT_DIR
from .ocr import Ocr
from .screens import ResultScreenDetector, VsScreenDetector
from .storage import prune_screenshots
from .tracker import MatchTracker

log = logging.getLogger(__name__)
CAPTURE_WARN = 10  # 画面の取得にこの回数続けて失敗したら画面に知らせる
CAPTURE_BLOCKED = "画面を取得できません（PC のロック中などは記録できません）"


class TrackerWorker(QThread):
    status = Signal(str)
    window = Signal(bool, str)
    recorded = Signal(dict)
    failed = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        # GUI スレッドが最新値を入れておく（読み取り専用で使う）
        self.known_decks = []
        self.last_cr = None
        self._running = False

    def run(self):
        try:
            ocr = Ocr()
            detector = ResultScreenDetector(self.settings.title_threshold)
            vs_detector = VsScreenDetector()
        except Exception as e:
            self.failed.emit(str(e))
            return
        tracker = MatchTracker(detector, vs_detector, ocr, self.settings,
                               known_decks=lambda: self.known_decks,
                               last_cr=lambda: self.last_cr,
                               on_record=self._on_record,
                               on_status=self.status.emit,
                               on_debug=self._on_debug)
        cap = WindowCapture(self.settings.window_title)
        self._running = True
        was_found = None
        blocked = False
        self.status.emit(tracker.state.value)
        while self._running:
            start = time.monotonic()
            try:
                frame = cap.grab()
                if cap.found != was_found:
                    was_found = cap.found
                    self.window.emit(cap.found, cap.title)
                if cap.failures >= CAPTURE_WARN and not blocked:
                    blocked = True
                    self.status.emit(CAPTURE_BLOCKED)
                elif blocked and frame is not None:
                    blocked = False
                    log.info("画面の取得が回復しました")
                    self.status.emit(tracker.state.value)
                if frame is not None:
                    tracker.feed(frame)
            except Exception:
                log.exception("フレーム処理でエラー")
            wait = tracker.interval - (time.monotonic() - start)  # VS 待ちの間だけ短くなる
            if wait > 0:
                self.msleep(int(wait * 1000))

    def stop(self):
        self._running = False
        self.wait(3000)

    def _on_debug(self, name, frame):
        """読み取りに失敗した画面を残す（古いものから消して最大20枚）"""
        folder = DATA_DIR / "debug"
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        for old in sorted(folder.glob("*.jpg"))[:-20]:
            old.unlink()

    def _on_record(self, rec, frame):
        if self.settings.save_screenshots and frame is not None:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            path = SCREENSHOT_DIR / f"{rec['result']}_{datetime.now():%Y%m%d_%H%M%S}.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            rec["screenshot"] = str(path)
            if self.settings.screenshot_limit > 0:
                prune_screenshots(SCREENSHOT_DIR, self.settings.screenshot_limit)
        self.recorded.emit(rec)
