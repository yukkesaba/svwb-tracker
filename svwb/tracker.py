"""1試合を記録するまでの状態遷移

    WAITING ──WIN/RESULT が confirm_frames 回連続──▶ COLLECTING
    COLLECTING ──サマリーを collect_sec 読んだ / 全部読めた / リザルト画面が LEAVE_SEC 消えた──▶ 記録して AFTER
    AFTER ──リザルト画面が LEAVE_SEC 続けて見えなくなった──▶ WAITING

リザルト画面は「MP内訳（再戦カウントダウン付き）」→「サマリー（変動CR・CR・使用デッキ）」と進み、
切り替わりの演出で WIN / RESULT の文字が一瞬消える。消えた時間で判断しないと1試合が2回記録される。

先攻・後攻と相手クラスは、対戦開始時の VS 画面から読んで「これから始まる試合」の分として持っておき、
リザルト画面を検出した時点でその試合に引き渡す。リザルト読み取り中に「バトル」で次の対戦に入ることが
あるので、どの状態でも（リザルト画面以外なら）VS 画面を見る。
相手クラス名はバッジより数秒早く表示されるので、VS 待ちの間は先回りして読んでおき、
バッジで確定した時点で直前の読み取りを多数決する。
"""
import collections
import logging
import time
from datetime import datetime
from enum import Enum

from .db import match_signature
from .result_reader import ResultInfo, read_result, similar_deck, snap_deck
from .screens import read_opponent_class

log = logging.getLogger(__name__)

LEAVE_SEC = 5.0           # リザルト画面がこの秒数見えなければ「画面が変わった」
MAX_COLLECT_SEC = 120.0   # MP内訳画面で放置されても、この秒数で打ち切って記録する
OCR_INTERVAL = 0.4        # リザルト読み取りの間隔（秒）
VS_CONFIRM = 2            # VS 画面の判定が何回続けて同じなら採用するか
MIN_SUMMARY_READS = 3     # サマリー画面を最低何回読んで多数決するか
SAME_MATCH_SEC = 6 * 3600 # この時間内に同じ指紋の記録が来たら同じ試合とみなす
VOTED_FIELDS = ("cr", "cr_change", "mp_gained", "rank", "format")
OPP_LOOKBACK = 8.0        # 先攻/後攻が確定した時点から、この秒数前までの相手クラス読み取りを使う
OPP_GRACE = 6.0           # 確定後もこの秒数は相手クラスを読み続ける
DIM_WEIGHT = 0.1          # 暗い画面（マッチング中）で読んだデッキ名の票の重さ
FAST_INTERVAL = 0.25     # VS 画面を待っている間のキャプチャ間隔（VS のバッジは約2秒しか出ない）


class VsInfo:
    """VS 画面から読んだ、これから始まる試合の情報"""

    def __init__(self):
        self.turn = None
        self.opponent = None
        self.turn_at = None
        self.started_at = None  # 試合開始（VS 画面で先攻/後攻が確定した）時刻
        self.frame = None
        self._seen, self._streak = None, 0
        self._opp_reads = collections.deque(maxlen=64)  # (時刻, クラス名)


class State(Enum):
    WAITING = "待機中"
    COLLECTING = "リザルト読み取り中"
    AFTER = "記録済み（画面遷移待ち）"


class MatchTracker:
    def __init__(self, detector, vs_detector, ocr, settings, known_decks=lambda: [], last_cr=lambda: None,
                 on_record=lambda rec, frame: None, on_status=lambda text: None,
                 on_debug=lambda name, frame: None):
        self.detector = detector
        self.vs_detector = vs_detector
        self.ocr = ocr
        self.settings = settings
        self.known_decks = known_decks
        self.last_cr = last_cr
        self.on_record = on_record
        self.on_status = on_status
        self.on_debug = on_debug
        self.state = State.WAITING
        self.vs = VsInfo()          # 次の試合（VS 画面で読んだもの）
        self.match_vs = VsInfo()    # いまリザルトを読んでいる試合の分
        self._debug_saved = False
        self._reset_collect()
        self._streak_verdict, self._streak = None, 0
        self._last_seen = 0.0
        self._last_sig = None  # 直前に記録した試合の「指紋」（同じ試合の再記録を防ぐ）
        self._last_sig_at = 0.0

    def _reset_collect(self):
        self.result = None
        self.info = ResultInfo()
        self._deck_votes = collections.Counter()
        self._votes = collections.defaultdict(collections.Counter)  # 項目ごとの読み取り値の投票
        self._summary_reads = 0
        self._collect_start = 0.0
        self._last_ocr = 0.0
        self._best_frame = None
        self._summary_since = None  # サマリー画面（変動CR）を最初に読めた時刻

    @property
    def interval(self):
        """次のキャプチャまでの間隔。VS 画面を待っている間だけ短くする"""
        base = self.settings.interval_sec
        return min(base, FAST_INTERVAL) if self.vs.turn is None else base

    # 旧名（テスト・GUI 互換）
    @property
    def turn(self):
        return self.vs.turn

    @property
    def opponent(self):
        return self.vs.opponent

    def _set_state(self, state, detail=""):
        self.state = state
        self.on_status(state.value + (f" {detail}" if detail else ""))

    # ------------------------------------------------------------------

    def feed(self, frame, now=None):
        now = time.monotonic() if now is None else now
        verdict, _ = self.detector.detect(frame)
        if verdict is None:
            self._scan_vs(frame, now)

        if self.state is State.WAITING:
            if verdict and verdict == self._streak_verdict:
                self._streak += 1
            else:
                self._streak_verdict, self._streak = verdict, (1 if verdict else 0)
            if verdict and self._streak >= self.settings.confirm_frames:
                self._reset_collect()
                self.result = verdict
                # ここまでに VS 画面で読んだ情報はこの試合のもの。以降の VS は次の試合
                self.match_vs, self.vs = self.vs, VsInfo()
                self._debug_saved = False
                self._collect_start = self._last_seen = now
                self._set_state(State.COLLECTING, "勝利" if verdict == "win" else "敗北")
                self._collect(frame, now)

        elif self.state is State.COLLECTING:
            if verdict == self.result:
                self._last_seen = now
                self._collect(frame, now)
            # 1回の読み間違いに引きずられないよう、サマリーは数回読んでから多数決で決める
            summary_done = (self._summary_since is not None
                            and ((self.info.complete and self._summary_reads >= MIN_SUMMARY_READS)
                                 or now - self._summary_since >= self.settings.collect_sec))
            gone = now - self._last_seen >= LEAVE_SEC
            if summary_done or gone or now - self._collect_start >= MAX_COLLECT_SEC:
                self._finish(now)

        elif self.state is State.AFTER:
            if verdict:
                self._last_seen = now
            if now - self._last_seen >= LEAVE_SEC:
                self._streak_verdict, self._streak = None, 0
                self._set_state(State.WAITING)

    def _collect(self, frame, now):
        if now - self._last_ocr < OCR_INTERVAL:
            return
        self._last_ocr = now
        got = read_result(self.ocr, frame)
        if got.deck and got.deck_dim:
            # マッチング中の暗い画面は読み間違えやすいので、明るい画面の読みが1回でもあればそちらを優先
            self._deck_votes[got.deck] += DIM_WEIGHT
            if self._best_frame is None:
                self._best_frame = frame.copy()
        elif got.deck:
            self._deck_votes[got.deck] += 1
            self._best_frame = frame.copy()  # デッキ名が見えている＝一番情報が多い画面
        elif self._best_frame is None:
            self._best_frame = frame.copy()
        got.deck = None
        if got.cr_change is not None:
            self._summary_reads += 1
            if self._summary_since is None:
                self._summary_since = now
        for f in VOTED_FIELDS:
            v = getattr(got, f)
            if v is not None:
                self._votes[f][v] += 1
                setattr(self.info, f, self._votes[f].most_common(1)[0][0])
        if self._deck_votes:
            self.info.deck = self._pick_deck()

    def _pick_deck(self):
        registered = list(self.settings.deck_names)
        history = [d for d in self.known_decks() if d not in registered]
        # まず全候補を既知のデッキ名に寄せて投票し、なければ一番多く読めた文字列
        votes = collections.Counter()
        for cand, n in self._deck_votes.items():
            votes[snap_deck(cand, registered, history)] += n
        # 「ミッドメア3」「ツドメア3」のような読み揺れは同じデッキとしてまとめて数える
        groups = []
        for name, n in votes.most_common():
            for g in groups:
                if similar_deck(name, g[0][0]):
                    g.append((name, n))
                    break
            else:
                groups.append([(name, n)])
        best = max(groups, key=lambda g: sum(n for _, n in g))
        head, head_n = best[0]
        if head in registered:
            return head
        # 端の文字を落として読むことが多いので、ある程度読めている長い方を採る
        longer = [name for name, n in best[1:] if n >= head_n * 0.2 and len(name) > len(head)]
        return max(longer, key=len) if longer else head

    def _finish(self, now):
        info = self.info
        if info.cr_change is None and info.cr is not None:
            prev = self.last_cr()
            if prev is not None and 0 < abs(info.cr - prev) <= 100:
                info.cr_change = info.cr - prev
        if info.cr_change is not None:
            # ランクマッチでは勝てば増え、負ければ減る。符号の読み落としを直す
            info.cr_change = abs(info.cr_change) * (1 if self.result == "win" else -1)
        if all(getattr(info, f) is None for f in VOTED_FIELDS):
            # ランクも MP も読めない＝ランクマッチのリザルトではない（ルームマッチや誤検出）
            log.info("ランクマッチのリザルトではないので記録しません (デッキ候補 %s)", dict(self._deck_votes))
            self._set_state(State.AFTER)
            return
        deck = self.settings.deck_override or info.deck
        rec = {
            # 記録の日時は試合開始時刻（VS 画面を見逃したときだけリザルトの時刻）
            "played_at": (self.match_vs.started_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
            "result": self.result,
            "turn_order": self.match_vs.turn,
            "opponent": self.match_vs.opponent,
            "deck": deck,
            "cr": info.cr,
            "cr_change": info.cr_change,
            "mp_gained": info.mp_gained,
            "rank": info.rank,
            "format": info.format,
            "source": "auto",
        }
        sig = match_signature(rec)
        # VS 画面を見てから始まった試合は必ず新しい試合（マスター帯は CR が出ないので、
        # 連勝で獲得MP が同じだと指紋だけでは区別できない）
        fresh = self.match_vs.started_at is not None
        if not fresh and sig is not None and sig == self._last_sig and now - self._last_sig_at < SAME_MATCH_SEC:
            # リザルト画面を開いたまま「確認」などで出入りした / 再表示されただけ
            log.info("同じ試合なので記録しません: %s", rec)
            self._set_state(State.AFTER)
            return
        self._last_sig, self._last_sig_at = sig, now
        log.info("記録: %s (デッキ候補 %s, 投票 %s)", rec, dict(self._deck_votes),
                 {k: dict(v) for k, v in self._votes.items()})
        self.on_record(rec, self._best_frame)
        self.match_vs = VsInfo()
        self._set_state(State.AFTER)

    def _scan_vs(self, frame, now):
        """VS 画面を見て、次の試合の先攻/後攻と相手クラスを読む"""
        vs = self.vs
        if vs.turn is not None and vs.opponent is None and now - vs.turn_at > OPP_GRACE:
            if not self._debug_saved:
                self._debug_saved = True
                log.warning("相手クラスを読めませんでした（data/debug に VS 画面を保存）")
                self.on_debug("vs_opponent_unread", vs.frame)
            return
        if vs.turn is not None and vs.opponent is not None:
            return  # 読み終わっている（対戦中はここで終わるので負荷は増えない）

        # 相手クラス名はバッジより先に出るので、VS 待ちの間は毎回読んでおく（1回 約6ms）
        try:
            cls = read_opponent_class(self.ocr, frame)
        except Exception as e:
            log.warning("相手クラスの OCR に失敗: %s", e)
            cls = None
        if cls:
            vs._opp_reads.append((now, cls))

        if vs.turn is None:
            turn = self.vs_detector.detect(frame)
            if turn is None:
                vs._seen, vs._streak = None, 0
                return
            vs._streak = vs._streak + 1 if turn == vs._seen else 1
            vs._seen = turn
            if vs._streak < VS_CONFIRM:
                return
            vs.turn, vs.turn_at, vs.frame = turn, now, frame.copy()
            vs.started_at = datetime.now()
            log.info("先攻/後攻: %s", turn)

        recent = collections.Counter(c for t, c in vs._opp_reads if t >= vs.turn_at - OPP_LOOKBACK)
        if recent:
            vs.opponent = recent.most_common(1)[0][0]
            log.info("相手クラス: %s （読み取り %s）", vs.opponent, dict(recent))

        detail = "先攻" if vs.turn == "first" else "後攻"
        if vs.opponent:
            detail += f" / 相手 {vs.opponent}"
        self.on_status(f"対戦中（{detail}）")
