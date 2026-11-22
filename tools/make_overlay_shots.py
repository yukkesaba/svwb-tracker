"""README 用の配信用表示のスクショ（docs/screenshots/6_overlay.png, 7_overlay_deck.png）を撮る

    python tools/make_overlay_shots.py

assets/overlay の HTML を一時フォルダに写し、見本の data.js を置いて、Chrome（なければ Edge）の
ヘッドレスで背景を透明にして撮る。撮った3枚を暗い背景の上に並べて1枚にする。本物の戦績は使わない
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from svwb import obs  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",  # Edge のヘッドレスは撮れないことがある
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
SCALE = 2  # 掲載しても粗く見えないよう2倍で撮る
PAGES = [("bar.html", 700, 100), ("card.html", 320, 220), ("minimal.html", 320, 160)]

R = ["win", "win", "loss", "win", "loss", "win", "win", "loss", "win", "win"]
SAMPLES = {
    "6_overlay.png": {"wins": 14, "losses": 9, "total": 23, "rate": 61, "streak": 2, "streak_kind": "win",
                      "cr": 1582, "cr_net": 64, "deck": "ランプドラゴン", "recent": R, "by_deck": False},
    "7_overlay_deck.png": {"wins": 5, "losses": 2, "total": 7, "rate": 71, "streak": 3, "streak_kind": "win",
                           "cr": 1582, "cr_net": 41, "deck": "ランプドラゴン", "recent": R[3:], "by_deck": True},
}


def browser():
    for b in BROWSERS:
        if Path(b).exists():
            return b
    sys.exit("Chrome か Edge が見つかりません")


def shoot(exe, html, w, h, png):
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    f"--user-data-dir={png.parent / 'profile'}",  # 普段使いのブラウザと分ける
                    f"--force-device-scale-factor={SCALE}", "--default-background-color=00000000",
                    "--virtual-time-budget=3000", f"--window-size={w},{h}", f"--screenshot={png}",
                    html.as_uri()], check=True, capture_output=True, timeout=60)
    img = cv2.imdecode(np.fromfile(str(png), np.uint8), cv2.IMREAD_UNCHANGED)
    ys, xs = np.where(img[:, :, 3] > 0)  # 透明な余白を切る
    return img[: ys.max() + 1, : xs.max() + 1]


def compose(shots, pad=24 * SCALE):
    """暗い背景（ゲーム画面の代わり）に、帯を上に、カードとミニマルを下に並べる"""
    bar, card, mini = shots
    w = max(bar.shape[1], card.shape[1] + mini.shape[1] + pad) + pad * 2
    h = bar.shape[0] + max(card.shape[0], mini.shape[0]) + pad * 3
    y, x = np.mgrid[0:h, 0:w]
    t = (x / w * 0.6 + y / h * 0.4)[..., None]
    bg = (np.array([60, 42, 30]) * (1 - t) + np.array([92, 58, 70]) * t).astype(np.float32)  # BGR の紺→紫
    for img, (ox, oy) in zip(shots, [(pad, pad), (pad, bar.shape[0] + pad * 2),
                                     (pad * 2 + card.shape[1], bar.shape[0] + pad * 2)]):
        a = img[:, :, 3:4].astype(np.float32) / 255
        region = bg[oy:oy + img.shape[0], ox:ox + img.shape[1]]
        region[:] = img[:, :, :3] * a + region * (1 - a)
    return bg.astype(np.uint8)


def main():
    exe = browser()
    with tempfile.TemporaryDirectory() as t:
        folder = Path(t)
        for name in obs.OVERLAY_FILES:
            shutil.copy(obs.OVERLAY_SRC / name, folder / name)
        for page, _, _ in PAGES:  # 動きの途中で撮らないよう、リングの伸びや跳ねを止める
            f = folder / page
            f.write_text(f.read_text(encoding="utf-8").replace(
                "</style>", "* { transition: none !important; animation: none !important; }\n</style>"), encoding="utf-8")
        for out, data in SAMPLES.items():
            (folder / "data.js").write_text("window.SVWB_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
                                            encoding="utf-8")
            shots = [shoot(exe, folder / page, w, h, folder / f"{page}.png") for page, w, h in PAGES]
            cv2.imencode(".png", compose(shots))[1].tofile(str(OUT / out))
            print("wrote", OUT / out)


if __name__ == "__main__":
    main()
