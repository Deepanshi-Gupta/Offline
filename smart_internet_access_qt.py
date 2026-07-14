"""Native PySide6 desktop implementation of the Smart Internet Access
control panel (§14 of the UI audit) — a Qt/QSS port of the HTML mockup
reviewed earlier, built for direct integration into the Hasaballa AI
Platform desktop app (min 1280×720, RTL Arabic, offline-first).

Arabic text: every QLabel/QPushButton string below is raw, un-reshaped
Arabic Unicode — Qt's text engine (HarfBuzz-backed QTextLayout) already
performs correct contextual shaping + BiDi reordering for widget text.
See common/arabic_text.py for why running arabic_reshaper/python-bidi on
top of that would double-process and corrupt it, and for where those
libraries actually belong (non-Qt raster pipelines elsewhere in the app).

Threading: the two operations that stand in for real async work — the
"connecting" handshake and the encrypted local-snapshot save before a
cloud handoff — run on QThreadPool via common/workers.Worker, never on
the GUI thread. Swap _simulate_handshake / _simulate_snapshot_save for
the real network/disk calls without touching any UI code.

Run with:
    python smart_internet_access_qt.py
"""

import sys
import time
from enum import Enum
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QThreadPool,
    QTimer,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from common.qt_theme import FONT_FAMILY, build_stylesheet, palette
from common.toggle_switch import ToggleSwitch
from common.workers import Worker

FONT_DIR = Path(__file__).parent / "assets" / "fonts"


class ConnectionState(Enum):
    LOCAL = "a"
    ONLINE = "b"
    CLOUD = "c"


STATE_COPY = {
    ConnectionState.LOCAL: {
        "badge": "محلي",
        "icon": "🔒",
        "message": "متصل محلياً فقط — البيانات آمنة تماماً على جهازك",
    },
    ConnectionState.ONLINE: {
        "badge": "متصل",
        "icon": "🌐",
        "message": "الاتصال نشط — مسموح بالبحث الذكي مؤقتاً",
    },
    ConnectionState.CLOUD: {
        "badge": "سحابي",
        "icon": "☁️",
        "message": "معالجة سحابية نشطة",
    },
}


def load_fonts():
    for name in ("Tajawal-Medium.ttf", "Tajawal-ExtraBold.ttf", "Tajawal-Regular.ttf", "Tajawal-Bold.ttf"):
        path = FONT_DIR / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


class SmartInternetAccessPanel(QFrame):
    """Reusable settings-screen widget — drop straight into §14."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panelCard")
        self.setFixedWidth(440)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

        self._state = ConnectionState.LOCAL
        self._dark = False
        self._reduced_motion = False
        self._connecting = False
        self._op_token = 0
        self._workers = []  # keeps Worker objects alive until they finish — see _run_worker

        self._build_ui()
        self._build_animations()
        self._render_state()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _make_row_shell(self, icon: str, title: str, help_text: str):
        row = QHBoxLayout()
        row.setSpacing(11)

        icon_frame = QFrame()
        icon_frame.setProperty("role", "rowIcon")
        icon_frame.setFixedSize(32, 32)
        icon_frame_layout = QHBoxLayout(icon_frame)
        icon_frame_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_frame_layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_label = QLabel(title)
        title_label.setProperty("class", "rowTitle")
        title_label.setWordWrap(True)
        title_row.addWidget(title_label)

        help_label = QLabel(help_text)
        help_label.setProperty("class", "rowHelp")
        help_label.setWordWrap(True)

        text_col.addLayout(title_row)
        text_col.addWidget(help_label)

        row.addWidget(icon_frame)
        row.addLayout(text_col, 1)

        return row, {
            "icon_frame": icon_frame,
            "title_row": title_row,
            "title": title_label,
            "help": help_label,
        }

    @staticmethod
    def _divider():
        line = QFrame()
        line.setProperty("role", "divider")
        line.setFixedHeight(1)
        return line

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(0)

        # ---- header: title + status badge ----
        header = QHBoxLayout()
        header.setSpacing(12)
        title_label = QLabel("التحكم في الاتصال بالإنترنت")
        title_label.setObjectName("panelTitle")
        title_label.setWordWrap(True)

        self.badge = QFrame()
        self.badge.setObjectName("statusBadge")
        badge_layout = QHBoxLayout(self.badge)
        badge_layout.setContentsMargins(11, 5, 9, 5)
        badge_layout.setSpacing(6)
        self.badge_dot = QFrame()
        self.badge_dot.setFixedSize(7, 7)
        self.badge_word = QLabel("محلي")
        badge_layout.addWidget(self.badge_dot)
        badge_layout.addWidget(self.badge_word)

        header.addWidget(title_label, 1)
        header.addWidget(self.badge, 0, Qt.AlignVCenter)
        outer.addLayout(header)
        outer.addSpacing(16)

        # ---- toast overlay (session-snapshot confirmation) ----
        self.toast = QFrame(self)
        self.toast.setObjectName("toast")
        toast_layout = QHBoxLayout(self.toast)
        toast_layout.setContentsMargins(14, 9, 14, 9)
        toast_layout.setSpacing(8)
        toast_icon = QLabel("✓")
        toast_text = QLabel("تم حفظ نسخة احتياطية مشفرة للجلسة المحلية")
        toast_text.setWordWrap(True)
        toast_layout.addWidget(toast_icon)
        toast_layout.addWidget(toast_text, 1)
        self.toast.hide()
        self._toast_opacity = QGraphicsOpacityEffect(self.toast)
        self._toast_opacity.setOpacity(0.0)
        self.toast.setGraphicsEffect(self._toast_opacity)

        # ---- hero state banner ----
        self.hero = QFrame()
        self.hero.setObjectName("hero")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(12)
        self.hero_icon = QLabel("🔒")
        self.hero_icon.setObjectName("heroIcon")
        self.hero_icon.setFixedSize(38, 38)
        self.hero_icon.setAlignment(Qt.AlignCenter)
        self.hero_copy = QLabel(STATE_COPY[ConnectionState.LOCAL]["message"])
        self.hero_copy.setObjectName("heroCopy")
        self.hero_copy.setWordWrap(True)
        hero_layout.addWidget(self.hero_icon)
        hero_layout.addWidget(self.hero_copy, 1)
        outer.addWidget(self.hero)
        outer.addSpacing(16)

        self._hero_glow = QGraphicsDropShadowEffect(self.hero)
        self._hero_glow.setBlurRadius(0)
        self._hero_glow.setOffset(0, 0)
        self._hero_glow.setColor(QColor(0, 0, 0, 0))
        self.hero.setGraphicsEffect(self._hero_glow)

        # ---- row 1: Smart Internet Access ----
        row1, w1 = self._make_row_shell(
            "🔍", "الوصول الذكي للإنترنت", "بحث مؤقت ومشفّر، دون حفظ سجل التصفح"
        )
        self.access_switch = ToggleSwitch(on_color=palette(self._dark)["b"]["fg"])
        self.access_switch.setAccessibleName("الوصول الذكي للإنترنت")
        self.access_switch.toggled.connect(self._on_access_toggled)
        row1.addWidget(self.access_switch, 0, Qt.AlignVCenter)
        outer.addLayout(row1)

        outer.addWidget(self._divider())

        # ---- row 2: Disconnect & Lock ----
        row2, w2 = self._make_row_shell(
            "📴", "قطع الاتصال والعودة للوضع الآمن", "يُلغي الرموز النشطة فوراً ويعيدك للوضع المحلي"
        )
        self.disconnect_btn = QPushButton("قطع فوري")
        self.disconnect_btn.setObjectName("disconnectBtn")
        self.disconnect_btn.setCursor(Qt.PointingHandCursor)
        self.disconnect_btn.clicked.connect(self._on_disconnect_clicked)
        row2.addWidget(self.disconnect_btn, 0, Qt.AlignVCenter)
        outer.addLayout(row2)
        outer.addSpacing(10)

        # ---- row 3: External AI Handoff (distinct bordered block) ----
        self.handoff_block = QFrame()
        self.handoff_block.setObjectName("handoffBlock")
        self.handoff_block.setProperty("active", "false")
        handoff_outer = QVBoxLayout(self.handoff_block)
        handoff_outer.setContentsMargins(13, 12, 13, 12)
        row3, w3 = self._make_row_shell(
            "☁️", "تحويل خارجي للذكاء الاصطناعي", "يتطلب تفعيل الوصول للإنترنت أولاً"
        )
        self.handoff_help_label = w3["help"]

        self.handoff_tag = QLabel("●  نشط الآن")
        self.handoff_tag.setObjectName("handoffTag")
        self.handoff_tag.hide()
        w3["title_row"].addWidget(self.handoff_tag)
        w3["title_row"].addStretch(1)

        self.handoff_switch = ToggleSwitch(on_color=palette(self._dark)["c"]["fg"])
        self.handoff_switch.setAccessibleName("تحويل خارجي للذكاء الاصطناعي")
        self.handoff_switch.toggled.connect(self._on_handoff_toggled)
        row3.addWidget(self.handoff_switch, 0, Qt.AlignVCenter)

        handoff_outer.addLayout(row3)
        outer.addWidget(self.handoff_block)
        outer.addSpacing(14)

        # ---- footer ----
        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 12, 0, 0)
        lock_note = QLabel("🔐 التخزين محلي دائماً")
        last_check = QLabel("آخر تحقق: قبل لحظات")
        footer_layout.addWidget(lock_note)
        footer_layout.addStretch(1)
        footer_layout.addWidget(last_check)
        outer.addWidget(footer)

    def _build_animations(self):
        # looping glow ring for the "loud" ONLINE state
        grow = QPropertyAnimation(self._hero_glow, b"blurRadius", self)
        grow.setDuration(900)
        grow.setStartValue(6)
        grow.setEndValue(26)
        grow.setEasingCurve(QEasingCurve.InOutSine)
        shrink = QPropertyAnimation(self._hero_glow, b"blurRadius", self)
        shrink.setDuration(900)
        shrink.setStartValue(26)
        shrink.setEndValue(6)
        shrink.setEasingCurve(QEasingCurve.InOutSine)
        self._glow_loop = QSequentialAnimationGroup(self)
        self._glow_loop.addAnimation(grow)
        self._glow_loop.addAnimation(shrink)
        self._glow_loop.setLoopCount(-1)

        # one-shot emerald flash confirming Disconnect & Lock
        flash_up = QPropertyAnimation(self._hero_glow, b"blurRadius", self)
        flash_up.setDuration(180)
        flash_up.setStartValue(0)
        flash_up.setEndValue(22)
        flash_down = QPropertyAnimation(self._hero_glow, b"blurRadius", self)
        flash_down.setDuration(320)
        flash_down.setStartValue(22)
        flash_down.setEndValue(0)
        self._flash_anim = QSequentialAnimationGroup(self)
        self._flash_anim.addAnimation(flash_up)
        self._flash_anim.addAnimation(flash_down)

        # toast fade in/out
        self._toast_show_anim = QPropertyAnimation(self._toast_opacity, b"opacity", self)
        self._toast_show_anim.setDuration(240)
        self._toast_show_anim.setStartValue(0.0)
        self._toast_show_anim.setEndValue(1.0)
        self._toast_hide_anim = QPropertyAnimation(self._toast_opacity, b"opacity", self)
        self._toast_hide_anim.setDuration(280)
        self._toast_hide_anim.setStartValue(1.0)
        self._toast_hide_anim.setEndValue(0.0)
        self._toast_hide_anim.finished.connect(self.toast.hide)

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(3000)
        self._toast_timer.timeout.connect(self._hide_toast)

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    @staticmethod
    def _rgba(hex_color: str, alpha: int) -> str:
        c = QColor(hex_color)
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"

    def _render_state(self):
        p = palette(self._dark)
        sp = p[self._state.value]

        if self._connecting:
            self.hero.setStyleSheet(
                f"#hero {{ background:{p['card']}; border:1px solid {p['card_border']}; border-radius:16px; }}"
            )
            self.hero_icon.setText("⏳")
            self.hero_icon.setStyleSheet(
                f"#heroIcon {{ background:{p['hairline']}; border-radius:11px; font-size:16px; }}"
            )
            self.hero_copy.setText("جارٍ الاتصال…")
            self.hero_copy.setStyleSheet(f"#heroCopy {{ color:{p['ink_soft']}; font-size:13.5px; }}")
        else:
            copy = STATE_COPY[self._state]
            self.hero.setStyleSheet(
                f"#hero {{ background:{sp['bg']}; border:1px solid {sp['border']}; border-radius:16px; }}"
            )
            self.hero_icon.setText(copy["icon"])
            self.hero_icon.setStyleSheet(
                f"#heroIcon {{ background:{self._rgba(sp['fg'], 40)}; border-radius:11px; font-size:18px; }}"
            )
            self.hero_copy.setText(copy["message"])
            self.hero_copy.setStyleSheet(f"#heroCopy {{ color:{sp['fg_strong']}; font-size:13.5px; }}")

        self.badge.setStyleSheet(
            f"#statusBadge {{ background:{sp['bg']}; border:1px solid {sp['border']}; border-radius:999px; }}"
        )
        self.badge_dot.setStyleSheet(f"background:{sp['fg']}; border-radius:3px;")
        self.badge_word.setStyleSheet(f"color:{sp['fg_strong']}; font-size:12px;")
        self.badge_word.setText(STATE_COPY[self._state]["badge"])

        access_on = self._connecting or self._state in (ConnectionState.ONLINE, ConnectionState.CLOUD)
        self.access_switch.blockSignals(True)
        self.access_switch.setChecked(access_on)
        self.access_switch.blockSignals(False)
        self.access_switch.setEnabled(not self._connecting)

        handoff_on = self._state == ConnectionState.CLOUD
        self.handoff_switch.blockSignals(True)
        self.handoff_switch.setChecked(handoff_on)
        self.handoff_switch.blockSignals(False)
        self.handoff_switch.setEnabled(self._state != ConnectionState.LOCAL and not self._connecting)

        self.handoff_block.setProperty("active", "true" if handoff_on else "false")
        self.handoff_block.style().unpolish(self.handoff_block)
        self.handoff_block.style().polish(self.handoff_block)
        self.handoff_tag.setVisible(handoff_on)
        if handoff_on:
            c = p["c"]
            self.handoff_tag.setStyleSheet(
                f"#handoffTag {{ color:{c['fg_strong']}; background:{self._rgba(c['fg'], 40)};"
                " border-radius:999px; padding:3px 9px; font-size:10.5px; }"
            )

        if self._state == ConnectionState.LOCAL:
            self.handoff_help_label.setText("يتطلب تفعيل الوصول للإنترنت أولاً")
        elif handoff_on:
            self.handoff_help_label.setText("تتم معالجة هذا الطلب عبر خط أنابيب سحابي مشفّر")
        else:
            self.handoff_help_label.setText("يُستخدم فقط عند الحاجة لمعالجة متقدمة")

        if self._state == ConnectionState.ONLINE and not self._reduced_motion and not self._connecting:
            self._start_glow_loop(sp["glow"])
        else:
            self._stop_glow_loop()

    def _position_toast(self):
        self.toast.setGeometry(20, 14, self.width() - 40, self.toast.sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toast()

    def _start_glow_loop(self, color_hex: str):
        color = QColor(color_hex)
        color.setAlpha(160)
        self._hero_glow.setColor(color)
        if self._glow_loop.state() != QPropertyAnimation.Running:
            self._glow_loop.start()

    def _stop_glow_loop(self):
        self._glow_loop.stop()
        self._hero_glow.setBlurRadius(0)

    def _flash_safe(self):
        if self._reduced_motion:
            return
        color = QColor(palette(self._dark)["a"]["glow"])
        color.setAlpha(170)
        self._glow_loop.stop()
        self._hero_glow.setColor(color)
        self._flash_anim.stop()
        self._flash_anim.start()

    def _show_toast(self):
        self._position_toast()
        self.toast.show()
        self.toast.raise_()
        if self._reduced_motion:
            self._toast_opacity.setOpacity(1.0)
        else:
            self._toast_hide_anim.stop()
            self._toast_show_anim.stop()
            self._toast_show_anim.start()
        self._toast_timer.start()

    def _hide_toast(self):
        if self._reduced_motion:
            self.toast.hide()
        else:
            self._toast_show_anim.stop()
            self._toast_hide_anim.stop()
            self._toast_hide_anim.start()

    # ------------------------------------------------------------------
    # state machine / interaction
    # ------------------------------------------------------------------
    def _set_state(self, state: ConnectionState):
        self._state = state
        self._render_state()

    def _run_worker(self, fn, on_done):
        """Runs fn() on QThreadPool and calls on_done(result) back on the
        GUI thread. Keeps a strong reference to the Worker until it settles
        — QRunnable's C++ lifetime is pool-managed, but without holding the
        Python wrapper (and its `signals` QObject) alive here, it can be
        garbage-collected before the background thread finishes and the
        finished signal is lost."""
        worker = Worker(fn)
        self._workers.append(worker)

        def _settle(handler, *args):
            if worker in self._workers:
                self._workers.remove(worker)
            handler(*args)

        worker.signals.finished.connect(lambda result=None: _settle(on_done, result))
        worker.signals.error.connect(lambda msg: _settle(lambda _m: None, msg))
        QThreadPool.globalInstance().start(worker)

    def _on_access_toggled(self, checked: bool):
        if checked:
            if self._state == ConnectionState.LOCAL and not self._connecting:
                self._begin_connecting()
        else:
            self._op_token += 1
            self._connecting = False
            self._stop_glow_loop()
            self._set_state(ConnectionState.LOCAL)

    def _begin_connecting(self):
        self._connecting = True
        self._op_token += 1
        token = self._op_token
        self._render_state()
        self._run_worker(self._simulate_handshake, lambda _result, t=token: self._finish_connecting(t))

    @staticmethod
    def _simulate_handshake():
        # placeholder for a real network handshake — runs off the GUI thread
        time.sleep(0.6)
        return None

    def _finish_connecting(self, token: int):
        if token != self._op_token or not self._connecting:
            return  # user disconnected / toggled off before the handshake finished
        self._connecting = False
        self._set_state(ConnectionState.ONLINE)

    def _on_handoff_toggled(self, checked: bool):
        if checked and self._state == ConnectionState.ONLINE:
            self._op_token += 1
            token = self._op_token
            self._run_worker(self._simulate_snapshot_save, lambda _result, t=token: self._finish_handoff_engage(t))
        elif not checked and self._state == ConnectionState.CLOUD:
            self._op_token += 1
            self._set_state(ConnectionState.ONLINE)

    @staticmethod
    def _simulate_snapshot_save():
        # placeholder for a real encrypted local-session snapshot write — runs off the GUI thread
        time.sleep(0.4)
        return None

    def _finish_handoff_engage(self, token: int):
        if token != self._op_token:
            return  # user backed out before the snapshot finished saving
        self._set_state(ConnectionState.CLOUD)
        self._show_toast()

    def _on_disconnect_clicked(self):
        self._op_token += 1
        self._connecting = False
        self._stop_glow_loop()
        self._toast_timer.stop()
        self._hide_toast()
        self._set_state(ConnectionState.LOCAL)
        self._flash_safe()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def set_dark(self, dark: bool):
        self._dark = dark
        self.access_switch.set_on_color(palette(dark)["b"]["fg"])
        self.handoff_switch.set_on_color(palette(dark)["c"]["fg"])
        self._render_state()

    def set_reduced_motion(self, enabled: bool):
        self._reduced_motion = enabled
        if enabled:
            self._stop_glow_loop()
        self._render_state()


class MainWindow(QMainWindow):
    """Demo host window — the panel above is the deliverable; this just
    proves it inside a real 1280×720-minimum, RTL, themeable Qt window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hasaballa AI Platform — التحكم في الاتصال بالإنترنت")
        self.setMinimumSize(1280, 720)
        self._dark = False

        central = QWidget()
        central.setObjectName("canvas")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        topbar = QHBoxLayout()
        topbar.setContentsMargins(24, 18, 24, 0)
        topbar.setSpacing(12)
        stage_label = QLabel("Hasaballa AI Platform — لوحة التحكم في الاتصال")
        stage_label.setObjectName("stageLabel")
        topbar.addWidget(stage_label)
        topbar.addStretch(1)

        self.reduced_motion_check = QCheckBox("تقليل الحركة")
        self.reduced_motion_check.toggled.connect(self._on_reduced_motion_toggled)
        topbar.addWidget(self.reduced_motion_check)

        self.theme_btn = QPushButton("🌙  الوضع الداكن")
        self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        topbar.addWidget(self.theme_btn)
        root.addLayout(topbar)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        self.panel = SmartInternetAccessPanel()
        center_row.addWidget(self.panel)
        center_row.addStretch(1)

        root.addStretch(1)
        root.addLayout(center_row)
        root.addStretch(2)

        self._apply_theme()

    def _toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme()

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(build_stylesheet(self._dark))
        self.panel.set_dark(self._dark)
        self.theme_btn.setText("☀️  الوضع الفاتح" if self._dark else "🌙  الوضع الداكن")

    def _on_reduced_motion_toggled(self, checked: bool):
        self.panel.set_reduced_motion(checked)


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    load_fonts()
    app.setFont(QFont(FONT_FAMILY, 10))
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
