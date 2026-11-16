"""ゲームウィンドウのキャプチャ（読み取りのみ）"""
import ctypes
import logging
import os

import cv2
import mss
import numpy as np
import win32gui
import win32process

from .config import BASE_H, BASE_W

log = logging.getLogger(__name__)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def normalize(img):
    """1920x1080 に揃える"""
    if img.shape[1] == BASE_W and img.shape[0] == BASE_H:
        return img
    return cv2.resize(img, (BASE_W, BASE_H), interpolation=cv2.INTER_AREA)


class WindowCapture:
    def __init__(self, title_keyword):
        self.keyword = title_keyword.lower()
        self.hwnd = None
        self.title = ""
        self._sct = self._new_sct()
        self._pid = os.getpid()
        self.failures = 0  # 画面の取得に連続で失敗した回数

    @staticmethod
    def _new_sct():
        return mss.MSS() if hasattr(mss, "MSS") else mss.mss()

    def _shot(self, region):
        """画面の一部を撮る。PC のロック中などは失敗するので、作り直して次の回に備える"""
        try:
            img = np.asarray(self._sct.grab(region))
        except Exception as e:
            self.failures += 1
            if self.failures == 1:
                log.warning("画面の取得に失敗: %s", e)
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = self._new_sct()
            return None
        self.failures = 0
        return img

    def _find(self):
        found = []

        def cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if self.keyword in title.lower():
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception:
                    pid = None
                if pid != self._pid:  # 自分のウィンドウは除外
                    found.append((hwnd, title))
            return True

        win32gui.EnumWindows(cb, None)
        if found:
            self.hwnd, self.title = found[0]
            log.info("ゲームウィンドウを検出: %s", self.title)
        else:
            self.hwnd, self.title = None, ""
        return self.hwnd

    def grab(self):
        """正規化済み BGR 画像。ウィンドウがない / 最小化中なら None"""
        if self.hwnd is None or not win32gui.IsWindow(self.hwnd):
            if self._find() is None:
                return None
        if win32gui.IsIconic(self.hwnd):
            return None
        try:
            l, t, r, b = win32gui.GetClientRect(self.hwnd)
            x, y = win32gui.ClientToScreen(self.hwnd, (l, t))
        except Exception:
            self.hwnd = None
            return None
        w, h = r - l, b - t
        if w < 320 or h < 180:
            return None
        img = self._shot({"left": x, "top": y, "width": w, "height": h})
        if img is None:
            return None
        return normalize(cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))

    @property
    def found(self):
        return self.hwnd is not None
