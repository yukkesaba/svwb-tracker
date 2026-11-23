"""統計タブ"""
from collections import defaultdict
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..db import cr_groups, summarize
from . import theme
from .widgets import CrChart, StatCard, fmt_record, panel

PERIODS = [("今日", 0), ("7日間", 7), ("30日間", 30), ("全期間", None)]


def period_start(days):
    if days is None:
        return None
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # 深夜プレイを考慮して「今日」は朝5時区切り
    if datetime.now().hour < 5:
        base -= timedelta(days=1)
    return (base.replace(hour=5) - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d %H:%M:%S")


def rate_text(wins, total):
    return f"{wins / total * 100:.1f}%" if total else "-"


class StatsTab(QWidget):
    def __init__(self, db, hidden_decks=lambda: (), deck_classes=lambda: {}):
        super().__init__()
        self.db = db
        self.hidden_decks = hidden_decks
        self.deck_classes = deck_classes
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)

        filters = QHBoxLayout()
        self.period = QComboBox()
        for name, _ in PERIODS:
            self.period.addItem(name)
        self.period.setCurrentIndex(3)
        self.deck = QComboBox()
        self.deck.setMinimumWidth(220)
        self.deck.setMaxVisibleItems(15)
        for w in (self.period, self.deck):
            w.currentIndexChanged.connect(self.refresh)
        filters.addWidget(QLabel("期間"))
        filters.addWidget(self.period)
        filters.addSpacing(12)
        filters.addWidget(QLabel("デッキ"))
        filters.addWidget(self.deck)
        filters.addStretch()
        lay.addLayout(filters)

        cards = QGridLayout()
        self.c_all = StatCard("勝率")
        self.c_first = StatCard("先攻 勝率", theme.FIRST)
        self.c_second = StatCard("後攻 勝率", theme.SECOND)
        self.c_cr = StatCard("CR 増減")
        for i, c in enumerate((self.c_all, self.c_first, self.c_second, self.c_cr)):
            cards.addWidget(c, 0, i)
        lay.addLayout(cards)

        chart_panel = panel()
        cp = QVBoxLayout(chart_panel)
        head = QHBoxLayout()
        t = QLabel("CR 推移")
        t.setObjectName("muted")
        self.cr_group = QComboBox()
        self.cr_group.setMinimumWidth(180)
        self.cr_group.setToolTip("CR はクラスごとに別なので、グラフはクラスごとに出します。\n"
                                 "クラスが分からないデッキは「デッキ整理」で指定できます")
        self.cr_group.currentIndexChanged.connect(self.refresh)
        head.addWidget(t)
        head.addWidget(self.cr_group)
        head.addStretch()
        cp.addLayout(head)
        self.chart = CrChart()
        cp.addWidget(self.chart)
        lay.addWidget(chart_panel, 2)

        tables = QHBoxLayout()
        self.by_deck = self._table(["デッキ", "試合", "勝敗", "勝率", "先攻", "後攻"])
        self.by_opp = self._table(["相手クラス", "試合", "勝敗", "勝率"])
        tables.addWidget(self.by_deck, 3)
        tables.addWidget(self.by_opp, 2)
        lay.addLayout(tables, 3)

    def _table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(headers)):
            t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        return t

    def reload_decks(self):
        cur = self.deck.currentData()
        self.deck.blockSignals(True)
        self.deck.clear()
        self.deck.addItem("すべて", None)
        for d in self.db.decks():
            if d not in self.hidden_decks():
                self.deck.addItem(d, d)
        i = self.deck.findData(cur)
        self.deck.setCurrentIndex(max(i, 0))
        self.deck.blockSignals(False)

    def _reload_groups(self, names):
        """グラフに出すクラスの選択肢を作り直して、出すものの名前を返す。選んでいなければ最近使ったクラス"""
        cur = self.cr_group.currentData()
        self.cr_group.blockSignals(True)
        self.cr_group.clear()
        self.cr_group.addItem(f"最近使ったクラス（{names[0]}）" if names else "最近使ったクラス", None)
        for n in names:
            self.cr_group.addItem(n, n)
        if cur and cur not in names:  # 期間を変えて記録がなくなっても、選んだクラスのままにする
            self.cr_group.addItem(cur, cur)
        self.cr_group.setCurrentIndex(max(self.cr_group.findData(cur), 0) if cur else 0)
        self.cr_group.blockSignals(False)
        self.cr_group.show()
        return cur or (names[0] if names else "")

    def refresh(self):
        rows = self.db.matches(deck=self.deck.currentData(), since=period_start(PERIODS[self.period.currentIndex()][1]))
        s = summarize(rows)
        v, sub = fmt_record(s["all"])
        self.c_all.set(v, sub, theme.WIN if (s["all"]["win_rate"] or 0) >= 50 else theme.LOSS)
        self.c_first.set(*fmt_record(s["first"]))
        self.c_second.set(*fmt_record(s["second"]))
        unknown = s["all"]["total"] - s["first"]["total"] - s["second"]["total"]
        if unknown:
            self.c_second.sub.setText(self.c_second.sub.text() + f"（先後不明 {unknown}）")
        net = s["cr_net"]
        # グラフと「現在」はクラスごと（デッキで絞り込んでいるときはそのデッキ）
        if self.deck.currentData():
            self.cr_group.hide()
            name, cr_rows = "", [r for r in rows if r["cr"] is not None]
        else:
            groups = cr_groups(rows, self.deck_classes())
            name = self._reload_groups(list(groups))
            cr_rows = groups.get(name, [])
        now = f"現在 {cr_rows[0]['cr']}" + (f"（{name}）" if name else "") if cr_rows else ""
        self.c_cr.set("-" if net is None else f"{net:+d}", now,
                      None if net is None else (theme.WIN if net >= 0 else theme.LOSS))
        self.chart.set_points([(r["cr"], r["result"]) for r in reversed(cr_rows)][-200:])

        self._fill(self.by_deck, self._group(rows, "deck"), with_turn=True)
        self._fill(self.by_opp, self._group(rows, "opponent"), with_turn=False)

    @staticmethod
    def _group(rows, key):
        g = defaultdict(lambda: {"n": 0, "w": 0, "fn": 0, "fw": 0, "sn": 0, "sw": 0})
        for r in rows:
            d = g[r[key] or "（未設定）"]
            win = r["result"] == "win"
            d["n"] += 1
            d["w"] += win
            if r["turn_order"] == "first":
                d["fn"] += 1
                d["fw"] += win
            elif r["turn_order"] == "second":
                d["sn"] += 1
                d["sw"] += win
        return sorted(g.items(), key=lambda kv: -kv[1]["n"])

    def _fill(self, table, groups, with_turn):
        table.setRowCount(len(groups))
        for i, (name, d) in enumerate(groups):
            cells = [name, str(d["n"]), f"{d['w']}-{d['n'] - d['w']}", rate_text(d["w"], d["n"])]
            if with_turn:
                cells += [rate_text(d["fw"], d["fn"]), rate_text(d["sw"], d["sn"])]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if j:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, j, it)
