"""保存済みスクリーンショットで判定・読み取り精度を測る

    python tools/eval_screens.py <スクショのフォルダ> [旧DB matches.db]

ファイル名の先頭（win_ / loss_）を正解として勝敗判定を採点し、
旧DB があれば、同じスクショに紐づく CR 値と読み取り結果を比べる。
"""
import collections
import sqlite3
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from svwb.capture import normalize  # noqa: E402
from svwb.ocr import Ocr  # noqa: E402
from svwb.result_reader import read_result  # noqa: E402
from svwb.screens import ResultScreenDetector  # noqa: E402


def main():
    folder = Path(sys.argv[1])
    truth = {}
    if len(sys.argv) > 2:
        con = sqlite3.connect(sys.argv[2])
        for path, cr, chg, deck in con.execute("select screenshot_path, cr_value, cr_change, deck_name from matches"):
            if path:
                truth[Path(path).name] = (cr, chg, deck)

    det, ocr = ResultScreenDetector(), Ocr()
    verdicts = collections.Counter()
    cr_cmp = collections.Counter()
    decks = collections.Counter()
    fields = collections.Counter()
    files = sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png"))
    for f in files:
        img = normalize(cv2.imread(str(f)))
        label = f.name.split("_")[0]
        verdict, _ = det.detect(img)
        verdicts[(label, verdict)] += 1
        if verdict is None:
            continue
        info = read_result(ocr, img)
        for k in ("cr", "cr_change", "mp_gained", "rank", "format", "deck"):
            fields[k] += getattr(info, k) is not None
        fields["total"] += 1
        if info.deck:
            decks[info.deck] += 1
        if f.name in truth and truth[f.name][0] is not None:
            ok = info.cr == truth[f.name][0]
            cr_cmp["一致" if ok else ("読めず" if info.cr is None else "不一致")] += 1
            if not ok and info.cr is not None:
                print(f"  CR不一致 {f.name}: 読み取り={info.cr} 旧DB={truth[f.name][0]}")
        if info.cr_change is not None and verdict and (info.cr_change > 0) != (verdict == "win"):
            print(f"  変動CRの符号が勝敗と逆 {f.name}: {info.cr_change} ({verdict})")

    print("\n勝敗判定 (ファイル名, 判定):", dict(verdicts))
    print("項目ごとの読み取り件数:", dict(fields))
    print("旧DBとのCR比較:", dict(cr_cmp))
    print("デッキ名:", decks.most_common())


if __name__ == "__main__":
    main()
