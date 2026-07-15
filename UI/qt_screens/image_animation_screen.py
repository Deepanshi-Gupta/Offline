"""Native PySide6 port of image_animation_app.py — the original Image
Animation screen. Same controls (description, 3 toggles, face-detection
grid, per-face voice assignment, skip/generate) as the Streamlit source.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_widgets import Card, SectionLabel, SelectableThumb
from common.style import face_paths
from common.toggle_switch import ToggleSwitch

THUMB_SIZE = 100
TOGGLE_KEYS = ("ia.toggle.full_body", "ia.toggle.bg_motion", "ia.toggle.lip_sync")
TOGGLE_DEFAULTS = (False, False, True)


class ImageAnimationScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.selected_face = 0
        self.voice_assigned = set()
        self._toggle_labels = {}

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 4, 4)
        outer.setSpacing(18)

        # ---- description ----
        self.description = QTextEdit()
        self.description.setFixedHeight(90)
        outer.addWidget(self.description)

        # ---- 3 toggles ----
        toggles_card = Card()
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(28)
        self._toggle_switches = {}
        for key, default in zip(TOGGLE_KEYS, TOGGLE_DEFAULTS):
            col = QVBoxLayout()
            label = SectionLabel()
            label.setProperty("role", "caption")
            switch = ToggleSwitch(on_color="#2F6FEF")
            switch.setChecked(default)
            col.addWidget(label)
            col.addWidget(switch)
            toggles_row.addLayout(col)
            self._toggle_labels[key] = label
            self._toggle_switches[key] = switch
        toggles_row.addStretch(1)
        toggles_card.layout().addLayout(toggles_row)
        outer.addWidget(toggles_card)

        # ---- face detection ----
        self.face_section_label = SectionLabel()
        outer.addWidget(self.face_section_label)

        self.face_paths = face_paths()
        face_row = QHBoxLayout()
        face_row.setSpacing(10)
        self._face_thumbs = []
        self._face_labels = []
        for i, path in enumerate(self.face_paths):
            col = QVBoxLayout()
            thumb = SelectableThumb(QPixmap(str(path)), size=THUMB_SIZE)
            thumb.setChecked(i == self.selected_face)
            thumb.toggled.connect(lambda checked, idx=i: self._on_face_toggled(idx, checked))
            col.addWidget(thumb)
            if i < 5:
                label = QPushButton()
                label.setCursor(Qt.PointingHandCursor)
                label.clicked.connect(lambda _c=False, idx=i: self._select_face(idx))
                col.addWidget(label)
                self._face_labels.append(label)
            self._face_thumbs.append(thumb)
            face_row.addLayout(col)
        face_row.addStretch(1)
        outer.addLayout(face_row)

        # ---- assign voice to face ----
        self.voice_section_label = SectionLabel()
        outer.addWidget(self.voice_section_label)

        voice_row = QHBoxLayout()
        voice_row.setSpacing(10)
        self._voice_buttons = []
        for i in range(6):
            btn = QPushButton("")
            btn.setFixedSize(THUMB_SIZE, 34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, idx=i: self._toggle_voice(idx))
            self._voice_buttons.append(btn)
            voice_row.addWidget(btn)
        voice_row.addStretch(1)
        outer.addLayout(voice_row)

        # ---- bottom actions ----
        outer.addSpacing(8)
        action_row = QHBoxLayout()
        self.skip_btn = QPushButton()
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        action_row.addWidget(self.skip_btn)
        action_row.addStretch(2)
        self.generate_btn = QPushButton()
        self.generate_btn.setProperty("variant", "primary")
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        action_row.addWidget(self.generate_btn, 1)
        outer.addLayout(action_row)

        outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    def _select_face(self, idx: int):
        self._face_thumbs[idx].setChecked(True)

    def _on_face_toggled(self, idx: int, checked: bool):
        if not checked:
            return
        self.selected_face = idx
        for j, thumb in enumerate(self._face_thumbs):
            if j != idx:
                thumb.blockSignals(True)
                thumb.setChecked(False)
                thumb.blockSignals(False)

    def _toggle_voice(self, idx: int):
        self.voice_assigned.symmetric_difference_update({idx})
        self._voice_buttons[idx].setText("✓" if idx in self.voice_assigned else "")

    def retranslate(self):
        self.description.setPlaceholderText(t("ia.desc.placeholder"))
        for key, label in self._toggle_labels.items():
            label.setText(t(key))
        self.face_section_label.setText(t("ia.section.face_detection"))
        self.voice_section_label.setText(t("ia.section.assign_voice"))
        for i, label in enumerate(self._face_labels):
            label.setText(t("ia.face.label", n=i + 1))
        self.skip_btn.setText(t("ia.btn.skip"))
        self.generate_btn.setText(t("ia.btn.generate"))

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
