"""アプリのアイコン（assets/icon.png と exe 用の assets/icon.ico）を描く

    python tools/make_icon.py

ゲームの素材は使わないオリジナルのデザイン: 右上がりの棒グラフ + 金色の矢印
タスクバーやトレイ（16〜32px）でも潰れないよう、余白を詰めて太い形だけで描く。
小さいサイズは矢印を省いて棒だけにした絵を別に描いて ico に入れる
"""
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
S = 512  # 大きく描いてから縮小する
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SMALL = 32  # これ以下は矢印なしの絵を使う


def draw(arrow=True):
    img = QImage(S, S, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 背景: 明るめの青 → 紫。暗いタスクバーの上でも埋もれないよう、ほぼ全面に描く
    bg = QLinearGradient(0, 0, S, S)
    bg.setColorAt(0, QColor("#2f7cf0"))
    bg.setColorAt(1, QColor("#6b3fd8"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(6, 6, S - 12, S - 12), 100, 100)

    # 右上がりの太い棒グラフ（白）
    base = 440 if arrow else 432
    bars = ((88, 120), (208, 200), (328, 290)) if arrow else ((70, 150), (198, 240), (326, 340))
    w = 100 if arrow else 116
    p.setBrush(QColor("#ffffff"))
    for x, h in bars:
        p.drawRoundedRect(QRectF(x, base - h, w, h), 18, 18)

    if arrow:
        # 金色の上向き矢印（暗い縁取りで棒の白から浮かせる）
        path = QPainterPath(QPointF(70, 300))
        path.lineTo(QPointF(200, 185))
        path.lineTo(QPointF(285, 245))
        path.lineTo(QPointF(385, 140))
        head = QPainterPath(QPointF(440, 82))
        head.lineTo(QPointF(432, 206))
        head.lineTo(QPointF(316, 112))
        head.closeSubpath()
        for color, width in ((QColor("#1a1440"), 78), (QColor("#ffc83d"), 50)):
            pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setBrush(color)
            p.drawPath(head)
    p.end()
    return img


def draw_check():
    """設定のチェックボックスのチェック印（theme.py の QCheckBox::indicator で使う）"""
    img = QImage(36, 36, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath(QPointF(8, 19))
    path.lineTo(QPointF(15, 26))
    path.lineTo(QPointF(28, 10))
    p.setPen(QPen(QColor("#0b1320"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(path)
    p.end()
    img.setDevicePixelRatio(2)
    return img


def draw_arrow(up):
    """数値欄の増減ボタンの矢印（theme.py の ::up-arrow / ::down-arrow で使う）"""
    img = QImage(20, 12, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    y0, y1 = (9, 3) if up else (3, 9)
    path = QPainterPath(QPointF(3, y0))
    path.lineTo(QPointF(10, y1))
    path.lineTo(QPointF(17, y0))
    p.setPen(QPen(QColor("#e6e8ee"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(path)
    p.end()
    return img


def main():
    QGuiApplication(sys.argv)
    draw_check().save(str(ASSETS / "check.png"))
    draw_arrow(True).save(str(ASSETS / "arrow_up.png"))
    draw_arrow(False).save(str(ASSETS / "arrow_down.png"))
    from PIL import Image  # exe 用の .ico（複数サイズ入り）

    def to_pil(img, size):
        small = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        tmp = ASSETS / f"_icon{size}.png"
        small.save(str(tmp))
        out = Image.open(tmp).copy()
        tmp.unlink()
        return out

    big, simple = draw(True), draw(False)
    png = ASSETS / "icon.png"
    big.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save(str(png))
    imgs = [to_pil(simple if s <= SMALL else big, s) for s in ICO_SIZES]
    imgs[-1].save(ASSETS / "icon.ico", sizes=[(s, s) for s in ICO_SIZES], append_images=imgs[:-1])
    print("saved", png, ASSETS / "icon.ico")


if __name__ == "__main__":
    main()
