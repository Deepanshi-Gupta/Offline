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

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from common.connection import ConnectionState, connection_manager
from common.desktop import DesktopTray, enable_high_dpi, make_app_icon, render_activity
from common.i18n import lang_manager, t
from common.language_toggle import LanguageTabToggle
from common.qt_theme import FONT_FAMILY, apply_app_palette, build_stylesheet
from common.qt_widgets import OfflinePill
from common.toggle_switch import ToggleSwitch
from qt_screens.character_pack_screen import CharacterPackScreen
from qt_screens.character_profile_screen import CharacterProfileScreen
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
from qt_screens.settings_screen import MODELS, SettingsScreen
from qt_screens.smart_director_screen import SmartDirectorScreen
from qt_screens.smart_edit_screen import SmartEditScreen
from qt_screens.smart_internet_access_screen import SmartInternetAccessScreen
from qt_screens.standalone_tools_screen import StandaloneToolsScreen
from qt_screens.subtitles_screen import SubtitlesScreen
from qt_screens.video_editor_screen import VideoEditorScreen
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
    ("character_profile", "", "nav.character_profile", lambda parent: CharacterProfileScreen(parent)),
    ("voice_cloning", "", "nav.voice_cloning", lambda parent: VoiceScreen(parent)),
    ("lip_sync", "", "nav.lip_sync", lambda parent: LipSyncScreen(parent)),
    ("audio_layering", "", "nav.audio_layering", lambda parent: AudioLayeringScreen(parent)),
    ("smart_director", "", "nav.smart_director", lambda parent: SmartDirectorScreen(parent)),
    ("motion_generation", "", "nav.motion_generation", lambda parent: MotionGenerationScreen(parent)),
    ("subtitles", "", "nav.subtitles", lambda parent: SubtitlesScreen(parent)),
    ("smart_edit", "", "nav.smart_edit", lambda parent: SmartEditScreen(parent)),
    ("video_editor", "", "nav.video_editor", lambda parent: VideoEditorScreen(parent)),
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


# Supported window-size breakpoints (task B5). Screens are scroll areas, so
# height is handled by vertical scrolling; width is the real constraint.
# COMPACT is the enforced minimum, so the window can never be sized below a
# tested breakpoint. Verified via tools/check_breakpoints.py, which compares
# each screen's inner minimum width against the width available at each size
# (window width minus the sidebar and content margins).
#
# (The Settings screen's old width debt — dense rows exceeding WIDE — was
# resolved by splitting it into sub-navigation tabs; see settings_screen.py.
# VoiceScreen [en] still exceeds COMPACT but fits WIDE.)
BREAKPOINT_COMPACT = (1440, 810)
BREAKPOINT_WIDE = (1720, 945)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hasaballa AI Platform")
        self.setMinimumSize(*BREAKPOINT_COMPACT)
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
        self.lang_toggle = LanguageTabToggle()
        topbar.addWidget(self.page_title)
        topbar.addStretch(1)
        topbar.addWidget(self.offline_pill)
        topbar.addWidget(self.smart_access_switch)
        topbar.addWidget(self.lang_toggle)
        content_lay.addLayout(topbar)

        self.stack = QStackedWidget()
        content_lay.addWidget(self.stack, 1)
        root.addWidget(content, 1)

        lang_manager.changed.connect(self._on_language_changed)
        connection_manager.changed.connect(self._render_connection)

        # ---- native desktop integration (tray + notifications + keep-awake) ----
        # The tray gives long renders a background home (minimize-to-tray) and is
        # also the emitter for native OS toasts on render complete/failure. When
        # no tray is available (headless/remote), everything below no-ops and the
        # window behaves like a plain top-level window.
        self._force_quit = False
        self._minimized_hint_shown = False
        self.setWindowIcon(make_app_icon())
        self.tray = DesktopTray(make_app_icon(), tooltip=t("app.tray.tooltip"), parent=self)
        if self.tray.available:
            self.tray.show_requested.connect(self._restore_from_tray)
            self.tray.quit_requested.connect(self._quit_from_tray)
            # keep this window alive when hidden to tray; real exit goes through
            # the tray menu (or the close path when idle).
            QApplication.instance().setQuitOnLastWindowClosed(False)
        render_activity.notify_requested.connect(self._on_render_notify)

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
            if hasattr(widget, "set_navigator"):
                widget.set_navigator(self._navigate)
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
        # the language toggle self-syncs off lang_manager.changed
        if self._current_key is not None:
            self.page_title.setText(t(TITLE_KEYS[self._current_key]))
        if self.tray.available:
            self.tray.set_labels(t("app.tray.show"), t("app.tray.quit"), t("app.tray.tooltip"))

    # ---- desktop tray / notifications / keep-awake --------------------
    def _on_render_notify(self, name: str, success: bool, detail: str):
        """A render reached a terminal state — fire a native OS toast so the
        user is told even when the window is minimised to the tray (gap A2)."""
        title = t("app.notify.complete_title") if success else t("app.notify.failed_title")
        message = f"{name} — {detail}" if detail else name
        self.tray.notify(title, message, success=success)

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self):
        self._force_quit = True
        QApplication.instance().quit()

    def changeEvent(self, event):
        # Minimize-to-tray: when the tray is available, minimising hides the
        # window into the tray (long renders keep running in the background)
        # with a one-time hint so the user knows where it went.
        if event.type() == QEvent.WindowStateChange and self.tray.available:
            if self.windowState() & Qt.WindowMinimized:
                event.accept()
                # defer hide() until after the state change is processed
                self.hide()
                if not self._minimized_hint_shown:
                    self._minimized_hint_shown = True
                    self.tray.notify(
                        t("app.tray.minimized_title"), t("app.tray.minimized_body"), success=True
                    )
                return
        super().changeEvent(event)

    def closeEvent(self, event):
        # An explicit quit (tray menu), or no tray at all → close for real.
        if self._force_quit or not self.tray.available:
            super().closeEvent(event)  # process exit clears any sleep guard
            return
        # A render is in flight → don't kill it; retreat to the tray instead.
        if render_activity.busy:
            event.ignore()
            self.hide()
            self.tray.notify(
                t("app.tray.render_bg_title"), t("app.tray.render_bg_body"), success=True
            )
            return
        # Idle → normal quit.
        self._force_quit = True
        QApplication.instance().quit()
        super().closeEvent(event)


def required_models_missing():
    """Required models (see settings_screen.MODELS) not yet located — the
    condition that triggers the first-launch gate."""
    return [m for m in MODELS if m.get("required") and not m["found"]]


class FirstLaunchGate(QDialog):
    """Blocking first-launch Model & Path configuration (task N3).

    Shown before the main UI when a required model is missing: the user must
    set the missing paths (Recheck marks a model found) or explicitly skip
    setup. Mutates the shared settings_screen.MODELS, so the Settings screen
    reflects whatever was resolved here. Modal — the main window is not shown
    until this closes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(520)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        # header: title + ENG|ARB tab so the setup form itself can be switched
        # between English and Arabic (before the main UI is reachable).
        head = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setProperty("role", "pageTitle")
        head.addWidget(self.title_label)
        head.addStretch(1)
        head.addWidget(LanguageTabToggle())
        lay.addLayout(head)

        self.intro_label = QLabel()
        self.intro_label.setWordWrap(True)
        lay.addWidget(self.intro_label)

        self._rows = {}
        for model in required_models_missing():
            row_wrap = QWidget()
            row_lay = QVBoxLayout(row_wrap)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(4)
            name = QLabel()
            name.setStyleSheet("font-weight:700;")
            row_lay.addWidget(name)
            edit_row = QHBoxLayout()
            path_edit = QLineEdit(model["path"])
            edit_row.addWidget(path_edit, 1)
            browse_btn = QPushButton()
            browse_btn.clicked.connect(lambda _c=False, e=path_edit: self._browse(e))
            edit_row.addWidget(browse_btn)
            recheck_btn = QPushButton()
            recheck_btn.setProperty("role", "navItem")
            recheck_btn.clicked.connect(lambda _c=False, m=model: self._recheck(m))
            edit_row.addWidget(recheck_btn)
            row_lay.addLayout(edit_row)
            lay.addWidget(row_wrap)
            self._rows[model["key"]] = {"name": name, "path": path_edit, "browse": browse_btn, "recheck": recheck_btn}

        self.all_set_label = QLabel()
        self.all_set_label.setVisible(False)
        lay.addWidget(self.all_set_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.skip_btn = QPushButton()
        self.skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.skip_btn)
        self.continue_btn = QPushButton()
        self.continue_btn.setProperty("variant", "primary")
        self.continue_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.continue_btn)
        lay.addLayout(btn_row)

        # live-retranslate while open (the ENG|ARB tab flips lang_manager)
        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()
        self._update_continue()

    def _on_language_changed(self, _lang: str):
        self.setLayoutDirection(lang_manager.layout_direction())
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(t("gate.title"))
        self.title_label.setText(t("gate.title"))
        self.intro_label.setText(t("gate.intro"))
        for key, w in self._rows.items():
            model = next(m for m in MODELS if m["key"] == key)
            w["name"].setText(t("gate.model_missing", name=t(model["name_key"])) if not model["found"] else t(model["name_key"]))
            w["path"].setPlaceholderText(t("gate.path_placeholder"))
            w["browse"].setText(t("gate.browse"))
            w["recheck"].setText(t("gate.recheck"))
        self.all_set_label.setText(t("gate.all_set"))
        self.skip_btn.setText(t("gate.skip"))
        self.continue_btn.setText(t("gate.continue"))

    def _browse(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, t("gate.browse"))
        if path:
            edit.setText(path)

    def _recheck(self, model):
        path = self._rows[model["key"]]["path"].text().strip()
        if not path:
            return
        model["path"] = path
        model["found"] = True
        self._rows[model["key"]]["name"].setText(t(model["name_key"]))
        self._rows[model["key"]]["path"].setEnabled(False)
        self._update_continue()

    def _update_continue(self):
        remaining = required_models_missing()
        self.continue_btn.setEnabled(not remaining)
        self.all_set_label.setVisible(not remaining)


def main():
    # Crisp fractional scaling on the client's 16" WQXGA @ 300Hz panel — must be
    # set before the QApplication is constructed (High-DPI checklist item).
    enable_high_dpi()
    app = QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    app.setLayoutDirection(lang_manager.layout_direction())
    apply_app_palette(app, dark=False)
    load_fonts()
    app.setFont(QFont(FONT_FAMILY, 10))
    win = MainWindow()  # constructing it installs the app stylesheet the gate inherits
    win.resize(*BREAKPOINT_WIDE)
    # First-launch Model & Path gate (N3): block the main UI until required
    # models are configured or setup is explicitly skipped.
    if required_models_missing():
        FirstLaunchGate(win).exec()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
