"""Native PySide6 screen for the Smart Edit Layer (Task 11).

The Arabic-first, timecoded editing layer that sits on top of a generated
video. Four pieces the audit calls out:

* **Timecoded Arabic-prompt editor** — free-text instructions in Arabic, each
  scoped to a start/end timecode.
* **Quality Guard integration** — an automatic post-edit check pass that
  surfaces warnings and auto-fixes what it can.
* **Timecoded Voice Speed Edit** — change speech speed within a range without
  altering pitch.
* **Timecoded Singing Pronunciation Fix** — correct a sung word's
  pronunciation within a range. (Singing *generation* itself stays deferred
  pending the client's dataset/licensing decision — see the note; this only
  stages the fixes.)

No real edit engine is wired in; actions mutate the in-memory model and
re-render, matching every other converted screen. Follows the app
i18n / set_dark conventions (common/i18n.py).
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout, show_toast

# Quality Guard checks and the (simulated) verdict each returns: pass / warn /
# fixed. A mix so every state is visible after a run.
QG_CHECKS = [
    ("exposure", "se.qg.check.exposure", "pass"),
    ("audio", "se.qg.check.audio", "fixed"),
    ("compliance", "se.qg.check.compliance", "pass"),
    ("sync", "se.qg.check.sync", "warn"),
]
QG_TONE = {"pass": "success", "warn": "warning", "fixed": "info"}
QG_LABEL = {"pass": "se.qg.pass", "warn": "se.qg.warn", "fixed": "se.qg.fixed"}
QG_TICK_MS = 120


class SmartEditScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False

        self.prompts = []   # {start, end, text}
        self.speeds = []    # {start, end, speed}
        self.fixes = []     # {start, end, word, fix}
        self.qg_state = "idle"   # idle | checking | done
        self._qg_progress = 0.0

        self._qg_timer = QTimer(self)
        self._qg_timer.setInterval(QG_TICK_MS)
        self._qg_timer.timeout.connect(self._on_qg_tick)

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(16)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_prompt_section()
        self._build_qg_section()
        self._build_speed_section()
        self._build_sing_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    @staticmethod
    def _range_row(from_key: str, to_key: str, end_default: float):
        """A shared (from-s, to-s) timecode entry pair. Returns
        (layout, from_label, from_spin, to_label, to_spin)."""
        row = QHBoxLayout()
        from_label = QLabel()
        from_spin = QDoubleSpinBox()
        from_spin.setRange(0.0, 3600.0)
        from_spin.setSingleStep(0.5)
        to_label = QLabel()
        to_spin = QDoubleSpinBox()
        to_spin.setRange(0.0, 3600.0)
        to_spin.setSingleStep(0.5)
        to_spin.setValue(end_default)
        row.addWidget(from_label)
        row.addWidget(from_spin)
        row.addWidget(to_label)
        row.addWidget(to_spin)
        return row, from_label, from_spin, to_label, to_spin

    # ------------------------------------------------------------------
    # Timecoded Arabic-prompt editor
    # ------------------------------------------------------------------
    def _build_prompt_section(self):
        self.prompt_title = SectionLabel()
        self.outer.addWidget(self.prompt_title)
        self.prompt_desc = CaptionLabel()
        self.outer.addWidget(self.prompt_desc)

        form = Card()
        fl = form.layout()
        (row, self.p_from_label, self.p_from_spin,
         self.p_to_label, self.p_to_spin) = self._range_row("se.prompt.from", "se.prompt.to", 4.0)
        fl.addLayout(row)
        self.p_text_label = QLabel()
        fl.addWidget(self.p_text_label)
        self.p_text = QTextEdit()
        self.p_text.setFixedHeight(56)
        self.p_text.setLayoutDirection(Qt.RightToLeft)
        fl.addWidget(self.p_text)
        self.p_add_btn = QPushButton()
        self.p_add_btn.setProperty("variant", "primary")
        self.p_add_btn.clicked.connect(self._add_prompt)
        fl.addWidget(self.p_add_btn)
        self.outer.addWidget(form)

        self.prompt_empty = CaptionLabel()
        self.outer.addWidget(self.prompt_empty)
        self.prompt_list = QVBoxLayout()
        self.prompt_list.setSpacing(8)
        self.outer.addLayout(self.prompt_list)

        self.p_apply_btn = QPushButton()
        self.p_apply_btn.clicked.connect(self._apply_prompts)
        self.outer.addWidget(self.p_apply_btn)

    def _add_prompt(self):
        text = self.p_text.toPlainText().strip()
        if not text:
            return
        self.prompts.append({"start": self.p_from_spin.value(), "end": self.p_to_spin.value(), "text": text})
        self.p_text.clear()
        self._render_prompts()

    def _render_prompts(self):
        clear_layout(self.prompt_list)
        self.prompt_empty.setVisible(not self.prompts)
        for i, p in enumerate(self.prompts):
            card = Card(flat=True, margins=(12, 8, 12, 8), spacing=4)
            head = QHBoxLayout()
            rng = StatusBadge(t("se.prompt.range", start=self._fmt(p["start"]), end=self._fmt(p["end"])),
                              tone="info", dark=self._dark)
            head.addWidget(rng)
            head.addStretch(1)
            remove = QPushButton(t("se.prompt.remove"))
            remove.setProperty("variant", "danger")
            remove.clicked.connect(lambda _c=False, idx=i: self._remove_prompt(idx))
            head.addWidget(remove)
            card.layout().addLayout(head)
            text = QLabel(p["text"])
            text.setWordWrap(True)
            text.setLayoutDirection(Qt.RightToLeft)
            card.layout().addWidget(text)
            self.prompt_list.addWidget(card)
        self.p_apply_btn.setEnabled(bool(self.prompts))

    def _remove_prompt(self, idx: int):
        del self.prompts[idx]
        self._render_prompts()

    def _apply_prompts(self):
        if not self.prompts:
            return
        show_toast(self, t("se.prompt.applied_toast", n=len(self.prompts)), dark=self._dark)

    # ------------------------------------------------------------------
    # Quality Guard
    # ------------------------------------------------------------------
    def _build_qg_section(self):
        self.qg_title = SectionLabel()
        self.outer.addWidget(self.qg_title)
        self.qg_desc = CaptionLabel()
        self.outer.addWidget(self.qg_desc)
        self.qg_run_btn = QPushButton()
        self.qg_run_btn.setProperty("variant", "primary")
        self.qg_run_btn.clicked.connect(self._run_qg)
        self.outer.addWidget(self.qg_run_btn)
        self.qg_bar = QProgressBar()
        self.qg_bar.setRange(0, 100)
        self.qg_bar.setVisible(False)
        self.outer.addWidget(self.qg_bar)
        self.qg_results = QVBoxLayout()
        self.qg_results.setSpacing(6)
        self.outer.addLayout(self.qg_results)

    def _run_qg(self):
        self.qg_state = "checking"
        self._qg_progress = 0.0
        clear_layout(self.qg_results)
        self.qg_bar.setValue(0)
        self.qg_bar.setVisible(True)
        self.qg_run_btn.setEnabled(False)
        self.qg_run_btn.setText(t("se.qg.checking"))
        self._qg_timer.start()

    def _on_qg_tick(self):
        self._qg_progress = min(1.0, self._qg_progress + 0.12)
        self.qg_bar.setValue(int(self._qg_progress * 100))
        if self._qg_progress >= 1.0:
            self._qg_timer.stop()
            self.qg_state = "done"
            self.qg_bar.setVisible(False)
            self.qg_run_btn.setEnabled(True)
            self.qg_run_btn.setText(t("se.qg.run"))
            self._render_qg_results()

    def _render_qg_results(self):
        clear_layout(self.qg_results)
        if self.qg_state != "done":
            return
        for _key, label_key, verdict in QG_CHECKS:
            row = QHBoxLayout()
            row.addWidget(CaptionLabel(t(label_key)), 1)
            row.addWidget(StatusBadge(t(QG_LABEL[verdict]), tone=QG_TONE[verdict], dark=self._dark))
            wrap = QWidget()
            wrap.setLayout(row)
            self.qg_results.addWidget(wrap)

    # ------------------------------------------------------------------
    # Timecoded Voice Speed Edit
    # ------------------------------------------------------------------
    def _build_speed_section(self):
        self.speed_title = SectionLabel()
        self.outer.addWidget(self.speed_title)
        self.speed_desc = CaptionLabel()
        self.outer.addWidget(self.speed_desc)

        form = Card()
        fl = form.layout()
        (row, self.s_from_label, self.s_from_spin,
         self.s_to_label, self.s_to_spin) = self._range_row("se.prompt.from", "se.prompt.to", 4.0)
        self.s_speed_label = QLabel()
        row.addWidget(self.s_speed_label)
        self.s_speed_spin = QDoubleSpinBox()
        self.s_speed_spin.setRange(0.5, 2.0)
        self.s_speed_spin.setSingleStep(0.05)
        self.s_speed_spin.setValue(1.0)
        row.addWidget(self.s_speed_spin)
        row.addStretch(1)
        fl.addLayout(row)
        self.s_add_btn = QPushButton()
        self.s_add_btn.setProperty("variant", "primary")
        self.s_add_btn.clicked.connect(self._add_speed)
        fl.addWidget(self.s_add_btn)
        self.outer.addWidget(form)

        self.speed_empty = CaptionLabel()
        self.outer.addWidget(self.speed_empty)
        self.speed_list = QVBoxLayout()
        self.speed_list.setSpacing(8)
        self.outer.addLayout(self.speed_list)

    def _add_speed(self):
        self.speeds.append({"start": self.s_from_spin.value(), "end": self.s_to_spin.value(),
                            "speed": self.s_speed_spin.value()})
        self._render_speeds()

    def _render_speeds(self):
        clear_layout(self.speed_list)
        self.speed_empty.setVisible(not self.speeds)
        for i, sp in enumerate(self.speeds):
            card = Card(flat=True, margins=(12, 8, 12, 8), spacing=4)
            row = QHBoxLayout()
            row.addWidget(StatusBadge(t("se.prompt.range", start=self._fmt(sp["start"]), end=self._fmt(sp["end"])),
                                      tone="info", dark=self._dark))
            row.addWidget(QLabel(f"{t('se.speed.label')} {sp['speed']:.2f}×"))
            row.addStretch(1)
            remove = QPushButton(t("se.prompt.remove"))
            remove.setProperty("variant", "danger")
            remove.clicked.connect(lambda _c=False, idx=i: self._remove_speed(idx))
            row.addWidget(remove)
            card.layout().addLayout(row)
            self.speed_list.addWidget(card)

    def _remove_speed(self, idx: int):
        del self.speeds[idx]
        self._render_speeds()

    # ------------------------------------------------------------------
    # Timecoded Singing Pronunciation Fix
    # ------------------------------------------------------------------
    def _build_sing_section(self):
        self.sing_title = SectionLabel()
        self.outer.addWidget(self.sing_title)
        self.sing_desc = CaptionLabel()
        self.outer.addWidget(self.sing_desc)
        self.sing_deferred = CaptionLabel()
        self.outer.addWidget(self.sing_deferred)

        form = Card()
        fl = form.layout()
        (row, self.g_from_label, self.g_from_spin,
         self.g_to_label, self.g_to_spin) = self._range_row("se.prompt.from", "se.prompt.to", 4.0)
        row.addStretch(1)
        fl.addLayout(row)
        word_row = QHBoxLayout()
        self.g_word_label = QLabel()
        word_row.addWidget(self.g_word_label)
        self.g_word = QLineEdit()
        self.g_word.setLayoutDirection(Qt.RightToLeft)
        word_row.addWidget(self.g_word, 1)
        self.g_fix_label = QLabel()
        word_row.addWidget(self.g_fix_label)
        self.g_fix = QLineEdit()
        self.g_fix.setLayoutDirection(Qt.RightToLeft)
        word_row.addWidget(self.g_fix, 1)
        fl.addLayout(word_row)
        self.g_add_btn = QPushButton()
        self.g_add_btn.setProperty("variant", "primary")
        self.g_add_btn.clicked.connect(self._add_fix)
        fl.addWidget(self.g_add_btn)
        self.outer.addWidget(form)

        self.sing_empty = CaptionLabel()
        self.outer.addWidget(self.sing_empty)
        self.sing_list = QVBoxLayout()
        self.sing_list.setSpacing(8)
        self.outer.addLayout(self.sing_list)

    def _add_fix(self):
        word = self.g_word.text().strip()
        fix = self.g_fix.text().strip()
        if not word or not fix:
            return
        self.fixes.append({"start": self.g_from_spin.value(), "end": self.g_to_spin.value(),
                           "word": word, "fix": fix})
        self.g_word.clear()
        self.g_fix.clear()
        self._render_fixes()

    def _render_fixes(self):
        clear_layout(self.sing_list)
        self.sing_empty.setVisible(not self.fixes)
        for i, fx in enumerate(self.fixes):
            card = Card(flat=True, margins=(12, 8, 12, 8), spacing=4)
            row = QHBoxLayout()
            row.addWidget(StatusBadge(t("se.prompt.range", start=self._fmt(fx["start"]), end=self._fmt(fx["end"])),
                                      tone="info", dark=self._dark))
            pair = QLabel(f"{fx['word']} → {fx['fix']}")
            pair.setLayoutDirection(Qt.RightToLeft)
            row.addWidget(pair, 1)
            remove = QPushButton(t("se.prompt.remove"))
            remove.setProperty("variant", "danger")
            remove.clicked.connect(lambda _c=False, idx=i: self._remove_fix(idx))
            row.addWidget(remove)
            card.layout().addLayout(row)
            self.sing_list.addWidget(card)

    def _remove_fix(self, idx: int):
        del self.fixes[idx]
        self._render_fixes()

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt(seconds: float) -> str:
        return f"{seconds:g}"

    def retranslate(self):
        self.subtitle.setText(t("se.subtitle"))

        self.prompt_title.setText(t("se.prompt.title"))
        self.prompt_desc.setText(t("se.prompt.desc"))
        self.p_from_label.setText(t("se.prompt.from"))
        self.p_to_label.setText(t("se.prompt.to"))
        self.p_text_label.setText(t("se.prompt.text"))
        self.p_text.setPlaceholderText(t("se.prompt.placeholder"))
        self.p_add_btn.setText(t("se.prompt.add"))
        self.prompt_empty.setText(t("se.prompt.empty"))
        self.p_apply_btn.setText(t("se.prompt.apply"))
        self._render_prompts()

        self.qg_title.setText(t("se.qg.title"))
        self.qg_desc.setText(t("se.qg.desc"))
        self.qg_run_btn.setText(t("se.qg.checking") if self.qg_state == "checking" else t("se.qg.run"))
        self._render_qg_results()

        self.speed_title.setText(t("se.speed.title"))
        self.speed_desc.setText(t("se.speed.desc"))
        self.s_from_label.setText(t("se.prompt.from"))
        self.s_to_label.setText(t("se.prompt.to"))
        self.s_speed_label.setText(t("se.speed.label"))
        self.s_add_btn.setText(t("se.speed.add"))
        self.speed_empty.setText(t("se.speed.empty"))
        self._render_speeds()

        self.sing_title.setText(t("se.sing.title"))
        self.sing_desc.setText(t("se.sing.desc"))
        self.sing_deferred.setText(t("se.sing.deferred"))
        self.g_from_label.setText(t("se.prompt.from"))
        self.g_to_label.setText(t("se.prompt.to"))
        self.g_word_label.setText(t("se.sing.word"))
        self.g_fix_label.setText(t("se.sing.fix"))
        self.g_add_btn.setText(t("se.sing.add"))
        self.sing_empty.setText(t("se.sing.empty"))
        self._render_fixes()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_prompts()
        self._render_qg_results()
        self._render_speeds()
        self._render_fixes()
