"""Character Profile screen — builds a reusable identity profile from
reference videos (e.g. a front-facing take and a turn/profile take). Two
videos are the minimum needed to build a profile; the user can add further
takes beyond that for a stronger identity match. The result can be picked
later as a "Profile Character" elsewhere in the app (see the Motion
Generation screen's Reference Inputs section).

No real video-identity model is wired in: generation is a simulated
queued/processing/complete run on a worker thread, the same QTimer-driven
progress-ramp pattern used by the Demucs tool (audio_layering_screen.py) and
the Lip Sync render preview (lip_sync_screen.py).
"""

import os
import time

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.eta import EtaEstimator, format_remaining
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout
from common.workers import Worker

VIDEO_FILTER = "Video (*.mp4 *.mov *.mkv *.avi)"
MIN_VIDEOS = 2

STATUS_TONE = {"idle": "neutral", "processing": "info", "complete": "success"}
STATUS_KEY = {
    "idle": "charprofile.status.idle",
    "processing": "charprofile.status.processing",
    "complete": "charprofile.status.complete",
}


class CharacterProfileScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._workers = []

        self.videos = [None] * MIN_VIDEOS
        self.status = "idle"
        self._progress = 0.0
        self._eta = EtaEstimator(min_elapsed=0.4)
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._on_tick)

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 4, 4)
        outer.setSpacing(14)

        self.subtitle = CaptionLabel()
        self.subtitle.setWordWrap(True)
        outer.addWidget(self.subtitle)

        card = Card()
        lay = card.layout()

        self.name_label = QLabel()
        lay.addWidget(self.name_label)
        self.name_edit = QLineEdit()
        lay.addWidget(self.name_edit)

        self.videos_title = SectionLabel()
        lay.addWidget(self.videos_title)
        self.videos_hint = CaptionLabel()
        self.videos_hint.setWordWrap(True)
        lay.addWidget(self.videos_hint)

        self.videos_rows = QVBoxLayout()
        self.videos_rows.setSpacing(6)
        lay.addLayout(self.videos_rows)

        self.add_video_btn = QPushButton()
        self.add_video_btn.clicked.connect(self._add_video)
        lay.addWidget(self.add_video_btn)

        outer.addWidget(card)

        status_row = QHBoxLayout()
        self.status_badge = StatusBadge()
        status_row.addWidget(self.status_badge)
        status_row.addStretch(1)
        outer.addLayout(status_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        outer.addWidget(self.progress_bar)
        self.progress_eta = CaptionLabel()
        self.progress_eta.setVisible(False)
        outer.addWidget(self.progress_eta)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setVisible(False)
        outer.addWidget(self.result_label)

        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton()
        self.generate_btn.setProperty("variant", "primary")
        self.generate_btn.clicked.connect(self._start_generate)
        btn_row.addWidget(self.generate_btn)
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self._reset)
        self.reset_btn.setVisible(False)
        btn_row.addWidget(self.reset_btn)
        outer.addLayout(btn_row)

        outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.name_edit.textChanged.connect(self._render)
        self.retranslate()

    # ------------------------------------------------------------------
    def _pick_video(self, idx: int):
        path, _f = QFileDialog.getOpenFileName(self, t("charprofile.video.btn", n=idx + 1), "", VIDEO_FILTER)
        if not path:
            return
        self.videos[idx] = path
        self._render()

    def _add_video(self):
        self.videos.append(None)
        self._render()

    def _remove_video(self, idx: int):
        if len(self.videos) <= MIN_VIDEOS:
            return
        self.videos.pop(idx)
        self._render()

    def _all_videos_selected(self) -> bool:
        return len(self.videos) >= MIN_VIDEOS and all(self.videos)

    def _start_generate(self):
        if not self._all_videos_selected() or self.status == "processing":
            return
        self.status = "processing"
        self._progress = 0.0
        self.progress_bar.setValue(0)
        self.progress_eta.setText(format_remaining(None))
        self._eta.start()
        self._timer.start()
        self._render()

        worker = Worker(lambda: time.sleep(1.2))
        self._workers.append(worker)

        def done(_r=None):
            if worker in self._workers:
                self._workers.remove(worker)
            self._timer.stop()
            self._eta.reset()
            self.status = "complete"
            self._render()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def _on_tick(self):
        self._progress = min(0.95, self._progress + 0.05)
        self.progress_bar.setValue(int(self._progress * 100))
        self.progress_eta.setText(format_remaining(self._eta.remaining(self._progress)))

    def _reset(self):
        self.videos = [None] * MIN_VIDEOS
        self.status = "idle"
        self._progress = 0.0
        self.name_edit.clear()
        self._render()

    # ------------------------------------------------------------------
    def _render_video_rows(self):
        clear_layout(self.videos_rows)
        processing = self.status == "processing"
        for i, path in enumerate(self.videos):
            row = QHBoxLayout()
            name = os.path.basename(path) if path else None
            label = CaptionLabel(t("charprofile.video.selected", name=name) if name else t("charprofile.video.none"))
            row.addWidget(label, 1)
            pick_btn = QPushButton(t("charprofile.video.btn", n=i + 1))
            pick_btn.setEnabled(not processing)
            pick_btn.clicked.connect(lambda _c=False, idx=i: self._pick_video(idx))
            row.addWidget(pick_btn)
            if i >= MIN_VIDEOS:
                remove_btn = QPushButton(t("charprofile.btn.remove_video"))
                remove_btn.setEnabled(not processing)
                remove_btn.clicked.connect(lambda _c=False, idx=i: self._remove_video(idx))
                row.addWidget(remove_btn)
            self.videos_rows.addLayout(row)

    def _render(self):
        s = semantic(self._dark)
        processing = self.status == "processing"

        self._render_video_rows()
        self.add_video_btn.setEnabled(not processing)

        self.status_badge.setText(t(STATUS_KEY[self.status]))
        self.status_badge.set_tone(STATUS_TONE[self.status], self._dark)

        self.progress_bar.setVisible(processing)
        self.progress_eta.setVisible(processing)
        if processing:
            self.progress_bar.setFormat(t("charprofile.processing_text"))

        complete = self.status == "complete"
        self.result_label.setVisible(complete)
        if complete:
            name = self.name_edit.text().strip() or t("charprofile.name.default")
            self.result_label.setText(t("charprofile.result.desc", name=name))
            self.result_label.setStyleSheet(
                f"color:{s['success_fg_strong']}; background:{s['success_bg']}; border-radius:8px; padding:6px 10px;"
            )

        self.generate_btn.setEnabled(self._all_videos_selected() and not processing)
        self.reset_btn.setVisible(complete)

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("charprofile.subtitle"))
        self.name_label.setText(t("charprofile.name.label"))
        self.name_edit.setPlaceholderText(t("charprofile.name.placeholder"))
        self.videos_title.setText(t("charprofile.videos.title"))
        self.videos_hint.setText(t("charprofile.videos.hint"))
        self.add_video_btn.setText(t("charprofile.btn.add_video"))
        self.generate_btn.setText(t("charprofile.btn.generate"))
        self.reset_btn.setText(t("charprofile.btn.reset"))
        self._render()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render()
