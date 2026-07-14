"""Native PySide6 port of lip_sync_app.py (§6 of the UI audit) — a
4-mode lip-sync selector living inside a timeline clip's properties panel.
Per the UX note, changing the mode never re-renders silently: it marks a
pending change until confirmed in a dialog, since a re-render is
expensive. isTalking indicators per character with a re-detect button.
No LatentSync model is wired in — renders and sync preview are simulated,
same scripted "megaphone fails once" demo as the Streamlit source.
"""

from PySide6.QtCore import QSize, Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.audio import samples_to_wav_bytes, synth_tone
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import AudioPlayer, CaptionLabel, SectionLabel, StatusBadge, Waveform, clear_layout, show_toast
from common.style import face_paths
from common.workers import Worker

CHARACTER_NAMES = ["Layla", "Omar"]
MODES = [
    {"key": "natural", "icon": "🗣️", "label_key": "lip.mode.natural", "desc_key": "lip.mode.natural_desc"},
    {"key": "radio", "icon": "📻", "label_key": "lip.mode.radio", "desc_key": "lip.mode.radio_desc"},
    {"key": "phone", "icon": "📱", "label_key": "lip.mode.phone", "desc_key": "lip.mode.phone_desc"},
    {"key": "megaphone", "icon": "📢", "label_key": "lip.mode.megaphone", "desc_key": "lip.mode.megaphone_desc"},
]
MODE_BY_KEY = {m["key"]: m for m in MODES}

CLIPS = [
    {"id": 0, "label": "Scene 3 · 00:12–00:18", "characters": ["Layla"]},
    {"id": 1, "label": "Scene 7 · 01:04–01:11", "characters": ["Omar"]},
    {"id": 2, "label": "Scene 12 · 02:30–02:36", "characters": ["Layla", "Omar"]},
]

STATUS_TONE = {"not_applied": "neutral", "processing": "info", "applied": "success", "failed": "danger"}
STATUS_KEY = {
    "not_applied": "lip.status.not_applied",
    "processing": "lip.status.processing",
    "applied": "lip.status.applied",
    "failed": "lip.status.failed",
}


class ConfirmRerenderDialog(QDialog):
    def __init__(self, current_label: str, target_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("lip.dialog.title"))
        self.setMinimumWidth(380)
        self.confirmed = False
        lay = QVBoxLayout(self)
        warn = QLabel(t("lip.dialog.warning", current=current_label, target=target_label))
        warn.setWordWrap(True)
        lay.addWidget(warn)
        row = QHBoxLayout()
        confirm_btn = QPushButton(t("lip.dialog.confirm"))
        confirm_btn.setProperty("variant", "primary")
        confirm_btn.clicked.connect(self._confirm)
        cancel_btn = QPushButton(t("lip.dialog.cancel"))
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(confirm_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)

    def _confirm(self):
        self.confirmed = True
        self.accept()


class LipSyncScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._workers = []
        self._player = AudioPlayer(self)
        self.faces = face_paths()
        self.selected_clip = 0
        self.redetect_counter = 0
        self.clips = {
            0: {"applied_mode": "natural", "pending_mode": None, "status": "applied", "talking": {"Layla": True}, "attempts": {}},
            1: {"applied_mode": None, "pending_mode": None, "status": "not_applied", "talking": {"Omar": False}, "attempts": {}},
            2: {"applied_mode": None, "pending_mode": None, "status": "not_applied", "talking": {"Layla": True, "Omar": False}, "attempts": {}},
        }

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(14)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        top_row = QHBoxLayout()
        self.clip_label = QLabel()
        top_row.addWidget(self.clip_label)
        self.clip_combo = QComboBox()
        self.clip_combo.addItems([self._clip_label(c) for c in CLIPS])
        self.clip_combo.currentIndexChanged.connect(self._on_clip_changed)
        top_row.addWidget(self.clip_combo, 1)
        self.status_badge = StatusBadge()
        top_row.addWidget(self.status_badge)
        self.outer.addLayout(top_row)

        self.outer.addWidget(self._hr())

        self.talking_title = SectionLabel()
        self.outer.addWidget(self.talking_title)
        self.talking_desc = CaptionLabel()
        self.outer.addWidget(self.talking_desc)
        self.talking_row = QHBoxLayout()
        self.outer.addLayout(self.talking_row)

        self.outer.addWidget(self._hr())

        self.mode_title = SectionLabel()
        self.outer.addWidget(self.mode_title)
        self.mode_row = QHBoxLayout()
        self.outer.addLayout(self.mode_row)

        self.pending_note = QLabel()
        self.pending_note.setWordWrap(True)
        self.pending_note.setVisible(False)
        self.outer.addWidget(self.pending_note)
        self.apply_btn = QPushButton()
        self.apply_btn.setProperty("variant", "primary")
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.apply_btn.setVisible(False)
        self.outer.addWidget(self.apply_btn)

        self.failed_desc = QLabel()
        self.failed_desc.setWordWrap(True)
        self.failed_desc.setVisible(False)
        self.outer.addWidget(self.failed_desc)
        self.retry_btn = QPushButton()
        self.retry_btn.setProperty("variant", "primary")
        self.retry_btn.clicked.connect(self._on_retry_clicked)
        self.retry_btn.setVisible(False)
        self.outer.addWidget(self.retry_btn)

        self.outer.addWidget(self._hr())

        self.preview_title = SectionLabel()
        self.outer.addWidget(self.preview_title)
        preview_row = QHBoxLayout()
        self.preview_img = QLabel()
        self.preview_img.setFixedSize(QSize(140, 140))
        preview_row.addWidget(self.preview_img)
        preview_info = QVBoxLayout()
        self.preview_status_label = QLabel()
        self.preview_status_label.setWordWrap(True)
        preview_info.addWidget(self.preview_status_label)
        self.preview_play_btn = QPushButton()
        self.preview_play_btn.clicked.connect(self._play_preview)
        preview_info.addWidget(self.preview_play_btn)
        preview_row.addLayout(preview_info, 1)
        self.outer.addLayout(preview_row)

        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()
        self._render()

    @staticmethod
    def _hr():
        from PySide6.QtWidgets import QFrame

        line = QFrame()
        line.setFixedHeight(1)
        line.setProperty("role", "divider")
        return line

    @staticmethod
    def _clip_label(clip: dict) -> str:
        return f"{clip['label']} ({' + '.join(clip['characters'])})"

    def _on_clip_changed(self, index: int):
        self.selected_clip = index
        self._render()

    # ------------------------------------------------------------------
    def _current_clip(self) -> dict:
        return CLIPS[self.selected_clip]

    def _current_state(self) -> dict:
        return self.clips[self._current_clip()["id"]]

    def _render(self):
        clip_id = self._current_clip()["id"]
        clip = self.clips[clip_id]
        characters = self._current_clip()["characters"]
        s = semantic(self._dark)

        self.status_badge.setText(t(STATUS_KEY[clip["status"]]))
        self.status_badge.set_tone(STATUS_TONE[clip["status"]], self._dark)

        # isTalking row
        clear_layout(self.talking_row)
        for name in characters:
            char_idx = CHARACTER_NAMES.index(name)
            col = QVBoxLayout()
            img = QLabel()
            pix = QPixmap(str(self.faces[char_idx % len(self.faces)]))
            img.setPixmap(pix.scaled(QSize(90, 90), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            img.setFixedSize(90, 90)
            img.setScaledContents(True)
            col.addWidget(img)
            talking = clip["talking"].get(name, False)
            badge = StatusBadge(t("lip.talking") if talking else t("lip.silent"), tone="success" if talking else "neutral", dark=self._dark)
            name_label = QLabel(name)
            col.addWidget(name_label)
            col.addWidget(badge)
            self.talking_row.addLayout(col)
        redetect_btn = QPushButton(t("lip.btn.redetect"))
        redetect_btn.clicked.connect(self._redetect)
        self.talking_row.addWidget(redetect_btn)
        self.talking_row.addStretch(1)

        # mode selector
        clear_layout(self.mode_row)
        for mode in MODES:
            col = QVBoxLayout()
            is_current = clip["pending_mode"] == mode["key"] or (clip["pending_mode"] is None and clip["applied_mode"] == mode["key"])
            btn = QPushButton(f"{mode['icon']} {t(mode['label_key'])}")
            btn.setProperty("variant", "primary" if is_current else "")
            btn.clicked.connect(lambda _c=False, k=mode["key"]: self._select_mode(k))
            col.addWidget(btn)
            desc = CaptionLabel(t(mode["desc_key"]))
            col.addWidget(desc)
            self.mode_row.addLayout(col)

        pending = clip["pending_mode"]
        if pending and pending != clip["applied_mode"]:
            applied_label = t(MODE_BY_KEY[clip["applied_mode"]]["label_key"]) if clip["applied_mode"] else t("lip.none")
            self.pending_note.setText(t("lip.pending_note", pending=t(MODE_BY_KEY[pending]["label_key"]), applied=applied_label))
            self.pending_note.setVisible(True)
            self.apply_btn.setVisible(True)
        else:
            self.pending_note.setVisible(False)
            self.apply_btn.setVisible(False)

        if clip["status"] == "failed":
            mode_label = t(MODE_BY_KEY[clip["pending_mode"]]["label_key"])
            self.failed_desc.setText(t("lip.failed_desc", mode=mode_label))
            self.failed_desc.setStyleSheet(f"color:{s['danger_fg_strong']};")
            self.failed_desc.setVisible(True)
            self.retry_btn.setVisible(True)
        else:
            self.failed_desc.setVisible(False)
            self.retry_btn.setVisible(False)

        # sync preview
        main_char = characters[0]
        self.preview_img.setPixmap(
            QPixmap(str(self.faces[CHARACTER_NAMES.index(main_char) % len(self.faces)])).scaled(
                self.preview_img.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
        )
        self.preview_img.setScaledContents(True)
        if clip["status"] == "applied":
            self.preview_status_label.setText(t("lip.preview.synced", mode=t(MODE_BY_KEY[clip["applied_mode"]]["label_key"])))
            self.preview_status_label.setStyleSheet(f"color:{s['success_fg_strong']};")
            self.preview_play_btn.setVisible(True)
        elif clip["status"] == "processing":
            self.preview_status_label.setText(t("lip.preview.rendering"))
            self.preview_status_label.setStyleSheet("")
            self.preview_play_btn.setVisible(False)
        elif clip["status"] == "failed":
            self.preview_status_label.setText(t("lip.preview.failed"))
            self.preview_status_label.setStyleSheet(f"color:{s['warning_fg_strong']};")
            self.preview_play_btn.setVisible(False)
        else:
            self.preview_status_label.setText(t("lip.preview.not_applied"))
            self.preview_status_label.setStyleSheet("")
            self.preview_play_btn.setVisible(False)

    def _redetect(self):
        self.redetect_counter += 1
        clip = self._current_state()
        characters = self._current_clip()["characters"]
        seed = self.redetect_counter + self._current_clip()["id"]
        for i, name in enumerate(characters):
            clip["talking"][name] = bool((seed + i) % 2)
        self._render()

    def _select_mode(self, mode_key: str):
        self._current_state()["pending_mode"] = mode_key
        self._render()

    def _on_apply_clicked(self):
        clip = self._current_state()
        current_label = t(MODE_BY_KEY[clip["applied_mode"]]["label_key"]) if clip["applied_mode"] else t("lip.none")
        target_label = t(MODE_BY_KEY[clip["pending_mode"]]["label_key"])
        dlg = ConfirmRerenderDialog(current_label, target_label, self)
        if dlg.exec() == QDialog.Accepted and dlg.confirmed:
            self._run_render(clip["pending_mode"])

    def _on_retry_clicked(self):
        clip = self._current_state()
        self._run_render(clip["pending_mode"])

    def _run_render(self, mode: str):
        clip = self._current_state()
        clip["status"] = "processing"
        self._render()

        worker = Worker(lambda: __import__("time").sleep(1.0))
        self._workers.append(worker)

        def done(_r=None):
            if worker in self._workers:
                self._workers.remove(worker)
            attempts = clip["attempts"].get(mode, 0)
            if mode == "megaphone" and attempts == 0:
                clip["status"] = "failed"
                clip["pending_mode"] = mode
                clip["attempts"][mode] = attempts + 1
            else:
                clip["applied_mode"] = mode
                clip["pending_mode"] = None
                clip["status"] = "applied"
                clip["attempts"][mode] = attempts + 1
            self._render()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def _play_preview(self):
        samples = synth_tone([220, 246, 220, 196], duration_each=0.18)
        self._player.play_bytes(samples_to_wav_bytes(samples))

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("lip.subtitle"))
        self.clip_label.setText(t("lip.clip.label"))
        self.talking_title.setText(t("lip.talking.title"))
        self.talking_desc.setText(t("lip.talking.desc"))
        self.mode_title.setText(t("lip.mode.title"))
        self.apply_btn.setText(t("lip.btn.apply"))
        self.retry_btn.setText(t("lip.btn.retry_render"))
        self.preview_title.setText(t("lip.preview.title"))
        self.preview_play_btn.setText(t("lip.btn.play_preview"))
        idx = self.clip_combo.currentIndex()
        self.clip_combo.blockSignals(True)
        self.clip_combo.clear()
        self.clip_combo.addItems([self._clip_label(c) for c in CLIPS])
        self.clip_combo.setCurrentIndex(max(0, idx))
        self.clip_combo.blockSignals(False)
        self._render()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render()
