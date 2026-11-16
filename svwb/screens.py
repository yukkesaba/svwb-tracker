"""画面の判定: リザルト画面（WIN / RESULT）と、対戦開始の VS 画面（先攻・後攻、相手クラス）"""
import difflib

import cv2

from .config import TEMPLATE_DIR

CLASSES = ["エルフ", "ロイヤル", "ウィッチ", "ドラゴン", "ナイトメア", "ビショップ", "ネメシス"]

# 1920x1080 基準。タイトル文字は画面上部中央の決まった位置に出る
TITLE_ROI = (640, 0, 640, 210)  # x, y, w, h

# VS 画面: 左が自分、右が相手。バッジの1文字目（先 / 後）の位置
MY_BADGE = (580, 695, 100, 95)
OPP_BADGE = (1140, 695, 100, 95)
BADGE_MARGIN = 20
OPP_CLASS_ROI = (1450, 665, 330, 110)  # 右側の「ネメシス」などのクラス名


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def _best(roi, templates):
    return max(float(cv2.minMaxLoc(cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED))[1]) for t in templates)


class ResultScreenDetector:
    """WIN / RESULT のタイトル文字をテンプレートマッチングで探す"""

    def __init__(self, threshold=0.6, template_dir=TEMPLATE_DIR):
        self.threshold = threshold
        self.templates = {}
        for key, name in (("win", "win.png"), ("loss", "result.png")):
            t = cv2.imread(str(template_dir / name), cv2.IMREAD_GRAYSCALE)
            if t is None:
                raise FileNotFoundError(template_dir / name)
            self.templates[key] = t

    def scores(self, frame):
        x, y, w, h = TITLE_ROI
        roi = _gray(frame[y:y + h, x:x + w])
        return {k: _best(roi, [t]) for k, t in self.templates.items()}

    def detect(self, frame):
        """('win' | 'loss' | None, scores)"""
        s = self.scores(frame)
        best = max(s, key=s.get)
        return (best if s[best] >= self.threshold else None), s


class VsScreenDetector:
    """VS 画面の「先攻」「後攻」バッジを見て、自分が先攻か後攻かを判定する。
    演出中は大きなカードで両方の文字が出るので、左右のバッジが確定位置にあり、
    かつ左右で逆になっているときだけ採用する"""

    def __init__(self, threshold=0.75, template_dir=TEMPLATE_DIR):
        self.threshold = threshold
        self.templates = {}
        for turn in ("first", "second"):
            ts = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in sorted(template_dir.glob(f"turn_{turn}_*.png"))]
            if not ts:
                raise FileNotFoundError(template_dir / f"turn_{turn}_*.png")
            self.templates[turn] = ts

    def _side(self, gray, box):
        x, y, w, h = box
        m = BADGE_MARGIN
        roi = gray[y - m:y + h + m, x - m:x + w + m]
        return {k: _best(roi, ts) for k, ts in self.templates.items()}

    def detect(self, frame):
        """'first' | 'second' | None"""
        gray = _gray(frame)
        me, opp = self._side(gray, MY_BADGE), self._side(gray, OPP_BADGE)
        mine = max(me, key=me.get)
        theirs = "second" if mine == "first" else "first"
        if me[mine] >= self.threshold and opp[theirs] >= self.threshold and me[theirs] < self.threshold:
            return mine
        return None


# 日本語 OCR はクラス名の飾り文字を決まった形で読み違える（「エルフ」→「工丿しフ」）
_CLASS_FIXES = [("丿し", "ル"), ("ノし", "ル"), ("丿", "ル"), ("工", "エ"), ("ェ", "エ"), ("八", "ル"), ("口", "ロ"), ("卜", "ト")]


def _class_of(text):
    """読めた1行を7クラスのどれかに寄せる。(クラス, 近さ)"""
    text = text.strip("・、。-ー")
    for a, b in _CLASS_FIXES:
        text = text.replace(a, b)
    best, best_ratio = None, 0.5
    for c in CLASSES:
        r = 1.0 if c in text else difflib.SequenceMatcher(None, text, c).ratio()
        if r > best_ratio:
            best, best_ratio = c, r
    return best, best_ratio


def _class_variants(crop):
    """読み方を変えた画像を順に返す。エンブレムの光が文字に重なると、そのままでは読めないことがある"""
    yield crop, 1.5
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    white = (hsv[..., 2] > 190) & (hsv[..., 1] < 70)  # 白い文字だけ残して白黒反転
    yield (~white).astype("uint8") * 255, 3
    yield _gray(crop), 3


def read_opponent_class(ocr, frame):
    """VS 画面右側のクラス名を OCR して、7クラスのどれかに寄せる"""
    x, y, w, h = OPP_CLASS_ROI
    best, best_ratio = None, 0.5
    for img, scale in _class_variants(frame[y:y + h, x:x + w]):
        for line in ocr.lines(img, scale=scale):
            c, r = _class_of(line.text)
            if r > best_ratio:
                best, best_ratio = c, r
        if best_ratio >= 0.99:  # はっきり読めたら残りの読み方は試さない
            break
    return best
