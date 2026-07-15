"""Native PySide6 port of audio_layering_app.py (§7 of the UI audit) —
the biggest single screen: a 16-category sound library browser, real
religious-compliance blocking logic (not cosmetic), a 5-track mixer with
mute/solo/volume/fade, an auto-duck level + LUFS meter, and a Demucs
standalone tool. No real audio engine is wired in — every sample is a
short synthesized placeholder tone (common/audio.py), and Demucs
processing is a simulated multi-stage progress run on a worker thread.
"""

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from common.audio import samples_to_wav_bytes, synth_tone
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import AudioPlayer, Card, CaptionLabel, SectionLabel, Waveform, clear_layout, show_toast
from common.sound_library import ASSETS, CATEGORIES, EMPTY_CATEGORIES, FLAG_LABELS, assets_in_category
from common.workers import Worker

TRACK_NAMES = ["Dialogue", "Music", "SFX Layer 1", "SFX Layer 2", "Ambience"]
DEFAULT_TRACK_FOR_FLAG = {"music": "Music", "oud": "Music", "tarab": "Music", "neutral": "SFX Layer 1"}


def flag_badge_widget(flag: str) -> QWidget:
    label, color = FLAG_LABELS.get(flag, ("Neutral", "#6B6E76"))
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color:{color}; background:{color}22; border-radius:999px; padding:2px 10px; font-size:10.5px; font-weight:700;")
    return lbl


class AudioLayeringScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._workers = []
        self._player = AudioPlayer(self)

        self.compliance_on = True
        self.sacred_context = False
        self.category_selected = CATEGORIES[0]
        self.search_query = ""
        self.tracks = {
            name: {"volume": 70, "mute": False, "solo": False, "fade_in": 0.5, "fade_out": 0.5} for name in TRACK_NAMES
        }
        self.auto_duck = True
        self.mix_layers = []
        self.demucs_result = None
        self._preview_open = set()
        self._audio_cache = {}

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(16)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_compliance_card()
        self.outer.addWidget(self._hr())
        self._build_library_section()
        self.outer.addWidget(self._hr())
        self._build_mixer_section()
        self.outer.addWidget(self._hr())
        self._build_demucs_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    @staticmethod
    def _hr() -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setProperty("role", "divider")
        return line

    def _asset_samples(self, asset_id: int):
        if asset_id not in self._audio_cache:
            base = 180 + (asset_id * 17) % 260
            samples = synth_tone([base, base * 1.2, base * 0.9], duration_each=0.2)
            self._audio_cache[asset_id] = (samples_to_wav_bytes(samples), samples)
        return self._audio_cache[asset_id]

    def _is_blocked(self, asset: dict):
        if not self.compliance_on:
            return False, None
        if self.sacred_context and asset["flag"] in ("music", "oud", "tarab"):
            return True, t("audio.blocked_reason")
        return False, None

    # ------------------------------------------------------------------
    # religious compliance
    # ------------------------------------------------------------------
    def _build_compliance_card(self):
        self.compliance_card = Card()
        lay = self.compliance_card.layout()
        self.compliance_title = SectionLabel()
        lay.addWidget(self.compliance_title)

        row = QHBoxLayout()
        self.compliance_check = QCheckBox()
        self.compliance_check.setChecked(True)
        self.compliance_check.toggled.connect(self._on_compliance_toggled)
        row.addWidget(self.compliance_check)
        self.sacred_check = QCheckBox()
        self.sacred_check.toggled.connect(self._on_sacred_toggled)
        row.addWidget(self.sacred_check)
        lay.addLayout(row)

        self.compliance_note = QLabel()
        self.compliance_note.setWordWrap(True)
        lay.addWidget(self.compliance_note)
        self.outer.addWidget(self.compliance_card)

    def _on_compliance_toggled(self, checked: bool):
        self.compliance_on = checked
        self.sacred_check.setEnabled(checked)
        self._render_compliance_note()
        self._render_library()

    def _on_sacred_toggled(self, checked: bool):
        self.sacred_context = checked
        self._render_compliance_note()
        self._render_library()

    def _render_compliance_note(self):
        s = semantic(self._dark)
        blocked_count = sum(1 for a in ASSETS if self._is_blocked(a)[0])
        if self.compliance_on and self.sacred_context:
            self.compliance_note.setText(t("audio.compliance.blocked_note", blocked=blocked_count, total=len(ASSETS)))
            self.compliance_note.setStyleSheet(f"color:{s['danger_fg_strong']}; background:{s['danger_bg']}; border-radius:8px; padding:6px 10px; font-weight:600;")
        elif self.compliance_on:
            self.compliance_note.setText(t("audio.compliance.ok_note"))
            self.compliance_note.setStyleSheet(f"color:{s['ink_faint']};")
        else:
            self.compliance_note.setText(t("audio.compliance.off_note"))
            self.compliance_note.setStyleSheet(f"color:{s['ink_faint']};")

    # ------------------------------------------------------------------
    # sound library
    # ------------------------------------------------------------------
    def _build_library_section(self):
        self.library_title = SectionLabel()
        self.outer.addWidget(self.library_title)

        filter_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItems(CATEGORIES)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        filter_row.addWidget(self.category_combo, 1)
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self.search_edit, 1)
        self.outer.addLayout(filter_row)

        self.library_grid = QGridLayout()
        self.library_grid.setSpacing(10)
        self.outer.addLayout(self.library_grid)
        self.library_empty_label = QLabel()
        self.library_empty_label.setWordWrap(True)
        self.outer.addWidget(self.library_empty_label)

    def _on_category_changed(self, text: str):
        self.category_selected = text
        self._render_library()

    def _on_search_changed(self, text: str):
        self.search_query = text
        self._render_library()

    def _render_library(self):
        clear_layout(self.library_grid)
        cat = self.category_selected
        if cat in EMPTY_CATEGORIES:
            self.library_empty_label.setText(t("audio.category.empty", cat=cat))
            self.library_empty_label.setVisible(True)
            return

        items = assets_in_category(cat)
        q = self.search_query.strip().lower()
        if q:
            items = [a for a in items if q in a["name"].lower()]
        if not items:
            self.library_empty_label.setText(t("audio.no_match"))
            self.library_empty_label.setVisible(True)
            return
        self.library_empty_label.setVisible(False)

        for i, asset in enumerate(items):
            card = self._build_asset_card(asset)
            row, col = divmod(i, 3)
            self.library_grid.addWidget(card, row, col)

    def _build_asset_card(self, asset: dict) -> QWidget:
        card = Card(flat=True, margins=(10, 8, 10, 8), spacing=4)
        lay = card.layout()
        name_label = QLabel(asset["name"])
        name_label.setStyleSheet("font-weight:700;")
        lay.addWidget(name_label)
        lay.addWidget(CaptionLabel(f"{asset['era']} · {asset['region']}"))
        lay.addWidget(flag_badge_widget(asset["flag"]))

        blocked, reason = self._is_blocked(asset)
        if blocked:
            s = semantic(self._dark)
            note = QLabel(t("audio.blocked_note", reason=reason))
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{s['danger_fg_strong']}; font-size:10.5px; font-weight:600;")
            lay.addWidget(note)

        btn_row = QHBoxLayout()
        preview_btn = QPushButton(t("audio.btn.preview"))
        preview_btn.clicked.connect(lambda _c=False, aid=asset["id"]: self._toggle_preview(aid))
        add_btn = QPushButton(t("audio.btn.add_to_mix"))
        add_btn.setEnabled(not blocked)
        add_btn.clicked.connect(lambda _c=False, a=asset: self._add_to_mix(a))
        btn_row.addWidget(preview_btn)
        btn_row.addWidget(add_btn)
        lay.addLayout(btn_row)

        if asset["id"] in self._preview_open:
            _wav_bytes, samples = self._asset_samples(asset["id"])
            wf = Waveform(samples, color="#2F6FEF")
            wf.setFixedHeight(36)
            lay.addWidget(wf)

        return card

    def _toggle_preview(self, asset_id: int):
        self._preview_open.symmetric_difference_update({asset_id})
        wav_bytes, _samples = self._asset_samples(asset_id)
        if asset_id in self._preview_open:
            self._player.play_bytes(wav_bytes)
        self._render_library()

    def _add_to_mix(self, asset: dict):
        track = DEFAULT_TRACK_FOR_FLAG[asset["flag"]]
        self.mix_layers.append({"asset_id": asset["id"], "track": track})
        show_toast(self, t("audio.added_toast", name=asset["name"], track=track), dark=self._dark)
        self._render_mix_layers()

    # ------------------------------------------------------------------
    # mixer
    # ------------------------------------------------------------------
    def _build_mixer_section(self):
        self.mixer_title = SectionLabel()
        self.outer.addWidget(self.mixer_title)

        tracks_row = QHBoxLayout()
        self._track_widgets = {}
        for name in TRACK_NAMES:
            tracks_row.addWidget(self._build_track_card(name))
        self.outer.addLayout(tracks_row)

        duck_row = QHBoxLayout()
        self.autoduck_check = QCheckBox()
        self.autoduck_check.setChecked(True)
        self.autoduck_check.toggled.connect(self._on_autoduck_toggled)
        duck_row.addWidget(self.autoduck_check)
        self.autoduck_caption = CaptionLabel()
        duck_row.addWidget(self.autoduck_caption, 1)
        self.outer.addLayout(duck_row)

        self.lufs_label = QLabel()
        self.outer.addWidget(self.lufs_label)
        self.lufs_bar = QProgressBar()
        self.lufs_bar.setRange(0, 100)
        self.lufs_bar.setTextVisible(False)
        self.lufs_bar.setFixedHeight(14)
        self.outer.addWidget(self.lufs_bar)

        self.assigned_title = SectionLabel()
        self.outer.addWidget(self.assigned_title)
        self.assigned_layout = QVBoxLayout()
        self.outer.addLayout(self.assigned_layout)

    def _build_track_card(self, name: str) -> QWidget:
        card = Card(flat=True, margins=(10, 8, 10, 8), spacing=6)
        lay = card.layout()
        track_name_label = QLabel(name)
        track_name_label.setStyleSheet("font-weight:700;")
        lay.addWidget(track_name_label)

        btn_row = QHBoxLayout()
        mute_check = QCheckBox(t("audio.track.mute"))
        mute_check.setChecked(self.tracks[name]["mute"])
        mute_check.toggled.connect(lambda checked, n=name: self._set_track_field(n, "mute", checked))
        solo_check = QCheckBox(t("audio.track.solo"))
        solo_check.setChecked(self.tracks[name]["solo"])
        solo_check.toggled.connect(lambda checked, n=name: self._set_track_field(n, "solo", checked))
        btn_row.addWidget(mute_check)
        btn_row.addWidget(solo_check)
        lay.addLayout(btn_row)

        volume_slider = QSlider(Qt.Horizontal)
        volume_slider.setRange(0, 100)
        volume_slider.setValue(self.tracks[name]["volume"])
        volume_slider.valueChanged.connect(lambda v, n=name: self._set_track_field(n, "volume", v))
        lay.addWidget(volume_slider)

        fade_row = QHBoxLayout()
        fade_in_spin = QDoubleSpinBox()
        fade_in_spin.setRange(0.0, 5.0)
        fade_in_spin.setSingleStep(0.25)
        fade_in_spin.setValue(self.tracks[name]["fade_in"])
        fade_in_spin.valueChanged.connect(lambda v, n=name: self._set_track_field(n, "fade_in", v))
        fade_out_spin = QDoubleSpinBox()
        fade_out_spin.setRange(0.0, 5.0)
        fade_out_spin.setSingleStep(0.25)
        fade_out_spin.setValue(self.tracks[name]["fade_out"])
        fade_out_spin.valueChanged.connect(lambda v, n=name: self._set_track_field(n, "fade_out", v))
        fade_row.addWidget(fade_in_spin)
        fade_row.addWidget(fade_out_spin)
        lay.addLayout(fade_row)

        self._track_widgets[name] = {
            "mute": mute_check, "solo": solo_check, "volume": volume_slider,
            "fade_in": fade_in_spin, "fade_out": fade_out_spin,
        }
        return card

    def _set_track_field(self, name: str, field: str, value):
        self.tracks[name][field] = value
        self._render_mixer_summary()

    def _on_autoduck_toggled(self, checked: bool):
        self.auto_duck = checked
        self._render_mixer_summary()

    def _render_mixer_summary(self):
        s = semantic(self._dark)
        music = self.tracks["Music"]
        if self.auto_duck and not music["mute"]:
            ducked = max(0, music["volume"] - 18)
            self.autoduck_caption.setText(t("audio.autoduck.on_caption", ducked=ducked, orig=music["volume"]))
        else:
            self.autoduck_caption.setText(t("audio.autoduck.off_caption"))

        any_solo = any(tr["solo"] for tr in self.tracks.values())
        active_volumes = []
        for tr in self.tracks.values():
            if tr["mute"]:
                continue
            if any_solo and not tr["solo"]:
                continue
            active_volumes.append(tr["volume"])
        avg_vol = (sum(active_volumes) / len(active_volumes)) if active_volumes else 0
        lufs = -30 + (avg_vol / 100) * 16
        target = -14.0
        diff = abs(lufs - target)
        color = s["success_fg"] if diff <= 1 else (s["warning_fg"] if diff <= 4 else "#E2622A")
        lufs_pct = max(0, min(100, (lufs + 40) / 30 * 100))
        self.lufs_label.setText(t("audio.lufs.title", current=f"{lufs:.1f}", target=f"{target:.0f}"))
        self.lufs_bar.setValue(int(lufs_pct))
        self.lufs_bar.setStyleSheet(f"QProgressBar::chunk {{ background:{color}; border-radius:6px; }}")

    def _render_mix_layers(self):
        clear_layout(self.assigned_layout)
        for j, layer in enumerate(list(self.mix_layers)):
            asset = next(a for a in ASSETS if a["id"] == layer["asset_id"])
            row = QHBoxLayout()
            row.addWidget(CaptionLabel(f"{asset['name']} ({asset['category']})"), 2)
            combo = QComboBox()
            combo.addItems(TRACK_NAMES)
            combo.setCurrentText(layer["track"])
            combo.currentTextChanged.connect(lambda text, idx=j: self._set_layer_track(idx, text))
            row.addWidget(combo, 2)
            remove_btn = QPushButton(t("audio.btn.remove"))
            remove_btn.clicked.connect(lambda _c=False, idx=j: self._remove_layer(idx))
            row.addWidget(remove_btn, 1)
            self.assigned_layout.addLayout(row)

    def _set_layer_track(self, idx: int, track: str):
        self.mix_layers[idx]["track"] = track

    def _remove_layer(self, idx: int):
        self.mix_layers.pop(idx)
        self._render_mix_layers()

    # ------------------------------------------------------------------
    # demucs
    # ------------------------------------------------------------------
    def _build_demucs_section(self):
        self.demucs_title = SectionLabel()
        self.outer.addWidget(self.demucs_title)
        self.demucs_desc = CaptionLabel()
        self.outer.addWidget(self.demucs_desc)

        self.demucs_upload_btn = QPushButton()
        self.demucs_upload_btn.clicked.connect(self._pick_raw_audio)
        self.outer.addWidget(self.demucs_upload_btn)
        self._raw_audio_path = None

        self.demucs_process_btn = QPushButton()
        self.demucs_process_btn.setProperty("variant", "primary")
        self.demucs_process_btn.setEnabled(False)
        self.demucs_process_btn.clicked.connect(self._process_demucs)
        self.outer.addWidget(self.demucs_process_btn)

        self.demucs_progress = QProgressBar()
        self.demucs_progress.setVisible(False)
        self.outer.addWidget(self.demucs_progress)

        self.demucs_result_row = QHBoxLayout()
        self.outer.addLayout(self.demucs_result_row)
        self.demucs_download_btn = QPushButton()
        self.demucs_download_btn.setVisible(False)
        self.demucs_download_btn.clicked.connect(self._download_demucs)
        self.outer.addWidget(self.demucs_download_btn)

    def _pick_raw_audio(self):
        path, _f = QFileDialog.getOpenFileName(self, t("audio.demucs.upload"), "", "Audio (*.wav *.mp3)")
        if path:
            self._raw_audio_path = path
            self.demucs_process_btn.setEnabled(True)

    def _process_demucs(self):
        self.demucs_process_btn.setEnabled(False)
        self.demucs_progress.setVisible(True)
        self.demucs_progress.setValue(0)
        stages = ["audio.demucs.stage1", "audio.demucs.stage2", "audio.demucs.stage3", "audio.demucs.stage4"]

        def run_stages():
            import time

            for _ in stages:
                time.sleep(0.35)
            before = synth_tone([140, 210, 175, 260], duration_each=0.15)
            after = synth_tone([220, 330], duration_each=0.3)
            return before, after

        worker = Worker(run_stages)
        self._workers.append(worker)

        def done(result):
            if worker in self._workers:
                self._workers.remove(worker)
            before_samples, after_samples = result
            self.demucs_result = (
                samples_to_wav_bytes(before_samples), before_samples,
                samples_to_wav_bytes(after_samples), after_samples,
            )
            self.demucs_progress.setValue(100)
            self.demucs_progress.setVisible(False)
            self.demucs_process_btn.setEnabled(True)
            self._render_demucs_result()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)
        # cosmetic progress ticking while the worker runs
        from PySide6.QtCore import QTimer

        self._demucs_timer = QTimer(self)
        self._demucs_timer.setInterval(140)
        progress_state = {"v": 0}

        def tick():
            if progress_state["v"] < 95:
                progress_state["v"] += 7
                self.demucs_progress.setValue(progress_state["v"])
            else:
                self._demucs_timer.stop()

        self._demucs_timer.timeout.connect(tick)
        self._demucs_timer.start()

    def _render_demucs_result(self):
        clear_layout(self.demucs_result_row)
        if not self.demucs_result:
            self.demucs_download_btn.setVisible(False)
            return
        _before_bytes, before_samples, _after_bytes, after_samples = self.demucs_result

        before_col = QVBoxLayout()
        before_col.addWidget(QLabel(t("audio.demucs.before")))
        before_wf = Waveform(before_samples, color="#B42318")
        before_col.addWidget(before_wf)
        before_play = QPushButton("▶")
        before_play.clicked.connect(lambda: self._player.play_bytes(self.demucs_result[0]))
        before_col.addWidget(before_play)
        self.demucs_result_row.addLayout(before_col)

        after_col = QVBoxLayout()
        after_col.addWidget(QLabel(t("audio.demucs.after")))
        after_wf = Waveform(after_samples, color="#187A43")
        after_col.addWidget(after_wf)
        after_play = QPushButton("▶")
        after_play.clicked.connect(lambda: self._player.play_bytes(self.demucs_result[2]))
        after_col.addWidget(after_play)
        self.demucs_result_row.addLayout(after_col)

        self.demucs_download_btn.setVisible(True)

    def _download_demucs(self):
        if not self.demucs_result:
            return
        path, _f = QFileDialog.getSaveFileName(self, t("audio.demucs.download"), "demucs_output.wav", "WAV (*.wav)")
        if path:
            with open(path, "wb") as f:
                f.write(self.demucs_result[2])

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("audio.subtitle"))
        self.compliance_title.setText(t("audio.compliance.title"))
        self.compliance_check.setText(t("audio.compliance.enabled"))
        self.sacred_check.setText(t("audio.compliance.sacred"))
        self._render_compliance_note()

        self.library_title.setText(t("audio.library.title"))
        idx = self.category_combo.currentIndex()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItems(CATEGORIES)
        self.category_combo.setCurrentIndex(max(0, idx))
        self.category_combo.blockSignals(False)
        self.search_edit.setPlaceholderText(t("audio.search.ph"))
        self._render_library()

        self.mixer_title.setText(t("audio.mixer.title"))
        for name, widgets in self._track_widgets.items():
            widgets["mute"].setText(t("audio.track.mute"))
            widgets["solo"].setText(t("audio.track.solo"))
        self.autoduck_check.setText(t("audio.autoduck"))
        self._render_mixer_summary()
        self.assigned_title.setText(t("audio.assigned_clips"))
        self._render_mix_layers()

        self.demucs_title.setText(t("audio.demucs.title"))
        self.demucs_desc.setText(t("audio.demucs.desc"))
        self.demucs_upload_btn.setText(t("audio.demucs.upload"))
        self.demucs_process_btn.setText(t("audio.btn.process"))
        self.demucs_download_btn.setText(t("audio.demucs.download"))
        self._render_demucs_result()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_compliance_note()
        self._render_library()
        self._render_mixer_summary()
