"""Hasaballa AI Platform — native PySide6 desktop shell.

Single QMainWindow with an RTL sidebar and a QStackedWidget body hosting
every converted screen. This is the entry point that ties the individual
screen conversions (qt_screens/) together into one application — matching
"the final application" being one desktop app, not 13 standalone windows.

Screens are constructed lazily on first visit and cached in
self._screen_cache. Screens not yet converted from their Streamlit source
show PlaceholderScreen until their turn in the migration.

Language: the whole UI flips Arabic ⇄ English from the header toggle (or
the Settings screen's language selector — both drive the same
common.i18n.lang_manager singleton). On a flip the app switches layout
direction (RTL for Arabic, LTR for English) and every screen re-runs its
retranslate() slot. See common/i18n.py.

Run with:
    python hasaballa_desktop_app.py
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from common.connection import ConnectionState, connection_manager
from common.i18n import lang_manager, t
from common.qt_theme import FONT_FAMILY, apply_app_palette, build_stylesheet
from common.qt_widgets import OfflinePill
from common.toggle_switch import ToggleSwitch
from qt_screens.character_pack_screen import CharacterPackScreen
from qt_screens.audio_layering_screen import AudioLayeringScreen
from qt_screens.chat_screen import ChatScreen
from qt_screens.export_screen import ExportScreen
from qt_screens.image_animation_screen import ImageAnimationScreen
from qt_screens.image_generation_screen import ImageGenerationScreen
from qt_screens.import_media_screen import ImportMediaScreen
from qt_screens.lip_sync_screen import LipSyncScreen
from qt_screens.motion_generation_screen import MotionGenerationScreen
from qt_screens.project_management_screen import ProjectManagementScreen
from qt_screens.publishing_screen import PublishingScreen
from qt_screens.settings_screen import SettingsScreen
from qt_screens.smart_director_screen import SmartDirectorScreen
from qt_screens.smart_internet_access_screen import SmartInternetAccessScreen
from qt_screens.standalone_tools_screen import StandaloneToolsScreen
from qt_screens.subtitles_screen import SubtitlesScreen
from qt_screens.voice_screen import VoiceScreen

FONT_DIR = Path(__file__).parent / "assets" / "fonts"


def load_fonts():
    for name in ("Tajawal-Medium.ttf", "Tajawal-ExtraBold.ttf", "Tajawal-Regular.ttf", "Tajawal-Bold.ttf"):
        path = FONT_DIR / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


class PlaceholderScreen(QWidget):
    """Shown for screens not yet converted from their Streamlit source."""

    def __init__(self, title_key: str, parent=None):
        super().__init__(parent)
        self._title_key = title_key
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("font-size: 14px; color: #8A8D94; line-height: 1.8;")
        lay.addWidget(self._label)
        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def retranslate(self):
        self._label.setText(f"{t(self._title_key)}\n{t('app.not_converted')}")

    def set_dark(self, _dark: bool):
        pass


# (key, icon, i18n-key, factory(parent) -> QWidget | None for not-yet-converted)
NAV_ITEMS = [
    ("chat", "", "nav.chat", lambda parent: ChatScreen(parent)),
    ("image_animation", "", "nav.image_animation", lambda parent: ImageAnimationScreen(parent)),
    ("image_generation", "", "nav.image_generation", lambda parent: ImageGenerationScreen(parent)),
    ("character_packs", "", "nav.character_packs", lambda parent: CharacterPackScreen(parent)),
    ("voice_cloning", "", "nav.voice_cloning", lambda parent: VoiceScreen(parent)),
    ("lip_sync", "", "nav.lip_sync", lambda parent: LipSyncScreen(parent)),
    ("audio_layering", "", "nav.audio_layering", lambda parent: AudioLayeringScreen(parent)),
    ("smart_director", "", "nav.smart_director", lambda parent: SmartDirectorScreen(parent)),
    ("motion_generation", "", "nav.motion_generation", lambda parent: MotionGenerationScreen(parent)),
    ("subtitles", "", "nav.subtitles", lambda parent: SubtitlesScreen(parent)),
    ("export", "", "nav.export", lambda parent: ExportScreen(parent)),
    ("project_management", "", "nav.project_management", lambda parent: ProjectManagementScreen(parent)),
    ("import_media", "", "nav.import_media", lambda parent: ImportMediaScreen(parent)),
    ("standalone_tools", "", "nav.standalone_tools", lambda parent: StandaloneToolsScreen(parent)),
    ("settings", "", "nav.settings", lambda parent: SettingsScreen(parent)),
    ("smart_internet_access", "", "nav.smart_internet_access", lambda parent: SmartInternetAccessScreen(parent)),
    ("publishing", "", "nav.publishing", lambda parent: PublishingScreen(parent)),
]

TITLE_KEYS = {key: title_key for key, _icon, title_key, _factory in NAV_ITEMS}


class Sidebar(QWidget):
    def __init__(self, on_select, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(4)

        self.brand = QLabel()
        self.brand.setObjectName("sidebarBrand")
        self.brand.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.brand)
        lay.addSpacing(10)

        self._buttons = {}
        self._icons = {}
        for key, icon, _title_key, _factory in NAV_ITEMS:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("role", "navItem")
            btn.clicked.connect(lambda _checked, k=key: on_select(k))
            lay.addWidget(btn)
            self._buttons[key] = btn
            self._icons[key] = icon
        lay.addStretch(1)
        self.retranslate()

    def retranslate(self):
        for key, _icon, title_key, _factory in NAV_ITEMS:
            self._buttons[key].setText(t(title_key))

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hasaballa AI Platform")
        self.setMinimumSize(1280, 720)
        self._dark = False
        self._screen_cache = {}
        self._current_key = None

        central = QWidget()
        central.setObjectName("appShell")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(self._navigate)
        root.addWidget(self.sidebar)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(24, 18, 24, 18)
        content_lay.setSpacing(12)

        topbar = QHBoxLayout()
        self.page_title = QLabel("")
        self.page_title.setProperty("role", "pageTitle")
        self.offline_pill = OfflinePill()
        self.smart_access_switch = ToggleSwitch(on_color="#E3A008")
        self.smart_access_switch.setToolTip(t("app.smart_access_toggle_tooltip"))
        self.smart_access_switch.toggled.connect(self._on_smart_access_toggled)
        self.lang_btn = QPushButton()
        self.lang_btn.setObjectName("themeToggle")
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.clicked.connect(lang_manager.toggle)
        topbar.addWidget(self.page_title)
        topbar.addStretch(1)
        topbar.addWidget(self.offline_pill)
        topbar.addWidget(self.smart_access_switch)
        topbar.addWidget(self.lang_btn)
        content_lay.addLayout(topbar)

        self.stack = QStackedWidget()
        content_lay.addWidget(self.stack, 1)
        root.addWidget(content, 1)

        lang_manager.changed.connect(self._on_language_changed)
        connection_manager.changed.connect(self._render_connection)

        self._apply_theme()
        self._apply_language()  # also renders the connection pill/toggle for the initial state
        self._navigate(NAV_ITEMS[0][0])

    def _on_smart_access_toggled(self, checked: bool):
        if checked:
            connection_manager.go_online()
        else:
            connection_manager.disconnect()

    def _render_connection(self):
        state = connection_manager.state
        connecting = connection_manager.connecting

        self.smart_access_switch.blockSignals(True)
        self.smart_access_switch.setChecked(connecting or state != ConnectionState.LOCAL)
        self.smart_access_switch.blockSignals(False)
        self.smart_access_switch.setEnabled(not connecting)

        if connecting:
            self.offline_pill.set_tone("info")
            self.offline_pill.set_text(t("app.connecting_pill"))
        elif state == ConnectionState.CLOUD:
            self.offline_pill.set_tone("info")
            self.offline_pill.set_text(t("app.cloud_pill"))
        elif state == ConnectionState.ONLINE:
            self.offline_pill.set_tone("warning")
            self.offline_pill.set_text(t("app.online_pill"))
        else:
            self.offline_pill.set_tone("success")
            self.offline_pill.set_text(t("app.offline_pill"))

    def _navigate(self, key: str):
        if key not in self._screen_cache:
            factory = next(f for k, _i, _l, f in NAV_ITEMS if k == key)
            widget = factory(self.stack) if factory else PlaceholderScreen(TITLE_KEYS[key])
            if hasattr(widget, "set_dark"):
                widget.set_dark(self._dark)
            self._screen_cache[key] = widget
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(self._screen_cache[key])
        self.sidebar.set_active(key)
        self._current_key = key
        self.page_title.setText(t(TITLE_KEYS[key]))

    def _apply_theme(self):
        # App is light-only (dark mode was removed); this simply applies the
        # single stylesheet and lets each screen keep its set_dark(False) hook.
        QApplication.instance().setStyleSheet(build_stylesheet(self._dark))
        self.offline_pill.set_dark(self._dark)
        for widget in self._screen_cache.values():
            if hasattr(widget, "set_dark"):
                widget.set_dark(self._dark)

    def _on_language_changed(self, _lang: str):
        self._apply_language()

    def _apply_language(self):
        QApplication.instance().setLayoutDirection(lang_manager.layout_direction())
        # header + sidebar own their text; screens retranslate via their own
        # connection to lang_manager.changed (each screen wires it in __init__).
        self.sidebar.brand.setText(t("app.brand"))
        self.sidebar.retranslate()
        self._render_connection()  # re-picks the right pill text for the current state
        self.smart_access_switch.setToolTip(t("app.smart_access_toggle_tooltip"))
        self.lang_btn.setText(t("app.switch_to_en") if lang_manager.is_rtl() else t("app.switch_to_ar"))
        if self._current_key is not None:
            self.page_title.setText(t(TITLE_KEYS[self._current_key]))


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(lang_manager.layout_direction())
    apply_app_palette(app, dark=False)
    load_fonts()
    app.setFont(QFont(FONT_FAMILY, 10))
    win = MainWindow()
    win.resize(1360, 840)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
