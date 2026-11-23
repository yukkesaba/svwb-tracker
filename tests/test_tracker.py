"""実際のスクリーンショットを順番に流して、記録の流れを確かめる

    python tests/test_tracker.py

tests/fixtures のスクショを使う。
"""
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from svwb.config import Settings  # noqa: E402
from svwb.ocr import Ocr  # noqa: E402
from svwb.result_reader import clean_deck_text, match_known_deck, parse_panel, read_result  # noqa: E402
from svwb.screens import ResultScreenDetector, VsScreenDetector, read_my_class, read_opponent_class  # noqa: E402
from svwb.tracker import MatchTracker, State  # noqa: E402

SHOTS = ROOT / "tests" / "fixtures"  # 旧版のスクショから必要なものだけコピー
FIXTURES = ROOT / "tests" / "fixtures"


def load(name):
    return cv2.imread(str(SHOTS / f"{name}.jpg"))


def make_tracker(records, last_cr=None, known=()):
    return MatchTracker(ResultScreenDetector(), VsScreenDetector(), OCR, Settings(),
                        known_decks=lambda: list(known), last_cr=lambda: last_cr,
                        on_record=lambda rec, frame: records.append((rec, frame)))


def run(tracker, frames, dt=0.5):
    t = 0.0
    for f in frames:
        tracker.feed(f, now=t)
        t += dt


def test_records_loss_once_and_ignores_lobby():
    lobby = load("win_20260303_020313")  # 旧版がロビーを勝利と誤記録していた画像
    loss = load("loss_20260504_022642")
    recs = []
    tr = make_tracker(recs)
    run(tr, [lobby] * 4 + [loss] * 12 + [lobby] * 4 + [loss] * 1 + [lobby] * 12)
    assert len(recs) == 1, recs
    rec = recs[0][0]
    assert rec["result"] == "loss"
    assert rec["cr"] == 1586 and rec["cr_change"] == -16, rec
    assert rec["deck"] == "徒姫無し進化ナイトメア", rec
    assert rec["rank"] == "Grand Master 3" and rec["format"] == "ローテーション", rec
    assert tr.state is State.WAITING


def test_win_breakdown_then_summary():
    """MP内訳画面（デッキ名なし）→ サマリー画面の順に出ても両方から拾う"""
    breakdown = load("win_20260504_021153")
    summary = load("win_20260504_023427")
    recs = []
    tr = make_tracker(recs)
    run(tr, [breakdown] * 3 + [summary] * 6)
    rec = recs[0][0]
    assert rec["result"] == "win" and rec["cr_change"] == 16 and rec["mp_gained"] == 173, rec


def test_mp_from_breakdown_when_summary_not_seen():
    """2026-11 の不具合: MP内訳画面だけ見てすぐ次へ進むと、獲得MP が空になっていた"""
    breakdown = load("win_20260504_021153")
    lobby = load("win_20260303_020313")
    recs = []
    tr = make_tracker(recs)
    run(tr, [breakdown] * 10 + [lobby] * 14)
    assert len(recs) == 1 and recs[0][0]["mp_gained"] == 218, [r for r, _ in recs]
    # 内訳の行数が違って「TOTAL」の字が読めない画面
    assert read_result(OCR, cv2.imread(str(FIXTURES / "win_20260927_223014.jpg"))).mp_total == 173


def test_no_double_record_across_breakdown_and_summary():
    """2026-09-27 の不具合: MP内訳 → 演出で WIN が一瞬消える → サマリー で2回記録されていた。
    MP内訳の CR（1583）は試合前の値なので使わず、サマリーの 1601 を採る"""
    new = FIXTURES
    breakdown = cv2.imread(str(new / "win_20260927_223014.jpg"))
    summary = cv2.imread(str(new / "win_20260927_223028.jpg"))
    if breakdown is None or summary is None:
        return
    lobby = load("win_20260303_020313")
    recs = []
    tr = make_tracker(recs)
    run(tr, [breakdown] * 20 + [lobby] * 4 + [summary] * 10 + [lobby] * 14)
    assert len(recs) == 1, [r for r, _ in recs]
    rec = recs[0][0]
    assert rec["cr"] == 1601 and rec["cr_change"] == 18 and rec["deck"] == "旗", rec
    assert rec["rank"] == "Grand Master 11", rec


def test_same_result_screen_again_is_not_recorded_twice():
    """2026-09-27 の不具合: リザルト画面を開いたまま「確認」などで出入りすると、何度も記録されていた"""
    summary = load("loss_20260504_022642")
    lobby = load("win_20260303_020313")
    recs = []
    tr = make_tracker(recs)
    run(tr, ([summary] * 10 + [lobby] * 14) * 3)
    assert len(recs) == 1, [r for r, _ in recs]


def test_db_merges_same_match_across_restart():
    """アプリを再起動して同じリザルト画面をもう一度読んだときは、DB 側で1件にまとめる"""
    import tempfile
    from svwb.db import Database
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "t.db")
        first = {"result": "loss", "cr": 1588, "cr_change": -16, "turn_order": None, "opponent": None}
        db.add(**first)
        again = dict(first, opponent="ビショップ", turn_order="second")
        same = db.find_same_match(again)
        assert same is not None
        db.fill_missing(same, again)
        m = db.matches()
        assert len(m) == 1 and m[0]["opponent"] == "ビショップ" and m[0]["turn_order"] == "second"
        # CR が同じでも、間に別の試合があれば別の試合
        db.add(result="win", cr=1604, cr_change=16)
        assert db.find_same_match(first) is None
        db.close()


def test_mp_info_icon_not_read_as_digit():
    """獲得MP の右の (i) アイコンを「1」と読まない"""
    from svwb.result_reader import read_result
    for name, mp in (("loss_20260504_022642", 15), ("win_20260504_023427", 173)):
        assert read_result(OCR, load(name)).mp_gained == mp, name


def test_deck_snaps_to_known_name():
    assert match_known_deck(["エンル、ロイヤル"], ["エンハロイヤル", "進化エルフ"]) == "エンハロイヤル"
    assert match_known_deck(["全然違う"], ["エンハロイヤル"]) is None
    assert clean_deck_text("工ンノ、ロイヤ丿し") == "エンハロイヤル"


def fixture(name):
    return cv2.imread(str(FIXTURES / f"{name}.jpg"))


def test_vs_screen_turn_and_class():
    vs = VsScreenDetector()
    for name, turn, opp in (("vs_second_vs_nightmare", "second", "ナイトメア"),
                            ("vs_second_vs_nemesis", "second", "ネメシス"),
                            ("vs_first_vs_witch", "first", "ウィッチ")):
        img = fixture(name)
        assert vs.detect(img) == turn, name
        assert read_opponent_class(OCR, img) == opp, name
    # リザルト画面やロビーでは反応しない
    assert vs.detect(load("loss_20260504_022642")) is None
    assert vs.detect(load("win_20260303_020313")) is None


def test_elf_class_read_through_emblem_glow():
    """2026-10〜11 の不具合: 相手がエルフのときだけ「工丿しフ」と読まれてクラスが空になっていた"""
    for name in ("vs_elf_unread_1", "vs_elf_unread_2", "vs_elf_unread_3", "vs_elf_unread_4"):
        assert read_opponent_class(OCR, fixture(name)) == "エルフ", name


def test_my_class_read_from_vs():
    for name, mine in (("vs_second_vs_nightmare", "ナイトメア"), ("vs_second_vs_nemesis", "ナイトメア"),
                       ("vs_first_vs_witch", "エルフ"), ("vs_elf_unread_1", "ナイトメア"),
                       ("vs_elf_unread_2", "ビショップ"), ("vs_elf_unread_3", "エルフ"),
                       ("vs_elf_unread_4", "ビショップ")):
        assert read_my_class(OCR, fixture(name)) == mine, name
    # 自分のクラスだけ読めなくても、先攻後攻と相手クラスは入り、読めない画面を1回だけ残す
    from svwb.screens import MY_CLASS_ROI
    vs = fixture("vs_second_vs_nemesis")
    x, y, w, h = MY_CLASS_ROI
    hidden = vs.copy()
    hidden[y:y + h, x:x + w] = 0
    other = load("win_20260303_020313")
    tr = make_tracker([])
    saved = []
    tr.on_debug = lambda name, frame: saved.append(name)
    run_dt(tr, [other] * 4 + [hidden] * 12 + [other] * 40)
    assert (tr.turn, tr.opponent, tr.vs.my_class) == ("second", "ネメシス", None)
    assert saved == ["vs_my_class_unread"], saved


def test_old_db_gets_my_class_column():
    import sqlite3
    import tempfile
    from svwb.db import SCHEMA, Database
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.db"
        old = sqlite3.connect(str(p))
        old.executescript("\n".join(x for x in SCHEMA.splitlines() if "my_class" not in x))
        old.execute("INSERT INTO matches (played_at, result, deck) VALUES ('2026-11-01 00:00:00', 'win', 'ランプ')")
        old.commit()
        old.close()
        for _ in range(2):  # 2回開いても同じ
            db = Database(p)
            assert db.matches()[0]["my_class"] is None and db.seen_classes() == {}
            db.close()
        db = Database(p)
        for c in ("ドラゴン", "ドラゴン", "ネメシス"):
            db.add(result="win", deck="ランプ", my_class=c)
        assert db.seen_classes() == {"ランプ": "ドラゴン"}
        db.close()


def test_full_flow_vs_then_result():
    """VS 画面 → 対戦（別の画面）→ リザルト の順で、先攻/後攻と相手クラスが記録に入る"""
    vs = fixture("vs_second_vs_nemesis")
    other = load("win_20260303_020313")
    loss = load("loss_20260504_022642")
    recs = []
    tr = make_tracker(recs)
    run(tr, [vs] * 4)
    started = tr.vs.started_at
    import time as _t
    _t.sleep(1.1)  # 開始とリザルトで時刻がずれるように
    run(tr, [other] * 5 + [loss] * 12 + [other] * 4)
    rec = recs[0][0]
    assert rec["turn_order"] == "second" and rec["opponent"] == "ネメシス", rec
    assert rec["my_class"] == "ナイトメア", rec
    # 記録の日時はリザルトの時刻ではなく試合開始（VS 画面）の時刻
    assert rec["played_at"] == started.strftime("%Y-%m-%d %H:%M:%S"), (rec["played_at"], started)
    # 記録したら次の試合に持ち越さない
    assert tr.turn is None and tr.opponent is None


def run_dt(tracker, frames, dt=0.25, t0=0.0):
    t = t0
    for f in frames:
        tracker.feed(f, now=t)
        t += dt
    return t


def test_consecutive_matches_with_same_numbers_both_recorded():
    """2026-11-03 の取りこぼし: マスター帯（CR なし）の連勝で獲得MP が同じだと、
    2試合目を「同じ試合」として捨てていた。VS 画面を挟んだら別の試合"""
    vs = fixture("vs_second_vs_nemesis")
    other = load("win_20260303_020313")
    win = load("win_20260504_023427")
    recs = []
    tr = make_tracker(recs)
    run_dt(tr, ([vs] * 8 + [other] * 30 + [win] * 20 + [other] * 30) * 2)
    assert len(recs) == 2, [r for r, _ in recs]


def test_vs_during_result_reading_goes_to_next_match():
    """2026-09-28 の取りこぼし: リザルト読み取り中に「バトル」→ VS 画面が出ると見逃していた。
    その VS は「次の試合」の分として持ち越し、今の試合には入れない"""
    vs = fixture("vs_second_vs_nemesis")
    other = load("win_20260303_020313")
    first_result = load("loss_20260504_022642")
    second_result = load("win_20260504_023427")
    recs = []
    tr = make_tracker(recs)
    t = run_dt(tr, [first_result] * 3 + [vs] * 8 + [other] * 30)
    assert len(recs) == 1 and recs[0][0]["turn_order"] is None, recs[0][0]
    assert tr.turn == "second" and tr.opponent == "ネメシス"
    run_dt(tr, [second_result] * 20 + [other] * 30, t0=t)
    assert len(recs) == 2
    assert recs[1][0]["turn_order"] == "second" and recs[1][0]["opponent"] == "ネメシス", recs[1][0]


def test_opponent_read_before_badges_appear():
    """2026-09-28 の取りこぼし: 相手クラス名はバッジより先に出るので、バッジ確定後だけ読むと取れないことがある"""
    from svwb.screens import MY_BADGE, OPP_BADGE, OPP_CLASS_ROI
    vs = fixture("vs_second_vs_nemesis")
    before = vs.copy()  # バッジがまだない（演出中）
    for x, y, w, h in (MY_BADGE, OPP_BADGE):
        before[y - 30:y + h + 30, x - 30:x + w + 30] = 0
    badges_only = vs.copy()  # バッジは出たがクラス名が読めない
    x, y, w, h = OPP_CLASS_ROI
    badges_only[y:y + h, x:x + w] = 0
    other = load("win_20260303_020313")
    recs = []
    tr = make_tracker(recs)
    run_dt(tr, [other] * 4 + [before] * 12 + [badges_only] * 8 + [other] * 40)
    assert tr.turn == "second" and tr.opponent == "ネメシス", (tr.turn, tr.opponent)


def test_fast_interval_only_while_waiting_for_vs():
    recs = []
    tr = make_tracker(recs)
    assert tr.interval == 0.25
    run_dt(tr, [fixture("vs_second_vs_nemesis")] * 4)
    assert tr.interval == Settings().interval_sec  # 対戦中は普段の間隔


def test_group_name_not_taken_as_deck():
    """2026-10-31 の不具合: Master 帯で「グループ ルビー / トパーズ」をデッキ名として拾っていた"""
    from svwb.result_reader import is_group_name
    for s in ("ルビ", "ルピ", "ト、なルビ", "トパーズ", "トハース", "サファイア"):
        assert is_group_name(clean_deck_text(s)), s
    for s in ("テンポエルフ", "クキシロ", "ランプ", "ミッドメア3", "旗", "徒姫無し進化ナイトメア"):
        assert not is_group_name(s), s


def test_deck_vote_merges_ocr_variants():
    """2026-11-01 の不具合: 過去の読み間違い「ッドメア」に正しい読みが吸い寄せられていた、
    「ツドメア3」（20回）が「ミッドメア3」（6回）に勝っていた"""
    import collections
    hist = ["ッドメア", "テンポエルフ", "クキシロ"]
    for votes, want in (({"ミッドナイトメア2": 13}, "ミッドナイトメア2"),
                        ({"ミッドメア3": 6, "ツドメア3": 20, "テンポエルフ": 2}, "ミッドメア3"),
                        ({"テンホエルフ": 9, "テンポエルフ": 2}, "テンポエルフ"),
                        ({"ツドメア3": 6}, "ツドメア3")):  # 過去に「ミッドメア3」がなければそのまま
        tr = make_tracker([], known=hist)
        tr._deck_votes = collections.Counter(votes)
        assert tr._pick_deck() == want, (votes, tr._pick_deck())


def test_dim_matching_screen_does_not_outvote_deck():
    """2026-11-02 の不具合: 「バトル」→ マッチング中で暗くなった画面を「ツドメア3」と読み続け、多数決で勝っていた"""
    import collections
    from svwb.result_reader import snap_deck
    shot = FIXTURES / "loss_20261102_012007.jpg"  # マッチング中の暗い画面
    img = cv2.imread(str(shot))
    from svwb.result_reader import read_result
    if img is not None:
        assert read_result(OCR, img).deck_dim
    assert read_result(OCR, load("loss_20260504_022642")).deck_dim  # これも「マッチング中」の画面
    assert not read_result(OCR, load("win_20260504_023427")).deck_dim
    tr = make_tracker([])
    tr._deck_votes = collections.Counter({"ミッドメア3": 1, "ツドメア3": 6 * 0.1})
    assert tr._pick_deck() == "ミッドメア3"
    # 暗い画面しか読めなくても、過去の記録に長い名前があればそちらに寄せる
    assert snap_deck("ツドメア3", [], ["ミッドメア3", "テンポエルフ"]) == "ミッドメア3"


def test_decks_listed_by_recent_use_and_merged():
    import sqlite3
    import tempfile
    from svwb.db import Database
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "m.db")
        for i, deck in enumerate(["古い", "古い", "古い", "新しい", "別名"]):
            db.add(played_at=f"2026-11-0{i + 1} 20:00:00", result="win" if i % 2 else "loss", deck=deck)
        assert db.decks() == ["別名", "新しい", "古い"]  # 試合数ではなく最近使った順
        backup = db.backup()
        assert db.rename_deck("別名", "新しい") == 1
        assert [(s["deck"], s["n"]) for s in db.deck_summary()] == [("新しい", 2), ("古い", 3)]
        src = sqlite3.connect(str(backup))
        assert src.execute("SELECT COUNT(*) FROM matches WHERE deck = '別名'").fetchone()[0] == 1  # 控えは変更前のまま
        src.close()
        db.close()


def test_matchup_counts_by_deck_and_opponent():
    from svwb.db import matchup
    rows = [dict(result="win", deck="A", opponent="エルフ"), dict(result="loss", deck="A", opponent="エルフ"),
            dict(result="win", deck="A", opponent=None), dict(result="win", deck="B", opponent="ドラゴン")]
    t = matchup(rows)
    assert t["A"]["エルフ"] == (1, 2) and t["A"]["合計"] == (2, 3)  # 相手が空の試合は合計にだけ入る
    assert t["合計"]["合計"] == (3, 4) and t["合計"]["ドラゴン"] == (1, 1)
    assert "エルフ" not in t["B"]


def test_cr_chart_split_by_class():
    from svwb.db import cr_groups, deck_class
    assert deck_class("純融合ネメシス") == "ネメシス" and deck_class("ミッドメア3") == "ナイトメア"
    assert deck_class("ランプ") is None and deck_class(None) is None
    assert deck_class("ランプ", {"ランプ": "ドラゴン"}) == "ドラゴン"
    rows = [{"deck": d, "cr": c} for d, c in [("ランプ", 1490), ("スペルキマイラ", 1328), ("DDエルフ", None),
                                              ("純スペルウィッチ", 1342), (None, 1500)]]
    g = cr_groups(rows, {"スペルキマイラ": "ウィッチ"})
    assert list(g) == ["ランプ", "ウィッチ", "（未設定）"]  # CR の無い試合は数えない
    assert [r["cr"] for r in g["ウィッチ"]] == [1328, 1342]
    assert list(cr_groups(rows)) == ["ランプ", "スペルキマイラ", "ウィッチ", "（未設定）"]
    # VS 画面で読んだクラス: その試合はデッキ名より優先、読めていない試合はデッキごとの多数で補う
    assert deck_class("ランプ", {}, {"ランプ": "ドラゴン"}) == "ドラゴン"
    assert deck_class("純融合ネメシス", {}, {"純融合ネメシス": "ドラゴン"}) == "ネメシス"
    rows = [{"deck": "純融合ネメシス", "cr": 1551, "my_class": "ドラゴン"}, {"deck": "ランプ", "cr": 1532, "my_class": None},
            {"deck": "純融合ネメシス", "cr": 1512, "my_class": None}]
    assert {k: len(v) for k, v in cr_groups(rows, {}, {"ランプ": "ドラゴン"}).items()} == {"ドラゴン": 2, "ネメシス": 1}


def test_obs_text():
    from svwb import obs
    rows = [dict(result="win", deck="X", cr=1520, cr_change=16), dict(result="win", deck="X", cr=1504, cr_change=15),
            dict(result="loss", deck="Y", cr=None, cr_change=None)]
    assert obs.render("{wins}勝 {losses}敗 勝率{rate}%", rows) == "2勝 1敗 勝率67%"
    assert obs.render("{streak}\\n{cr} ({cr_net}) {deck}", rows) == "2連勝\n1520 (+31) X"
    assert obs.render("{wins}-{losses} {rate} {streak} {cr}", []) == "0-0 - - -"
    assert obs.render("{unknown} {wins", rows) == "{unknown} {wins"  # 書式が壊れていても落ちない
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "obs" / "today.txt"
        assert obs.write("a", path) and not obs.write("a", path) and obs.write("b", path)
        assert path.read_text(encoding="utf-8") == "b"


def test_overlay_files_and_data(tmp=None):
    import json
    import tempfile
    from svwb import obs
    rows = [{"result": "win", "cr": 1618, "cr_change": 17, "deck": "兎ビショップ"},
            {"result": "win", "cr": 1601, "cr_change": 15, "deck": "兎ビショップ"},
            {"result": "loss", "cr": 1586, "cr_change": -13, "deck": "兎ビショップ"}]
    d = obs.overlay_data(rows)
    assert d["wins"] == 2 and d["losses"] == 1 and d["rate"] == 67, d
    assert d["streak"] == 2 and d["streak_kind"] == "win" and d["cr"] == 1618 and d["cr_net"] == 19, d
    assert d["recent"] == ["loss", "win", "win"], d  # 右端が直前の試合
    mixed = [{"result": "loss", "deck": "旗"}] + rows
    only = obs.same_deck(mixed)
    assert only == mixed[:1], only  # デッキを替えたら、そのデッキだけで数える
    assert obs.same_deck(rows) == rows and obs.same_deck([]) == []
    assert obs.overlay_data(only, by_deck=True)["by_deck"] is True
    empty = obs.overlay_data([])
    assert empty["rate"] is None and empty["recent"] == [] and empty["cr"] is None, empty
    with tempfile.TemporaryDirectory() as t:
        folder = Path(t) / "obs"
        assert obs.write_overlay(rows, folder)
        assert not obs.write_overlay(rows, folder)  # 変わっていなければ書かない
        for name in obs.OVERLAY_FILES:
            assert (folder / name).exists(), name
        text = (folder / "data.js").read_text(encoding="utf-8")
        assert json.loads(text.split("=", 1)[1].strip().rstrip(";")) == d


def test_all_sources_compile():
    # GUI はテストで読み込まないので、書き間違いで起動できなくなるのをここで防ぐ
    import py_compile
    for f in (Path(__file__).resolve().parent.parent / "svwb").rglob("*.py"):
        py_compile.compile(str(f), doraise=True)


def test_old_screenshots_pruned():
    import os
    import tempfile
    from svwb.storage import prune_screenshots
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for i in range(5):
            f = d / f"{'win' if i % 2 else 'loss'}_2026110{i}_000000.jpg"
            f.write_bytes(b"x")
            os.utime(f, (1000 + i, 1000 + i))
        (d / "memo.txt").write_text("keep")
        (d / "other.jpg").write_bytes(b"x")  # トラッカーが作ったもの以外は消さない
        assert prune_screenshots(d, 0) == 0 and len(list(d.iterdir())) == 7
        assert prune_screenshots(d, 2) == 3
        assert sorted(f.name for f in d.iterdir()) == ["loss_20261104_000000.jpg", "memo.txt", "other.jpg",
                                                       "win_20261103_000000.jpg"]


def test_capture_recovers_after_failure():
    from svwb.capture import WindowCapture

    class Broken:
        closed = False

        def grab(self, region):
            raise RuntimeError("BitBlt")

        def close(self):
            self.closed = True

    cap = WindowCapture("no-such-window-zzz")
    broken = cap._sct = Broken()
    region = {"left": 0, "top": 0, "width": 8, "height": 8}
    assert cap._shot(region) is None and cap.failures == 1
    assert broken.closed and cap._sct is not broken  # 取り直しのために作り直す
    cap._sct = Broken()
    assert cap._shot(region) is None and cap.failures == 2

    class Ok:
        def grab(self, region):
            import numpy as np
            return np.zeros((8, 8, 4), dtype=np.uint8)

    cap._sct = Ok()
    assert cap._shot(region) is not None and cap.failures == 0


def test_parse_panel_signs():
    from svwb.ocr import OcrLine
    lines = [OcrLine("変動CR", 578, 277, 100, 30), OcrLine("ー14", 808, 280, 50, 30), OcrLine("CR1752", 700, 335, 170, 35)]
    info = parse_panel(lines)
    assert info.cr == 1752 and info.cr_change == -14
    # 2026-11 の不具合: (i) アイコンを塗りつぶしきれず +218 が +2181 と記録された
    assert parse_panel([OcrLine("獲得MP+2181", 500, 120, 200, 30)]).mp_gained == 218
    assert parse_panel([OcrLine("獲得MP+173", 500, 120, 200, 30)]).mp_gained == 173


if __name__ == "__main__":
    OCR = Ocr()
    tests = [(k, v) for k, v in dict(globals()).items() if k.startswith("test_")]
    HAVE_SHOTS = any(FIXTURES.glob("*.jpg"))
    NEEDS_SHOTS = {"load", "fixture", "FIXTURES", "SHOTS"}
    skipped = 0
    for name, fn in tests:
        # スクショ（tests/fixtures）は公開していないので、無ければスクショを使うテストは飛ばす
        if not HAVE_SHOTS and NEEDS_SHOTS & set(fn.__code__.co_names):
            print("skip", name)
            skipped += 1
            continue
        fn()
        print("ok", name)
    print(f"{len(tests) - skipped} tests passed" + (f"（スクショが無いので {skipped} 件は飛ばしました）" if skipped else ""))
