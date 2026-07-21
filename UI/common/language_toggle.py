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
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget

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


class LanguageTabToggle(QWidget):
    """Segmented ENG | ARB tab (a two-segment pill), an alternative to the
    switch-style LanguageToggle. Same contract: a self-syncing view over the
    shared lang_manager singleton — one segment is always active, and flipping
    the language anywhere else keeps this in sync. Used where a tab reads more
    clearly than a switch (e.g. the first-launch setup form)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        # keep ENG…ARB order stable regardless of the app's RTL mirroring
        self.setLayoutDirection(Qt.LeftToRight)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.en_btn = QPushButton("ENG")
        self.ar_btn = QPushButton("ARB")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for btn, code in ((self.en_btn, "en"), (self.ar_btn, "ar")):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, lang=code: lang_manager.set_lang(lang))
            self._group.addButton(btn)
            lay.addWidget(btn)

        self._sync_from_lang()
        lang_manager.changed.connect(lambda _lang: self._sync_from_lang())

    def _sync_from_lang(self):
        arabic = lang_manager.is_rtl()
        self.ar_btn.setChecked(arabic)
        self.en_btn.setChecked(not arabic)
        self._apply_style()

    def _apply_style(self):
        s = semantic(self._dark)
        arabic = lang_manager.is_rtl()

        def seg(active: bool, left: bool):
            radius = "8px 0 0 8px" if left else "0 8px 8px 0"
            if active:
                return (
                    f"QPushButton {{ background:{s['primary']}; color:#FFFFFF; font-weight:800;"
                    f" border:1px solid {s['primary']}; border-radius:{radius}; padding:4px 12px; font-size:11.5px; }}"
                )
            return (
                f"QPushButton {{ background:{s['surface']}; color:{s['ink_faint']}; font-weight:700;"
                f" border:1px solid {s['border']}; border-radius:{radius}; padding:4px 12px; font-size:11.5px; }}"
                f"QPushButton:hover {{ color:{s['ink']}; }}"
            )

        # EN sits on the left, AR on the right (fixed LTR visual order)
        self.en_btn.setStyleSheet(seg(not arabic, left=True))
        self.ar_btn.setStyleSheet(seg(arabic, left=False))

    def set_dark(self, dark: bool):
        self._dark = dark
        self._apply_style()
