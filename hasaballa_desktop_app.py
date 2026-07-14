"""Hasaballa AI Platform — native PySide6 desktop shell.

Single QMainWindow with an RTL sidebar and a QStackedWidget body hosting
every converted screen. This is the entry point that ties the individual
screen conversions (qt_screens/) together into one application — matching
"the final application" being one desktop app, not 13 standalone windows.

Screens are constructed lazily on first visit and cached in
self._screen_cache. Screens not yet converted from their Streamlit source
show PlaceholderScreen until their turn in the migration.

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

from common.qt_theme import FONT_FAMILY, build_stylesheet
from common.qt_widgets import OfflinePill
from qt_screens.settings_screen import SettingsScreen

FONT_DIR = Path(__file__).parent / "assets" / "fonts"


def load_fonts():
    for name in ("Tajawal-Medium.ttf", "Tajawal-ExtraBold.ttf", "Tajawal-Regular.ttf", "Tajawal-Bold.ttf"):
        path = FONT_DIR / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


class PlaceholderScreen(QWidget):
    """Shown for screens not yet converted from their Streamlit source."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        label = QLabel(f"🚧\n{title}\nلم يتم تحويلها بعد من Streamlit")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 14px; color: #8A8D94; line-height: 1.8;")
        lay.addWidget(label)

    def set_dark(self, _dark: bool):
        pass


# (key, icon, Arabic label, factory(parent) -> QWidget | None for not-yet-converted)
NAV_ITEMS = [
    ("chat", "💬", "الدردشة — Hasaballa GPT", None),
    ("image_animation", "🎬", "تحريك الصور", None),
    ("image_generation", "🖼️", "توليد الصور", None),
    ("character_packs", "👤", "حزم الشخصيات", None),
    ("voice_cloning", "🎙️", "الصوت واستنساخه", None),
    ("lip_sync", "👄", "مزامنة الشفاه", None),
    ("audio_layering", "🎵", "الصوت والمكتبة الصوتية", None),
    ("smart_director", "🎯", "المخرج الذكي", None),
    ("motion_generation", "🎞️", "توليد الحركة", None),
    ("subtitles", "📝", "الترجمة والدبلجة", None),
    ("export", "⬇️", "التصدير والعرض", None),
    ("settings", "⚙️", "الإعدادات والامتثال", lambda parent: SettingsScreen(parent)),
    ("publishing", "📤", "النشر", None),
]

LABELS = {key: label for key, _icon, label, _factory in NAV_ITEMS}


class Sidebar(QWidget):
    def __init__(self, on_select, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(4)

        brand = QLabel("Hasaballa AI")
        brand.setObjectName("sidebarBrand")
        brand.setAlignment(Qt.AlignCenter)
        lay.addWidget(brand)
        lay.addSpacing(10)

        self._buttons = {}
        for key, icon, label, _factory in NAV_ITEMS:
            btn = QPushButton(f"{label}   {icon}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("role", "navItem")
            btn.clicked.connect(lambda _checked, k=key: on_select(k))
            lay.addWidget(btn)
            self._buttons[key] = btn
        lay.addStretch(1)

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
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setFixedWidth(40)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        topbar.addWidget(self.page_title)
        topbar.addStretch(1)
        topbar.addWidget(self.offline_pill)
        topbar.addWidget(self.theme_btn)
        content_lay.addLayout(topbar)

        self.stack = QStackedWidget()
        content_lay.addWidget(self.stack, 1)
        root.addWidget(content, 1)

        self._apply_theme()
        self._navigate(NAV_ITEMS[0][0])

    def _navigate(self, key: str):
        if key not in self._screen_cache:
            factory = next(f for k, _i, _l, f in NAV_ITEMS if k == key)
            widget = factory(self.stack) if factory else PlaceholderScreen(LABELS[key])
            if hasattr(widget, "set_dark"):
                widget.set_dark(self._dark)
            self._screen_cache[key] = widget
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(self._screen_cache[key])
        self.sidebar.set_active(key)
        self.page_title.setText(LABELS[key])

    def _toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme()

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(build_stylesheet(self._dark))
        self.offline_pill.set_dark(self._dark)
        self.theme_btn.setText("☀️" if self._dark else "🌙")
        for widget in self._screen_cache.values():
            if hasattr(widget, "set_dark"):
                widget.set_dark(self._dark)


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    load_fonts()
    app.setFont(QFont(FONT_FAMILY, 10))
    win = MainWindow()
    win.resize(1360, 840)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
