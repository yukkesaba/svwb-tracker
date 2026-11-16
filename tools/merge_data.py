"""別のフォルダで使っていたトラッカーの data を、このフォルダの app/data に取り込む

    python tools/merge_data.py "E:\\SBTracker\\release\\SVWB Tracker\\data"          # 何が起きるかを表示するだけ
    python tools/merge_data.py "E:\\SBTracker\\release\\SVWB Tracker\\data" --apply  # 実際に取り込む

取り込み元は読むだけで変更しない。取り込み先は先に控え（matches.backup_日時.db）を作る。
同じ日時・結果の試合は飛ばすので、2回実行しても増えない
"""
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "app" / "data"
COLS = ["played_at", "result", "turn_order", "deck", "opponent", "cr", "cr_change", "mp_gained", "rank", "format",
        "notes", "screenshot", "source"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    src_dir = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    src = sqlite3.connect(f"file:{(src_dir / 'matches.db').as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = [dict(r) for r in src.execute("SELECT * FROM matches ORDER BY played_at, id")]
    src.close()

    dest = sqlite3.connect(str(DEST / "matches.db"))
    before = dest.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    existing = {(r[0], r[1]) for r in dest.execute("SELECT played_at, result FROM matches")}
    new = [r for r in rows if (r["played_at"], r["result"]) not in existing]
    shots = []
    for r in new:
        if r.get("screenshot"):
            old = Path(r["screenshot"])
            if not old.exists():
                old = src_dir / "screenshots" / old.name
            if old.exists():
                target = DEST / "screenshots" / old.name
                shots.append((old, target))
                r["screenshot"] = str(target)
    print(f"取り込み元 {len(rows)} 試合 / 取り込み先 {before} 試合 / 新しく入る {len(new)} 試合 / スクショ {len(shots)} 枚")
    if new:
        print(f"  {new[0]['played_at']} 〜 {new[-1]['played_at']}")
    if not apply:
        print("（表示だけ。--apply を付けると取り込みます）")
        dest.close()
        return

    backup = DEST / f"matches.backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    out = sqlite3.connect(str(backup))
    dest.backup(out)
    out.close()
    (DEST / "screenshots").mkdir(exist_ok=True)
    for old, target in shots:
        if not target.exists():
            shutil.copy2(old, target)
    with dest:
        dest.executemany(f"INSERT INTO matches ({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})",
                         [[r.get(c) for c in COLS] for r in new])
    after = dest.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    dest.close()
    # 設定は最近使っていた方（取り込み元）に合わせる。隠したデッキは両方を合わせる。元の設定は控えを残す
    if (src_dir / "settings.json").exists():
        merged = json.loads((src_dir / "settings.json").read_text(encoding="utf-8"))
        if (DEST / "settings.json").exists():
            old = json.loads((DEST / "settings.json").read_text(encoding="utf-8"))
            shutil.copy2(DEST / "settings.json", DEST / f"settings.backup_{datetime.now():%Y%m%d_%H%M%S}.json")
            merged["hidden_decks"] = list(dict.fromkeys(old.get("hidden_decks", []) + merged.get("hidden_decks", [])))
        (DEST / "settings.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"控え {backup.name} / 取り込み後 {after} 試合（{before} + {after - before}）")


if __name__ == "__main__":
    main()
