"""Windows 標準の OCR エンジン（日本語）を同期的に呼ぶ薄いラッパー"""
import asyncio
import logging
import threading
from dataclasses import dataclass

import cv2

log = logging.getLogger(__name__)

try:
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
except ImportError:  # pragma: no cover - Windows 以外 / 未インストール
    OcrEngine = None


@dataclass
class OcrLine:
    text: str  # 単語間の空白は除去済み（日本語OCRは1文字ずつ空白が入るため）
    x: int
    y: int
    w: int
    h: int


class Ocr:
    def __init__(self, lang="ja"):
        if OcrEngine is None:
            raise RuntimeError("winrt の OCR パッケージがありません（pip install -r requirements.txt）")
        self.engine = OcrEngine.try_create_from_language(Language(lang))
        if self.engine is None:
            raise RuntimeError("Windows の日本語 OCR が使えません（Windowsの設定で日本語の言語パックを追加してください）")
        self._lock = threading.Lock()

    def lines(self, img, scale=1.0):
        """BGR 画像を読んで行のリストを返す。座標は元画像基準"""
        if scale != 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        h, w = img.shape[:2]
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA) if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        bmp = SoftwareBitmap(BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)
        bmp.copy_from_buffer(memoryview(bgra.tobytes()))

        async def run():
            return await self.engine.recognize_async(bmp)

        with self._lock:
            result = asyncio.run(run())
        out = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            xs = [wd.bounding_rect.x for wd in words]
            ys = [wd.bounding_rect.y for wd in words]
            x2 = [wd.bounding_rect.x + wd.bounding_rect.width for wd in words]
            y2 = [wd.bounding_rect.y + wd.bounding_rect.height for wd in words]
            out.append(OcrLine(
                text="".join(wd.text for wd in words),
                x=int(min(xs) / scale), y=int(min(ys) / scale),
                w=int((max(x2) - min(xs)) / scale), h=int((max(y2) - min(ys)) / scale),
            ))
        return out

    def text(self, img, scale=1.0):
        return "\n".join(l.text for l in self.lines(img, scale))
