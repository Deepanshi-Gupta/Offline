"""Native PySide6 port of §16 (Standalone Tools).

The full catalog of pipeline stages that Task 3 requires to also be usable
on their own, each as a self-contained utility: Demucs (audio clean-up →
−14 LUFS) and Whisper (audio → transcript + SRT) keep rich, bespoke panels;
the rest — NLLB translation, text-to-speech, image generation, lip-sync and
motion generation — are data-driven SimpleToolPanels (see TOOLS). Every tool
uses the same skeleton: a standard QTabWidget, one input picker, a run
button, progress, and a result panel. No real engine is wired in; processing
is simulated. A filename containing "fail"/"corrupt" drives the Failed state
so it can be exercised.
"""

import math

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, Waveform, show_toast

TICK_MS = 110


def _wave(n=180, noisy=False):
    out = []
    for i in range(n):
        v = math.sin(i * 0.20) * 0.6 + math.sin(i * 0.05) * 0.3
        if noisy:
            v += math.sin(i * 1.7) * 0.35 + math.sin(i * 0.9) * 0.2
        out.append(v)
    return out


class ToolPanel(QWidget):
    """Shared skeleton: input picker → run → progress → result / failed."""

    INPUT_FILTER_KEY = "tools.dialog.audio_filter"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        self.selected = None          # basename of the chosen input, or None
        self.status = "empty"         # empty | processing | complete | failed
        self._progress = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(4, 8, 4, 4)
        self.root.setSpacing(12)

        self.desc = CaptionLabel()
        self.root.addWidget(self.desc)

        # input row
        input_card = Card()
        in_lay = input_card.layout()
        self.input_label = SectionLabel()
        in_lay.addWidget(self.input_label)
        row = QHBoxLayout()
        self.choose_btn = QPushButton()
        self.choose_btn.clicked.connect(self._choose)
        row.addWidget(self.choose_btn)
        self.file_label = CaptionLabel()
        row.addWidget(self.file_label, 1)
        in_lay.addLayout(row)
        self.root.addWidget(input_card)

        self._build_body(self.root)  # subclass content

        self.run_btn = QPushButton()
        self.run_btn.setProperty("variant", "primary")
        self.run_btn.clicked.connect(self._run)
        self.root.addWidget(self.run_btn)

        self.progress_label = CaptionLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.root.addWidget(self.progress_label)
        self.root.addWidget(self.progress_bar)

        self.failed_label = CaptionLabel()
        self.failed_label.setWordWrap(True)
        self.retry_btn = QPushButton()
        self.retry_btn.setProperty("variant", "primary")
        self.retry_btn.clicked.connect(self._run)
        self.root.addWidget(self.failed_label)
        self.root.addWidget(self.retry_btn)

        self.root.addStretch(1)

    # -- hooks subclasses override --------------------------------------
    def _build_body(self, layout):
        self.result_group = QWidget()
        layout.addWidget(self.result_group)

    def _render_result(self):
        pass

    def _retranslate_body(self):
        pass

    def _run_label_key(self):
        return "tools.processing"

    # -- flow -----------------------------------------------------------
    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, t("tools.btn.choose"), "", t(self.INPUT_FILTER_KEY))
        if not path:
            return
        self.selected = path.replace("\\", "/").split("/")[-1]
        self.status = "empty"
        self._render()

    def _run(self):
        if not self.selected:
            return
        self.status = "processing"
        self._progress = 0.0
        self._timer.start()
        self._render()

    def _on_tick(self):
        self._progress = min(1.0, self._progress + 0.09)
        self.progress_bar.setValue(int(self._progress * 100))
        if self._progress >= 1.0:
            self._timer.stop()
            fail = any(w in (self.selected or "").lower() for w in ("fail", "corrupt"))
            self.status = "failed" if fail else "complete"
            self._render()

    def _render(self):
        s = semantic(self._dark)
        self.file_label.setText(self.selected or t("tools.input.none"))
        self.run_btn.setEnabled(self.selected is not None and self.status != "processing")

        processing = self.status == "processing"
        self.progress_label.setVisible(processing)
        self.progress_bar.setVisible(processing)
        if processing:
            self.progress_label.setText(t("tools.processing"))

        failed = self.status == "failed"
        self.failed_label.setVisible(failed)
        self.retry_btn.setVisible(failed)
        if failed:
            self.failed_label.setText(t("tools.failed"))
            self.failed_label.setStyleSheet(f"color:{s['danger_fg_strong']};")

        self.result_group.setVisible(self.status == "complete")
        if self.status == "complete":
            self._render_result()

    def retranslate(self):
        self.choose_btn.setText(t("tools.btn.choose"))
        self.input_label.setText(t("tools.input.label"))
        self._retranslate_body()
        self._render()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render()


class DemucsPanel(ToolPanel):
    def _build_body(self, layout):
        self.result_group = QWidget()
        gl = QVBoxLayout(self.result_group)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        self.before_label = CaptionLabel()
        gl.addWidget(self.before_label)
        self.before_wave = Waveform(_wave(noisy=True), color="#B42318")
        gl.addWidget(self.before_wave)
        self.after_label = CaptionLabel()
        gl.addWidget(self.after_label)
        self.after_wave = Waveform(_wave(noisy=False), color="#187A43")
        gl.addWidget(self.after_wave)
        self.done_label = CaptionLabel()
        gl.addWidget(self.done_label)
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(lambda: show_toast(self, t("tools.demucs.saved_toast"), dark=self._dark))
        gl.addWidget(self.save_btn)
        layout.addWidget(self.result_group)

    def _render_result(self):
        self.before_wave.set_samples(_wave(noisy=True), color=semantic(self._dark)["danger_fg"])
        self.after_wave.set_samples(_wave(noisy=False), color=semantic(self._dark)["success_fg"])

    def _retranslate_body(self):
        self.desc.setText(t("tools.demucs.desc"))
        self.run_btn.setText(t("tools.demucs.btn.run"))
        self.before_label.setText(t("tools.demucs.before"))
        self.after_label.setText(t("tools.demucs.after"))
        self.done_label.setText(t("tools.demucs.done"))
        self.save_btn.setText(t("tools.demucs.btn.save"))


class WhisperPanel(ToolPanel):
    DIALECTS = ["العربية (فصحى)", "مصري", "خليجي", "شامي", "مغربي", "English"]

    def _build_body(self, layout):
        self.result_group = QWidget()
        gl = QVBoxLayout(self.result_group)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        self.accuracy_label = QLabel()
        self.accuracy_label.setStyleSheet("font-weight:700;")
        gl.addWidget(self.accuracy_label)
        self.transcript_label = SectionLabel()
        gl.addWidget(self.transcript_label)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setFixedHeight(96)
        gl.addWidget(self.transcript)
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(lambda: show_toast(self, t("tools.whisper.saved_toast"), dark=self._dark))
        gl.addWidget(self.save_btn)
        layout.addWidget(self.result_group)

    def _render_result(self):
        self.accuracy_label.setText(t("tools.whisper.accuracy", pct=94))
        self.transcript.setPlainText(t("tools.whisper.sample_text"))

    def _retranslate_body(self):
        self.desc.setText(t("tools.whisper.desc"))
        self.run_btn.setText(t("tools.whisper.btn.run"))
        self.lang_label.setText(t("tools.whisper.lang.label"))
        self.transcript_label.setText(t("tools.whisper.transcript"))
        self.save_btn.setText(t("tools.whisper.btn.save"))
        if self.status == "complete":
            self.accuracy_label.setText(t("tools.whisper.accuracy", pct=94))
            self.transcript.setPlainText(t("tools.whisper.sample_text"))

    # Whisper adds a language/dialect selector above the run button.
    def __init__(self, parent=None):
        super().__init__(parent)
        # insert the language selector just before the run button
        lang_card = Card()
        cl = lang_card.layout()
        self.lang_label = SectionLabel()
        cl.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(self.DIALECTS)
        cl.addWidget(self.lang_combo)
        # place it right after the input card (index 2: desc=0, input=1)
        self.root.insertWidget(2, lang_card)


class SimpleToolPanel(ToolPanel):
    """A tool whose result is a single success badge + summary line + save
    button — the common shape for the pipeline stages that also run
    standalone (translate, TTS, image-gen, lip-sync, motion). Each instance
    is configured by a small spec dict so a new standalone tool is one entry
    in TOOLS, not a new class."""

    def __init__(self, spec: dict, parent=None):
        self._spec = spec
        self.INPUT_FILTER_KEY = spec["filter_key"]
        super().__init__(parent)

    def _build_body(self, layout):
        self.result_group = QWidget()
        gl = QVBoxLayout(self.result_group)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        self.result_badge = StatusBadge(t("tools.result.done"), tone="success", dark=self._dark)
        gl.addWidget(self.result_badge)
        self.result_line = CaptionLabel()
        self.result_line.setWordWrap(True)
        gl.addWidget(self.result_line)
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(lambda: show_toast(self, t("tools.saved_toast_generic"), dark=self._dark))
        gl.addWidget(self.save_btn)
        layout.addWidget(self.result_group)

    def _render_result(self):
        self.result_badge.set_tone("success", self._dark)
        self.result_badge.setText(t("tools.result.done"))
        self.result_line.setText(t(self._spec["result_key"]))

    def _retranslate_body(self):
        self.desc.setText(t(self._spec["desc_key"]))
        self.run_btn.setText(t(self._spec["run_key"]))
        self.save_btn.setText(t("tools.btn.save_generic"))
        if self.status == "complete":
            self.result_line.setText(t(self._spec["result_key"]))


# The standalone-tool catalog. Demucs and Whisper keep their rich, bespoke
# panels; the remaining pipeline stages that Task 3 requires to be
# independently usable are data-driven SimpleToolPanels.
TOOLS = [
    {"key": "translate", "tab": "tools.tab.translate", "desc_key": "tools.translate.desc",
     "run_key": "tools.translate.btn.run", "result_key": "tools.translate.result", "filter_key": "tools.dialog.text_filter"},
    {"key": "tts", "tab": "tools.tab.tts", "desc_key": "tools.tts.desc",
     "run_key": "tools.tts.btn.run", "result_key": "tools.tts.result", "filter_key": "tools.dialog.text_filter"},
    {"key": "imagegen", "tab": "tools.tab.imagegen", "desc_key": "tools.imagegen.desc",
     "run_key": "tools.imagegen.btn.run", "result_key": "tools.imagegen.result", "filter_key": "tools.dialog.image_filter"},
    {"key": "lipsync", "tab": "tools.tab.lipsync", "desc_key": "tools.lipsync.desc",
     "run_key": "tools.lipsync.btn.run", "result_key": "tools.lipsync.result", "filter_key": "tools.dialog.video_filter"},
    {"key": "motion", "tab": "tools.tab.motion", "desc_key": "tools.motion.desc",
     "run_key": "tools.motion.btn.run", "result_key": "tools.motion.result", "filter_key": "tools.dialog.image_filter"},
]


class StandaloneToolsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.subtitle = CaptionLabel()
        lay.addWidget(self.subtitle)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        # the two rich bespoke panels first, then the data-driven catalog
        self.demucs = DemucsPanel()
        self.whisper = WhisperPanel()
        self._panels = [("tools.tab.demucs", self.demucs), ("tools.tab.whisper", self.whisper)]
        for spec in TOOLS:
            self._panels.append((spec["tab"], SimpleToolPanel(spec)))
        for _tab_key, panel in self._panels:
            self.tabs.addTab(panel, "")
        lay.addWidget(self.tabs, 1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    def retranslate(self):
        self.subtitle.setText(t("tools.subtitle"))
        for i, (tab_key, panel) in enumerate(self._panels):
            self.tabs.setTabText(i, t(tab_key))
            panel.retranslate()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        for _tab_key, panel in self._panels:
            panel.set_dark(dark)
