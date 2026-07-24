"""Native PySide6 port of motion_generation_app.py (§9 of the UI audit) —
explicitly scoped "Minimal UI (mostly backend)" per the audit doc. Only
camera-effect, body-motion, and cinematic-FX are real controls; era-motion
and BIE are read-only status lines (never exposed as controls), and the
GPU queue / quality-guard drift-and-autofix are simulated status/timing,
same scripted demo scene as the Streamlit source.
"""

import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.characters import character_registry
from common.compliance import compliance_activity
from common.eta import EtaEstimator, format_remaining
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, ComplianceActivityIndicator, SectionLabel, StatusBadge, repolish

NUM_SCENES = 14
CAMERA_EFFECTS = [
    ("pan", "motion.camera.pan"),
    ("zoom", "motion.camera.zoom"),
    ("dolly", "motion.camera.dolly"),
    ("rack_focus", "motion.camera.rack_focus"),
]
FX_OPTIONS = [("smoke", "motion.fx.smoke"), ("haze", "motion.fx.haze"), ("explosions", "motion.fx.explosions")]
# Camera effects are combinable (multi-select); Zoom carries a speed variant.
ZOOM_SPEEDS = [("slow", "motion.camera.zoom.slow"), ("medium", "motion.camera.zoom.medium"), ("fast", "motion.camera.zoom.fast")]
GEN_MODES = [("i2v", "motion.genmode.i2v"), ("t2v", "motion.genmode.t2v")]
DURATION_MODES = [
    ("manual", "motion.duration.mode.manual"),
    ("auto_voice", "motion.duration.mode.auto_voice"),
    ("loop_voice", "motion.duration.mode.loop_voice"),
]
TV_SOURCES = [("loop", "motion.tv.source.loop"), ("static", "motion.tv.source.static")]
DURATION_MIN, DURATION_MAX, DURATION_DEFAULT = 1.0, 15.0, 4.0  # 3–5s recommended, 1–15s manual
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
            i: {
                "status": "not_animated",
                "camera_effects": {"pan"},  # multi-select / combinable
                "zoom_speed": "medium",
                "gen_mode": "i2v",
                "duration_mode": "manual",
                "duration_s": DURATION_DEFAULT,
                "tv_bg": False,
                "tv_source": "loop",
                "body_motion": True,
                "fx": set(),
                "ref_image_path": None,
                "ref_audio_path": None,
                "profile_character": None,
                "quality_note": None,
                "_jobs_ahead": 0,
                "_progress": 0.0,
            }
            for i in range(NUM_SCENES)
        }

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._active_scene = None
        self._phase = None  # "queued" | "generating" | "quality_check"
        self._eta = EtaEstimator()

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
        self.queue_eta = CaptionLabel()
        self.queue_eta.setVisible(False)
        outer.addWidget(self.queue_eta)
        compliance_row = QHBoxLayout()
        self.compliance_indicator = ComplianceActivityIndicator()
        self.compliance_indicator.setVisible(False)
        compliance_row.addWidget(self.compliance_indicator)
        compliance_row.addStretch(1)
        outer.addLayout(compliance_row)

        card = Card()
        lay = card.layout()

        # ---- reference inputs (image / audio) + profile character ----
        self.reference_title = SectionLabel()
        lay.addWidget(self.reference_title)

        ref_img_row = QHBoxLayout()
        self.ref_image_label = CaptionLabel()
        ref_img_row.addWidget(self.ref_image_label, 1)
        self.ref_image_btn = QPushButton()
        self.ref_image_btn.clicked.connect(self._pick_reference_image)
        ref_img_row.addWidget(self.ref_image_btn)
        self.ref_image_clear_btn = QPushButton()
        self.ref_image_clear_btn.clicked.connect(self._clear_reference_image)
        ref_img_row.addWidget(self.ref_image_clear_btn)
        lay.addLayout(ref_img_row)

        ref_audio_row = QHBoxLayout()
        self.ref_audio_label = CaptionLabel()
        ref_audio_row.addWidget(self.ref_audio_label, 1)
        self.ref_audio_btn = QPushButton()
        self.ref_audio_btn.clicked.connect(self._pick_reference_audio)
        ref_audio_row.addWidget(self.ref_audio_btn)
        self.ref_audio_clear_btn = QPushButton()
        self.ref_audio_clear_btn.clicked.connect(self._clear_reference_audio)
        ref_audio_row.addWidget(self.ref_audio_clear_btn)
        lay.addLayout(ref_audio_row)

        profile_row = QHBoxLayout()
        self.profile_char_label = CaptionLabel()
        profile_row.addWidget(self.profile_char_label)
        self.profile_char_combo = QComboBox()
        self.profile_char_combo.currentIndexChanged.connect(self._on_profile_character_changed)
        profile_row.addWidget(self.profile_char_combo, 1)
        lay.addLayout(profile_row)
        self.profile_char_hint = CaptionLabel()
        self.profile_char_hint.setWordWrap(True)
        lay.addWidget(self.profile_char_hint)

        # ---- generation mode: Image-to-Video vs Text-to-Video ----
        self.genmode_title = SectionLabel()
        lay.addWidget(self.genmode_title)
        genmode_row = QHBoxLayout()
        self._genmode_buttons = {}
        for key, label_key in GEN_MODES:
            btn = QPushButton()
            btn.clicked.connect(lambda _c=False, k=key: self._set_gen_mode(k))
            genmode_row.addWidget(btn)
            self._genmode_buttons[key] = btn
        genmode_row.addStretch(1)
        lay.addLayout(genmode_row)
        self.genmode_caption = CaptionLabel()
        lay.addWidget(self.genmode_caption)

        # ---- animation duration ----
        self.duration_title = SectionLabel()
        lay.addWidget(self.duration_title)
        dur_row = QHBoxLayout()
        self.duration_combo = QComboBox()
        self.duration_combo.addItems([t(lk) for _k, lk in DURATION_MODES])
        self.duration_combo.currentIndexChanged.connect(self._on_duration_mode_changed)
        dur_row.addWidget(self.duration_combo)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(DURATION_MIN, DURATION_MAX)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setValue(DURATION_DEFAULT)
        self.duration_spin.setSuffix(" s")
        self.duration_spin.valueChanged.connect(self._on_duration_value_changed)
        dur_row.addWidget(self.duration_spin)
        dur_row.addStretch(1)
        lay.addLayout(dur_row)
        self.duration_caption = CaptionLabel()
        self.duration_caption.setWordWrap(True)
        lay.addWidget(self.duration_caption)

        # ---- camera effect (multi-select / combinable) ----
        self.camera_title = SectionLabel()
        lay.addWidget(self.camera_title)
        self.camera_hint = CaptionLabel()
        lay.addWidget(self.camera_hint)
        cam_row = QHBoxLayout()
        self._camera_buttons = {}
        for key, label_key in CAMERA_EFFECTS:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c=False, k=key: self._toggle_camera_effect(k))
            cam_row.addWidget(btn)
            self._camera_buttons[key] = btn
        cam_row.addStretch(1)
        lay.addLayout(cam_row)

        # zoom speed variant — visible only while Zoom is selected
        self.zoom_speed_container = QWidget()
        zoom_row = QHBoxLayout(self.zoom_speed_container)
        zoom_row.setContentsMargins(0, 0, 0, 0)
        self.zoom_speed_label = CaptionLabel()
        zoom_row.addWidget(self.zoom_speed_label)
        self._zoom_speed_buttons = {}
        for key, label_key in ZOOM_SPEEDS:
            btn = QPushButton()
            btn.clicked.connect(lambda _c=False, k=key: self._set_zoom_speed(k))
            zoom_row.addWidget(btn)
            self._zoom_speed_buttons[key] = btn
        zoom_row.addStretch(1)
        self.zoom_speed_container.setVisible(False)
        lay.addWidget(self.zoom_speed_container)

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

        # ---- embedded screen / TV background (6-B-1) ----
        self.tv_title = SectionLabel()
        lay.addWidget(self.tv_title)
        self.tv_check = QCheckBox()
        self.tv_check.toggled.connect(self._on_tv_toggled)
        lay.addWidget(self.tv_check)
        self.tv_desc = CaptionLabel()
        self.tv_desc.setWordWrap(True)
        lay.addWidget(self.tv_desc)
        self.tv_source_container = QWidget()
        tv_src_row = QHBoxLayout(self.tv_source_container)
        tv_src_row.setContentsMargins(0, 0, 0, 0)
        self.tv_source_label = CaptionLabel()
        tv_src_row.addWidget(self.tv_source_label)
        self.tv_source_combo = QComboBox()
        self.tv_source_combo.addItems([t(lk) for _k, lk in TV_SOURCES])
        self.tv_source_combo.currentIndexChanged.connect(self._on_tv_source_changed)
        tv_src_row.addWidget(self.tv_source_combo)
        tv_src_row.addStretch(1)
        self.tv_source_container.setVisible(False)
        lay.addWidget(self.tv_source_container)

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
        character_registry.changed.connect(self._refresh_profile_combo)
        self.retranslate()

    # ------------------------------------------------------------------
    def _current_scene(self) -> dict:
        return self.scenes[self.selected_scene]

    def _on_scene_changed(self, index: int):
        self.selected_scene = index
        self._render()

    def _toggle_camera_effect(self, key: str):
        effects = self._current_scene()["camera_effects"]
        effects.symmetric_difference_update({key})
        self._render()

    def _set_zoom_speed(self, key: str):
        self._current_scene()["zoom_speed"] = key
        self._render()

    def _set_gen_mode(self, key: str):
        self._current_scene()["gen_mode"] = key
        self._render()

    def _on_duration_mode_changed(self, index: int):
        self._current_scene()["duration_mode"] = DURATION_MODES[index][0]
        self._render()

    def _on_duration_value_changed(self, value: float):
        self._current_scene()["duration_s"] = round(value, 1)
        self._render()

    def _on_tv_toggled(self, checked: bool):
        self._current_scene()["tv_bg"] = checked
        self._render()

    def _on_tv_source_changed(self, index: int):
        self._current_scene()["tv_source"] = TV_SOURCES[index][0]

    def _on_body_motion_toggled(self, checked: bool):
        self._current_scene()["body_motion"] = checked

    def _on_fx_toggled(self, key: str, checked: bool):
        fx = self._current_scene()["fx"]
        if checked:
            fx.add(key)
        else:
            fx.discard(key)

    # ------------------------------------------------------------------
    # reference inputs (image / audio) + profile character
    # ------------------------------------------------------------------
    def _pick_reference_image(self):
        path, _f = QFileDialog.getOpenFileName(self, t("motion.reference.image.btn"), "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._current_scene()["ref_image_path"] = path
            self._render()

    def _clear_reference_image(self):
        self._current_scene()["ref_image_path"] = None
        self._render()

    def _pick_reference_audio(self):
        path, _f = QFileDialog.getOpenFileName(self, t("motion.reference.audio.btn"), "", "Audio (*.wav *.mp3 *.m4a *.flac *.ogg)")
        if path:
            self._current_scene()["ref_audio_path"] = path
            self._render()

    def _clear_reference_audio(self):
        self._current_scene()["ref_audio_path"] = None
        self._render()

    def _on_profile_character_changed(self, index: int):
        names = character_registry.names()
        self._current_scene()["profile_character"] = names[index - 1] if index > 0 else None

    def _refresh_profile_combo(self):
        scene = self._current_scene()
        names = character_registry.names()
        self.profile_char_combo.blockSignals(True)
        self.profile_char_combo.clear()
        self.profile_char_combo.addItem(t("motion.reference.profile.none"))
        self.profile_char_combo.addItems(names)
        current = scene["profile_character"]
        self.profile_char_combo.setCurrentIndex(names.index(current) + 1 if current in names else 0)
        self.profile_char_combo.blockSignals(False)
        self.profile_char_hint.setText(t("motion.reference.profile.hint") if names else t("motion.reference.profile.empty_hint"))

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
                self._eta.start()
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
            # quality-guard detected drift and auto-fixed it — a silent
            # correction the session indicator surfaces (B3)
            scene["quality_note"] = t("motion.quality.drift")
            compliance_activity.record(1)
            self._finish_generation(scene)

        if self.selected_scene == idx:
            self._render()

    def _finish_generation(self, scene: dict):
        scene["status"] = "complete"
        self._eta.reset()
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

        # session compliance-activity indicator: during generation, and after
        # once any auto-correction has happened this session
        self.compliance_indicator.setVisible(self._active_scene is not None or compliance_activity.count > 0)

        is_active_scene = self._active_scene == self.selected_scene
        if scene["status"] == "queued" and is_active_scene:
            self.queue_progress.setVisible(True)
            self.queue_progress.setFormat(t("motion.gpu_wait", n=max(0, scene["_jobs_ahead"])))
            self.queue_progress.setValue(30)
        elif scene["status"] == "generating" and is_active_scene:
            self.queue_progress.setVisible(True)
            self.queue_progress.setFormat(t("motion.generating_text"))
            self.queue_progress.setValue(int(scene["_progress"] * 100))
            self.queue_eta.setVisible(True)
            self.queue_eta.setText(format_remaining(self._eta.remaining(scene["_progress"])))
        else:
            self.queue_progress.setVisible(False)
            self.queue_eta.setVisible(False)

        # reference inputs
        img_path = scene["ref_image_path"]
        self.ref_image_label.setText(
            t("motion.reference.image.selected", name=os.path.basename(img_path)) if img_path else t("motion.reference.image.none")
        )
        self.ref_image_clear_btn.setEnabled(bool(img_path))

        audio_path = scene["ref_audio_path"]
        self.ref_audio_label.setText(
            t("motion.reference.audio.selected", name=os.path.basename(audio_path)) if audio_path else t("motion.reference.audio.none")
        )
        self.ref_audio_clear_btn.setEnabled(bool(audio_path))

        self._refresh_profile_combo()

        # generation mode
        for key, btn in self._genmode_buttons.items():
            btn.setProperty("variant", "primary" if scene["gen_mode"] == key else "")
            repolish(btn)
        self.genmode_caption.setText(t(f"motion.genmode.{scene['gen_mode']}_caption"))

        # duration
        self.duration_combo.blockSignals(True)
        self.duration_combo.setCurrentIndex([k for k, _lk in DURATION_MODES].index(scene["duration_mode"]))
        self.duration_combo.blockSignals(False)
        manual = scene["duration_mode"] == "manual"
        self.duration_spin.setVisible(manual)
        if manual:
            self.duration_spin.blockSignals(True)
            self.duration_spin.setValue(scene["duration_s"])
            self.duration_spin.blockSignals(False)
            self.duration_caption.setText(t("motion.duration.manual_caption", sec=f"{scene['duration_s']:.1f}"))
        else:
            self.duration_caption.setText(t(f"motion.duration.{scene['duration_mode']}_caption"))

        # camera effects (multi-select) + zoom speed variant
        effects = scene["camera_effects"]
        for key, btn in self._camera_buttons.items():
            selected = key in effects
            btn.blockSignals(True)
            btn.setChecked(selected)
            btn.blockSignals(False)
            btn.setProperty("variant", "primary" if selected else "")
            repolish(btn)
        self.camera_hint.setText(t("motion.camera.none") if not effects else t("motion.camera.multi_hint"))
        zoom_on = "zoom" in effects
        self.zoom_speed_container.setVisible(zoom_on)
        if zoom_on:
            for key, btn in self._zoom_speed_buttons.items():
                btn.setProperty("variant", "primary" if scene["zoom_speed"] == key else "")
                repolish(btn)

        # embedded screen / TV background
        self.tv_check.blockSignals(True)
        self.tv_check.setChecked(scene["tv_bg"])
        self.tv_check.blockSignals(False)
        self.tv_source_container.setVisible(scene["tv_bg"])
        self.tv_source_combo.blockSignals(True)
        self.tv_source_combo.setCurrentIndex([k for k, _lk in TV_SOURCES].index(scene["tv_source"]))
        self.tv_source_combo.blockSignals(False)

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
            icon = "" if scene["quality_note"] == t("motion.quality.drift") else "✓"
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

        self.reference_title.setText(t("motion.reference.title"))
        self.ref_image_btn.setText(t("motion.reference.image.btn"))
        self.ref_image_clear_btn.setText(t("motion.reference.clear"))
        self.ref_audio_btn.setText(t("motion.reference.audio.btn"))
        self.ref_audio_clear_btn.setText(t("motion.reference.clear"))
        self.profile_char_label.setText(t("motion.reference.profile.label"))

        self.genmode_title.setText(t("motion.genmode.title"))
        for key, btn in self._genmode_buttons.items():
            btn.setText(t(next(lk for k, lk in GEN_MODES if k == key)))

        self.duration_title.setText(t("motion.duration.title"))
        d_idx = self.duration_combo.currentIndex()
        self.duration_combo.blockSignals(True)
        self.duration_combo.clear()
        self.duration_combo.addItems([t(lk) for _k, lk in DURATION_MODES])
        self.duration_combo.setCurrentIndex(max(0, d_idx))
        self.duration_combo.blockSignals(False)

        self.camera_title.setText(t("motion.camera.title"))
        for key, btn in self._camera_buttons.items():
            label_key = next(lk for k, lk in CAMERA_EFFECTS if k == key)
            btn.setText(t(label_key))
        self.zoom_speed_label.setText(t("motion.camera.zoom_speed"))
        for key, btn in self._zoom_speed_buttons.items():
            btn.setText(t(next(lk for k, lk in ZOOM_SPEEDS if k == key)))

        self.tv_title.setText(t("motion.tv.title"))
        self.tv_check.setText(t("motion.tv.enable"))
        self.tv_desc.setText(t("motion.tv.desc"))
        self.tv_source_label.setText(t("motion.tv.source"))
        tv_idx = self.tv_source_combo.currentIndex()
        self.tv_source_combo.blockSignals(True)
        self.tv_source_combo.clear()
        self.tv_source_combo.addItems([t(lk) for _k, lk in TV_SOURCES])
        self.tv_source_combo.setCurrentIndex(max(0, tv_idx))
        self.tv_source_combo.blockSignals(False)

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
