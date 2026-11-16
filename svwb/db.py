"""戦績データベース（SQLite）。GUI スレッドからだけ使う"""
import csv
import io
import sqlite3
from datetime import datetime

from .config import DB_PATH

COLUMNS = ["id", "played_at", "result", "turn_order", "deck", "opponent", "cr", "cr_change",
           "mp_gained", "rank", "format", "notes", "screenshot", "source"]
EDITABLE = {"played_at", "result", "turn_order", "deck", "opponent", "cr", "cr_change",
            "mp_gained", "rank", "format", "notes"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    played_at   TEXT NOT NULL,              -- 'YYYY-MM-DD HH:MM:SS'
    result      TEXT NOT NULL CHECK (result IN ('win', 'loss')),
    turn_order  TEXT CHECK (turn_order IN ('first', 'second')),
    deck        TEXT,
    opponent    TEXT,                       -- 相手のクラス（手入力。将来自動化）
    cr          INTEGER,
    cr_change   INTEGER,
    mp_gained   INTEGER,
    rank        TEXT,
    format      TEXT,
    notes       TEXT,
    screenshot  TEXT,
    source      TEXT DEFAULT 'auto'         -- auto / manual / import
);
CREATE INDEX IF NOT EXISTS idx_matches_played_at ON matches(played_at);
"""


class Database:
    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add(self, **values):
        values.setdefault("played_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cols = [c for c in COLUMNS if c != "id" and c in values]
        cur = self.conn.execute(
            f"INSERT INTO matches ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [values[c] for c in cols])
        self.conn.commit()
        return cur.lastrowid

    def find_same_match(self, rec):
        """直前の記録が同じ試合（指紋が一致）ならその id を返す"""
        sig = match_signature(rec)
        if sig is None:
            return None
        r = self.conn.execute("SELECT * FROM matches ORDER BY played_at DESC, id DESC LIMIT 1").fetchone()
        if not r or match_signature(dict(r)) != sig:
            return None
        # どちらも VS 画面で読んだ試合開始時刻があり、それが違うなら別の試合
        if rec.get("turn_order") and r["turn_order"] and rec.get("played_at") and rec["played_at"] != r["played_at"]:
            return None
        return r["id"]

    def fill_missing(self, match_id, rec):
        """同じ試合の記録で、空欄だけを埋める"""
        cur = self.get(match_id)
        values = {k: v for k, v in rec.items() if k in EDITABLE and v is not None and cur.get(k) is None}
        if values:
            self.update(match_id, **values)
        return values

    def update(self, match_id, **values):
        values = {k: v for k, v in values.items() if k in EDITABLE}
        if not values:
            return
        sets = ", ".join(f"{k} = ?" for k in values)
        self.conn.execute(f"UPDATE matches SET {sets} WHERE id = ?", [*values.values(), match_id])
        self.conn.commit()

    def delete(self, ids):
        self.conn.executemany("DELETE FROM matches WHERE id = ?", [(i,) for i in ids])
        self.conn.commit()

    def get(self, match_id):
        r = self.conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        return dict(r) if r else None

    def matches(self, deck=None, since=None, fmt=None):
        """新しい順"""
        q, p = "SELECT * FROM matches WHERE 1=1", []
        if deck:
            q += " AND deck = ?"
            p.append(deck)
        if since:
            q += " AND played_at >= ?"
            p.append(since)
        if fmt:
            q += " AND format = ?"
            p.append(fmt)
        q += " ORDER BY played_at DESC, id DESC"
        return [dict(r) for r in self.conn.execute(q, p)]

    def decks(self):
        """最近使った順のデッキ名"""
        return [r["deck"] for r in self.deck_summary()]

    def deck_summary(self):
        """デッキごとの試合数・勝ち数・最後に使った日時（最近使った順）"""
        return [dict(r) for r in self.conn.execute(
            "SELECT deck, COUNT(*) AS n, SUM(result = 'win') AS wins, MAX(played_at) AS last FROM matches "
            "WHERE deck IS NOT NULL AND deck != '' GROUP BY deck ORDER BY last DESC")]

    def rename_deck(self, old, new):
        """デッキ名を変える。new が既にあれば統合になる"""
        cur = self.conn.execute("UPDATE matches SET deck = ? WHERE deck = ?", (new, old))
        self.conn.commit()
        return cur.rowcount

    def backup(self):
        """DB の控えを同じフォルダに作ってパスを返す"""
        dest = self.path.with_name(f"matches.backup_{datetime.now():%Y%m%d_%H%M%S}.db")
        with sqlite3.connect(str(dest)) as out:
            self.conn.backup(out)
        out.close()
        return dest

    def last_cr(self):
        r = self.conn.execute(
            "SELECT cr FROM matches WHERE cr IS NOT NULL ORDER BY played_at DESC, id DESC LIMIT 1").fetchone()
        return r[0] if r else None

    def export_csv(self):
        rows = self.matches()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    def import_v1(self, v1_path):
        """旧版（antigravity 版）の matches.db から取り込む。同じ日時・結果の行は飛ばす。取り込んだ件数を返す"""
        from pathlib import Path
        src = sqlite3.connect(f"file:{v1_path}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        shot_dir = Path(v1_path).parent / "screenshots"
        existing = {(r[0], r[1]) for r in self.conn.execute("SELECT played_at, result FROM matches")}
        n = 0
        for r in src.execute("SELECT * FROM matches ORDER BY timestamp"):
            r = dict(r)
            if r.get("result") not in ("win", "loss") or (r["timestamp"], r["result"]) in existing:
                continue
            shot = None
            if r.get("screenshot_path"):
                p = shot_dir / Path(r["screenshot_path"]).name  # 旧版はフォルダ移動で絶対パスが古い
                shot = str(p) if p.exists() else r["screenshot_path"]
            self.add(played_at=r["timestamp"], result=r["result"],
                     turn_order=r.get("turn_order") if r.get("turn_order") in ("first", "second") else None,
                     deck=r.get("deck_name"), cr=r.get("cr_value"), cr_change=r.get("cr_change"),
                     notes=r.get("notes"), screenshot=shot, source="import")
            n += 1
        src.close()
        return n

    def close(self):
        self.conn.close()


def summarize(rows):
    """勝敗・先攻後攻別の集計"""
    def wr(w, n):
        return round(w / n * 100, 1) if n else None

    out = {}
    for key, sub in (("all", rows),
                     ("first", [r for r in rows if r["turn_order"] == "first"]),
                     ("second", [r for r in rows if r["turn_order"] == "second"])):
        wins = sum(r["result"] == "win" for r in sub)
        out[key] = {"total": len(sub), "wins": wins, "losses": len(sub) - wins, "win_rate": wr(wins, len(sub))}
    changes = [r["cr_change"] for r in rows if r["cr_change"] is not None]
    out["cr_net"] = sum(changes) if changes else None
    return out


def matchup(rows):
    """{デッキ: {相手クラス: (勝ち, 試合数)}}。'合計' の行と列も入れる。相手クラスが空の試合は合計にだけ数える"""
    out = {}
    for r in rows:
        win = r["result"] == "win"
        for deck in (r["deck"] or "（未設定）", "合計"):
            for opp in (r["opponent"], "合計"):
                if opp:
                    w, n = out.setdefault(deck, {}).get(opp, (0, 0))
                    out[deck][opp] = (w + win, n + 1)
    return out


def match_signature(rec):
    """同じ試合かどうかを見分ける指紋。CR と変動CR が読めていればそれで一意に決まる
    （別の試合で結果・CR・変動CR が全部同じになるには、間に最低2試合はさむ必要がある）"""
    if rec.get("cr") is not None and rec.get("cr_change") is not None:
        return (rec["result"], rec["cr"], rec["cr_change"])
    if rec.get("mp_gained") is not None:
        return (rec["result"], "mp", rec["mp_gained"], rec.get("deck"))
    return None
