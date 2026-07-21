"""Native PySide6 port of image_generation_app.py (§3 of the UI audit) —
14-scene batch image generation with seed reproducibility, per-scene
review (approve/reject/regenerate), a scripted compliance-rejection demo,
a scripted single-retry failure, and a manual-review queue for repeated
compliance failures (Addendum A4).

The batch loop runs on a QTimer (one scene per tick) instead of a blocking
Python loop with time.sleep — same architecture as Smart Director — so the
grid updates live and Cancel is honoured within one tick.
"""

from PySide6.QtCore import QSize, Qt, QTimer, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.compliance import compliance_activity
from common.eta import EtaEstimator, format_remaining
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import (
    Card,
    CaptionLabel,
    ComplianceActivityIndicator,
    SectionLabel,
    StatusBadge,
    clear_layout,
    show_toast,
)
from common.scenes import scene_paths
from common.style import reference_paths
from common.toggle_switch import ToggleSwitch
from common.workers import Worker

TOTAL_SCENES = 14
COMPLIANCE_DEMO_IDX = 4
RETRY_DEMO_IDX = 8
MANUAL_REVIEW_DEMO_IDX = 11
TICK_MS = 150
REF_SLOTS = 8  # up to 8 reference images (parity with Character Pack Manager)

DEFAULT_PROMPT = "رجل وامرأة يتحدثان في مقهى"
ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:2"]
# Existing characters offered in the per-slot dropdown — proper nouns, so the
# names themselves are not translated (same rule as Project Management).
EXISTING_CHARACTERS = ["Layla", "Omar", "Yusuf", "Fatima"]
ERAS = [
    ("preislamic", "img.era.preislamic"), ("early_islamic", "img.era.early_islamic"),
    ("abbasid", "img.era.abbasid"), ("andalusian", "img.era.andalusian"),
    ("ottoman", "img.era.ottoman"), ("modern", "img.era.modern"),
]
PACKS = [
    ("abbasid", "img.pack.abbasid"), ("andalusian", "img.pack.andalusian"),
    ("bedouin", "img.pack.bedouin"), ("ottoman", "img.pack.ottoman"),
]


class BatchState:
    """UI-free batch logic — the st.session_state.batch replacement."""

    def __init__(self):
        self.scenes = None  # None = never generated (empty state)
        self.running = False
        self.cur_index = 0
        self.phase = "generating"

    def start(self):
        self.scenes = [{"status": "queued", "approved": None} for _ in range(TOTAL_SCENES)]
        self.running = True
        self.cur_index = 0
        self.phase = "generating"
        self.scenes[0]["status"] = "generating"

    def tick(self):
        i = self.cur_index
        if self.phase == "generating":
            if i == COMPLIANCE_DEMO_IDX:
                self.scenes[i]["status"] = "compliance"
                self.phase = "compliance"
                return
            self._finish_scene(i)
        elif self.phase == "compliance":
            # content tripped the modesty filter and was auto-regenerated to
            # comply — a silent correction the session indicator surfaces (B3)
            self.scenes[i]["status"] = "success"
            compliance_activity.record(1)
            self._advance()

    def _finish_scene(self, i):
        if i == RETRY_DEMO_IDX:
            self.scenes[i]["status"] = "failed"
        elif i == MANUAL_REVIEW_DEMO_IDX:
            self.scenes[i]["status"] = "manual_review"
        else:
            self.scenes[i]["status"] = "success"
        self._advance()

    def _advance(self):
        self.phase = "generating"
        if self.cur_index < TOTAL_SCENES - 1:
            self.cur_index += 1
            self.scenes[self.cur_index]["status"] = "generating"
        else:
            self.running = False

    def counts(self):
        c = {"success": 0, "failed": 0, "manual_review": 0, "skipped": 0}
        for sc in self.scenes:
            c[sc["status"]] = c.get(sc["status"], 0) + 1
        approved = sum(1 for sc in self.scenes if sc.get("approved") is True)
        return c, approved


class RegenerateDialog(QDialog):
    def __init__(self, idx: int, scene: dict, seed: int, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("img.regen_dialog.title"))
        self.setMinimumWidth(360)
        self.result_confirmed = False
        lay = QVBoxLayout(self)

        if scene["status"] != "manual_review" and pixmap is not None:
            preview = QLabel()
            preview.setPixmap(pixmap.scaled(QSize(220, 150), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lay.addWidget(preview)
        else:
            lay.addWidget(QLabel(t("img.regen_dialog.withheld")))

        lay.addWidget(QLabel(t("img.regen_dialog.prompt")))
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText(t("img.regen_dialog.prompt_ph"))
        lay.addWidget(self.prompt_edit)

        lay.addWidget(QLabel(t("img.regen_dialog.seed")))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(seed)
        lay.addWidget(self.seed_spin)

        btn_row = QHBoxLayout()
        confirm_btn = QPushButton(t("img.regen_dialog.confirm"))
        confirm_btn.setProperty("variant", "primary")
        confirm_btn.clicked.connect(self._confirm)
        cancel_btn = QPushButton(t("img.regen_dialog.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    def _confirm(self):
        self.result_confirmed = True
        self.accept()


class ImageGenerationScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.batch = BatchState()
        self.gen_seed = 42
        self._eta = EtaEstimator()
        self._workers = []
        self.scene_imgs = scene_paths()
        self.ref_imgs = reference_paths()

        # ---- expanded controls state (Task 5 / D) ----
        self.aspect = "9:16"
        self.identity_lock = True
        self.cinematic = False
        self.era = "abbasid"
        self.selected_packs = set()
        self.outfit_lock = True
        self.arch_lock = True
        self.arabic_in_image = True
        self.reuse_identity = True
        self._advanced_open = False
        self.ref_slots = self._seed_ref_slots()
        self._slot_widgets = []

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 4, 4)
        outer.setSpacing(16)

        # ---- prompt ----
        self.prompt_label = SectionLabel()
        outer.addWidget(self.prompt_label)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(DEFAULT_PROMPT)
        self.prompt_edit.setFixedHeight(90)
        outer.addWidget(self.prompt_edit)

        self._build_controls_section(outer)
        self._build_advanced_section(outer)
        self._build_reference_slots(outer)
        self._build_cultural_section(outer)
        self._build_identity_snapshot(outer)

        # ---- generate / cancel ----
        gen_row = QHBoxLayout()
        self.generate_btn = QPushButton()
        self.generate_btn.setProperty("variant", "primary")
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self._start_batch)
        self.cancel_btn = QPushButton()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_batch)
        gen_row.addWidget(self.generate_btn, 3)
        gen_row.addWidget(self.cancel_btn, 1)
        outer.addLayout(gen_row)

        # ---- batch grid ----
        self.batch_title = SectionLabel()
        outer.addWidget(self.batch_title)
        self.empty_label = QLabel()
        self.empty_label.setWordWrap(True)
        outer.addWidget(self.empty_label)

        self.summary_caption = CaptionLabel()
        outer.addWidget(self.summary_caption)
        self.gen_eta = CaptionLabel()
        self.gen_eta.setVisible(False)
        outer.addWidget(self.gen_eta)
        compliance_row = QHBoxLayout()
        self.compliance_indicator = ComplianceActivityIndicator()
        self.compliance_indicator.setVisible(False)
        compliance_row.addWidget(self.compliance_indicator)
        compliance_row.addStretch(1)
        outer.addLayout(compliance_row)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        outer.addWidget(self.grid_widget)
        self._tiles = []

        # ---- manual review queue ----
        self.review_title = SectionLabel()
        outer.addWidget(self.review_title)
        self.review_container = QVBoxLayout()
        outer.addLayout(self.review_container)

        outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()
        self._render_grid()

    # ------------------------------------------------------------------
    # construction of the expanded control sections (Task 5 / D)
    # ------------------------------------------------------------------
    def _seed_ref_slots(self):
        slots = [{"img": None, "name": "", "character": ""} for _ in range(REF_SLOTS)]
        for i, path in enumerate(self.ref_imgs[:REF_SLOTS]):
            slots[i]["img"] = str(path)
        return slots

    def _build_controls_section(self, outer: QVBoxLayout):
        row = QHBoxLayout()
        aspect_col = QVBoxLayout()
        self.aspect_label = QLabel()
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(ASPECT_RATIOS)
        self.aspect_combo.setCurrentText(self.aspect)
        self.aspect_combo.currentTextChanged.connect(lambda v: setattr(self, "aspect", v))
        aspect_col.addWidget(self.aspect_label)
        aspect_col.addWidget(self.aspect_combo)
        row.addLayout(aspect_col)

        id_col = QVBoxLayout()
        self.identity_lock_label = QLabel()
        self.identity_lock_switch = ToggleSwitch(on_color="#2F6FEF")
        self.identity_lock_switch.setChecked(self.identity_lock)
        self.identity_lock_switch.toggled.connect(lambda v: setattr(self, "identity_lock", v))
        id_col.addWidget(self.identity_lock_label)
        id_col.addWidget(self.identity_lock_switch)
        row.addLayout(id_col)

        cine_col = QVBoxLayout()
        self.cinematic_label = QLabel()
        self.cinematic_switch = ToggleSwitch(on_color="#2F6FEF")
        self.cinematic_switch.setChecked(self.cinematic)
        self.cinematic_switch.toggled.connect(lambda v: setattr(self, "cinematic", v))
        cine_col.addWidget(self.cinematic_label)
        cine_col.addWidget(self.cinematic_switch)
        row.addLayout(cine_col)
        row.addStretch(1)
        outer.addLayout(row)
        self.identity_lock_caption = CaptionLabel()
        outer.addWidget(self.identity_lock_caption)
        self.cinematic_caption = CaptionLabel()
        outer.addWidget(self.cinematic_caption)

    def _build_advanced_section(self, outer: QVBoxLayout):
        # manual seed is hidden behind an Advanced expander by default (5-C-1,
        # client-confirmed) — reproducibility stays reachable without clutter.
        self.advanced_btn = QPushButton()
        self.advanced_btn.setCursor(Qt.PointingHandCursor)
        self.advanced_btn.setProperty("role", "navItem")
        self.advanced_btn.clicked.connect(self._toggle_advanced)
        outer.addWidget(self.advanced_btn, 0, Qt.AlignLeft)

        self.advanced_body = QWidget()
        abody = QHBoxLayout(self.advanced_body)
        abody.setContentsMargins(0, 0, 0, 0)
        seed_col = QVBoxLayout()
        self.seed_label = QLabel()
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(self.gen_seed)
        self.seed_spin.valueChanged.connect(self._on_seed_changed)
        seed_col.addWidget(self.seed_label)
        seed_col.addWidget(self.seed_spin)
        abody.addLayout(seed_col)

        lock_col = QVBoxLayout()
        self.lock_label = QLabel()
        self.lock_switch = ToggleSwitch(on_color="#2F6FEF")
        self.lock_switch.setChecked(True)
        lock_col.addWidget(self.lock_label)
        lock_col.addWidget(self.lock_switch)
        abody.addLayout(lock_col)
        self.seed_advanced_note = CaptionLabel()
        abody.addWidget(self.seed_advanced_note, 1)
        self.advanced_body.setVisible(self._advanced_open)
        outer.addWidget(self.advanced_body)

    def _toggle_advanced(self):
        self._advanced_open = not self._advanced_open
        self.advanced_body.setVisible(self._advanced_open)
        self._render_advanced_btn()

    def _render_advanced_btn(self):
        arrow = "▾" if self._advanced_open else "▸"
        self.advanced_btn.setText(f"{arrow}  {t('img.advanced.label')}")

    def _build_reference_slots(self, outer: QVBoxLayout):
        self.refslots_title = SectionLabel()
        outer.addWidget(self.refslots_title)
        self.refslots_caption = CaptionLabel()
        outer.addWidget(self.refslots_caption)
        grid = QGridLayout()
        grid.setSpacing(8)
        self._slot_widgets = []
        for i in range(REF_SLOTS):
            card, widgets = self._build_slot_card(i)
            self._slot_widgets.append(widgets)
            grid.addWidget(card, i // 4, i % 4)
        outer.addLayout(grid)

    def _build_slot_card(self, idx: int):
        card = Card(flat=True, margins=(8, 8, 8, 8), spacing=6)
        card.setFixedWidth(158)
        lay = card.layout()
        thumb = QLabel()
        thumb.setFixedSize(140, 80)
        thumb.setAlignment(Qt.AlignCenter)
        lay.addWidget(thumb)

        btn_row = QHBoxLayout()
        add_btn = QPushButton()
        add_btn.clicked.connect(lambda _c=False, i=idx: self._pick_slot_image(i))
        clear_btn = QPushButton()
        clear_btn.clicked.connect(lambda _c=False, i=idx: self._clear_slot(i))
        btn_row.addWidget(add_btn)
        btn_row.addWidget(clear_btn)
        lay.addLayout(btn_row)

        name_edit = QLineEdit(self.ref_slots[idx]["name"])
        name_edit.setLayoutDirection(Qt.RightToLeft)
        name_edit.textChanged.connect(lambda text, i=idx: self.ref_slots[i].__setitem__("name", text))
        lay.addWidget(name_edit)

        char_combo = QComboBox()
        char_combo.currentIndexChanged.connect(lambda ci, i=idx: self._on_slot_character(i, ci))
        lay.addWidget(char_combo)

        widgets = {"thumb": thumb, "add": add_btn, "clear": clear_btn, "name": name_edit, "combo": char_combo}
        self._render_slot(idx, widgets)
        return card, widgets

    def _render_slot(self, idx: int, widgets: dict):
        slot = self.ref_slots[idx]
        s = semantic(self._dark)
        if slot["img"]:
            pix = QPixmap(slot["img"]).scaled(QSize(140, 80), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            widgets["thumb"].setPixmap(pix)
            widgets["thumb"].setStyleSheet("border-radius:8px;")
        else:
            widgets["thumb"].setPixmap(QPixmap())
            widgets["thumb"].setText(t("img.slot.add"))
            widgets["thumb"].setStyleSheet(
                f"background:{s['surface_muted']}; color:{s['ink_fainter']}; border-radius:8px; font-size:11px;"
            )
        widgets["clear"].setEnabled(slot["img"] is not None)

    def _pick_slot_image(self, idx: int):
        path, _ = QFileDialog.getOpenFileName(self, t("img.slot.add"), "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            # keep the mock usable without a file on disk: fall back to a sample
            samples = [str(p) for p in self.ref_imgs] or [str(p) for p in self.scene_imgs]
            if not samples:
                return
            path = samples[idx % len(samples)]
        self.ref_slots[idx]["img"] = path
        self._render_slot(idx, self._slot_widgets[idx])
        self._render_refslots_title()

    def _clear_slot(self, idx: int):
        self.ref_slots[idx]["img"] = None
        self._render_slot(idx, self._slot_widgets[idx])
        self._render_refslots_title()

    def _on_slot_character(self, idx: int, combo_index: int):
        if combo_index <= 0:
            self.ref_slots[idx]["character"] = ""
            return
        name = EXISTING_CHARACTERS[combo_index - 1]
        self.ref_slots[idx]["character"] = name
        # choosing an existing character fills the name tag if it's empty
        widgets = self._slot_widgets[idx]
        if not widgets["name"].text().strip():
            widgets["name"].setText(name)

    def _render_refslots_title(self):
        filled = sum(1 for s in self.ref_slots if s["img"])
        self.refslots_title.setText(t("img.refslots.title", filled=filled))

    def _build_cultural_section(self, outer: QVBoxLayout):
        card = Card()
        cl = card.layout()
        self.cultural_title = SectionLabel()
        cl.addWidget(self.cultural_title)
        self.cultural_desc = CaptionLabel()
        cl.addWidget(self.cultural_desc)

        era_row = QHBoxLayout()
        self.era_label = QLabel()
        era_row.addWidget(self.era_label)
        self.era_combo = QComboBox()
        self.era_combo.currentIndexChanged.connect(lambda i: setattr(self, "era", ERAS[i][0]) if i >= 0 else None)
        era_row.addWidget(self.era_combo)
        era_row.addStretch(1)
        cl.addLayout(era_row)

        self.packs_label = SectionLabel()
        cl.addWidget(self.packs_label)
        self.packs_caption = CaptionLabel()
        cl.addWidget(self.packs_caption)
        packs_row = QHBoxLayout()
        self._pack_buttons = {}
        for i, (key, _label_key) in enumerate(PACKS):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("role", "navItem")
            btn.toggled.connect(lambda checked, k=key: self._toggle_pack(k, checked))
            packs_row.addWidget(btn)
            self._pack_buttons[key] = btn
        packs_row.addStretch(1)
        cl.addLayout(packs_row)

        lock_row = QHBoxLayout()
        outfit_col = QVBoxLayout()
        self.outfit_lock_label = QLabel()
        self.outfit_lock_switch = ToggleSwitch(on_color="#2F6FEF")
        self.outfit_lock_switch.setChecked(self.outfit_lock)
        self.outfit_lock_switch.toggled.connect(lambda v: setattr(self, "outfit_lock", v))
        outfit_col.addWidget(self.outfit_lock_label)
        outfit_col.addWidget(self.outfit_lock_switch)
        lock_row.addLayout(outfit_col)
        arch_col = QVBoxLayout()
        self.arch_lock_label = QLabel()
        self.arch_lock_switch = ToggleSwitch(on_color="#2F6FEF")
        self.arch_lock_switch.setChecked(self.arch_lock)
        self.arch_lock_switch.toggled.connect(lambda v: setattr(self, "arch_lock", v))
        arch_col.addWidget(self.arch_lock_label)
        arch_col.addWidget(self.arch_lock_switch)
        lock_row.addLayout(arch_col)
        lock_row.addStretch(1)
        cl.addLayout(lock_row)

        self.arabic_guarantee_title = SectionLabel()
        cl.addWidget(self.arabic_guarantee_title)
        arb_row = QHBoxLayout()
        self.arabic_text_check = QCheckBox()
        self.arabic_text_check.setChecked(self.arabic_in_image)
        self.arabic_text_check.toggled.connect(self._on_arabic_toggled)
        arb_row.addWidget(self.arabic_text_check)
        self.arabic_badge = StatusBadge(tone="success", dark=self._dark)
        arb_row.addWidget(self.arabic_badge)
        arb_row.addStretch(1)
        cl.addLayout(arb_row)
        self.arabic_guarantee_note = CaptionLabel()
        cl.addWidget(self.arabic_guarantee_note)

        outer.addWidget(card)

    def _toggle_pack(self, key: str, checked: bool):
        if checked:
            self.selected_packs.add(key)
        else:
            self.selected_packs.discard(key)

    def _on_arabic_toggled(self, checked: bool):
        self.arabic_in_image = checked
        self.arabic_badge.setVisible(checked)

    def _build_identity_snapshot(self, outer: QVBoxLayout):
        card = Card()
        cl = card.layout()
        self.snapshot_title = SectionLabel()
        cl.addWidget(self.snapshot_title)
        self.snapshot_desc = CaptionLabel()
        cl.addWidget(self.snapshot_desc)
        row = QHBoxLayout()
        self.snapshot_save_btn = QPushButton()
        self.snapshot_save_btn.setProperty("variant", "primary")
        self.snapshot_save_btn.clicked.connect(
            lambda: show_toast(self, t("img.snapshot.saved_toast"), dark=self._dark)
        )
        row.addWidget(self.snapshot_save_btn)
        self.snapshot_export_btn = QPushButton()
        self.snapshot_export_btn.clicked.connect(self._export_snapshot)
        row.addWidget(self.snapshot_export_btn)
        row.addStretch(1)
        cl.addLayout(row)
        reuse_row = QHBoxLayout()
        self.reuse_label = QLabel()
        self.reuse_switch = ToggleSwitch(on_color="#2F6FEF")
        self.reuse_switch.setChecked(self.reuse_identity)
        self.reuse_switch.toggled.connect(lambda v: setattr(self, "reuse_identity", v))
        reuse_row.addWidget(self.reuse_label)
        reuse_row.addWidget(self.reuse_switch)
        reuse_row.addStretch(1)
        cl.addLayout(reuse_row)
        self.reuse_caption = CaptionLabel()
        cl.addWidget(self.reuse_caption)
        outer.addWidget(card)

    def _export_snapshot(self):
        path, _ = QFileDialog.getSaveFileName(self, t("img.snapshot.export"), "identity.json", "JSON (*.json)")
        if path:
            show_toast(self, t("img.snapshot.exported_toast"), dark=self._dark)

    # ------------------------------------------------------------------
    def _on_seed_changed(self, value: int):
        self.gen_seed = value

    # ------------------------------------------------------------------
    # batch driving
    # ------------------------------------------------------------------
    def _start_batch(self):
        self.batch.start()
        self._eta.start()
        self.generate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._render_grid()
        self._timer.start()

    def _cancel_batch(self):
        self._timer.stop()
        self._eta.reset()
        self.batch.running = False
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._render_grid()

    def _on_tick(self):
        self.batch.tick()
        if not self.batch.running:
            self._eta.reset()
        self._render_grid()
        if not self.batch.running:
            self._timer.stop()
            self.generate_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)

    def _batch_progress(self) -> float:
        scenes = self.batch.scenes or []
        if not scenes:
            return 0.0
        terminal = {"success", "failed", "manual_review", "skipped"}
        return sum(1 for sc in scenes if sc["status"] in terminal) / len(scenes)

    # ------------------------------------------------------------------
    # scene tile rendering
    # ------------------------------------------------------------------
    def _scene_pixmap(self, idx: int) -> QPixmap:
        return QPixmap(str(self.scene_imgs[idx % len(self.scene_imgs)]))

    def _render_grid(self):
        clear_layout(self.grid_layout)
        self._tiles = []

        has_batch = self.batch.scenes is not None
        self.empty_label.setVisible(not has_batch)
        self.grid_widget.setVisible(has_batch)
        self.summary_caption.setVisible(has_batch)
        self.review_title.setVisible(has_batch)

        self.gen_eta.setVisible(has_batch and self.batch.running)
        if has_batch and self.batch.running:
            self.gen_eta.setText(format_remaining(self._eta.remaining(self._batch_progress())))
        # session compliance-activity indicator: visible once generation has run
        self.compliance_indicator.setVisible(has_batch)

        if not has_batch:
            clear_layout(self.review_container)
            return

        s = semantic(self._dark)
        counts, approved = self.batch.counts()
        self.summary_caption.setText(
            t(
                "img.summary",
                success=counts.get("success", 0),
                approved=approved,
                failed=counts.get("failed", 0),
                review=counts.get("manual_review", 0),
                skipped=counts.get("skipped", 0),
            )
        )

        for i, scene in enumerate(self.batch.scenes):
            tile = self._build_tile(i, scene, s)
            row, col = divmod(i, 7)
            self.grid_layout.addWidget(tile, row, col)

        clear_layout(self.review_container)
        flagged = [i for i, sc in enumerate(self.batch.scenes) if sc["status"] == "manual_review"]
        if flagged:
            for i in flagged:
                self.review_container.addWidget(self._build_review_row(i))

    def _build_tile(self, i: int, scene: dict, s: dict) -> QWidget:
        card = Card(flat=True, margins=(6, 6, 6, 6), spacing=4)
        card.setFixedWidth(130)
        lay = card.layout()

        status = scene["status"]
        img_label = QLabel()
        img_label.setFixedSize(118, 78)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setWordWrap(True)

        if status == "success":
            pix = self._scene_pixmap(i)
            img_label.setPixmap(pix.scaled(QSize(118, 78), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            img_label.setScaledContents(True)
        else:
            tone = {
                "queued": ("surface_muted", "ink_fainter", "img.status.queued"),
                "generating": ("info_bg", "info_fg", "img.status.generating"),
                "compliance": ("warning_bg", "warning_fg_strong", "img.status.compliance"),
                "failed": ("danger_bg", "danger_fg_strong", "img.status.failed"),
                "manual_review": ("danger_bg", "danger_fg_strong", "img.status.manual_review"),
                "skipped": ("surface_muted", "ink_fainter", "img.status.skipped"),
            }[status]
            bg_k, fg_k, key = tone
            img_label.setStyleSheet(f"background:{s[bg_k]}; color:{s[fg_k]}; border-radius:8px; font-size:10.5px; font-weight:600;")
            img_label.setText(t(key))
        lay.addWidget(img_label)

        caption = CaptionLabel(t("img.scene", n=i + 1))
        caption.setAlignment(Qt.AlignCenter)
        lay.addWidget(caption)

        if status == "success":
            if scene.get("approved") is True:
                badge = QLabel(t("img.approved"))
                badge.setStyleSheet(f"color:{s['success_fg_strong']}; font-weight:700; font-size:10.5px;")
                badge.setAlignment(Qt.AlignCenter)
                lay.addWidget(badge)
            elif scene.get("approved") is False:
                badge = QLabel(t("img.rejected"))
                badge.setStyleSheet(f"color:{s['danger_fg_strong']}; font-weight:700; font-size:10.5px;")
                badge.setAlignment(Qt.AlignCenter)
                lay.addWidget(badge)
            ac_row = QHBoxLayout()
            approve_btn = QPushButton(t("img.btn.approve"))
            approve_btn.setFixedHeight(24)
            approve_btn.clicked.connect(lambda _c=False, idx=i: self._set_approved(idx, True))
            reject_btn = QPushButton(t("img.btn.reject"))
            reject_btn.setFixedHeight(24)
            reject_btn.clicked.connect(lambda _c=False, idx=i: self._set_approved(idx, False))
            ac_row.addWidget(approve_btn)
            ac_row.addWidget(reject_btn)
            lay.addLayout(ac_row)
            regen_btn = QPushButton(t("img.btn.regenerate"))
            regen_btn.clicked.connect(lambda _c=False, idx=i: self._open_regen_dialog(idx))
            lay.addWidget(regen_btn)
        elif status == "failed":
            retry_btn = QPushButton(t("img.btn.retry"))
            retry_btn.setProperty("variant", "primary")
            retry_btn.clicked.connect(lambda _c=False, idx=i: self._retry_scene(idx))
            lay.addWidget(retry_btn)

        return card

    def _build_review_row(self, i: int) -> QWidget:
        card = Card(margins=(12, 10, 12, 10), spacing=6)
        lay = card.layout()
        lay.addWidget(QLabel(t("img.manual_review.desc", n=i + 1)))
        row = QHBoxLayout()
        regen_btn = QPushButton(t("img.btn.regenerate"))
        regen_btn.clicked.connect(lambda _c=False, idx=i: self._open_regen_dialog(idx))
        edit_btn = QPushButton(t("img.btn.edit_prompt"))
        edit_btn.clicked.connect(lambda _c=False, idx=i: self._open_regen_dialog(idx))
        skip_btn = QPushButton(t("img.btn.skip"))
        skip_btn.clicked.connect(lambda _c=False, idx=i: self._skip_scene(idx))
        row.addWidget(regen_btn)
        row.addWidget(edit_btn)
        row.addWidget(skip_btn)
        lay.addLayout(row)
        return card

    # ------------------------------------------------------------------
    # scene actions
    # ------------------------------------------------------------------
    def _set_approved(self, idx: int, value: bool):
        self.batch.scenes[idx]["approved"] = value
        self._render_grid()

    def _retry_scene(self, idx: int):
        worker = Worker(self._simulate_retry)
        self._workers.append(worker)

        def done(_r=None):
            if worker in self._workers:
                self._workers.remove(worker)
            self.batch.scenes[idx]["status"] = "success"
            self._render_grid()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    @staticmethod
    def _simulate_retry():
        import time

        time.sleep(0.5)
        return None

    def _skip_scene(self, idx: int):
        self.batch.scenes[idx]["status"] = "skipped"
        self._render_grid()

    def _open_regen_dialog(self, idx: int):
        scene = self.batch.scenes[idx]
        pixmap = self._scene_pixmap(idx) if scene["status"] != "manual_review" else None
        dlg = RegenerateDialog(idx, scene, self.gen_seed, pixmap, self)
        if dlg.exec() == QDialog.Accepted and dlg.result_confirmed:
            worker = Worker(self._simulate_retry)
            self._workers.append(worker)

            def done(_r=None):
                if worker in self._workers:
                    self._workers.remove(worker)
                self.batch.scenes[idx] = {"status": "success", "approved": None}
                self._render_grid()

            worker.signals.finished.connect(done)
            QThreadPool.globalInstance().start(worker)

    # ------------------------------------------------------------------
    def retranslate(self):
        self.prompt_label.setText(t("img.prompt.label"))

        # controls
        self.aspect_label.setText(t("img.aspect.label"))
        self.identity_lock_label.setText(t("img.identity_lock"))
        self.identity_lock_caption.setText(t("img.identity_lock.caption"))
        self.cinematic_label.setText(t("img.cinematic"))
        self.cinematic_caption.setText(t("img.cinematic.caption"))

        # advanced (seed)
        self._render_advanced_btn()
        self.seed_label.setText(t("img.seed.label"))
        self.lock_label.setText(t("img.seed.lock"))
        self.seed_advanced_note.setText(t("img.seed.advanced_note"))

        # reference slots
        self._render_refslots_title()
        self.refslots_caption.setText(t("img.refslots.caption"))
        for idx, widgets in enumerate(self._slot_widgets):
            widgets["add"].setText(t("img.slot.add"))
            widgets["clear"].setText(t("img.slot.clear"))
            widgets["name"].setPlaceholderText(t("img.slot.name_ph"))
            combo = widgets["combo"]
            combo.blockSignals(True)
            cur = combo.currentIndex()
            combo.clear()
            combo.addItem(t("img.slot.unassigned"))
            combo.addItems(EXISTING_CHARACTERS)
            combo.setCurrentIndex(max(0, cur))
            combo.blockSignals(False)
            if not self.ref_slots[idx]["img"]:
                self._render_slot(idx, widgets)

        # cultural & historical
        self.cultural_title.setText(t("img.cultural.title"))
        self.cultural_desc.setText(t("img.cultural.desc"))
        self.era_label.setText(t("img.era.label"))
        era_idx = next((i for i, (k, _) in enumerate(ERAS) if k == self.era), 0)
        self.era_combo.blockSignals(True)
        self.era_combo.clear()
        self.era_combo.addItems([t(k) for _c, k in ERAS])
        self.era_combo.setCurrentIndex(era_idx)
        self.era_combo.blockSignals(False)
        self.packs_label.setText(t("img.packs.label"))
        self.packs_caption.setText(t("img.packs.caption"))
        for key, btn in self._pack_buttons.items():
            btn.setText(t(next(lk for k, lk in PACKS if k == key)))
        self.outfit_lock_label.setText(t("img.outfit_lock"))
        self.arch_lock_label.setText(t("img.arch_lock"))
        self.arabic_guarantee_title.setText(t("img.arabic_guarantee.title"))
        self.arabic_text_check.setText(t("img.arabic_text"))
        self.arabic_badge.setText(t("img.arabic_guarantee.badge"))
        self.arabic_badge.setVisible(self.arabic_in_image)
        self.arabic_guarantee_note.setText(t("img.arabic_guarantee.note"))

        # identity snapshot
        self.snapshot_title.setText(t("img.snapshot.title"))
        self.snapshot_desc.setText(t("img.snapshot.desc"))
        self.snapshot_save_btn.setText(t("img.snapshot.save"))
        self.snapshot_export_btn.setText(t("img.snapshot.export"))
        self.reuse_label.setText(t("img.snapshot.reuse"))
        self.reuse_caption.setText(t("img.snapshot.reuse_caption"))

        self.generate_btn.setText(t("img.batch.generate"))
        self.cancel_btn.setText(t("img.batch.cancel"))
        self.batch_title.setText(t("img.batch.title"))
        self.empty_label.setText(t("img.batch.empty"))
        self.review_title.setText(t("img.manual_review.title"))
        self._render_grid()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_grid()
