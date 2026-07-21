"""Native PySide6 port of export_app.py (§11 of the UI audit): simultaneous
multi-ratio 4K export, a bitrate preset selector, proxy previews, a
disk-space warning gate before starting, and an independent per-ratio
render queue (one ratio can fail while the others keep succeeding).

Architecture parity: mirrors Smart Director's chained-tick pattern via
QTimer instead of a blocking loop, so Pause is honoured within one tick.
"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.eta import EtaEstimator, format_remaining
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout, show_toast
from common.scenes import scene_paths

RATIOS = ["16:9", "9:16", "1:1"]
RATIO_ASPECT = {"16:9": QSize(160, 90), "9:16": QSize(90, 160), "1:1": QSize(120, 120)}
FORMATS = ["MP4", "MOV", "WebM"]
# Resolution tier — deliberately INDEPENDENT of the bitrate preset below, so a
# 4K frame can be exported at a light bitrate (or vice-versa). The factor scales
# the disk estimate; "HD"/"720p" and "Full HD"/"1080p" are the same tier under
# two common names, matching how the client refers to them.
RESOLUTIONS = ["HD", "Full HD", "720p", "1080p", "4K"]
RESOLUTION_FACTOR = {"HD": 0.55, "Full HD": 1.0, "720p": 0.55, "1080p": 1.0, "4K": 2.4}
BITRATE_PRESETS = {
    "YouTube 4K": {"est_gb": 18, "note_key": "note_youtube"},
    "Instagram": {"est_gb": 10, "note_key": "note_instagram"},
    "WhatsApp": {"est_gb": 3, "note_key": "note_whatsapp"},
}
BITRATE_NOTE_KEY = {
    "note_youtube": "exp.bitrate.youtube", "note_instagram": "exp.bitrate.instagram", "note_whatsapp": "exp.bitrate.whatsapp",
}
FREE_DISK_GB = 38
FAIL_RATIO = "9:16"
FAIL_AT = 0.45
TICK_MS = 130

STATUS_TONE = {
    "not_started": "neutral", "queued": "neutral", "rendering": "info",
    "paused": "warning", "complete": "success", "failed": "danger",
}
STATUS_KEY = {
    "not_started": "exp.status.not_started", "queued": "exp.status.queued", "rendering": "exp.status.rendering",
    "paused": "exp.status.paused", "complete": "exp.status.complete", "failed": "exp.status.failed",
}


class ExportScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.scenes = scene_paths()

        self.export_ratios = {r: True for r in RATIOS}
        self.export_format = "MP4"
        self.resolution = "1080p"
        self.bitrate_preset = "YouTube 4K"
        self.burn_in = True
        self.mixdown = True
        self.export_timeline = False
        self.proceed_anyway = False
        self.queue = None
        self.overall_status = "idle"  # idle | running | paused | done
        self._eta = EtaEstimator()
        self._navigator = None  # injected by the shell; opens the Video Editor

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(16)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_settings_card()
        self._build_proxy_section()
        self._build_disk_section()
        self._build_queue_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    def _selected_ratios(self):
        return [r for r in RATIOS if self.export_ratios[r]]

    def _estimated_gb(self):
        base = BITRATE_PRESETS[self.bitrate_preset]["est_gb"] * len(self._selected_ratios())
        return round(base * RESOLUTION_FACTOR[self.resolution])

    # ------------------------------------------------------------------
    def _build_settings_card(self):
        self.settings_card = Card()
        lay = self.settings_card.layout()
        self.settings_title = SectionLabel()
        lay.addWidget(self.settings_title)

        self.ratios_title = QLabel()
        lay.addWidget(self.ratios_title)
        ratio_row = QHBoxLayout()
        self._ratio_checks = {}
        for r in RATIOS:
            cb = QCheckBox(r)
            cb.setChecked(True)
            cb.toggled.connect(lambda checked, ratio=r: self._on_ratio_toggled(ratio, checked))
            ratio_row.addWidget(cb)
            self._ratio_checks[r] = cb
        lay.addLayout(ratio_row)

        row2 = QHBoxLayout()
        col_fmt = QVBoxLayout()
        self.format_label = QLabel()
        col_fmt.addWidget(self.format_label)
        self.format_combo = QComboBox()
        self.format_combo.addItems(FORMATS)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        col_fmt.addWidget(self.format_combo)
        row2.addLayout(col_fmt)

        col_res = QVBoxLayout()
        self.resolution_label = QLabel()
        col_res.addWidget(self.resolution_label)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTIONS)
        self.resolution_combo.setCurrentText(self.resolution)
        self.resolution_combo.currentTextChanged.connect(self._on_resolution_changed)
        col_res.addWidget(self.resolution_combo)
        row2.addLayout(col_res)

        col_bitrate = QVBoxLayout()
        self.bitrate_label = QLabel()
        col_bitrate.addWidget(self.bitrate_label)
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(list(BITRATE_PRESETS.keys()))
        self.bitrate_combo.currentTextChanged.connect(self._on_bitrate_changed)
        col_bitrate.addWidget(self.bitrate_combo)
        row2.addLayout(col_bitrate)
        lay.addLayout(row2)

        self.resolution_note = CaptionLabel()
        lay.addWidget(self.resolution_note)
        self.bitrate_note = CaptionLabel()
        lay.addWidget(self.bitrate_note)

        toggle_row = QHBoxLayout()
        self.burn_in_check = QCheckBox()
        self.burn_in_check.setChecked(True)
        self.burn_in_check.toggled.connect(self._on_burn_in_toggled)
        toggle_row.addWidget(self.burn_in_check)
        self.mixdown_check = QCheckBox()
        self.mixdown_check.setChecked(True)
        self.mixdown_check.toggled.connect(self._on_mixdown_toggled)
        toggle_row.addWidget(self.mixdown_check)
        lay.addLayout(toggle_row)

        # export an editable layered timeline alongside the flattened video
        self.timeline_check = QCheckBox()
        self.timeline_check.setChecked(self.export_timeline)
        self.timeline_check.toggled.connect(self._on_timeline_toggled)
        lay.addWidget(self.timeline_check)
        self.timeline_caption = CaptionLabel()
        lay.addWidget(self.timeline_caption)

        self.outer.addWidget(self.settings_card)

    def _on_resolution_changed(self, value: str):
        self.resolution = value
        self._render_disk()
        self._render_queue()

    def _on_timeline_toggled(self, checked: bool):
        self.export_timeline = checked

    def _on_ratio_toggled(self, ratio: str, checked: bool):
        self.export_ratios[ratio] = checked
        self._render_proxy()
        self._render_disk()

    def _on_format_changed(self, fmt: str):
        self.export_format = fmt

    def _on_bitrate_changed(self, preset: str):
        self.bitrate_preset = preset
        self._render_bitrate_note()
        self._render_disk()

    def _on_burn_in_toggled(self, checked: bool):
        self.burn_in = checked

    def _on_mixdown_toggled(self, checked: bool):
        self.mixdown = checked

    def _render_bitrate_note(self):
        note_key = BITRATE_PRESETS[self.bitrate_preset]["note_key"]
        self.bitrate_note.setText(t(BITRATE_NOTE_KEY[note_key]))

    # ------------------------------------------------------------------
    def _build_proxy_section(self):
        self.proxy_title = SectionLabel()
        self.outer.addWidget(self.proxy_title)
        self.proxy_row = QHBoxLayout()
        self.outer.addLayout(self.proxy_row)
        self.proxy_empty_label = QLabel()
        self.outer.addWidget(self.proxy_empty_label)

    def _render_proxy(self):
        clear_layout(self.proxy_row)
        ratios = self._selected_ratios()
        self.proxy_empty_label.setVisible(not ratios)
        for i, r in enumerate(ratios):
            size = RATIO_ASPECT[r]
            frame = QLabel()
            frame.setFixedSize(size)
            pix = QPixmap(str(self.scenes[i % len(self.scenes)])).scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            frame.setPixmap(pix)
            frame.setStyleSheet("border-radius:10px;")
            col = QVBoxLayout()
            col.addWidget(frame)
            col.addWidget(QLabel(r))
            self.proxy_row.addLayout(col)
        self.proxy_row.addStretch(1)

    # ------------------------------------------------------------------
    def _build_disk_section(self):
        self.disk_label = QLabel()
        self.outer.addWidget(self.disk_label)
        self.disk_warning = QLabel()
        self.disk_warning.setWordWrap(True)
        self.disk_warning.setVisible(False)
        self.outer.addWidget(self.disk_warning)
        self.proceed_check = QCheckBox()
        self.proceed_check.toggled.connect(self._on_proceed_toggled)
        self.proceed_check.setVisible(False)
        self.outer.addWidget(self.proceed_check)

        self.start_btn = QPushButton()
        self.start_btn.setProperty("variant", "primary")
        self.start_btn.clicked.connect(self._start_export)
        self.outer.addWidget(self.start_btn)

        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self._pause_export)
        self.pause_btn.setVisible(False)
        self.outer.addWidget(self.pause_btn)

        self.resume_btn = QPushButton()
        self.resume_btn.setProperty("variant", "primary")
        self.resume_btn.clicked.connect(self._resume_export)
        self.resume_btn.setVisible(False)
        self.outer.addWidget(self.resume_btn)

        done_row = QHBoxLayout()
        self.open_folder_btn = QPushButton()
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.open_folder_btn.setVisible(False)
        done_row.addWidget(self.open_folder_btn)
        self.open_timeline_btn = QPushButton()
        self.open_timeline_btn.clicked.connect(self._open_timeline)
        self.open_timeline_btn.setVisible(False)
        done_row.addWidget(self.open_timeline_btn)
        self.new_export_btn = QPushButton()
        self.new_export_btn.clicked.connect(self._new_export)
        self.new_export_btn.setVisible(False)
        done_row.addWidget(self.new_export_btn)
        self.outer.addLayout(done_row)

    def _open_timeline(self):
        show_toast(self, t("exp.toast.opened_timeline"), dark=self._dark)
        if self._navigator is not None:
            self._navigator("video_editor")

    def _on_proceed_toggled(self, checked: bool):
        self.proceed_anyway = checked
        self._render_disk()

    def _render_disk(self):
        est = self._estimated_gb()
        self.disk_label.setText(t("exp.disk.estimate", size=est, n=len(self._selected_ratios()), free=FREE_DISK_GB))
        over_budget = est > FREE_DISK_GB
        show_warning = over_budget and self.overall_status == "idle"
        self.disk_warning.setVisible(show_warning)
        self.proceed_check.setVisible(show_warning)
        if show_warning:
            self.disk_warning.setText(t("exp.disk.warning", size=est, free=FREE_DISK_GB))

        start_disabled = (not self._selected_ratios()) or (over_budget and not self.proceed_anyway)
        self.start_btn.setEnabled(not start_disabled)

        self.start_btn.setVisible(self.overall_status == "idle")
        self.pause_btn.setVisible(self.overall_status == "running")
        self.resume_btn.setVisible(self.overall_status == "paused")
        self.open_folder_btn.setVisible(self.overall_status == "done")
        self.open_timeline_btn.setVisible(self.overall_status == "done" and self.export_timeline)
        self.new_export_btn.setVisible(self.overall_status == "done")

    # ------------------------------------------------------------------
    def _build_queue_section(self):
        self.queue_title = SectionLabel()
        self.queue_title.setVisible(False)
        self.outer.addWidget(self.queue_title)
        self.queue_eta = CaptionLabel()
        self.queue_eta.setVisible(False)
        self.outer.addWidget(self.queue_eta)
        self.queue_container = QVBoxLayout()
        self.outer.addLayout(self.queue_container)
        self._queue_rows = {}

    def _start_export(self):
        # each ratio carries its own estimator so the queue shows a per-row
        # time-remaining, not only the queue-level total.
        self.queue = {
            r: {"status": "queued", "progress": 0.0, "attempts": 0, "eta": EtaEstimator()}
            for r in self._selected_ratios()
        }
        self.overall_status = "running"
        self._eta.start()
        self._render_disk()
        self._render_queue(rebuild=True)
        self._timer.start()

    def _pause_export(self):
        self.overall_status = "paused"
        self._eta.pause()
        for item in self.queue.values():
            item["eta"].pause()
        self._timer.stop()
        self._render_disk()
        self._render_queue()

    def _resume_export(self):
        self.overall_status = "running"
        self._eta.resume()
        for item in self.queue.values():
            if item["status"] == "rendering":
                item["eta"].resume()
        self._render_disk()
        self._timer.start()

    def _new_export(self):
        self.queue = None
        self.overall_status = "idle"
        self._eta.reset()
        self.queue_title.setVisible(False)
        self.queue_eta.setVisible(False)
        clear_layout(self.queue_container)
        self._render_disk()

    def _open_folder(self):
        show_toast(self, t("exp.toast.opened_folder"), dark=self._dark)

    def _on_tick(self):
        for i, (ratio, item) in enumerate(self.queue.items()):
            if item["status"] == "queued":
                item["status"] = "rendering"
                item["eta"].start()
                continue
            if item["status"] != "rendering":
                continue
            step = 0.05 + i * 0.015
            if ratio == FAIL_RATIO and item["attempts"] == 0:
                item["progress"] = min(FAIL_AT, item["progress"] + step)
                if item["progress"] >= FAIL_AT:
                    item["status"] = "failed"
                    item["attempts"] += 1
                    item["eta"].reset()
                continue
            item["progress"] = min(1.0, item["progress"] + step)
            if item["progress"] >= 1.0:
                item["status"] = "complete"
                item["eta"].reset()

        if all(item["status"] in ("complete", "failed") for item in self.queue.values()):
            self.overall_status = "done"
            self._eta.reset()
            self._timer.stop()
            self._render_disk()

        self._render_queue()

    def _overall_progress(self) -> float:
        # failed items are terminal — they count as "settled" (1.0) for the
        # queue-level estimate so one failure doesn't stall the ETA forever.
        vals = [1.0 if it["status"] in ("complete", "failed") else it["progress"] for it in self.queue.values()]
        return sum(vals) / len(vals) if vals else 0.0

    def _retry_ratio(self, ratio: str):
        self.queue[ratio]["status"] = "queued"
        self.queue[ratio]["progress"] = 0.0
        self.queue[ratio]["eta"].reset()
        self.overall_status = "running"
        self._eta.start()
        self._render_disk()
        self._timer.start()

    def _render_queue(self, rebuild=False):
        if not self.queue:
            self.queue_title.setVisible(False)
            self.queue_eta.setVisible(False)
            clear_layout(self.queue_container)
            return
        self.queue_title.setVisible(True)
        # queue-level time-remaining (not just per-bar %) while actively rendering
        running = self.overall_status == "running"
        self.queue_eta.setVisible(running)
        if running:
            self.queue_eta.setText(format_remaining(self._eta.remaining(self._overall_progress())))
        s = semantic(self._dark)

        if rebuild or set(self._queue_rows.keys()) != set(self.queue.keys()):
            clear_layout(self.queue_container)
            self._queue_rows = {}
            for ratio in self.queue:
                card = Card(margins=(12, 10, 12, 10), spacing=6)
                lay = card.layout()
                head = QHBoxLayout()
                name_label = QLabel()
                head.addWidget(name_label, 1)
                badge = StatusBadge(dark=self._dark)
                head.addWidget(badge)
                lay.addLayout(head)
                progress = QProgressBar()
                progress.setRange(0, 100)
                lay.addWidget(progress)
                row_eta = CaptionLabel()
                row_eta.setVisible(False)
                lay.addWidget(row_eta)
                failed_note = QLabel()
                failed_note.setWordWrap(True)
                failed_note.setVisible(False)
                lay.addWidget(failed_note)
                retry_btn = QPushButton()
                retry_btn.setProperty("variant", "primary")
                retry_btn.setVisible(False)
                retry_btn.clicked.connect(lambda _c=False, r=ratio: self._retry_ratio(r))
                lay.addWidget(retry_btn)
                self.queue_container.addWidget(card)
                self._queue_rows[ratio] = {
                    "name": name_label, "badge": badge, "progress": progress,
                    "row_eta": row_eta, "failed_note": failed_note, "retry_btn": retry_btn,
                }

        for ratio, item in self.queue.items():
            widgets = self._queue_rows[ratio]
            widgets["name"].setText(f"{ratio} · {self.resolution} · {self.export_format} · {self.bitrate_preset}")
            widgets["badge"].setText(t(STATUS_KEY[item["status"]]))
            widgets["badge"].set_tone(STATUS_TONE[item["status"]], self._dark)
            widgets["progress"].setValue(int(item["progress"] * 100))
            row_rendering = item["status"] == "rendering" and self.overall_status == "running"
            widgets["row_eta"].setVisible(row_rendering)
            if row_rendering:
                widgets["row_eta"].setText(format_remaining(item["eta"].remaining(item["progress"])))
            is_failed = item["status"] == "failed"
            widgets["failed_note"].setVisible(is_failed)
            widgets["retry_btn"].setVisible(is_failed)
            if is_failed:
                widgets["failed_note"].setText(t("exp.failed_note", ratio=ratio))
                widgets["failed_note"].setStyleSheet(f"color:{s['danger_fg_strong']};")
                widgets["retry_btn"].setText(t("exp.btn.retry_ratio", ratio=ratio))

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("exp.subtitle"))
        self.settings_title.setText(t("exp.settings.title"))
        self.ratios_title.setText(t("exp.ratios.title"))
        self.format_label.setText(t("exp.format"))
        self.resolution_label.setText(t("exp.resolution"))
        self.resolution_note.setText(t("exp.resolution.note"))
        self.bitrate_label.setText(t("exp.bitrate"))
        self._render_bitrate_note()
        self.burn_in_check.setText(t("exp.burn_in"))
        self.mixdown_check.setText(t("exp.mixdown"))
        self.timeline_check.setText(t("exp.timeline"))
        self.timeline_caption.setText(t("exp.timeline.caption"))

        self.proxy_title.setText(t("exp.proxy.title"))
        self.proxy_empty_label.setText(t("exp.proxy.select_ratio"))
        self._render_proxy()

        self.proceed_check.setText(t("exp.disk.proceed_anyway"))
        self.start_btn.setText(t("exp.btn.start"))
        self.pause_btn.setText(t("exp.btn.pause"))
        self.resume_btn.setText(t("exp.btn.resume"))
        self.open_folder_btn.setText(t("exp.btn.open_folder"))
        self.open_timeline_btn.setText(t("exp.btn.open_timeline"))
        self.new_export_btn.setText(t("exp.btn.new_export"))
        self._render_disk()

        self.queue_title.setText(t("exp.queue.title"))
        self._render_queue()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_navigator(self, on_navigate):
        self._navigator = on_navigate

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_queue()
