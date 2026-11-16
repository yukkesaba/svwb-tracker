# SVWB Tracker v2

Shadowverse: Worlds Beyond（Steam版）のリザルト画面を読み取って、戦績を自動で記録します。
ゲームの画面を**読むだけ**で、操作は一切しません。

## 起動

`SVWB Tracker.bat` をダブルクリック（起動すると自動で監視を始めます）。
ウィンドウを閉じてもトレイに残って記録を続けます。終了はトレイアイコンの右クリック →「終了」。

初回セットアップ（別のPCなど）:

```
py -3.10 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Windows の設定で「日本語」の言語パックが入っている必要があります（OCR に使用）。

## 自動で記録されるもの

| 項目 | 取り方 |
|---|---|
| 勝敗 | 画面上部の WIN / RESULT をテンプレートマッチング |
| CR・変動CR・獲得MP・ランク・フォーマット | リザルト画面右側を Windows OCR |
| 使用デッキ | 「使用デッキ」の名前を OCR → 過去に使ったデッキ名に自動で寄せる |
| 先攻・後攻 | VS 画面の自分側（左）のバッジをテンプレートマッチング。左右のバッジが逆になっているときだけ採用 |
| 相手クラス | VS 画面右側のクラス名を OCR |

先攻・後攻と相手クラスは、アプリ起動が対戦途中だった場合などは空になります。「直前の試合」のボタンで1クリックで直せます。

変動CRが読めなかったときは、前回の CR との差から計算します。

## 仕組み

```
capture.py  ウィンドウの描画領域を撮影して 1920x1080 に揃える
screens.py  WIN / RESULT のタイトル文字を判定
tracker.py  待機 → 2フレーム連続で確定 → 数秒かけて数値を読む → 記録 → 画面が変わるまで待つ
result_reader.py  OCR の結果から CR やデッキ名を拾う
db.py       SQLite（data/matches.db）
gui/        PySide6 の画面
```

## 精度の確認

旧版が保存したスクショ（約300枚）で測定できます:

```
.venv\Scripts\python tools\eval_screens.py ..\data\screenshots ..\data\matches.db
.venv\Scripts\python tests\test_tracker.py
```

2026-09 時点: 勝敗判定 247/247、旧版がロビーを誤って「勝ち」にしていた 54 枚はすべて除外、CR 41/41 一致。

## exe 版（E:\SBTracker）

- 起動: `SVWB Tracker.bat`（`app\SVWB Tracker.exe` を起動します）
- 戦績・設定・スクショ・ログ: `app\data\`
- ビルド: `build.bat`（`app\` を作り直します。`app\data` は消しません）
- ソースから直接動かす `python app.py` は `data\`（別の場所）を使うので注意

## 権利について

- 非公式のファンメイドツールです。株式会社Cygames とは関係ありません。
- 「Shadowverse」およびゲーム内の画像・名称の権利は株式会社Cygames に帰属します。
  `assets/templates` の画像は、画面の判定に必要な文字部分だけを切り出したものです。
- テストで使うゲーム画面のスクリーンショット（`tests/fixtures`）は公開していません。
  無い場合、スクリーンショットを使うテストは自動で飛ばされます。
