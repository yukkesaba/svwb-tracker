"""色とスタイルシート（ダークテーマ）"""
from ..config import ASSET_DIR
from ..screens import CLASSES  # noqa: F401  （GUI からは theme.CLASSES で参照）

BG = "#15171c"
PANEL = "#1e2129"
PANEL_2 = "#262a34"
BORDER = "#323744"
TEXT = "#e6e8ee"
MUTED = "#8b91a1"
ACCENT = "#5aa9ff"
WIN = "#4cc38a"
LOSS = "#ef6461"
FIRST = "#f2b84b"
SECOND = "#b18cff"

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: "Yu Gothic UI", "Meiryo UI", sans-serif; font-size: 10pt; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#h1 {{ font-size: 15pt; font-weight: 600; }}
QPushButton {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton#primary {{ background: {ACCENT}; color: #0b1320; border: none; font-weight: 600; }}
QPushButton#danger {{ color: {LOSS}; }}
QPushButton#chip {{ padding: 4px 10px; border-radius: 12px; }}
QPushButton#chip:checked {{ background: {ACCENT}; color: #0b1320; border-color: {ACCENT}; }}
QComboBox, QLineEdit, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px; }}
QComboBox {{ combobox-popup: 0; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; selection-background-color: {ACCENT}; }}
QSpinBox, QDoubleSpinBox, QDateTimeEdit {{ padding-right: 24px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QDateTimeEdit::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
    width: 22px; background: {BORDER}; border: none; border-top-right-radius: 6px; margin-bottom: 1px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateTimeEdit::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 22px; background: {BORDER}; border: none; border-bottom-right-radius: 6px; margin-top: 1px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QDateTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover, QDateTimeEdit::down-button:hover {{ background: {ACCENT}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateTimeEdit::up-arrow {{ width: 10px; height: 6px; image: url("{(ASSET_DIR / 'arrow_up.png').as_posix()}"); }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateTimeEdit::down-arrow {{ width: 10px; height: 6px; image: url("{(ASSET_DIR / 'arrow_down.png').as_posix()}"); }}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; background: {PANEL_2}; border: 2px solid {MUTED}; border-radius: 4px; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{(ASSET_DIR / 'check.png').as_posix()}"); }}
QTabWidget::pane {{ border: none; }}
QTabWidget::tab-bar {{ left: 0; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: {PANEL_2}; color: {MUTED}; border: 1px solid {BORDER}; padding: 7px 28px;
    margin-bottom: 8px; font-size: 11pt; font-weight: 600; min-width: 64px; }}
QTabBar::tab:first {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QTabBar::tab:middle {{ border-left: none; }}
QTabBar::tab:last {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; border-left: none; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; border-color: {ACCENT}; }}
QTabBar::tab:selected {{ background: {ACCENT}; color: #0b1320; border-color: {ACCENT}; }}
QTableWidget {{ background: {PANEL}; alternate-background-color: {PANEL_2}; gridline-color: {BORDER};
    border: 1px solid {BORDER}; border-radius: 8px; selection-background-color: #2f4a6b; }}
QHeaderView::section {{ background: {PANEL_2}; color: {MUTED}; border: none; padding: 6px; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""
