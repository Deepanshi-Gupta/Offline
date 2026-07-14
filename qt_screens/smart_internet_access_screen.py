"""Standalone showcase screen for SmartInternetAccessPanel — the same
component embedded inside Settings (§14), reachable here on its own via
the sidebar so its full interaction (state machine, toasts, animations,
reduced-motion) can be reviewed without the rest of the Settings screen
around it.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from common.i18n import lang_manager, t
from common.qt_widgets import CaptionLabel
from smart_internet_access_qt import SmartInternetAccessPanel


class SmartInternetAccessScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        self.subtitle = CaptionLabel()
        outer.addWidget(self.subtitle)

        controls_row = QHBoxLayout()
        self.reduced_motion_check = QCheckBox()
        self.reduced_motion_check.toggled.connect(self._on_reduced_motion_toggled)
        controls_row.addWidget(self.reduced_motion_check)
        controls_row.addStretch(1)
        outer.addLayout(controls_row)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        self.panel = SmartInternetAccessPanel()
        center_row.addWidget(self.panel)
        center_row.addStretch(1)
        outer.addLayout(center_row)
        outer.addStretch(2)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    def _on_reduced_motion_toggled(self, checked: bool):
        self.panel.set_reduced_motion(checked)

    def retranslate(self):
        self.subtitle.setText(t("sia.screen.subtitle"))
        self.reduced_motion_check.setText(t("sia.reduced_motion"))

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self.panel.set_dark(dark)
