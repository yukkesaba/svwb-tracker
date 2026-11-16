"""相性タブ: 自分のデッキ × 相手クラスの勝率表"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..db import matchup
from . import stats, theme

TURNS = [("すべて", None), ("先攻のみ", "first"), ("後攻のみ", "second")]
TOTAL = "合計"
FEW = 5  # これより少ない試合数は参考程度なので色を付けない


class MatchupTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)

        filters = QHBoxLayout()
        self.period = QComboBox()
        for name, _ in stats.PERIODS:
            self.period.addItem(name)
        self.period.setCurrentIndex(3)
        self.turn = QComboBox()
        for name, key in TURNS:
            self.turn.addItem(name, key)
        for w in (self.period, self.turn):
            w.currentIndexChanged.connect(self.refresh)
        filters.addWidget(QLabel("期間"))
        filters.addWidget(self.period)
        filters.addSpacing(12)
        filters.addWidget(QLabel("先後"))
        filters.addWidget(self.turn)
        filters.addSpacing(16)
        note = QLabel(f"上段は勝率、下段は勝ち-負け。{FEW} 試合未満は色を付けません")
        note.setObjectName("muted")
        filters.addWidget(note)
        filters.addStretch()
        lay.addLayout(filters)

        self.cols = list(theme.CLASSES) + [TOTAL]
        self.table = QTableWidget(0, len(self.cols) + 1)
        self.table.setHorizontalHeaderLabels(["デッキ ＼ 相手"] + self.cols)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table)

    def refresh(self):
        rows = self.db.matches(since=stats.period_start(stats.PERIODS[self.period.currentIndex()][1]))
        turn = self.turn.currentData()
        if turn:
            rows = [r for r in rows if r["turn_order"] == turn]
        table = matchup(rows)
        decks = sorted((d for d in table if d != TOTAL), key=lambda d: -table[d][TOTAL][1])
        if decks:
            decks.append(TOTAL)
        self.table.setRowCount(len(decks))
        for i, deck in enumerate(decks):
            self.table.setItem(i, 0, QTableWidgetItem(deck))
            for j, opp in enumerate(self.cols, 1):
                wins, n = table[deck].get(opp, (0, 0))
                it = QTableWidgetItem(f"{wins / n * 100:.0f}%\n{wins}-{n - wins}" if n else "")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if n:
                    rate = wins / n * 100
                    if n < FEW:
                        it.setForeground(QColor(theme.MUTED))
                    elif rate >= 55:
                        it.setForeground(QColor(theme.WIN))
                    elif rate <= 45:
                        it.setForeground(QColor(theme.LOSS))
                    it.setToolTip(f"{deck} vs {opp}: {n} 試合 {wins}勝 {n - wins}敗")
                self.table.setItem(i, j, it)
