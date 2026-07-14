"""Native PySide6 port of subtitles_app.py (§10 of the UI audit): a
manual subtitle block editor, live timing-shift preview, a caption
styling panel whose preview renders real Arabic (diacritics included —
never a Latin placeholder), a 5-language layer with simulated NLLB
translation (Urdu scripted to fail once), a 14-scene per-scene language
override table, real SRT import/export, and a burn-in toggle.
"""

from PySide6.QtCore import QSize, Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout
from common.scenes import scene_paths
from common.workers import Worker

NUM_SCENES = 14
LANGUAGES = [("ar", "sub.lang.ar"), ("en", "sub.lang.en"), ("fr", "sub.lang.fr"), ("ur", "sub.lang.ur"), ("ms", "sub.lang.ms")]
ALWAYS_ON = {"ar", "en"}
FONTS = ["Tajawal", "Cairo", "Amiri", "Noto Naskh Arabic"]
FAIL_LANG = "ur"

DEFAULT_BLOCKS = [
    {"id": 0, "start_ms": 0, "end_ms": 2000, "ar": "مَرْحَبًا بِكُمْ فِي هَذِهِ الْقِصَّةِ."},
    {"id": 1, "start_ms": 2000, "end_ms": 4500, "ar": "كَانَ يَا مَا كَانَ، فِي قَدِيمِ الزَّمَانِ."},
    {"id": 2, "start_ms": 4500, "end_ms": 7000, "ar": "رَجُلٌ حَكِيمٌ يَعِيشُ فِي الصَّحْرَاءِ."},
    {"id": 3, "start_ms": 7000, "end_ms": 9500, "ar": "وَذَاتَ يَوْمٍ، سَمِعَ صَوْتًا غَرِيبًا."},
    {"id": 4, "start_ms": 9500, "end_ms": 12000, "ar": "فَقَرَّرَ أَنْ يَتْبَعَهُ."},
]
EN_TRANSLATION = {
    0: "Welcome to this story.", 1: "Once upon a time, long ago.", 2: "A wise man lived in the desert.",
    3: "One day, he heard a strange sound.", 4: "So he decided to follow it.",
}


def ms_to_srt_ts(ms: int) -> str:
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms_rest = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms_rest:03d}"


def blocks_to_srt(blocks) -> str:
    lines = []
    for i, b in enumerate(blocks, start=1):
        lines.append(str(i))
        lines.append(f"{ms_to_srt_ts(b['start_ms'])} --> {ms_to_srt_ts(b['end_ms'])}")
        lines.append(b["ar"])
        lines.append("")
    return "\n".join(lines)


class SubtitlesScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.scenes = scene_paths()

        self.sub_status = "no_subtitles"
        self.blocks = []
        self.out_of_sync = False
        self.shift_ms = 0
        self.active_langs = {"ar", "en"}
        self.translations = {"en": dict(EN_TRANSLATION)}
        self.lang_status = {code: "not_translated" for code, _k in LANGUAGES if code not in ALWAYS_ON}
        self.lang_attempts = {}
        self.style = {"font": FONTS[0], "size": 26, "color": "#FFFFFF", "bg_on": True, "bg_opacity": 60, "position": "bottom"}
        self.scene_overrides = {i: "global" for i in range(NUM_SCENES)}
        self.burn_in = False
        self.preview_block = 0
        self._workers = []

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(16)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self.empty_card = Card()
        elay = self.empty_card.layout()
        self.empty_label = QLabel()
        elay.addWidget(self.empty_label)
        self.auto_gen_btn = QPushButton()
        self.auto_gen_btn.setProperty("variant", "primary")
        self.auto_gen_btn.clicked.connect(self._auto_generate)
        elay.addWidget(self.auto_gen_btn)
        self.outer.addWidget(self.empty_card)

        self.editor_container = QWidget()
        editor_lay = QVBoxLayout(self.editor_container)
        editor_lay.setContentsMargins(0, 0, 0, 0)
        editor_lay.setSpacing(16)
        self._build_sync_section(editor_lay)
        editor_lay.addWidget(self._hr())
        self._build_blocks_section(editor_lay)
        editor_lay.addWidget(self._hr())
        self._build_shift_section(editor_lay)
        editor_lay.addWidget(self._hr())
        self._build_style_section(editor_lay)
        editor_lay.addWidget(self._hr())
        self._build_language_section(editor_lay)
        editor_lay.addWidget(self._hr())
        self._build_override_section(editor_lay)
        editor_lay.addWidget(self._hr())
        self._build_io_section(editor_lay)
        self.outer.addWidget(self.editor_container)
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()
        self._sync_visibility()

    @staticmethod
    def _hr() -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setProperty("role", "divider")
        return line

    def _sync_visibility(self):
        has_subs = self.sub_status != "no_subtitles"
        self.empty_card.setVisible(not has_subs)
        self.editor_container.setVisible(has_subs)

    def _auto_generate(self):
        self.auto_gen_btn.setEnabled(False)
        self.auto_gen_btn.setText(t("sub.transcribing"))
        self._run_worker(lambda: __import__("time").sleep(0.7), self._finish_auto_generate)

    def _run_worker(self, fn, on_done):
        worker = Worker(fn)
        self._workers.append(worker)

        def settle(_result=None):
            if worker in self._workers:
                self._workers.remove(worker)
            on_done()

        worker.signals.finished.connect(settle)
        QThreadPool.globalInstance().start(worker)

    def _finish_auto_generate(self):
        self.blocks = [dict(b) for b in DEFAULT_BLOCKS]
        self.sub_status = "editing"
        self._sync_visibility()
        self._render_blocks()
        self._render_style_preview()

    # ------------------------------------------------------------------
    # out-of-sync / autosync
    # ------------------------------------------------------------------
    def _build_sync_section(self, parent_lay: QVBoxLayout):
        self.sync_warning = QLabel()
        self.sync_warning.setWordWrap(True)
        self.sync_warning.setVisible(False)
        parent_lay.addWidget(self.sync_warning)
        self.autosync_btn = QPushButton()
        self.autosync_btn.setProperty("variant", "primary")
        self.autosync_btn.clicked.connect(self._autosync)
        self.autosync_btn.setVisible(False)
        parent_lay.addWidget(self.autosync_btn)

        self.sim_desync_btn = QPushButton()
        self.sim_desync_btn.clicked.connect(self._sim_desync)
        parent_lay.addWidget(self.sim_desync_btn)
        self.sim_desync_caption = CaptionLabel()
        parent_lay.addWidget(self.sim_desync_caption)

    def _sim_desync(self):
        self.out_of_sync = True
        self._render_sync()

    def _autosync(self):
        self.autosync_btn.setEnabled(False)
        self.autosync_btn.setText(t("sub.syncing"))
        self._run_worker(lambda: __import__("time").sleep(0.5), self._finish_autosync)

    def _finish_autosync(self):
        self.out_of_sync = False
        self._render_sync()

    def _render_sync(self):
        self.sync_warning.setVisible(self.out_of_sync)
        self.autosync_btn.setVisible(self.out_of_sync)
        self.autosync_btn.setEnabled(True)
        self.autosync_btn.setText(t("sub.btn.autosync"))
        self.sim_desync_btn.setVisible(not self.out_of_sync)
        self.sim_desync_caption.setVisible(not self.out_of_sync)

    # ------------------------------------------------------------------
    # blocks
    # ------------------------------------------------------------------
    def _build_blocks_section(self, parent_lay: QVBoxLayout):
        self.blocks_title = SectionLabel()
        parent_lay.addWidget(self.blocks_title)
        self.blocks_container = QVBoxLayout()
        parent_lay.addLayout(self.blocks_container)
        self.add_block_btn = QPushButton()
        self.add_block_btn.clicked.connect(self._add_block)
        parent_lay.addWidget(self.add_block_btn)

    def _render_blocks(self):
        clear_layout(self.blocks_container)
        for b in self.blocks:
            self.blocks_container.addWidget(self._build_block_row(b))

    def _build_block_row(self, b: dict) -> QWidget:
        card = Card(flat=True, margins=(10, 8, 10, 8), spacing=6)
        lay = card.layout()

        time_row = QHBoxLayout()
        start_spin = QSpinBox()
        start_spin.setRange(0, 999_999)
        start_spin.setSingleStep(100)
        start_spin.setValue(b["start_ms"])
        start_spin.valueChanged.connect(lambda v, bid=b["id"]: self._set_block_field(bid, "start_ms", v))
        end_spin = QSpinBox()
        end_spin.setRange(0, 999_999)
        end_spin.setSingleStep(100)
        end_spin.setValue(b["end_ms"])
        end_spin.valueChanged.connect(lambda v, bid=b["id"]: self._set_block_field(bid, "end_ms", v))
        delete_btn = QPushButton()
        delete_btn.setProperty("variant", "danger")
        delete_btn.clicked.connect(lambda _c=False, bid=b["id"]: self._delete_block(bid))
        self._set_delete_text(delete_btn)
        time_row.addWidget(start_spin)
        time_row.addWidget(end_spin)
        time_row.addWidget(delete_btn)
        lay.addLayout(time_row)

        text_edit = QTextEdit()
        text_edit.setFixedHeight(56)
        text_edit.setPlainText(b["ar"])
        text_edit.setLayoutDirection(Qt.RightToLeft)
        text_edit.textChanged.connect(lambda te=text_edit, bid=b["id"]: self._set_block_field(bid, "ar", te.toPlainText()))
        lay.addWidget(text_edit)

        if "en" in self.active_langs:
            en_text = self.translations.get("en", {}).get(b["id"], "—")
            lay.addWidget(CaptionLabel(t("sub.en_line", text=en_text)))

        return card

    @staticmethod
    def _set_delete_text(btn: QPushButton):
        btn.setText(t("sub.btn.delete"))

    def _set_block_field(self, block_id: int, field: str, value):
        block = next(b for b in self.blocks if b["id"] == block_id)
        block[field] = value
        if field == "ar":
            self._render_style_preview()

    def _delete_block(self, block_id: int):
        self.blocks = [b for b in self.blocks if b["id"] != block_id]
        self._render_blocks()

    def _add_block(self):
        new_id = (max((b["id"] for b in self.blocks), default=-1)) + 1
        last_end = self.blocks[-1]["end_ms"] if self.blocks else 0
        self.blocks.append({"id": new_id, "start_ms": last_end, "end_ms": last_end + 2000, "ar": ""})
        self._render_blocks()

    # ------------------------------------------------------------------
    # timing shift
    # ------------------------------------------------------------------
    def _build_shift_section(self, parent_lay: QVBoxLayout):
        self.shift_title = SectionLabel()
        parent_lay.addWidget(self.shift_title)
        row = QHBoxLayout()
        self.shift_label = QLabel()
        row.addWidget(self.shift_label)
        self.shift_spin = QSpinBox()
        self.shift_spin.setRange(-999_999, 999_999)
        self.shift_spin.setSingleStep(50)
        self.shift_spin.valueChanged.connect(self._on_shift_changed)
        row.addWidget(self.shift_spin)
        self.shift_preview_label = QLabel()
        row.addWidget(self.shift_preview_label, 1)
        parent_lay.addLayout(row)
        self.apply_shift_btn = QPushButton()
        self.apply_shift_btn.setEnabled(False)
        self.apply_shift_btn.clicked.connect(self._apply_shift)
        parent_lay.addWidget(self.apply_shift_btn)

    def _on_shift_changed(self, value: int):
        self.shift_ms = value
        self.apply_shift_btn.setEnabled(value != 0)
        self._render_shift_preview()

    def _render_shift_preview(self):
        if not self.blocks:
            self.shift_preview_label.setText("")
            return
        b0 = self.blocks[0]
        start = ms_to_srt_ts(b0["start_ms"] + self.shift_ms)[3:]
        end = ms_to_srt_ts(b0["end_ms"] + self.shift_ms)[3:]
        self.shift_preview_label.setText(t("sub.shift.preview", start=start, end=end))

    def _apply_shift(self):
        for b in self.blocks:
            b["start_ms"] = max(0, b["start_ms"] + self.shift_ms)
            b["end_ms"] = max(0, b["end_ms"] + self.shift_ms)
        self.shift_ms = 0
        self.shift_spin.setValue(0)
        self._render_blocks()

    # ------------------------------------------------------------------
    # caption styling
    # ------------------------------------------------------------------
    def _build_style_section(self, parent_lay: QVBoxLayout):
        self.style_title = SectionLabel()
        parent_lay.addWidget(self.style_title)

        row = QHBoxLayout()
        col1 = QVBoxLayout()
        self.font_label = QLabel()
        col1.addWidget(self.font_label)
        self.font_combo = QComboBox()
        self.font_combo.addItems(FONTS)
        self.font_combo.currentTextChanged.connect(self._on_style_font)
        col1.addWidget(self.font_combo)
        self.size_label = QLabel()
        col1.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(16, 48)
        self.size_slider.setValue(self.style["size"])
        self.size_slider.valueChanged.connect(self._on_style_size)
        col1.addWidget(self.size_slider)
        row.addLayout(col1)

        col2 = QVBoxLayout()
        self.color_label = QLabel()
        col2.addWidget(self.color_label)
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self._pick_color)
        col2.addWidget(self.color_btn)
        self.position_label = QLabel()
        col2.addWidget(self.position_label)
        pos_row = QHBoxLayout()
        self.top_radio = QRadioButton()
        self.top_radio.toggled.connect(lambda checked: self._on_position_changed("top") if checked else None)
        self.bottom_radio = QRadioButton()
        self.bottom_radio.setChecked(True)
        self.bottom_radio.toggled.connect(lambda checked: self._on_position_changed("bottom") if checked else None)
        pos_row.addWidget(self.top_radio)
        pos_row.addWidget(self.bottom_radio)
        col2.addLayout(pos_row)
        row.addLayout(col2)

        col3 = QVBoxLayout()
        self.bg_check = QCheckBox()
        self.bg_check.setChecked(True)
        self.bg_check.toggled.connect(self._on_bg_toggled)
        col3.addWidget(self.bg_check)
        self.bg_opacity_label = QLabel()
        col3.addWidget(self.bg_opacity_label)
        self.bg_opacity_slider = QSlider(Qt.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(self.style["bg_opacity"])
        self.bg_opacity_slider.valueChanged.connect(self._on_bg_opacity_changed)
        col3.addWidget(self.bg_opacity_slider)
        row.addLayout(col3)
        parent_lay.addLayout(row)

        preview_row = QHBoxLayout()
        self.preview_block_label = QLabel()
        preview_row.addWidget(self.preview_block_label)
        self.preview_block_combo = QComboBox()
        self.preview_block_combo.currentIndexChanged.connect(self._on_preview_block_changed)
        preview_row.addWidget(self.preview_block_combo, 1)
        parent_lay.addLayout(preview_row)

        self.preview_frame = QLabel()
        self.preview_frame.setFixedSize(QSize(480, 270))
        self.preview_frame.setAlignment(Qt.AlignCenter)
        self.preview_frame.setStyleSheet("background:#101114; border-radius:12px;")
        parent_lay.addWidget(self.preview_frame)

        self.preview_caption = QLabel(self.preview_frame)
        self.preview_caption.setAlignment(Qt.AlignCenter)
        self.preview_caption.setWordWrap(True)
        self.preview_caption.setLayoutDirection(Qt.RightToLeft)

        self.style_note = CaptionLabel()
        parent_lay.addWidget(self.style_note)

    def _on_style_font(self, font: str):
        self.style["font"] = font
        self._render_style_preview()

    def _on_style_size(self, value: int):
        self.style["size"] = value
        self._render_style_preview()

    def _pick_color(self):
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self.style["color"]), self)
        if color.isValid():
            self.style["color"] = color.name()
            self._render_style_preview()

    def _on_position_changed(self, pos: str):
        self.style["position"] = pos
        self._render_style_preview()

    def _on_bg_toggled(self, checked: bool):
        self.style["bg_on"] = checked
        self.bg_opacity_slider.setEnabled(checked)
        self._render_style_preview()

    def _on_bg_opacity_changed(self, value: int):
        self.style["bg_opacity"] = value
        self._render_style_preview()

    def _on_preview_block_changed(self, index: int):
        self.preview_block = max(0, index)
        self._render_style_preview()

    def _render_style_preview(self):
        self.preview_block_combo.blockSignals(True)
        current = self.preview_block_combo.currentIndex()
        self.preview_block_combo.clear()
        self.preview_block_combo.addItems([t("sub.style.block_n", n=i + 1) for i in range(len(self.blocks))])
        if self.blocks:
            self.preview_block_combo.setCurrentIndex(min(max(0, current), len(self.blocks) - 1) if current >= 0 else 0)
        self.preview_block_combo.blockSignals(False)

        if not self.blocks:
            self.preview_frame.setPixmap(QPixmap())
            self.preview_caption.setText("")
            return

        idx = min(self.preview_block, len(self.blocks) - 1)
        pb = self.blocks[idx]
        scene_pix = QPixmap(str(self.scenes[idx % len(self.scenes)])).scaled(
            self.preview_frame.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        self.preview_frame.setPixmap(scene_pix)

        text = pb["ar"] or t("sub.style.empty_block")
        bg = f"background: rgba(0,0,0,{self.style['bg_opacity'] / 100:.2f});" if self.style["bg_on"] else ""
        self.preview_caption.setStyleSheet(
            f"{bg} color:{self.style['color']}; font-size:{self.style['size']}px; font-family:'{self.style['font']}'; border-radius:8px; padding:6px 10px;"
        )
        self.preview_caption.setText(text)
        self.preview_caption.adjustSize()
        frame_w = self.preview_frame.width()
        cap_w = min(frame_w - 40, max(200, self.preview_caption.sizeHint().width()))
        self.preview_caption.setFixedWidth(cap_w)
        self.preview_caption.adjustSize()
        x = (frame_w - self.preview_caption.width()) // 2
        y = 16 if self.style["position"] == "top" else self.preview_frame.height() - self.preview_caption.height() - 16
        self.preview_caption.move(x, y)
        self.preview_caption.show()

    # ------------------------------------------------------------------
    # language / dubbing
    # ------------------------------------------------------------------
    def _build_language_section(self, parent_lay: QVBoxLayout):
        self.lang_title = SectionLabel()
        parent_lay.addWidget(self.lang_title)
        self.lang_desc = CaptionLabel()
        parent_lay.addWidget(self.lang_desc)
        self.lang_row = QHBoxLayout()
        parent_lay.addLayout(self.lang_row)

    def _render_languages(self):
        clear_layout(self.lang_row)
        for code, key in LANGUAGES:
            col = QVBoxLayout()
            if code in ALWAYS_ON:
                badge = StatusBadge(f"✓ {t(key)}", tone="success", dark=self._dark)
                col.addWidget(badge)
            else:
                check = QCheckBox(t(key))
                check.setChecked(code in self.active_langs)
                check.toggled.connect(lambda checked, c=code: self._on_lang_toggled(c, checked))
                col.addWidget(check)
                status = self.lang_status[code]
                if code in self.active_langs:
                    if status == "not_translated":
                        btn = QPushButton(t("sub.btn.translate"))
                        btn.clicked.connect(lambda _c=False, c=code: self._translate(c))
                        col.addWidget(btn)
                    elif status == "translated":
                        col.addWidget(StatusBadge(t("sub.translated"), tone="success", dark=self._dark))
                    elif status == "failed":
                        col.addWidget(StatusBadge(t("sub.translate_failed"), tone="danger", dark=self._dark))
                        retry_btn = QPushButton(t("sub.btn.retry"))
                        retry_btn.setProperty("variant", "primary")
                        retry_btn.clicked.connect(lambda _c=False, c=code: self._translate(c))
                        col.addWidget(retry_btn)
            self.lang_row.addLayout(col)

    def _on_lang_toggled(self, code: str, checked: bool):
        if checked:
            self.active_langs.add(code)
        else:
            self.active_langs.discard(code)
        self._render_languages()

    def _translate(self, code: str):
        self._render_languages()
        self._run_worker(lambda: __import__("time").sleep(0.5), lambda: self._finish_translate(code))

    def _finish_translate(self, code: str):
        attempts = self.lang_attempts.get(code, 0)
        if code == FAIL_LANG and attempts == 0:
            self.lang_status[code] = "failed"
            self.lang_attempts[code] = attempts + 1
        else:
            lang_name = next(t(k) for c, k in LANGUAGES if c == code)
            self.translations[code] = {b["id"]: f"[{lang_name}] {EN_TRANSLATION.get(b['id'], b['ar'])}" for b in self.blocks}
            self.lang_status[code] = "translated"
            self.lang_attempts[code] = attempts + 1
        self._render_languages()

    # ------------------------------------------------------------------
    # per-scene override
    # ------------------------------------------------------------------
    def _build_override_section(self, parent_lay: QVBoxLayout):
        self.override_title = SectionLabel()
        parent_lay.addWidget(self.override_title)
        self.override_grid = QVBoxLayout()
        parent_lay.addLayout(self.override_grid)

    def _render_overrides(self):
        clear_layout(self.override_grid)
        options = ["global"] + [code for code, _k in LANGUAGES]
        for i in range(NUM_SCENES):
            row = QHBoxLayout()
            row.addWidget(CaptionLabel(t("sub.override.scene", n=i + 1)))
            combo = QComboBox()
            for opt in options:
                label = t("sub.override.use_global") if opt == "global" else t(next(k for c, k in LANGUAGES if c == opt))
                combo.addItem(label, opt)
            combo.setCurrentIndex(options.index(self.scene_overrides[i]))
            combo.currentIndexChanged.connect(lambda idx, scene=i, opts=options: self._set_override(scene, opts[idx]))
            row.addWidget(combo, 1)
            self.override_grid.addLayout(row)

    def _set_override(self, scene: int, value: str):
        self.scene_overrides[scene] = value

    # ------------------------------------------------------------------
    # SRT import/export + burn-in
    # ------------------------------------------------------------------
    def _build_io_section(self, parent_lay: QVBoxLayout):
        self.io_title = SectionLabel()
        parent_lay.addWidget(self.io_title)
        row = QHBoxLayout()
        self.import_btn = QPushButton()
        self.import_btn.clicked.connect(self._import_srt)
        row.addWidget(self.import_btn)
        self.export_btn = QPushButton()
        self.export_btn.clicked.connect(self._export_srt)
        row.addWidget(self.export_btn)
        parent_lay.addLayout(row)
        self.import_note = QLabel()
        self.import_note.setWordWrap(True)
        self.import_note.setVisible(False)
        parent_lay.addWidget(self.import_note)

        burn_row = QHBoxLayout()
        self.burn_in_check = QCheckBox()
        self.burn_in_check.toggled.connect(self._on_burn_in_toggled)
        burn_row.addWidget(self.burn_in_check)
        self.burn_in_caption = CaptionLabel()
        burn_row.addWidget(self.burn_in_caption, 1)
        parent_lay.addLayout(burn_row)

    def _import_srt(self):
        path, _f = QFileDialog.getOpenFileName(self, t("sub.io.import"), "", "SRT (*.srt)")
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        count = sum(1 for line in text.splitlines() if "-->" in line)
        self.import_note.setText(t("sub.io.import_note", n=count))
        self.import_note.setVisible(True)

    def _export_srt(self):
        path, _f = QFileDialog.getSaveFileName(self, t("sub.io.export"), "subtitles.srt", "SRT (*.srt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(blocks_to_srt(self.blocks))

    def _on_burn_in_toggled(self, checked: bool):
        self.burn_in = checked

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("sub.subtitle"))
        self.empty_label.setText(t("sub.empty"))
        self.auto_gen_btn.setText(t("sub.btn.auto_generate"))

        self.sync_warning.setText(t("sub.out_of_sync"))
        self.sim_desync_btn.setText(t("sub.btn.sim_desync"))
        self.sim_desync_caption.setText(t("sub.sim_desync_caption"))
        self._render_sync()

        self.blocks_title.setText(t("sub.blocks.title"))
        self.add_block_btn.setText(t("sub.btn.add_block"))
        self._render_blocks()

        self.shift_title.setText(t("sub.shift.title"))
        self.shift_label.setText(t("sub.shift.label"))
        self.apply_shift_btn.setText(t("sub.btn.apply_shift"))
        self._render_shift_preview()

        self.style_title.setText(t("sub.style.title"))
        self.font_label.setText(t("sub.style.font"))
        self.size_label.setText(t("sub.style.size"))
        self.color_label.setText(t("sub.style.color"))
        self.color_btn.setText(self.style["color"])
        self.position_label.setText(t("sub.style.position"))
        self.top_radio.setText(t("sub.style.top"))
        self.bottom_radio.setText(t("sub.style.bottom"))
        self.bg_check.setText(t("sub.style.bg"))
        self.bg_opacity_label.setText(t("sub.style.bg_opacity"))
        self.preview_block_label.setText(t("sub.style.preview_block"))
        self.style_note.setText(t("sub.style.note"))
        self._render_style_preview()

        self.lang_title.setText(t("sub.lang.title"))
        self.lang_desc.setText(t("sub.lang.desc"))
        self._render_languages()

        self.override_title.setText(t("sub.override.title"))
        self._render_overrides()

        self.io_title.setText(t("sub.io.title"))
        self.import_btn.setText(t("sub.io.import"))
        self.export_btn.setText(t("sub.io.export"))
        self.burn_in_check.setText(t("sub.burn_in"))
        self.burn_in_caption.setText(t("sub.burn_in.caption"))

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_languages()
