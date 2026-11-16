"""パスと設定"""
import json
import logging
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

if getattr(sys, "frozen", False):  # PyInstaller で exe 化したとき
    APP_DIR = Path(sys.executable).parent
    ASSET_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "assets"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    ASSET_DIR = APP_DIR / "assets"

DATA_DIR = APP_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
DB_PATH = DATA_DIR / "matches.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
LOG_PATH = DATA_DIR / "tracker.log"
TEMPLATE_DIR = ASSET_DIR / "templates"

# 画面はこのサイズに揃えてから判定する（座標はすべてこの基準）
BASE_W, BASE_H = 1920, 1080


@dataclass
class Settings:
    window_title: str = "ShadowverseWB"
    interval_sec: float = 0.5          # キャプチャ間隔
    title_threshold: float = 0.6       # WIN / RESULT 判定のしきい値
    confirm_frames: int = 2            # 何フレーム連続で見えたら確定するか
    collect_sec: float = 3.0           # サマリー画面（変動CR・デッキ）を読み続ける最大時間
    save_screenshots: bool = True
    screenshot_limit: int = 500        # 残すリザルト画面の枚数（0 で無制限）。超えたら古いものから消す
    notify: bool = True                # 記録時などにトレイの通知を出す
    deck_override: str = ""            # 空なら OCR で自動取得
    deck_names: list = field(default_factory=list)  # 手動で登録したデッキ名（OCR 結果をこれに寄せる）
    hidden_decks: list = field(default_factory=list)  # デッキ整理で隠したデッキ（選択肢と OCR の候補から外す）
    start_minimized: bool = False
    obs_enabled: bool = False          # 今日の戦績を data/obs/today.txt に書き出す
    obs_template: str = "{wins}勝 {losses}敗 勝率{rate}%"

    @classmethod
    def load(cls):
        s = cls()
        if SETTINGS_PATH.exists():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                for f in fields(cls):
                    if f.name in raw:
                        setattr(s, f.name, raw[f.name])
            except Exception as e:
                log.warning("設定ファイルを読めませんでした: %s", e)
        return s

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
