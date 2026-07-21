"""Native PySide6 screen for the Full Video Editor / Timeline Panel
(Task 10-F/G — the largest of the remaining new screens).

A CapCut-style, multi-track timeline mock built entirely from native Qt
widgets, matching the client's intent that the desktop app be one shell:

* a preview frame,
* a tool palette (select / trim / split / transition / filter / overlay /
  external import) with one active tool at a time,
* a zoomable, horizontally-scrolling multi-track timeline (video, overlays,
  voice, music, subtitles) whose clips are selectable blocks,
* a clip-properties panel (volume, fade in/out, incoming transition, filter,
  split, delete), and
* an "AI polish suggestions" list you can apply or dismiss.

No real editing engine is wired in; edits mutate the in-memory clip model and
re-render, the same simulated-backend approach every other converted screen
takes. Follows the app i18n / set_dark conventions (see common/i18n.py).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout, show_toast
from common.scenes import scene_paths

TOOLS = ["select", "trim", "split", "transition", "filter", "overlay", "import"]
TOOL_KEY = {tool: f"ve.tool.{tool}" for tool in TOOLS}

# (track_key, i18n-key, accent colour for that track's clips)
TRACKS = [
    ("video", "ve.track.video", "#2F6FEF"),
    ("overlay", "ve.track.overlay", "#7C4DFF"),
    ("voice", "ve.track.voice", "#187A43"),
    ("music", "ve.track.music", "#B76E00"),
    ("subtitle", "ve.track.subtitle", "#0E7490"),
]
TRANSITIONS = ["none", "fade", "dissolve", "slide", "wipe"]
FILTERS = ["none", "warm", "cool", "cinematic", "mono"]

PX_PER_SEC = 26          # base timeline scale before zoom
TRACK_LABEL_W = 96
CLIP_H = 46


class ClipButton(QPushButton):
    """A selectable timeline clip block. Width tracks duration × zoom."""

    def __init__(self, clip: dict, accent: str, parent=None):
        super().__init__(parent)
        self.clip = clip
        self._accent = accent
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(CLIP_H)

    def apply_style(self, selected: bool):
        border = "#111827" if selected else self._accent
        width = 3 if selected else 1
        self.setStyleSheet(
            f"QPushButton {{ background:{self._accent}22; color:#111827; text-align:left;"
            f" border:{width}px solid {border}; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{self._accent}33; }}"
        )


class VideoEditorScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._navigator = None
        self.scenes = scene_paths()

        self.active_tool = "select"
        self.zoom = 1.0
        self.selected = None  # (track_key, clip_id) or None
        self.tracks = self._seed_tracks()
        self.dismissed_suggestions = set()

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(16)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_preview_section()
        self._build_tools_section()
        self._build_timeline_section()
        self._build_props_section()
        self._build_ai_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    # ------------------------------------------------------------------
    def _seed_tracks(self):
        def clips(track, specs):
            return [
                {"id": f"{track}{i}", "scene": scene, "start": start, "dur": dur,
                 "volume": 100, "fade_in": 0.0, "fade_out": 0.0,
                 "transition": "none", "filter": "none"}
                for i, (scene, start, dur) in enumerate(specs, start=1)
            ]
        return {
            "video": clips("video", [(n, (n - 1) * 4.0, 4.0) for n in range(1, 8)]),
            "overlay": clips("overlay", [(1, 2.0, 3.0), (5, 14.0, 4.0)]),
            "voice": clips("voice", [(n, (n - 1) * 4.0 + 0.3, 3.4) for n in range(1, 8)]),
            "music": clips("music", [(1, 0.0, 28.0)]),
            "subtitle": clips("subtitle", [(n, (n - 1) * 4.0, 3.8) for n in range(1, 8)]),
        }

    def _find_clip(self, sel):
        if not sel:
            return None
        track_key, clip_id = sel
        for c in self.tracks[track_key]:
            if c["id"] == clip_id:
                return c
        return None

    # ------------------------------------------------------------------
    def _build_preview_section(self):
        self.preview_title = SectionLabel()
        self.outer.addWidget(self.preview_title)
        self.preview_frame = QLabel()
        self.preview_frame.setFixedSize(480, 270)
        self.preview_frame.setAlignment(Qt.AlignCenter)
        self.preview_frame.setStyleSheet("background:#101114; border-radius:12px;")
        if self.scenes:
            pix = QPixmap(str(self.scenes[0])).scaled(
                self.preview_frame.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self.preview_frame.setPixmap(pix)
        self.outer.addWidget(self.preview_frame)

    # ------------------------------------------------------------------
    def _build_tools_section(self):
        self.tools_title = SectionLabel()
        self.outer.addWidget(self.tools_title)
        tool_row = QHBoxLayout()
        self._tool_buttons = {}
        for tool in TOOLS:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(tool == self.active_tool)
            btn.clicked.connect(lambda _c=False, tl=tool: self._set_tool(tl))
            tool_row.addWidget(btn)
            self._tool_buttons[tool] = btn
        tool_row.addStretch(1)
        self.outer.addLayout(tool_row)
        self.tool_hint = CaptionLabel()
        self.outer.addWidget(self.tool_hint)

        zoom_row = QHBoxLayout()
        self.zoom_label = QLabel()
        zoom_row.addWidget(self.zoom_label)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 200)  # 0.5x .. 2.0x
        self.zoom_slider.setValue(int(self.zoom * 100))
        self.zoom_slider.valueChanged.connect(self._on_zoom)
        zoom_row.addWidget(self.zoom_slider, 1)
        self.outer.addLayout(zoom_row)

    def _set_tool(self, tool: str):
        self.active_tool = tool
        for tl, btn in self._tool_buttons.items():
            btn.setChecked(tl == tool)
        self.tool_hint.setText(t("ve.tool.hint", tool=t(TOOL_KEY[tool])))
        if tool == "import":
            show_toast(self, t("ve.import.toast"), dark=self._dark)

    def _on_zoom(self, value: int):
        self.zoom = value / 100.0
        self._render_timeline()

    # ------------------------------------------------------------------
    def _build_timeline_section(self):
        self.timeline_title = SectionLabel()
        self.outer.addWidget(self.timeline_title)
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.timeline_scroll.setMinimumHeight(len(TRACKS) * (CLIP_H + 12) + 16)
        self.timeline_scroll.setFrameShape(QFrame.NoFrame)
        self._timeline_body = QWidget()
        self._timeline_lay = QVBoxLayout(self._timeline_body)
        self._timeline_lay.setContentsMargins(4, 4, 4, 4)
        self._timeline_lay.setSpacing(8)
        self.timeline_scroll.setWidget(self._timeline_body)
        self.outer.addWidget(self.timeline_scroll)

    def _render_timeline(self):
        clear_layout(self._timeline_lay)
        for track_key, title_key, accent in TRACKS:
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            label = QLabel(t(title_key))
            label.setFixedWidth(TRACK_LABEL_W)
            label.setStyleSheet("font-weight:700; font-size:11.5px;")
            row.addWidget(label)
            for clip in self.tracks[track_key]:
                btn = ClipButton(clip, accent)
                btn.setFixedWidth(max(36, int(clip["dur"] * PX_PER_SEC * self.zoom)))
                btn.setText(t("ve.clip.scene", n=clip["scene"]))
                selected = self.selected == (track_key, clip["id"])
                btn.setChecked(selected)
                btn.apply_style(selected)
                btn.clicked.connect(lambda _c=False, tk=track_key, cid=clip["id"]: self._on_clip_clicked(tk, cid))
                row.addWidget(btn)
            row.addStretch(1)
            self._timeline_lay.addWidget(row_w)

    def _on_clip_clicked(self, track_key: str, clip_id: str):
        self.selected = (track_key, clip_id)
        # tool-specific one-click actions; others just select for the props panel
        if self.active_tool == "split":
            self._split_selected()
        elif self.active_tool == "transition":
            self._cycle_field("transition", TRANSITIONS)
        elif self.active_tool == "filter":
            self._cycle_field("filter", FILTERS)
        self._render_timeline()
        self._render_props()

    def _cycle_field(self, field: str, options: list):
        clip = self._find_clip(self.selected)
        if clip:
            clip[field] = options[(options.index(clip[field]) + 1) % len(options)]

    # ------------------------------------------------------------------
    def _build_props_section(self):
        self.props_card = Card()
        lay = self.props_card.layout()
        self.props_title = SectionLabel()
        lay.addWidget(self.props_title)
        self.props_none = CaptionLabel()
        lay.addWidget(self.props_none)

        self.props_body = QWidget()
        pl = QVBoxLayout(self.props_body)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        self.props_selected = QLabel()
        self.props_selected.setStyleSheet("font-weight:700;")
        pl.addWidget(self.props_selected)

        vol_row = QHBoxLayout()
        self.volume_label = QLabel()
        vol_row.addWidget(self.volume_label)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(lambda v: self._set_clip_field("volume", v))
        vol_row.addWidget(self.volume_slider, 1)
        self.volume_value = QLabel()
        vol_row.addWidget(self.volume_value)
        pl.addLayout(vol_row)

        fade_row = QHBoxLayout()
        self.fade_in_label = QLabel()
        fade_row.addWidget(self.fade_in_label)
        self.fade_in_spin = QDoubleSpinBox()
        self.fade_in_spin.setRange(0.0, 5.0)
        self.fade_in_spin.setSingleStep(0.1)
        self.fade_in_spin.valueChanged.connect(lambda v: self._set_clip_field("fade_in", v))
        fade_row.addWidget(self.fade_in_spin)
        self.fade_out_label = QLabel()
        fade_row.addWidget(self.fade_out_label)
        self.fade_out_spin = QDoubleSpinBox()
        self.fade_out_spin.setRange(0.0, 5.0)
        self.fade_out_spin.setSingleStep(0.1)
        self.fade_out_spin.valueChanged.connect(lambda v: self._set_clip_field("fade_out", v))
        fade_row.addWidget(self.fade_out_spin)
        fade_row.addStretch(1)
        pl.addLayout(fade_row)

        combo_row = QHBoxLayout()
        self.transition_label = QLabel()
        combo_row.addWidget(self.transition_label)
        self.transition_combo = QComboBox()
        self.transition_combo.currentIndexChanged.connect(
            lambda i: self._set_clip_field("transition", TRANSITIONS[i]) if i >= 0 else None
        )
        combo_row.addWidget(self.transition_combo)
        self.filter_label = QLabel()
        combo_row.addWidget(self.filter_label)
        self.filter_combo = QComboBox()
        self.filter_combo.currentIndexChanged.connect(
            lambda i: self._set_clip_field("filter", FILTERS[i]) if i >= 0 else None
        )
        combo_row.addWidget(self.filter_combo)
        combo_row.addStretch(1)
        pl.addLayout(combo_row)

        btn_row = QHBoxLayout()
        self.split_btn = QPushButton()
        self.split_btn.clicked.connect(self._split_selected)
        btn_row.addWidget(self.split_btn)
        self.delete_btn = QPushButton()
        self.delete_btn.setProperty("variant", "danger")
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch(1)
        pl.addLayout(btn_row)

        lay.addWidget(self.props_body)
        self.outer.addWidget(self.props_card)

    def _set_clip_field(self, field: str, value):
        clip = self._find_clip(self.selected)
        if clip is None:
            return
        clip[field] = value
        if field == "volume":
            self.volume_value.setText(f"{int(value)}%")

    def _split_selected(self):
        clip = self._find_clip(self.selected)
        if clip is None:
            return
        track_key, _cid = self.selected
        track = self.tracks[track_key]
        idx = track.index(clip)
        half = clip["dur"] / 2.0
        clip["dur"] = half
        new_clip = dict(clip)
        new_clip["id"] = clip["id"] + "b"
        new_clip["start"] = clip["start"] + half
        new_clip["transition"] = "none"
        track.insert(idx + 1, new_clip)
        show_toast(self, t("ve.split.toast", name=t("ve.clip.scene", n=clip["scene"])), dark=self._dark)
        self._render_timeline()
        self._render_props()

    def _delete_selected(self):
        clip = self._find_clip(self.selected)
        if clip is None:
            return
        track_key, _cid = self.selected
        self.tracks[track_key] = [c for c in self.tracks[track_key] if c is not clip]
        show_toast(self, t("ve.delete.toast", name=t("ve.clip.scene", n=clip["scene"])), dark=self._dark)
        self.selected = None
        self._render_timeline()
        self._render_props()

    def _render_props(self):
        clip = self._find_clip(self.selected)
        has = clip is not None
        self.props_none.setVisible(not has)
        self.props_body.setVisible(has)
        if not has:
            return
        track_key, _cid = self.selected
        track_name = t(next(k for tk, k, _a in TRACKS if tk == track_key))
        self.props_selected.setText(
            t("ve.props.selected", name=t("ve.clip.scene", n=clip["scene"]), track=track_name)
        )
        for w in (self.volume_slider, self.fade_in_spin, self.fade_out_spin, self.transition_combo, self.filter_combo):
            w.blockSignals(True)
        self.volume_slider.setValue(int(clip["volume"]))
        self.volume_value.setText(f"{int(clip['volume'])}%")
        self.fade_in_spin.setValue(clip["fade_in"])
        self.fade_out_spin.setValue(clip["fade_out"])
        self.transition_combo.setCurrentIndex(TRANSITIONS.index(clip["transition"]))
        self.filter_combo.setCurrentIndex(FILTERS.index(clip["filter"]))
        for w in (self.volume_slider, self.fade_in_spin, self.fade_out_spin, self.transition_combo, self.filter_combo):
            w.blockSignals(False)

    # ------------------------------------------------------------------
    def _build_ai_section(self):
        self.ai_title = SectionLabel()
        self.outer.addWidget(self.ai_title)
        self.ai_desc = CaptionLabel()
        self.outer.addWidget(self.ai_desc)
        self.ai_empty = CaptionLabel()
        self.outer.addWidget(self.ai_empty)
        self.ai_container = QVBoxLayout()
        self.ai_container.setSpacing(8)
        self.outer.addLayout(self.ai_container)

    def _render_ai(self):
        clear_layout(self.ai_container)
        keys = [k for k in ("ve.ai.s1", "ve.ai.s2", "ve.ai.s3") if k not in self.dismissed_suggestions]
        self.ai_empty.setVisible(not keys)
        for key in keys:
            card = Card(flat=True, margins=(12, 8, 12, 8), spacing=6)
            row = QHBoxLayout()
            row.addWidget(CaptionLabel(t(key)), 1)
            apply_btn = QPushButton(t("ve.ai.apply"))
            apply_btn.setProperty("variant", "primary")
            apply_btn.clicked.connect(lambda _c=False, k=key: self._apply_suggestion(k))
            row.addWidget(apply_btn)
            dismiss_btn = QPushButton(t("ve.ai.dismiss"))
            dismiss_btn.clicked.connect(lambda _c=False, k=key: self._dismiss_suggestion(k))
            row.addWidget(dismiss_btn)
            card.layout().addLayout(row)
            self.ai_container.addWidget(card)

    def _apply_suggestion(self, key: str):
        self.dismissed_suggestions.add(key)
        show_toast(self, t("ve.ai.applied"), dark=self._dark)
        self._render_ai()

    def _dismiss_suggestion(self, key: str):
        self.dismissed_suggestions.add(key)
        self._render_ai()

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("ve.subtitle"))
        self.preview_title.setText(t("ve.preview.title"))
        self.tools_title.setText(t("ve.tools.title"))
        for tool, btn in self._tool_buttons.items():
            btn.setText(t(TOOL_KEY[tool]))
        self.tool_hint.setText(t("ve.tool.hint", tool=t(TOOL_KEY[self.active_tool])))
        self.zoom_label.setText(t("ve.zoom"))
        self.timeline_title.setText(t("ve.timeline.title"))
        self._render_timeline()

        self.props_title.setText(t("ve.props.title"))
        self.props_none.setText(t("ve.props.none"))
        self.volume_label.setText(t("ve.props.volume"))
        self.fade_in_label.setText(t("ve.props.fade_in"))
        self.fade_out_label.setText(t("ve.props.fade_out"))
        self.transition_label.setText(t("ve.props.transition"))
        self.filter_label.setText(t("ve.props.filter"))
        self.split_btn.setText(t("ve.props.split_at"))
        self.delete_btn.setText(t("ve.props.delete"))
        self.transition_combo.blockSignals(True)
        self.transition_combo.clear()
        self.transition_combo.addItems([t(f"ve.transition.{x}") for x in TRANSITIONS])
        self.transition_combo.blockSignals(False)
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems([t(f"ve.filter.{x}") for x in FILTERS])
        self.filter_combo.blockSignals(False)
        self._render_props()

        self.ai_title.setText(t("ve.ai.title"))
        self.ai_desc.setText(t("ve.ai.desc"))
        self.ai_empty.setText(t("ve.ai.empty"))
        self._render_ai()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_navigator(self, on_navigate):
        self._navigator = on_navigate

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_timeline()
