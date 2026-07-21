"""EN [toggle] AR language switch — a self-syncing view over the shared
common.i18n.lang_manager singleton.

Replaces the old single language button in the header. Layout, per the
reference design:

    EN    [ Toggle ]    AR

* Toggle OFF -> English active (EN highlighted, AR inactive)
* Toggle ON  -> Arabic  active (AR highlighted, EN inactive)

Only one language is ever active — the highlight and the app language are
both derived from lang_manager, so flipping the language anywhere else (the
Settings language selector) keeps this toggle in sync.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from common.i18n import lang_manager
from common.qt_theme import semantic
from common.toggle_switch import ToggleSwitch


class LanguageToggle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False

        # Keep EN…AR visual order stable regardless of the app's RTL mirroring,
        # so the switch always reads left-to-right (ON travels toward AR).
        self.setLayoutDirection(Qt.LeftToRight)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.en_label = QLabel("EN")
        self.switch = ToggleSwitch(on_color="#a3620a")
        self.switch.setToolTip("English / العربية")
        self.ar_label = QLabel("AR")

        lay.addWidget(self.en_label)
        lay.addWidget(self.switch)
        lay.addWidget(self.ar_label)

        self._sync_from_lang()
        self.switch.toggled.connect(self._on_toggled)
        lang_manager.changed.connect(lambda _lang: self._sync_from_lang())

    def _on_toggled(self, checked: bool):
        # ON = Arabic, OFF = English. set_lang is a no-op when unchanged, so the
        # changed -> _sync_from_lang round-trip does not recurse.
        lang_manager.set_lang("ar" if checked else "en")
        self._render_highlight()

    def _sync_from_lang(self):
        self.switch.setChecked(lang_manager.is_rtl())  # Arabic -> ON
        self._render_highlight()

    def _render_highlight(self):
        s = semantic(self._dark)
        arabic = lang_manager.is_rtl()
        active = f"color:{s['ink']}; font-weight:800;"
        inactive = f"color:{s['ink_fainter']}; font-weight:600;"
        self.en_label.setStyleSheet(inactive if arabic else active)
        self.ar_label.setStyleSheet(active if arabic else inactive)

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_highlight()
