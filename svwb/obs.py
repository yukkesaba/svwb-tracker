"""配信用の出力。data/obs に書き出して OBS から読む

- today.txt: テキストソースの「ファイルから読み取り」用
- bar.html / card.html / minimal.html: ブラウザソースの「ローカルファイル」用。data.js を読んで描く
"""
import json
import logging

from .config import ASSET_DIR, DATA_DIR

log = logging.getLogger(__name__)
OBS_PATH = DATA_DIR / "obs" / "today.txt"
OVERLAY_SRC = ASSET_DIR / "overlay"
OVERLAY_FILES = ("bar.html", "card.html", "minimal.html", "overlay.js")
RECENT = 10  # 直近何試合の勝敗を並べるか
DEFAULT_TEMPLATE = "{wins}勝 {losses}敗 勝率{rate}%"
VARIABLES = "{wins} 勝ち数 / {losses} 負け数 / {total} 試合数 / {rate} 勝率 / {streak} 連勝・連敗 / " \
            "{cr} 現在のCR / {cr_net} CRの増減 / {deck} 直前のデッキ / \\n 改行"


class _Blank(dict):
    def __missing__(self, key):  # 知らない名前はそのまま残す
        return "{" + key + "}"


def render(template, rows):
    """rows は今日の戦績（新しい順）"""
    wins = sum(r["result"] == "win" for r in rows)
    streak = 0
    for r in rows:
        if r["result"] != rows[0]["result"]:
            break
        streak += 1
    changes = [r["cr_change"] for r in rows if r.get("cr_change") is not None]
    crs = [r["cr"] for r in rows if r.get("cr") is not None]
    values = _Blank(
        wins=wins, losses=len(rows) - wins, total=len(rows),
        rate=f"{wins / len(rows) * 100:.0f}" if rows else "-",
        streak=f"{streak}連{'勝' if rows[0]['result'] == 'win' else '敗'}" if streak >= 2 else "-",
        cr=crs[0] if crs else "-", cr_net=f"{sum(changes):+d}" if changes else "-",
        deck=(rows[0].get("deck") or "-") if rows else "-")
    try:
        text = template.format_map(values)
    except (ValueError, IndexError, KeyError):  # 括弧の閉じ忘れなど
        text = template
    return text.replace("\\n", "\n")


def overlay_data(rows):
    """配信用表示に渡す値。rows は今日の戦績（新しい順）"""
    wins = sum(r["result"] == "win" for r in rows)
    streak = 0
    for r in rows:
        if r["result"] != rows[0]["result"]:
            break
        streak += 1
    changes = [r["cr_change"] for r in rows if r.get("cr_change") is not None]
    crs = [r["cr"] for r in rows if r.get("cr") is not None]
    return {
        "wins": wins, "losses": len(rows) - wins, "total": len(rows),
        "rate": round(wins / len(rows) * 100) if rows else None,
        "streak": streak if streak >= 2 else 0,
        "streak_kind": rows[0]["result"] if streak >= 2 else None,
        "cr": crs[0] if crs else None,
        "cr_net": sum(changes) if changes else None,
        "deck": (rows[0].get("deck") or None) if rows else None,
        "recent": [r["result"] for r in rows[:RECENT]][::-1],  # 古い順（右端が直前の試合）
    }


def write_overlay(rows, folder=None):
    """表示用の HTML を最新にして、data.js を書く。書いたら True"""
    folder = folder or OBS_PATH.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name in OVERLAY_FILES:  # 更新で見た目が変わったら差し替える
            src, dst = OVERLAY_SRC / name, folder / name
            data = src.read_bytes()
            if not dst.exists() or dst.read_bytes() != data:
                dst.write_bytes(data)
    except OSError as e:
        log.warning("配信用表示を書き出せませんでした: %s", e)
        return False
    text = "window.SVWB_DATA = " + json.dumps(overlay_data(rows), ensure_ascii=False) + ";\n"
    return write(text, folder / "data.js")


def write(text, path=None):
    """内容が変わったときだけ書く。書いたら True"""
    path = path or OBS_PATH
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True
    except OSError as e:
        log.warning("配信用テキストを書けませんでした: %s", e)
        return False
