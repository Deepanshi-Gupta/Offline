"""Native PySide6 port of voice_cloning_app.py (§5 of the UI audit) —
Voice/TTS & Voice Cloning: per-character voice assignment, TTS/clone
generation (worker thread), a 12-voice library browser with preview, a
21-dialect honesty table, a speed control with presets, and the
enhancement/library-fallback/background-audio sections from the client
spec. No local TTS model is wired in — generated/cloned/preview audio are
short synthesized tones (common/audio.py), same as the Streamlit source.
"""

from PySide6.QtCore import QSize, Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.audio import load_wav_samples, samples_to_wav_bytes, synth_tone
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import AudioPlayer, Card, CaptionLabel, SectionLabel, Waveform, clear_layout, show_toast
from common.style import face_paths
from common.voices import DIALECTS, QUALITY_COLORS, SPEED_PRESETS, VOICES, voice_preview_path
from common.workers import Worker

VOICE_NAMES = [f"{v['icon']} {v['name']}" for v in VOICES]
DIALECT_NAMES = [d["name"] for d in DIALECTS]
QUALITY_LABEL_KEY = {
    "high": "voice.quality.high_label",
    "medium": "voice.quality.medium_label",
    "low": "voice.quality.low_label",
    "unsupported": "voice.quality.unsupported_label",
}
QUALITY_WORD_KEY = {
    "high": "voice.quality.high",
    "medium": "voice.quality.medium",
    "low": "voice.quality.low",
    "unsupported": "voice.quality.unsupported",
}


def quality_dot_widget(quality: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    dot = QFrame()
    dot.setFixedSize(9, 9)
    dot.setStyleSheet(f"background:{QUALITY_COLORS.get(quality, '#9AA0A6')}; border-radius:4px;")
    label = QLabel(t(QUALITY_LABEL_KEY.get(quality, "voice.quality.unsupported_label")))
    label.setStyleSheet("font-size:11.5px;")
    lay.addWidget(dot)
    lay.addWidget(label)
    return w


class VoiceScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._workers = []
        self.faces = face_paths()
        self.char_voice_idx = [0, 3, 5]
        self.speaking_as = 0
        self.speed = 1.0
        self.dialect_selected = DIALECT_NAMES[0]
        self.gen_audio = None
        self.clone_audio = None
        self.ref_audio_path = None
        self._preview_open = set()
        self._player = AudioPlayer(self)

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(18)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_section_a()
        self.outer.addWidget(self._hr())
        self._build_library_section()
        self.outer.addWidget(self._hr())
        self._build_dialect_section()
        self.outer.addWidget(self._hr())
        self._build_speed_section()
        self.outer.addWidget(self._hr())
        self._build_enhance_section()
        self._build_static_sections()
        self.outer.addWidget(self._hr())
        self._build_library_fallback_section()
        self.outer.addWidget(self._hr())
        self._build_background_audio_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    @staticmethod
    def _hr() -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setProperty("role", "divider")
        return line

    def _section_header(self, icon="🎤") -> tuple[QWidget, QLabel]:
        row = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setFixedSize(34, 34)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background:#16171A; color:white; border-radius:17px; font-size:16px;")
        title = SectionLabel()
        row.addWidget(icon_label)
        row.addWidget(title)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        return wrap, title

    # ------------------------------------------------------------------
    def _build_section_a(self):
        head, self.a_title = self._section_header("🎙️")
        self.outer.addWidget(head)

        row = QHBoxLayout()
        left = QVBoxLayout()
        face_row = QHBoxLayout()
        self._char_combos = []
        self._char_captions = []
        for i, path in enumerate(self.faces[:3]):
            col = QVBoxLayout()
            img = QLabel()
            pix = QPixmap(str(path))
            img.setPixmap(pix.scaled(QSize(120, 120), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            img.setFixedSize(120, 120)
            img.setScaledContents(True)
            col.addWidget(img)
            combo = QComboBox()
            combo.addItems(VOICE_NAMES)
            combo.setCurrentIndex(self.char_voice_idx[i])
            combo.currentIndexChanged.connect(lambda idx, ci=i: self._set_char_voice(ci, idx))
            col.addWidget(combo)
            caption = CaptionLabel()
            col.addWidget(caption)
            self._char_combos.append(combo)
            self._char_captions.append(caption)
            face_row.addLayout(col)
        left.addLayout(face_row)
        row.addLayout(left, 3)

        right = QVBoxLayout()
        self.speaking_as_label = QLabel()
        right.addWidget(self.speaking_as_label)
        self.speaking_as_combo = QComboBox()
        self.speaking_as_combo.addItems([f"Character {i + 1}" for i in range(3)])
        self.speaking_as_combo.currentIndexChanged.connect(self._set_speaking_as)
        right.addWidget(self.speaking_as_combo)

        self.tts_text = QTextEdit()
        self.tts_text.setFixedHeight(80)
        right.addWidget(self.tts_text)

        self.generate_voice_btn = QPushButton()
        self.generate_voice_btn.setProperty("variant", "primary")
        self.generate_voice_btn.clicked.connect(self._generate_voice)
        right.addWidget(self.generate_voice_btn)

        self.gen_audio_caption = CaptionLabel()
        self.gen_audio_caption.setVisible(False)
        right.addWidget(self.gen_audio_caption)
        self.gen_play_btn = QPushButton("▶")
        self.gen_play_btn.setVisible(False)
        self.gen_play_btn.clicked.connect(lambda: self._player.play_bytes(self.gen_audio[0]) if self.gen_audio else None)
        right.addWidget(self.gen_play_btn)
        self.gen_waveform = Waveform()
        self.gen_waveform.setVisible(False)
        right.addWidget(self.gen_waveform)

        self.ref_audio_btn = QPushButton()
        self.ref_audio_btn.clicked.connect(self._pick_ref_audio)
        right.addWidget(self.ref_audio_btn)
        self.clone_voice_btn = QPushButton()
        self.clone_voice_btn.setProperty("variant", "primary")
        self.clone_voice_btn.clicked.connect(self._clone_voice)
        right.addWidget(self.clone_voice_btn)

        self.clone_audio_caption = CaptionLabel()
        self.clone_audio_caption.setVisible(False)
        right.addWidget(self.clone_audio_caption)
        self.clone_play_btn = QPushButton("▶")
        self.clone_play_btn.setVisible(False)
        self.clone_play_btn.clicked.connect(lambda: self._player.play_bytes(self.clone_audio[0]) if self.clone_audio else None)
        right.addWidget(self.clone_play_btn)
        self.clone_waveform = Waveform()
        self.clone_waveform.setVisible(False)
        right.addWidget(self.clone_waveform)

        row.addLayout(right, 2)
        self.outer.addLayout(row)

    def _set_char_voice(self, char_idx: int, voice_idx: int):
        self.char_voice_idx[char_idx] = voice_idx

    def _set_speaking_as(self, idx: int):
        self.speaking_as = idx

    @staticmethod
    def _placeholder_audio(base_freq: float):
        samples = synth_tone([base_freq, base_freq * 1.25, base_freq * 1.5], duration_each=0.22)
        return samples_to_wav_bytes(samples), samples

    def _generate_voice(self):
        voice_idx = self.char_voice_idx[self.speaking_as]
        voice = VOICES[voice_idx]
        if not self.tts_text.toPlainText().strip():
            show_toast(self, t("voice.warn.no_text"), dark=self._dark)
            return
        if voice["quality"] == "unsupported":
            show_toast(self, t("voice.warn.unsupported", voice=voice["name"]), dark=self._dark)
            return

        worker = Worker(self._placeholder_audio, 200 + voice_idx * 12 * self.speed)
        self._workers.append(worker)

        def done(result):
            if worker in self._workers:
                self._workers.remove(worker)
            audio_bytes, samples = result
            self.gen_audio = (audio_bytes, samples, voice["name"])
            self._render_gen_audio()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def _render_gen_audio(self):
        if not self.gen_audio:
            return
        audio_bytes, samples, voice_name = self.gen_audio
        self.gen_audio_caption.setText(t("voice.generated_caption", voice=voice_name))
        self.gen_audio_caption.setVisible(True)
        self.gen_play_btn.setVisible(True)
        self.gen_waveform.set_samples(samples)
        self.gen_waveform.setVisible(True)

    def _pick_ref_audio(self):
        path, _f = QFileDialog.getOpenFileName(self, t("voice.ref_audio_ph"), "", "Audio (*.wav *.mp3 *.m4a)")
        if path:
            self.ref_audio_path = path

    def _clone_voice(self):
        if not self.ref_audio_path:
            show_toast(self, t("voice.warn.no_ref"), dark=self._dark)
            return
        import os

        size = os.path.getsize(self.ref_audio_path)
        base = 180 + (size % 40)

        worker = Worker(self._placeholder_audio, base)
        self._workers.append(worker)

        def done(result):
            if worker in self._workers:
                self._workers.remove(worker)
            audio_bytes, samples = result
            self.clone_audio = (audio_bytes, samples)
            self._render_clone_audio()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def _render_clone_audio(self):
        if not self.clone_audio:
            return
        _audio_bytes, samples = self.clone_audio
        self.clone_audio_caption.setText(t("voice.cloned_caption"))
        self.clone_audio_caption.setVisible(True)
        self.clone_play_btn.setVisible(True)
        self.clone_waveform.set_samples(samples)
        self.clone_waveform.setVisible(True)

    # ------------------------------------------------------------------
    def _build_library_section(self):
        head, self.g_title = self._section_header("📚")
        self.outer.addWidget(head)
        self.g_desc = CaptionLabel()
        self.outer.addWidget(self.g_desc)

        self.library_grid = QVBoxLayout()
        self.outer.addLayout(self.library_grid)
        self._render_library()

    def _render_library(self):
        clear_layout(self.library_grid)
        for row_start in range(0, len(VOICES), 3):
            row = QHBoxLayout()
            for i in range(row_start, min(row_start + 3, len(VOICES))):
                row.addWidget(self._build_voice_card(i))
            self.library_grid.addLayout(row)

    def _build_voice_card(self, i: int) -> QWidget:
        voice = VOICES[i]
        card = Card(flat=True, margins=(10, 8, 10, 8), spacing=4)
        lay = card.layout()
        lay.addWidget(QLabel(f"{voice['icon']} {voice['name']}"))
        lay.addWidget(CaptionLabel(voice["use_case"]))
        lay.addWidget(CaptionLabel(f"🗣️ {voice['best_for']}"))
        lay.addWidget(quality_dot_widget(voice["quality"]))

        if voice["quality"] == "unsupported":
            btn = QPushButton(t("voice.btn.preview"))
            btn.setEnabled(False)
            lay.addWidget(btn)
            lay.addWidget(CaptionLabel(t("voice.preview_unavailable")))
        else:
            btn = QPushButton(t("voice.btn.preview"))
            btn.clicked.connect(lambda _c=False, idx=i: self._toggle_preview(idx))
            lay.addWidget(btn)
            if i in self._preview_open:
                play_btn = QPushButton("▶")
                play_btn.clicked.connect(lambda _c=False, idx=i: self._play_preview(idx))
                lay.addWidget(play_btn)
                samples = load_wav_samples(voice_preview_path(i))
                wf = Waveform(samples)
                lay.addWidget(wf)
        return card

    def _toggle_preview(self, idx: int):
        self._preview_open.symmetric_difference_update({idx})
        self._render_library()

    def _play_preview(self, idx: int):
        with open(voice_preview_path(idx), "rb") as f:
            self._player.play_bytes(f.read())

    # ------------------------------------------------------------------
    def _build_dialect_section(self):
        head, self.dialect_title = self._section_header("🌍")
        self.outer.addWidget(head)
        self.dialect_desc = CaptionLabel()
        self.outer.addWidget(self.dialect_desc)

        self.active_dialect_label = QLabel()
        self.outer.addWidget(self.active_dialect_label)
        self.dialect_combo = QComboBox()
        self.dialect_combo.addItems(DIALECT_NAMES)
        self.dialect_combo.currentTextChanged.connect(self._on_dialect_changed)
        self.outer.addWidget(self.dialect_combo)

        self.dialect_warning = QLabel()
        self.dialect_warning.setWordWrap(True)
        self.dialect_warning.setVisible(False)
        self.outer.addWidget(self.dialect_warning)

        self.dialect_rows_layout = QVBoxLayout()
        self.outer.addLayout(self.dialect_rows_layout)
        self._render_dialect_rows()

    def _on_dialect_changed(self, text: str):
        self.dialect_selected = text
        self._render_dialect_warning()

    def _render_dialect_warning(self):
        active = next(d for d in DIALECTS if d["name"] == self.dialect_selected)
        s = semantic(self._dark)
        if active["quality"] in ("low", "unsupported"):
            self.dialect_warning.setText(
                t("voice.dialect_warning", dialect=active["name"], quality=t(QUALITY_WORD_KEY[active["quality"]]))
            )
            self.dialect_warning.setStyleSheet(f"color:{s['warning_fg_strong']}; background:{s['warning_bg']}; border-radius:8px; padding:6px 10px;")
            self.dialect_warning.setVisible(True)
        else:
            self.dialect_warning.setVisible(False)

    def _render_dialect_rows(self):
        clear_layout(self.dialect_rows_layout)
        for row_start in range(0, len(DIALECTS), 3):
            row = QHBoxLayout()
            for i in range(row_start, min(row_start + 3, len(DIALECTS))):
                d = DIALECTS[i]
                item = QHBoxLayout()
                label = QLabel(f"{d['name']} ({d['ar']})")
                item.addWidget(label)
                item.addWidget(quality_dot_widget(d["quality"]))
                row.addLayout(item)
            self.dialect_rows_layout.addLayout(row)

    # ------------------------------------------------------------------
    def _build_speed_section(self):
        head, self.speed_title = self._section_header("⏱️")
        self.outer.addWidget(head)

        preset_row = QHBoxLayout()
        self._preset_buttons = {}
        for label_key in ("voice.speed.slow", "voice.speed.normal", "voice.speed.fast", "voice.speed.sprint"):
            btn = QPushButton()
            btn.clicked.connect(lambda _c=False, k=label_key: self._apply_speed_preset(k))
            preset_row.addWidget(btn)
            self._preset_buttons[label_key] = btn
        self.outer.addLayout(preset_row)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(int(self.speed * 100))
        self.speed_slider.valueChanged.connect(self._on_speed_slider)
        self.outer.addWidget(self.speed_slider)

        self.speed_caption = CaptionLabel()
        self.outer.addWidget(self.speed_caption)

    def _apply_speed_preset(self, label_key: str):
        preset_name = {"voice.speed.slow": "Slow", "voice.speed.normal": "Normal", "voice.speed.fast": "Fast", "voice.speed.sprint": "Sprint"}[label_key]
        self.speed = SPEED_PRESETS[preset_name]
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(int(self.speed * 100))
        self.speed_slider.blockSignals(False)
        self._render_speed_caption()

    def _on_speed_slider(self, value: int):
        self.speed = value / 100.0
        self._render_speed_caption()

    def _render_speed_caption(self):
        preset_key = "voice.speed.custom"
        for name, val in SPEED_PRESETS.items():
            if abs(val - self.speed) < 0.01:
                preset_key = {"Slow": "voice.speed.slow", "Normal": "voice.speed.normal", "Fast": "voice.speed.fast", "Sprint": "voice.speed.sprint"}[name]
                break
        self.speed_caption.setText(t("voice.speed.caption", speed=f"{self.speed:.2f}", preset=t(preset_key)))

    # ------------------------------------------------------------------
    def _build_enhance_section(self):
        row = QHBoxLayout()
        left = QVBoxLayout()
        head, self.s_title = self._section_header("🎧")
        left.addWidget(head)
        self.s_desc = CaptionLabel()
        left.addWidget(self.s_desc)
        row.addLayout(left, 3)
        self.enhance_btn = QPushButton()
        self.enhance_btn.setProperty("variant", "primary")
        self.enhance_btn.clicked.connect(self._enhance_voice)
        row.addWidget(self.enhance_btn, 1)
        self.outer.addLayout(row)

    def _enhance_voice(self):
        worker = Worker(lambda: __import__("time").sleep(0.5))
        self._workers.append(worker)

        def done(_r=None):
            if worker in self._workers:
                self._workers.remove(worker)
            show_toast(self, t("voice.enhance_done"), dark=self._dark)

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    # ------------------------------------------------------------------
    def _build_static_sections(self):
        head7, self.sec7_title = self._section_header("🌀")
        self.outer.addWidget(head7)
        self.sec7_desc = CaptionLabel()
        self.outer.addWidget(self.sec7_desc)

        head8, self.sec8_title = self._section_header("8")
        self.outer.addWidget(head8)
        self.sec8_desc = CaptionLabel()
        self.outer.addWidget(self.sec8_desc)

    def _build_library_fallback_section(self):
        row = QHBoxLayout()
        left = QVBoxLayout()
        head, self.f_title = self._section_header("👥")
        left.addWidget(head)
        self.f_desc = CaptionLabel()
        left.addWidget(self.f_desc)
        row.addLayout(left, 3)
        self.library_gen_btn = QPushButton()
        self.library_gen_btn.setProperty("variant", "primary")
        self.library_gen_btn.clicked.connect(self._generate_from_library)
        row.addWidget(self.library_gen_btn, 1)
        self.outer.addLayout(row)

        head_g2, self.g2_title = self._section_header("📋")
        self.outer.addWidget(head_g2)
        self.g2_desc = CaptionLabel()
        self.outer.addWidget(self.g2_desc)

    def _generate_from_library(self):
        fallback_voice = VOICES[7]  # Neutral Educator
        worker = Worker(self._placeholder_audio, 260)
        self._workers.append(worker)

        def done(result):
            if worker in self._workers:
                self._workers.remove(worker)
            audio_bytes, samples = result
            self.gen_audio = (audio_bytes, samples, fallback_voice["name"])
            self._render_gen_audio()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def _build_background_audio_section(self):
        row = QHBoxLayout()
        left = QVBoxLayout()
        head, self.h_title = self._section_header("🎧")
        left.addWidget(head)
        self.h_desc = CaptionLabel()
        left.addWidget(self.h_desc)
        self.match_reference_check = QCheckBox()
        self.match_reference_check.setChecked(True)
        left.addWidget(self.match_reference_check)
        self.fallback_audio_check = QCheckBox()
        self.fallback_audio_check.setChecked(True)
        left.addWidget(self.fallback_audio_check)
        self.skip_caption = CaptionLabel()
        left.addWidget(self.skip_caption)
        row.addLayout(left, 3)
        self.skip_step_btn = QPushButton()
        self.skip_step_btn.setProperty("variant", "primary")
        row.addWidget(self.skip_step_btn, 1)
        self.outer.addLayout(row)

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("voice.subtitle"))
        self.a_title.setText(t("voice.sec.a.title"))
        for i, caption in enumerate(self._char_captions):
            caption.setText(t("voice.character", n=i + 1))
        self.speaking_as_label.setText(t("voice.speaking_as"))
        self.tts_text.setPlaceholderText(t("voice.tts_text_ph"))
        self.generate_voice_btn.setText(t("voice.btn.generate"))
        self.ref_audio_btn.setText(t("voice.ref_audio_ph"))
        self.clone_voice_btn.setText(t("voice.btn.clone"))
        self._render_gen_audio()
        self._render_clone_audio()

        self.g_title.setText(t("voice.sec.g.title"))
        self.g_desc.setText(t("voice.sec.g.desc"))
        self._render_library()

        self.dialect_title.setText(t("voice.sec.dialect.title"))
        self.dialect_desc.setText(t("voice.sec.dialect.desc"))
        self.active_dialect_label.setText(t("voice.active_dialect"))
        self._render_dialect_warning()
        self._render_dialect_rows()

        self.speed_title.setText(t("voice.sec.speed.title"))
        for key, btn in self._preset_buttons.items():
            btn.setText(t(key))
        self._render_speed_caption()

        self.s_title.setText(t("voice.sec.s.title"))
        self.s_desc.setText(t("voice.sec.s.desc"))
        self.enhance_btn.setText(t("voice.btn.enhance"))

        self.sec7_title.setText(t("voice.sec.7.title"))
        self.sec7_desc.setText(t("voice.sec.7.desc"))
        self.sec8_title.setText(t("voice.sec.8a.title"))
        self.sec8_desc.setText(t("voice.sec.8a.desc"))

        self.f_title.setText(t("voice.sec.f.title"))
        self.f_desc.setText(t("voice.sec.f.desc"))
        self.library_gen_btn.setText(t("voice.btn.library_generate"))
        self.g2_title.setText(t("voice.sec.g2.title"))
        self.g2_desc.setText(t("voice.sec.g2.desc"))

        self.h_title.setText(t("voice.sec.h.title"))
        self.h_desc.setText(t("voice.sec.h.desc"))
        self.match_reference_check.setText(t("voice.match_reference"))
        self.fallback_audio_check.setText(t("voice.fallback_audio"))
        self.skip_caption.setText(t("voice.skip_caption"))
        self.skip_step_btn.setText(t("voice.btn.skip_step"))

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_dialect_warning()
