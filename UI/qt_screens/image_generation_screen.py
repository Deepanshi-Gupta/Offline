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
from common.qt_widgets import Card, CaptionLabel, ComplianceActivityIndicator, SectionLabel, clear_layout
from common.scenes import scene_paths
from common.style import reference_paths
from common.toggle_switch import ToggleSwitch
from common.workers import Worker

TOTAL_SCENES = 14
COMPLIANCE_DEMO_IDX = 4
RETRY_DEMO_IDX = 8
MANUAL_REVIEW_DEMO_IDX = 11
TICK_MS = 150

DEFAULT_PROMPT = "رجل وامرأة يتحدثان في مقهى"


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

        # ---- seed / lock / ref slot ----
        seed_row = QHBoxLayout()
        seed_col = QVBoxLayout()
        self.seed_label = QLabel()
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(self.gen_seed)
        self.seed_spin.valueChanged.connect(self._on_seed_changed)
        seed_col.addWidget(self.seed_label)
        seed_col.addWidget(self.seed_spin)
        seed_row.addLayout(seed_col)

        lock_col = QVBoxLayout()
        self.lock_label = QLabel()
        self.lock_switch = ToggleSwitch(on_color="#2F6FEF")
        self.lock_switch.setChecked(True)
        lock_col.addWidget(self.lock_label)
        lock_col.addWidget(self.lock_switch)
        seed_row.addLayout(lock_col)

        ref_col = QVBoxLayout()
        self.ref_slot_btn = QPushButton()
        self.ref_slot_btn.clicked.connect(self._pick_ref_image)
        ref_col.addWidget(self.ref_slot_btn)
        self.ref_slot_caption = CaptionLabel()
        ref_col.addWidget(self.ref_slot_caption)
        seed_row.addLayout(ref_col, 1)
        outer.addLayout(seed_row)

        # ---- style reference row ----
        style_head = QHBoxLayout()
        self.style_refs_label = SectionLabel()
        style_head.addWidget(self.style_refs_label)
        style_head.addStretch(1)
        self.arabic_text_check = QCheckBox()
        self.arabic_text_check.setChecked(True)
        style_head.addWidget(self.arabic_text_check)
        outer.addLayout(style_head)

        ref_row = QHBoxLayout()
        for path in self.ref_imgs:
            img = QLabel()
            pix = QPixmap(str(path))
            img.setPixmap(pix.scaled(QSize(140, 84), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            img.setFixedSize(140, 84)
            img.setScaledContents(True)
            ref_row.addWidget(img)
        outer.addLayout(ref_row)

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
    def _on_seed_changed(self, value: int):
        self.gen_seed = value

    def _pick_ref_image(self):
        # purely cosmetic in this mockup — no identity-locking model wired in
        QFileDialog.getOpenFileName(self, t("img.ref_slot"), "", "Images (*.png *.jpg *.jpeg)")

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
        self.seed_label.setText(t("img.seed.label"))
        self.lock_label.setText(t("img.seed.lock"))
        self.ref_slot_btn.setText(t("img.ref_slot"))
        self.ref_slot_caption.setText(t("img.ref_slot.caption"))
        self.style_refs_label.setText(t("img.style_refs", n=len(self.ref_imgs)))
        self.arabic_text_check.setText(t("img.arabic_text"))
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
