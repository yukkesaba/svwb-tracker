"""リザルト画面から CR・変動CR・獲得MP・ランク・フォーマット・使用デッキを読む

リザルト画面は「MP内訳」→「ランク/CR/使用デッキ」の2段階で表示が変わるので、
右側パネルをまとめて OCR し、文字列のパターンで拾う。複数フレームの結果は merge() でまとめる。
"""
import collections
import difflib
import re
import unicodedata
from dataclasses import dataclass, fields

import cv2
import numpy as np

PANEL_ROI = (960, 180, 960, 820)    # 右半分（ランク・MP・CR が出る範囲）
DECK_ROI = (1040, 808, 438, 42)     # 「使用デッキ」の下の名前帯
INFO_ICON = (1772, 218, 68, 66)     # 獲得MP の右の (i) アイコン
DIM_LEVEL = 160                     # デッキ名の帯の一番明るいところがこれ未満なら「暗くなっている」（普段は約225、暗いと約110）

MINUS = "-ー－−―‐"


@dataclass
class ResultInfo:
    cr: int = None
    cr_change: int = None
    mp_gained: int = None
    rank: str = None
    format: str = None
    deck: str = None
    deck_raw: str = None  # 補正前の OCR 文字列（デバッグ用）
    deck_dim: bool = False  # マッチング中などで画面が暗く、デッキ名が読み間違えやすい

    def merge(self, other):
        """まだ空の項目を other で埋める"""
        for f in fields(self):
            if getattr(self, f.name) is None and getattr(other, f.name) is not None:
                setattr(self, f.name, getattr(other, f.name))
        return self

    @property
    def complete(self):
        return self.cr is not None and self.cr_change is not None and self.deck is not None


def _crop(img, roi):
    x, y, w, h = roi
    return img[y:y + h, x:x + w]


def parse_panel(lines):
    """OCR の行リスト（座標は PANEL_ROI 内）から数値を拾う"""
    info = ResultInfo()
    change_label = None
    cr = None
    for ln in lines:
        t = ln.text
        m = re.fullmatch(r"[cC][rR](\d{4})", t)
        if m and cr is None:
            cr = int(m.group(1))
        if "変動" in t:
            change_label = ln
            m = re.search(rf"CR([+{MINUS}])(\d{{1,3}})$", t)
            if m:
                info.cr_change = _signed(m.group(1), m.group(2))
        m = re.search(r"MP\+(\d{1,4})$", t)
        if m and info.mp_gained is None and ln.y < 200:
            info.mp_gained = int(m.group(1))
        m = re.fullmatch(r"(Grand)?Master(\d{1,2})", t)
        if m and info.rank is None:
            info.rank = ("Grand Master " if m.group(1) else "Master ") + m.group(2)
        if info.format is None:
            if "リミテ" in t or "アンリ" in t:
                info.format = "アンリミテッド"
            elif "テーシ" in t or "ーション" in t:
                info.format = "ローテーション"
    # 「変動CR」と同じ高さの右側にある「+16」「ー14」
    if info.cr_change is None and change_label is not None:
        for ln in lines:
            if ln is change_label or ln.x <= change_label.x:
                continue
            if abs((ln.y + ln.h / 2) - (change_label.y + change_label.h / 2)) < 20:
                m = re.fullmatch(rf"([+{MINUS}])(\d{{1,3}})", ln.text)
                if m:
                    info.cr_change = _signed(m.group(1), m.group(2))
    if info.cr_change is not None and abs(info.cr_change) > 100:
        info.cr_change = None
    # MP内訳画面の CR は試合前の値のまま（数え上げ演出の途中）のことがあるので、
    # 「変動CR」と同じ画面（サマリー）に出ている CR だけ採用する
    if change_label is not None:
        info.cr = cr
    return info


def _signed(sign, digits):
    v = int(digits)
    return -v if sign in MINUS else v


# 日本語 OCR がデッキ名の飾り文字でよく間違える字の置き換え
_FIXES = [
    ("丿し", "ル"), ("丿", "ル"), ("ノ(", "パ"), ("ノ、", "ハ"), ("ン八", "ンハ"), ("八", "ハ"),
    ("工", "エ"), ("ェ", "エ"), ("口", "ロ"), ("力", "カ"), ("卜", "ト"), ("夕", "タ"),
]


def clean_deck_text(text):
    text = text.replace("\n", "").replace(" ", "")
    for a, b in _FIXES:
        text = text.replace(a, b)
    return text.strip("・。、,.-~'/ー–—`\"")


def deck_candidates(ocr, frame):
    """デッキ名の帯を何通りかの前処理で読む（白文字を抜き出したものが一番読みやすい）"""
    crop = _crop(frame, DECK_ROI)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, inv = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    out = []
    for img, scale in ((inv, 3), (gray, 3), (crop, 2)):
        t = clean_deck_text(ocr.text(img, scale))
        # 「旗」のような1文字のデッキ名もあるので、1文字でも漢字・かなならデッキ名とみなす
        if len(t) >= 2 or (len(t) == 1 and _is_kana_kanji(t)):
            out.append(t)
    if not out:
        single = _read_single_char(ocr, gray)
        if single:
            out.append(single)
    return out


def _is_kana_kanji(ch):
    return re.match(r"[\u3040-\u30ff\u4e00-\u9fff]", ch) is not None


def _read_single_char(ocr, gray):
    """Windows OCR \u306f1\u6587\u5b57\u3060\u3051\u3060\u3068\u8aad\u307e\u306a\u3044\u306e\u3067\u3001\u6587\u5b57\u90e8\u5206\u30923\u56de\u4e26\u3079\u3066\u8aad\u307f\u30012\u56de\u4ee5\u4e0a\u51fa\u305f\u5b57\u3092\u63a1\u308b"""
    # \u30c7\u30c3\u30ad\u540d\u306f\u30b5\u30e0\u30cd\u30a4\u30eb\u306e\u4e2d\u592e\u306b\u5bc4\u305b\u3066\u8868\u793a\u3055\u308c\u308b\u306e\u3067\u3001\u4e2d\u592e\u306b\u4e00\u756a\u8fd1\u3044\u767d\u3044\u5217\u306e\u304b\u305f\u307e\u308a\u3092\u6587\u5b57\u3068\u307f\u306a\u3059
    strip = gray[8:38]
    cols = np.where((strip > 200).sum(axis=0) >= 2)[0]
    if len(cols) == 0:
        return None
    runs, start = [], cols[0]
    for a, b in zip(cols, cols[1:]):
        if b - a > 6:
            runs.append((start, a))
            start = b
    runs.append((start, cols[-1]))
    center = gray.shape[1] // 2
    x0, x1 = min(runs, key=lambda r: 0 if r[0] <= center <= r[1] else min(abs(r[0] - center), abs(r[1] - center)))
    if x1 - x0 > strip.shape[0] * 1.6 or min(abs(x0 - center), abs(x1 - center)) > 40 and not x0 <= center <= x1:
        return None  # 1\u6587\u5b57\u3088\u308a\u5e83\u3044 / \u4e2d\u592e\u304b\u3089\u96e2\u308c\u3066\u3044\u308b
    x0, x1 = max(x0 - 3, 0), min(x1 + 4, gray.shape[1])
    _, inv = cv2.threshold(gray[:, x0:x1], 150, 255, cv2.THRESH_BINARY_INV)
    gap = np.full((inv.shape[0], 10), 255, np.uint8)
    text = ocr.text(np.hstack([inv, gap, inv, gap, inv]), 3)
    counts = collections.Counter(ch for ch in text if _is_kana_kanji(ch))
    if counts:
        ch, n = counts.most_common(1)[0]
        if n >= 2:
            return ch
    return None


def match_known_deck(candidates, known, cutoff=0.6):
    """登録済みのデッキ名に一番近いものを返す。なければ None"""
    best, best_ratio = None, cutoff
    for c in candidates:
        for k in known:
            r = difflib.SequenceMatcher(None, c, k).ratio()
            if r > best_ratio:
                best, best_ratio = k, r
    return best


def snap_deck(cand, registered, history):
    """OCR で読んだデッキ名を、手動登録したデッキ名 → 過去の記録のデッキ名 の順に寄せる。
    過去の記録には読み間違いも混ざっている（「ッドメア」など）ので、文字数が同じで
    1〜2文字違い（テンホエルフ → テンポエルフ）のときだけ寄せる"""
    hit = match_known_deck([cand], registered)
    if hit:
        return hit
    same_len = [k for k in history if len(k) == len(cand)]
    hit = match_known_deck([cand], same_len, cutoff=0.8)
    if hit:
        return hit
    # 先頭の文字を落とした読み（ツドメア3 → ミッドメア3）は、ほぼ同じで長い名前に寄せる
    longer = [k for k in history if len(k) > len(cand) and similar_deck(cand, k, 0.85)]
    return max(longer, key=lambda k: difflib.SequenceMatcher(None, cand, k).ratio()) if longer else cand


# Master 帯のリザルト画面に出る「グループ」の名前。演出中にデッキ名の位置を横切ることがあるので
# デッキ名としては採らない
GROUP_NAMES = ["ルビー", "サファイア", "トパーズ", "エメラルド", "ダイヤモンド", "アメジスト",
               "パール", "ガーネット", "オパール", "アクアマリン"]


def _loose(text):
    """長音・濁点・半濁点を落とす（OCR がよく取り違える）"""
    t = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in t if not unicodedata.combining(ch) and ch not in "ー一-")


_SMALL = str.maketrans("ッャュョァィゥェォ", "ツヤユヨアイウエオ")


def similar_deck(a, b, cutoff=0.7):
    """OCR の読み揺れの範囲で同じデッキ名か"""
    a, b = _loose(a).translate(_SMALL), _loose(b).translate(_SMALL)
    return bool(a and b) and difflib.SequenceMatcher(None, a, b).ratio() >= cutoff


def is_group_name(text, extra=()):
    t = _loose(text)
    if not t:
        return False
    for g in list(GROUP_NAMES) + [e for e in extra if e]:
        g2 = _loose(g)
        if len(g2) < 2:
            continue
        if g2 in t or (len(t) >= 2 and difflib.SequenceMatcher(None, t, g2).ratio() >= 0.6):
            return True
    return False


def read_result(ocr, frame, known_decks=()):
    """1フレーム分を読む"""
    panel = _crop(frame, PANEL_ROI).copy()
    # 「獲得MP +15」の右の (i) アイコンを「1」と読んで +151 になるので塗りつぶす
    x, y, w, h = INFO_ICON
    panel[y - PANEL_ROI[1]:y - PANEL_ROI[1] + h, x - PANEL_ROI[0]:x - PANEL_ROI[0] + w] = 0
    lines = ocr.lines(panel)
    info = parse_panel(lines)
    # 「グループ」の下に出ているグループ名（座標は PANEL_ROI 内）
    group = [clean_deck_text(ln.text) for ln in lines if 300 <= ln.y + ln.h / 2 <= 350 and ln.x < 400]
    cands = deck_candidates(ocr, frame)
    # 「バトル」を押してマッチング中になると画面が暗くなり、「ミッドメア3」が「ツドメア3」になる
    band = cv2.cvtColor(_crop(frame, DECK_ROI), cv2.COLOR_BGR2GRAY)[8:38]
    info.deck_dim = float(np.percentile(band, 99.5)) < DIM_LEVEL
    if cands:
        info.deck_raw = cands[0]
        # 「Masterレベル50」などデッキ名でない帯（MP内訳画面）やグループ名は捨てる
        if not re.search(r"Master|レベ|MP", cands[0]) and not is_group_name(cands[0], group):
            info.deck = match_known_deck(cands, known_decks) or cands[0]
    return info
