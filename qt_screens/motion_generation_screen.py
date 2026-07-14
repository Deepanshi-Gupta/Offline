"""Native PySide6 port of motion_generation_app.py (§9 of the UI audit) —
explicitly scoped "Minimal UI (mostly backend)" per the audit doc. Only
camera-effect, body-motion, and cinematic-FX are real controls; era-motion
and BIE are read-only status lines (never exposed as controls), and the
GPU queue / quality-guard drift-and-autofix are simulated status/timing,
same scripted demo scene as the Streamlit source.
"""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, repolish

NUM_SCENES = 14
CAMERA_EFFECTS = [
    ("pan", "motion.camera.pan"),
    ("zoom", "motion.camera.zoom"),
    ("dolly", "motion.camera.dolly"),
    ("rack_focus", "motion.camera.rack_focus"),
]
FX_OPTIONS = [("smoke", "motion.fx.smoke"), ("haze", "motion.fx.haze"), ("explosions", "motion.fx.explosions")]
QUALITY_GUARD_DEMO_SCENE = 6  # Scene 7

STATUS_TONE = {
    "not_animated": "neutral", "queued": "neutral", "generating": "info",
    "quality_check": "warning", "complete": "success",
}
STATUS_KEY = {
    "not_animated": "motion.status.not_animated", "queued": "motion.status.queued",
    "generating": "motion.status.generating", "quality_check": "motion.status.quality_check",
    "complete": "motion.status.complete",
}
TICK_MS = 140


class MotionGenerationScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.selected_scene = 0
        self.scenes = {
            i: {"status": "not_animated", "camera_effect": "pan", "body_motion": True, "fx": set(), "quality_note": None, "_jobs_ahead": 0, "_progress": 0.0}
            for i in range(NUM_SCENES)
        }

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._active_scene = None
        self._phase = None  # "queued" | "generating" | "quality_check"

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 4, 4)
        outer.setSpacing(14)

        self.subtitle = CaptionLabel()
        outer.addWidget(self.subtitle)

        top_row = QHBoxLayout()
        self.scene_label = QLabel()
        top_row.addWidget(self.scene_label)
        self.scene_combo = QComboBox()
        self.scene_combo.addItems([t("motion.scene", n=i + 1) for i in range(NUM_SCENES)])
        self.scene_combo.currentIndexChanged.connect(self._on_scene_changed)
        top_row.addWidget(self.scene_combo, 1)
        self.status_badge = StatusBadge()
        top_row.addWidget(self.status_badge)
        outer.addLayout(top_row)

        self.queue_progress = QProgressBar()
        self.queue_progress.setRange(0, 100)
        self.queue_progress.setVisible(False)
        outer.addWidget(self.queue_progress)

        card = Card()
        lay = card.layout()

        self.camera_title = SectionLabel()
        lay.addWidget(self.camera_title)
        cam_row = QHBoxLayout()
        self._camera_buttons = {}
        for key, label_key in CAMERA_EFFECTS:
            btn = QPushButton()
            btn.clicked.connect(lambda _c=False, k=key: self._set_camera_effect(k))
            cam_row.addWidget(btn)
            self._camera_buttons[key] = btn
        lay.addLayout(cam_row)

        body_row = QHBoxLayout()
        self.body_motion_check = QCheckBox()
        self.body_motion_check.setChecked(True)
        self.body_motion_check.toggled.connect(self._on_body_motion_toggled)
        body_row.addWidget(self.body_motion_check)
        self.body_motion_desc = CaptionLabel()
        body_row.addWidget(self.body_motion_desc, 1)
        lay.addLayout(body_row)

        self.fx_title = SectionLabel()
        lay.addWidget(self.fx_title)
        fx_row = QHBoxLayout()
        self._fx_checks = {}
        for key, label_key in FX_OPTIONS:
            cb = QCheckBox()
            cb.toggled.connect(lambda checked, k=key: self._on_fx_toggled(k, checked))
            fx_row.addWidget(cb)
            self._fx_checks[key] = cb
        lay.addLayout(fx_row)
        outer.addWidget(card)

        self.auto_title = SectionLabel()
        outer.addWidget(self.auto_title)
        self.auto_note = QLabel()
        self.auto_note.setWordWrap(True)
        outer.addWidget(self.auto_note)
        self.quality_note_label = QLabel()
        self.quality_note_label.setWordWrap(True)
        self.quality_note_label.setVisible(False)
        outer.addWidget(self.quality_note_label)

        self.generate_btn = QPushButton()
        self.generate_btn.setProperty("variant", "primary")
        self.generate_btn.clicked.connect(self._start_generate)
        outer.addWidget(self.generate_btn)

        outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    # ------------------------------------------------------------------
    def _current_scene(self) -> dict:
        return self.scenes[self.selected_scene]

    def _on_scene_changed(self, index: int):
        self.selected_scene = index
        self._render()

    def _set_camera_effect(self, key: str):
        self._current_scene()["camera_effect"] = key
        self._render()

    def _on_body_motion_toggled(self, checked: bool):
        self._current_scene()["body_motion"] = checked

    def _on_fx_toggled(self, key: str, checked: bool):
        fx = self._current_scene()["fx"]
        if checked:
            fx.add(key)
        else:
            fx.discard(key)

    # ------------------------------------------------------------------
    # generation simulation (QTimer-driven, same pattern as other screens)
    # ------------------------------------------------------------------
    def _start_generate(self):
        scene_idx = self.selected_scene
        scene = self.scenes[scene_idx]
        scene["_jobs_ahead"] = (scene_idx % 3) + 1
        scene["status"] = "queued"
        scene["_progress"] = 0.0
        scene["quality_note"] = None
        self._active_scene = scene_idx
        self._phase = "queued"
        self.generate_btn.setEnabled(False)
        self._render()
        self._timer.start()

    def _on_tick(self):
        idx = self._active_scene
        if idx is None:
            self._timer.stop()
            return
        scene = self.scenes[idx]

        if self._phase == "queued":
            scene["_jobs_ahead"] -= 1
            if scene["_jobs_ahead"] <= 0:
                self._phase = "generating"
                scene["status"] = "generating"
                scene["_progress"] = 0.0
        elif self._phase == "generating":
            scene["_progress"] = min(1.0, scene["_progress"] + 0.18)
            if scene["_progress"] >= 1.0:
                if idx == QUALITY_GUARD_DEMO_SCENE:
                    self._phase = "quality_check"
                    scene["status"] = "quality_check"
                else:
                    scene["quality_note"] = t("motion.quality.none")
                    self._finish_generation(scene)
        elif self._phase == "quality_check":
            scene["quality_note"] = t("motion.quality.drift")
            self._finish_generation(scene)

        if self.selected_scene == idx:
            self._render()

    def _finish_generation(self, scene: dict):
        scene["status"] = "complete"
        self._timer.stop()
        self._active_scene = None
        self._phase = None
        self.generate_btn.setEnabled(True)

    # ------------------------------------------------------------------
    def _render(self):
        scene = self._current_scene()
        s = semantic(self._dark)

        self.status_badge.setText(t(STATUS_KEY[scene["status"]]))
        self.status_badge.set_tone(STATUS_TONE[scene["status"]], self._dark)

        is_active_scene = self._active_scene == self.selected_scene
        if scene["status"] == "queued" and is_active_scene:
            self.queue_progress.setVisible(True)
            self.queue_progress.setFormat(t("motion.gpu_wait", n=max(0, scene["_jobs_ahead"])))
            self.queue_progress.setValue(30)
        elif scene["status"] == "generating" and is_active_scene:
            self.queue_progress.setVisible(True)
            self.queue_progress.setFormat(t("motion.generating_text"))
            self.queue_progress.setValue(int(scene["_progress"] * 100))
        else:
            self.queue_progress.setVisible(False)

        for key, btn in self._camera_buttons.items():
            btn.setProperty("variant", "primary" if scene["camera_effect"] == key else "")
            repolish(btn)

        self.body_motion_check.blockSignals(True)
        self.body_motion_check.setChecked(scene["body_motion"])
        self.body_motion_check.blockSignals(False)

        for key, cb in self._fx_checks.items():
            cb.blockSignals(True)
            cb.setChecked(key in scene["fx"])
            cb.blockSignals(False)

        era_status = t("motion.auto.applied") if scene["status"] == "complete" else (
            t("motion.auto.applying") if scene["status"] == "generating" else t("motion.auto.dash")
        )
        bie_status = t("motion.auto.applied") if scene["status"] == "complete" else (
            t("motion.auto.running") if scene["status"] == "generating" else t("motion.auto.dash")
        )
        self.auto_note.setText(
            f"{t('motion.auto.era')} {era_status} — {t('motion.auto.era_note')}\n"
            f"{t('motion.auto.bie')} {bie_status} — {t('motion.auto.bie_note')}"
        )
        self.auto_note.setStyleSheet(f"background:{s['surface_soft']}; border:1px dashed {s['border']}; border-radius:10px; padding:8px 10px; color:{s['ink_soft']}; font-size:11.5px;")

        if scene["status"] == "quality_check":
            self.quality_note_label.setText(t("motion.quality.banner"))
            self.quality_note_label.setStyleSheet(f"color:{s['warning_fg_strong']}; background:{s['warning_bg']}; border-radius:8px; padding:6px 10px;")
            self.quality_note_label.setVisible(True)
        elif scene["quality_note"]:
            icon = "🛡️" if scene["quality_note"] == t("motion.quality.drift") else "✓"
            self.quality_note_label.setText(f"{icon} {t('motion.quality.title')} {scene['quality_note']}")
            self.quality_note_label.setStyleSheet(f"background:{s['surface_soft']}; border:1px dashed {s['border']}; border-radius:10px; padding:8px 10px; color:{s['ink_soft']}; font-size:11.5px;")
            self.quality_note_label.setVisible(True)
        else:
            self.quality_note_label.setVisible(False)

        self.generate_btn.setEnabled(self._active_scene is None)

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("motion.subtitle"))
        self.scene_label.setText(t("motion.scene.label"))
        idx = self.scene_combo.currentIndex()
        self.scene_combo.blockSignals(True)
        self.scene_combo.clear()
        self.scene_combo.addItems([t("motion.scene", n=i + 1) for i in range(NUM_SCENES)])
        self.scene_combo.setCurrentIndex(max(0, idx))
        self.scene_combo.blockSignals(False)

        self.camera_title.setText(t("motion.camera.title"))
        for key, btn in self._camera_buttons.items():
            label_key = next(lk for k, lk in CAMERA_EFFECTS if k == key)
            btn.setText(t(label_key))
        self.body_motion_check.setText(t("motion.body_motion"))
        self.body_motion_desc.setText(t("motion.body_motion.desc"))
        self.fx_title.setText(t("motion.fx.title"))
        for key, cb in self._fx_checks.items():
            label_key = next(lk for k, lk in FX_OPTIONS if k == key)
            cb.setText(t(label_key))

        self.auto_title.setText(t("motion.auto.title"))
        self.generate_btn.setText(t("motion.btn.generate"))
        self._render()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render()
