"""Shared Qt widgets reused across every converted screen.

These are native ports of the small HTML/CSS components that recur in
nearly every *_app.py Streamlit source (the offline pill, the colored
status badge, `st.container(border=True)` cards, the waveform image, the
selectable face thumbnail) — centralizing them here means each converted
screen wires up behavior, not rewrites of the same pill/badge/card CSS in
QSS thirteen times.
"""

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEasingCurve,
    QIODevice,
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from common.compliance import compliance_activity
from common.i18n import lang_manager, t
from common.qt_theme import semantic

TONE_KEYS = {
    "success": ("success_bg", "success_border", "success_fg_strong"),
    "warning": ("warning_bg", "warning_border", "warning_fg_strong"),
    "danger": ("danger_bg", "danger_border", "danger_fg_strong"),
    "info": ("info_bg", "info_border", "info_fg"),
    "neutral": ("surface_muted", "border", "ink_faint"),
}


def repolish(widget: QWidget):
    """Call after setProperty() on an already-shown widget so QSS
    property-selectors (e.g. [role="card"]) re-evaluate immediately."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def clear_layout(layout):
    """Removes and deletes every widget from a layout (rebuild-on-render
    pattern used by several screens). Binds `item.widget()` to a local
    once — calling it repeatedly on the same QLayoutItem after
    `setParent(None)` risks the temporary wrapper being garbage-collected
    between calls, invalidating the next `.widget()` lookup.

    Hides each widget before reparenting: `setParent(None)` alone turns a
    QWidget into an independent top-level window, which can flash on
    screen (or bleed into an offscreen grab) for the frame or two before
    the deferred `deleteLater()` actually runs.

    Recurses into nested layouts (items added via `addLayout(...)`, e.g. a
    grid of per-row QHBoxLayouts): `item.widget()` is None for those, so
    without this they — and every widget inside them — silently survive
    each "clear" and pile up as duplicates on every re-render.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)


def set_role(widget: QWidget, role: str):
    widget.setProperty("role", role)
    repolish(widget)


def skip_step_button(parent=None) -> QPushButton:
    """The one canonical "⏭ Skip This Step" control (task B2).

    Skipping the current step and aborting the whole operation are two
    different actions and must look different: this button is deliberately
    neutral (no `variant`), whereas Cancel/Abort carry `variant="danger"`.
    Callers connect their own handler and re-set the text from
    t("common.btn.skip_step") in their `retranslate()` (the shared key keeps
    the label identical on every screen). Kept as a factory, not a
    QPushButton subclass, so it drops straight into existing button rows."""
    btn = QPushButton(t("common.btn.skip_step"), parent)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setProperty("role", "skipStep")
    return btn


class Card(QFrame):
    """Native port of `st.container(border=True)` — a bordered, rounded
    panel. Use `.layout()` (installed below) to add content."""

    def __init__(self, parent=None, flat=False, margins=(16, 14, 16, 14), spacing=8):
        super().__init__(parent)
        self.setProperty("role", "cardFlat" if flat else "card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)


class SectionLabel(QLabel):
    """Native port of the recurring `.section-label` bold header text."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "sectionLabel")


class CaptionLabel(QLabel):
    """Native port of `st.caption(...)`."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "caption")
        self.setWordWrap(True)


class OfflinePill(QFrame):
    """The small "Offline — no network used" header pill repeated at the
    top of almost every screen. Tone-able (green/warning/info/...) so it
    can double as the app-wide connection-status indicator — see
    set_tone(), used by hasaballa_desktop_app.py's header toggle."""

    def __init__(self, text="Offline — no network used", dark=False, tone="success", parent=None):
        super().__init__(parent)
        self.setObjectName("offlinePill")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 4, 11, 4)
        lay.setSpacing(6)
        self._dot = QFrame()
        self._dot.setFixedSize(7, 7)
        self._label = QLabel(text)
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        self._tone = tone
        self._dark = dark
        self._apply_style()

    def set_text(self, text: str):
        self._label.setText(text)

    def set_tone(self, tone: str):
        self._tone = tone
        self._apply_style()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._apply_style()

    def _apply_style(self):
        s = semantic(self._dark)
        bg_k, border_k, fg_k = TONE_KEYS.get(self._tone, TONE_KEYS["success"])
        fg_dot_k = {"success_bg": "success_fg", "warning_bg": "warning_fg", "danger_bg": "danger_fg", "info_bg": "info_fg"}.get(bg_k, "success_fg")
        self.setStyleSheet(
            f"#offlinePill {{ background:{s[bg_k]}; border:1px solid {s[border_k]}; border-radius:999px; }}"
        )
        self._dot.setStyleSheet(f"background:{s.get(fg_dot_k, s[fg_k])}; border-radius:3px; border:none;")
        self._label.setStyleSheet(
            f"color:{s[fg_k]}; font-size:11.5px; font-weight:600; background:transparent; border:none;"
        )


class StatusBadge(QLabel):
    """Generic colored status pill (success/warning/danger/info/neutral)
    — the native equivalent of every screen's local `status_badge_html()`."""

    def __init__(self, text="", tone="neutral", dark=False, parent=None):
        super().__init__(text, parent)
        self.setObjectName("statusBadgePlain")
        self._tone = tone
        self.set_dark(dark)

    def set_tone(self, tone: str, dark: bool = False):
        self._tone = tone
        self.set_dark(dark)

    def set_dark(self, dark: bool):
        s = semantic(dark)
        bg_k, border_k, fg_k = TONE_KEYS.get(self._tone, TONE_KEYS["neutral"])
        self.setStyleSheet(
            f"#statusBadgePlain {{ background:{s[bg_k]}; border:1px solid {s[border_k]}; color:{s[fg_k]};"
            " border-radius:999px; padding:2px 10px; font-size:11.5px; font-weight:700; }"
        )


class ComplianceActivityIndicator(QFrame):
    """Small info-toned pill — "N items auto-corrected this session" (B3).

    Reads the process-wide `compliance_activity` counter and updates itself
    live whenever a screen records a correction or the language flips.
    Screens place one in their generation area and show it during
    generation; the count itself is session-wide, so switching screens
    mid-session preserves it."""

    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self.setObjectName("complianceIndicator")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 4, 11, 4)
        lay.setSpacing(6)
        self._dot = QFrame()
        self._dot.setFixedSize(7, 7)
        self._label = QLabel()
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        self._dark = dark
        compliance_activity.changed.connect(self._refresh)
        lang_manager.changed.connect(self._refresh)
        self._apply_style()
        self._refresh()

    def _refresh(self, *_):
        n = compliance_activity.count
        key = "common.compliance.none" if n == 0 else "common.compliance.one" if n == 1 else "common.compliance.many"
        self._label.setText(t(key, n=n))

    def set_dark(self, dark: bool):
        self._dark = dark
        self._apply_style()

    def _apply_style(self):
        s = semantic(self._dark)
        self.setStyleSheet(
            f"#complianceIndicator {{ background:{s['info_bg']}; border:1px solid {s['info_border']}; border-radius:999px; }}"
        )
        self._dot.setStyleSheet(f"background:{s['info_fg']}; border-radius:3px; border:none;")
        self._label.setStyleSheet(
            f"color:{s['info_fg']}; font-size:11.5px; font-weight:600; background:transparent; border:none;"
        )


class IconBadge(QLabel):
    """Circular (or rounded-square, `variant='green'`) icon chip used in
    the voice-cloning section headers."""

    def __init__(self, icon_text: str, variant="dark", size=34, dark=False, parent=None):
        super().__init__(icon_text, parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._variant = variant
        self.set_dark(dark)

    def set_dark(self, dark: bool):
        s = semantic(dark)
        if self._variant == "green":
            self.setStyleSheet(f"background:{s['success_fg']}; color:white; border-radius:8px; font-size:15px; font-weight:700;")
        else:
            radius = self.width() // 2
            self.setStyleSheet(
                f"background:{s['surface']}; color:{s['ink']}; border:1px solid {s['border']};"
                f" border-radius:{radius}px; font-size:15px; font-weight:700;"
            )


class SelectableThumb(QToolButton):
    """Checkable square image thumbnail with a dashed selection ring —
    native port of `common/style.py`'s `thumb_html()`."""

    def __init__(self, pixmap, size=96, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(QIcon(pixmap))
        self.setIconSize(pixmap.size().scaled(size - 8, size - 8, Qt.KeepAspectRatioByExpanding))
        self.setFixedSize(size, size)
        self.setProperty("role", "thumb")
        self.toggled.connect(lambda _checked: repolish(self))


class Waveform(QWidget):
    """Native paint port of `common/audio.py`'s `waveform_svg_data_uri()`
    — same bucket/normalize/bar algorithm, drawn directly with QPainter
    instead of round-tripping through an SVG data URI."""

    def __init__(self, samples=None, color="#2F6FEF", bars=64, parent=None):
        super().__init__(parent)
        self._samples = samples or [0.0]
        self._color = QColor(color)
        self._bars = bars
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_samples(self, samples, color=None):
        self._samples = samples or [0.0]
        if color:
            self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        samples = self._samples or [0.0]
        chunk = max(1, len(samples) // self._bars)
        levels = []
        for i in range(self._bars):
            seg = samples[i * chunk : (i + 1) * chunk] or [0.0]
            levels.append(max(abs(v) for v in seg))
        peak = max(levels) or 1.0
        levels = [lvl / peak for lvl in levels]

        bar_w = w / self._bars
        mid = h / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        for i, lvl in enumerate(levels):
            bar_h = max(2.0, lvl * (h - 6))
            x = i * bar_w
            y = mid - bar_h / 2
            painter.drawRoundedRect(int(x), int(y), max(1, int(bar_w * 0.6)), int(bar_h), 1.5, 1.5)


class BarChart(QWidget):
    """Minimal bottom-anchored bar chart (values grow up from a baseline)
    — used for small analytics strips like "views, last 7 days"."""

    def __init__(self, values=None, color="#2F6FEF", parent=None):
        super().__init__(parent)
        self._values = values or []
        self._color = QColor(color)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_values(self, values, color=None):
        self._values = values or []
        if color:
            self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        values = self._values or [0]
        peak = max(values) or 1
        n = len(values)
        gap = 6
        bar_w = (w - gap * (n - 1)) / n if n else w
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        for i, v in enumerate(values):
            bar_h = max(2.0, (v / peak) * (h - 4))
            x = i * (bar_w + gap)
            y = h - bar_h
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 2.0, 2.0)


class AudioPlayer(QObject):
    """Plays raw WAV bytes (from common/audio.py) via QMediaPlayer. Keeps
    the QBuffer alive on `self` for the duration of playback — the same
    GC-lifetime pitfall documented in common/workers.py applies here."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._buffer = None

    def play_bytes(self, wav_bytes: bytes):
        self._player.stop()
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(wav_bytes))
        self._buffer.open(QIODevice.ReadOnly)
        self._player.setSourceDevice(self._buffer, QUrl("clip.wav"))
        self._player.play()

    def stop(self):
        self._player.stop()


class Toast(QFrame):
    """Floating auto-fading confirmation banner — native port of every
    screen's `st.toast(...)` calls. Positions itself at the bottom-center
    of `parent`, fades in, holds, fades out, then deletes itself."""

    def __init__(self, parent: QWidget, text: str, dark: bool = False, msec: int = 2600):
        super().__init__(parent)
        self.setObjectName("toastPlain")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 9)
        label = QLabel(text)
        label.setWordWrap(True)
        lay.addWidget(label)
        self.set_dark(dark)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self.adjustSize()
        self._reposition()

        self._show_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._show_anim.setDuration(220)
        self._show_anim.setStartValue(0.0)
        self._show_anim.setEndValue(1.0)
        self._show_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._hide_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._hide_anim.setDuration(260)
        self._hide_anim.setStartValue(1.0)
        self._hide_anim.setEndValue(0.0)
        self._hide_anim.finished.connect(self.deleteLater)

        self.show()
        self.raise_()
        self._show_anim.start()
        QTimer.singleShot(msec, self._hide_anim.start)

    def set_dark(self, dark: bool):
        s = semantic(dark)
        self.setStyleSheet(
            f"#toastPlain {{ background:{s['surface']}; border:1px solid {s['border']}; border-radius:10px; }}"
            f" #toastPlain QLabel {{ color:{s['ink']}; font-size:12.5px; font-weight:600; background:transparent; }}"
        )

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 24
        self.move(max(8, x), max(8, y))


def show_toast(parent: QWidget, text: str, dark: bool = False, msec: int = 2600) -> Toast:
    return Toast(parent, text, dark=dark, msec=msec)
