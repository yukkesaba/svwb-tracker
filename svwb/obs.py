"""配信用テキスト（OBS のテキストソースで「ファイルから読み取り」に指定する）"""
import logging

from .config import DATA_DIR

log = logging.getLogger(__name__)
OBS_PATH = DATA_DIR / "obs" / "today.txt"
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
