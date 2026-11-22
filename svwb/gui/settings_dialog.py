"""設定ダイアログ"""
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QLabel,
                             QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox)

from .. import __version__, obs
from ..config import DATA_DIR


class SettingsDialog(QDialog):
    def __init__(self, parent, settings, db):
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.setWindowTitle("設定")
        form = QFormLayout(self)

        self.title = QLineEdit(settings.window_title)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.2, 5.0)
        self.interval.setSingleStep(0.1)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(settings.interval_sec)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.3, 0.95)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(settings.title_threshold)
        self.confirm = QSpinBox()
        self.confirm.setRange(1, 10)
        self.confirm.setValue(settings.confirm_frames)
        self.collect = QDoubleSpinBox()
        self.collect.setRange(2.0, 20.0)
        self.collect.setSuffix(" 秒")
        self.collect.setValue(settings.collect_sec)
        self.shots = QCheckBox("リザルト画面を保存する")
        self.shots.setChecked(settings.save_screenshots)
        self.notify = QCheckBox("通知を表示する（記録したとき・トレイに隠れたとき）")
        self.notify.setChecked(settings.notify)
        self.shot_limit = QSpinBox()
        self.shot_limit.setRange(0, 100000)
        self.shot_limit.setSingleStep(100)
        self.shot_limit.setSuffix(" 枚")
        self.shot_limit.setSpecialValueText("無制限")
        self.shot_limit.setValue(settings.screenshot_limit)
        self.shot_limit.setToolTip("これを超えたら古いリザルト画面から消します（戦績は消えません）。0 で無制限")
        self.obs = QCheckBox("配信用の表示を書き出す（OBS 用）")
        self.obs.setChecked(settings.obs_enabled)
        self.obs.setToolTip("今日の戦績を data フォルダの obs に書き出します。\n"
                            "bar.html / card.html / minimal.html … OBS のブラウザソース（ローカルファイル）用\n"
                            "today.txt … OBS のテキストソース（ファイルから読み取り）用")
        self.obs_by_deck = QCheckBox("今使っているデッキの戦績だけを出す")
        self.obs_by_deck.setChecked(settings.obs_by_deck)
        self.obs_by_deck.setToolTip("オンにすると、直前の試合のデッキで今日戦った分だけを数えます。
"
                                    "デッキを替えて試合をすると、そのデッキの数字に切り替わります。
"
                                    "オフなら今日の全試合を数えます")
        self.obs_template = QLineEdit(settings.obs_template)
        self.obs_template.setToolTip("使える名前: " + obs.VARIABLES)
        obs_btn = QPushButton("配信用フォルダを開く")
        obs_btn.clicked.connect(self._open_obs)
        self.decks = QPlainTextEdit("\n".join(settings.deck_names))
        self.decks.setPlaceholderText("1行に1デッキ\n例:\n旗\n徒姫無し進化ナイトメア")
        self.decks.setFixedHeight(120)
        import_btn = QPushButton("旧版の戦績を取り込む…")
        import_btn.clicked.connect(self._import)
        open_btn = QPushButton("データフォルダを開く")
        open_btn.clicked.connect(lambda: __import__("os").startfile(DATA_DIR))

        form.addRow("ゲームのウィンドウ名（部分一致）", self.title)
        form.addRow("キャプチャ間隔", self.interval)
        form.addRow("WIN/RESULT 判定のしきい値", self.threshold)
        form.addRow("確定に必要な連続フレーム数", self.confirm)
        form.addRow("サマリー画面を読み続ける時間", self.collect)
        form.addRow("", self.shots)
        form.addRow("残すリザルト画面", self.shot_limit)
        form.addRow("", self.notify)
        form.addRow("", self.obs)
        form.addRow("", self.obs_by_deck)
        form.addRow("配信用テキストの書式", self.obs_template)
        form.addRow("", obs_btn)
        form.addRow("登録デッキ名", self.decks)
        form.addRow("", import_btn)
        form.addRow("", open_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        version = QLabel(f"SVWB Tracker v{__version__}")
        version.setObjectName("muted")
        form.addRow(version, buttons)

    def _save(self):
        s = self.settings
        s.window_title = self.title.text().strip() or s.window_title
        s.interval_sec = self.interval.value()
        s.title_threshold = self.threshold.value()
        s.confirm_frames = self.confirm.value()
        s.collect_sec = self.collect.value()
        s.save_screenshots = self.shots.isChecked()
        s.notify = self.notify.isChecked()
        s.screenshot_limit = self.shot_limit.value()
        s.obs_enabled = self.obs.isChecked()
        s.obs_by_deck = self.obs_by_deck.isChecked()
        s.obs_template = self.obs_template.text() or obs.DEFAULT_TEMPLATE
        names = []
        for line in self.decks.toPlainText().splitlines():
            if line.strip() and line.strip() not in names:
                names.append(line.strip())
        s.deck_names = names
        s.save()
        self.accept()

    def _open_obs(self):
        obs.OBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        __import__("os").startfile(obs.OBS_PATH.parent)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "旧版の matches.db を選択", "", "SQLite (*.db)")
        if not path:
            return
        try:
            n = self.db.import_v1(path)
        except Exception as e:
            QMessageBox.warning(self, "取り込み", f"取り込めませんでした: {e}")
            return
        QMessageBox.information(self, "取り込み", f"{n} 件を取り込みました。")
