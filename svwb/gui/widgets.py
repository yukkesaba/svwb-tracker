"""小さな部品: 数字カード、CR推移グラフ"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from . import theme


def panel():
    f = QFrame()
    f.setObjectName("panel")
    return f


class StatCard(QFrame):
    """見出し・大きな数字・補足の3段"""

    def __init__(self, title, color=theme.TEXT):
        super().__init__()
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.value = QLabel("-")
        self.value.setStyleSheet(f"font-size: 20pt; font-weight: 600; color: {color};")
        self.sub = QLabel("")
        self.sub.setObjectName("muted")
        for w in (self.title, self.value, self.sub):
            lay.addWidget(w)

    def set(self, value, sub="", color=None):
        self.value.setText(value)
        self.sub.setText(sub)
        if color:
            self.value.setStyleSheet(f"font-size: 20pt; font-weight: 600; color: {color};")


def fmt_record(s):
    """{'total','wins','losses','win_rate'} → ('58.3%', '7勝5敗')"""
    if not s["total"]:
        return "-", "記録なし"
    return f"{s['win_rate']:.1f}%", f"{s['wins']}勝 {s['losses']}敗"


class CrChart(QWidget):
    """CR の推移。点の色は勝敗"""

    def __init__(self):
        super().__init__()
        self.points = []  # [(cr, result)] 古い順
        self.setMinimumHeight(180)

    def set_points(self, points):
        self.points = points
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(48, 14, -14, -24)
        p.setPen(QColor(theme.MUTED))
        if len(self.points) < 2:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "CR の記録が2件以上になるとグラフが出ます")
            return
        vals = [c for c, _ in self.points]
        lo, hi = min(vals), max(vals)
        pad = max(10, (hi - lo) * 0.1)
        lo, hi = lo - pad, hi + pad

        def pt(i, v):
            x = r.left() + r.width() * i / (len(vals) - 1)
            y = r.bottom() - r.height() * (v - lo) / (hi - lo)
            return QPointF(x, y)

        p.setFont(QFont(p.font().family(), 8))
        grid = QPen(QColor(theme.BORDER))
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            y = pt(0, v).y()
            p.setPen(grid)
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, y - 8, 44, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v:.0f}")
        p.drawText(QRectF(r.left(), r.bottom() + 4, r.width(), 18), Qt.AlignmentFlag.AlignCenter,
                   f"直近 {len(vals)} 試合")

        path = QPainterPath(pt(0, vals[0]))
        for i, v in enumerate(vals[1:], 1):
            path.lineTo(pt(i, v))
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        p.drawPath(path)
        radius = 3.5 if len(vals) <= 60 else 2
        for i, (v, res) in enumerate(self.points):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.WIN if res == "win" else theme.LOSS))
            p.drawEllipse(pt(i, v), radius, radius)
