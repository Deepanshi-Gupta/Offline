"""Native Windows-desktop integration the browser-era Streamlit app could not
have — three concerns the desktop checklist (UI-audit gaps A2/A3 + tray) asks
for, gathered in one leaf module:

  * ``SleepInhibitor`` — keeps the machine (and, optionally, the display) awake
    while held, so a 45-minute render is never killed by Windows sleeping
    mid-way (gap A3). Ref-counted; a no-op on non-Windows / headless.
  * ``render_activity`` — a process-wide signal screens raise around a render.
    While any render is active it holds the ``SleepInhibitor``; on completion
    it asks the shell to fire a *native* OS notification (gap A2).
  * ``DesktopTray`` — a ``QSystemTrayIcon`` wrapper: system-tray presence,
    minimize-to-tray, and ``notify()`` which produces a real Windows toast
    (shows even when the window is minimised/hidden). This is deliberately
    distinct from ``common.qt_widgets.show_toast``, which is an *in-app*
    floating banner only visible while the window is focused.

Pure standard library + PySide6 (``ctypes`` reaches the Win32 power API),
matching backend.md §1.1's "the UI imports only stdlib + PySide6" rule. Every
Windows-only path degrades to a harmless no-op elsewhere so the app still
launches on a machine with no tray / no GPU (backend.md §1).

Usage from a render screen::

    from common.desktop import render_activity

    render_activity.begin("export")          # running -> hold sleep-inhibit
    ...
    render_activity.end("export")            # paused/stopped -> release
    render_activity.notify(t("nav.export"), success=True, detail="3 ratios")
"""

import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


# =====================================================================
# Keep-awake (gap A3)
# =====================================================================
class SleepInhibitor:
    """Prevent Windows from sleeping / blanking the display while held.

    Ref-counted: nested/overlapping renders each ``acquire()`` and the machine
    is only released to sleep again once the *last* one ``release()``s, so one
    render finishing never lets the box sleep out from under another. Off
    Windows (or if the Win32 call is unavailable) every method is a no-op — the
    render simply proceeds without a sleep guard rather than crashing.
    """

    # winbase.h SetThreadExecutionState flags
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, keep_display_on: bool = True):
        self._count = 0
        self._keep_display = keep_display_on

    def acquire(self):
        self._count += 1
        if self._count == 1:
            self._apply(active=True)

    def release(self):
        if self._count == 0:
            return
        self._count -= 1
        if self._count == 0:
            self._apply(active=False)

    @property
    def held(self) -> bool:
        return self._count > 0

    def _apply(self, active: bool):
        if sys.platform != "win32":
            return
        try:
            import ctypes

            flags = self._ES_CONTINUOUS
            if active:
                flags |= self._ES_SYSTEM_REQUIRED
                if self._keep_display:
                    flags |= self._ES_DISPLAY_REQUIRED
            # ES_CONTINUOUS sets a persistent state until the next call; passing
            # bare ES_CONTINUOUS clears the system/display request again.
            ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
        except Exception:  # noqa: BLE001 - a missing power API must never crash a render
            pass


# =====================================================================
# Render-activity hub (drives sleep-inhibit + native notifications)
# =====================================================================
class _RenderActivity(QObject):
    """Process-wide, GUI-thread render tracker.

    Screens call ``begin(token)`` when a render *starts running* and
    ``end(token)`` when it *stops running* (pause, cancel, or finish). The set
    of active tokens holds the shared :class:`SleepInhibitor`. Terminal success
    or failure is announced separately via ``notify(...)`` so the shell can fire
    a native OS toast — pausing must not look like "done".
    """

    active_changed = Signal(int)                    # number of running renders
    notify_requested = Signal(str, bool, str)       # name, success, detail

    def __init__(self):
        super().__init__()
        self._active: set = set()
        self._inhibitor = SleepInhibitor()

    def begin(self, token: str):
        was_idle = not self._active
        self._active.add(token)
        if was_idle:
            self._inhibitor.acquire()
        self.active_changed.emit(len(self._active))

    def end(self, token: str):
        if token not in self._active:
            return
        self._active.discard(token)
        if not self._active:
            self._inhibitor.release()
        self.active_changed.emit(len(self._active))

    def notify(self, name: str, success: bool = True, detail: str = ""):
        """Announce a render reached a terminal state — the shell turns this
        into a native OS toast (gap A2)."""
        self.notify_requested.emit(str(name), bool(success), str(detail))

    @property
    def busy(self) -> bool:
        return bool(self._active)


# The one instance screens and the shell share.
render_activity = _RenderActivity()


# =====================================================================
# App / tray icon
# =====================================================================
def make_app_icon(color: str = "#2F6FEF") -> QIcon:
    """A crisp, self-drawn app/tray icon (no bundled .ico asset exists).

    Rendered at 3 sizes so Windows picks a sharp one for the tray, taskbar, and
    high-DPI notification thumbnail rather than upscaling a single bitmap.
    """
    icon = QIcon()
    for size in (16, 32, 64):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        radius = size * 0.28
        p.drawRoundedRect(0, 0, size, size, radius, radius)
        p.setPen(QColor("#FFFFFF"))
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(size * 0.62))
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignCenter, "H")
        p.end()
        icon.addPixmap(pix)
    return icon


class DesktopTray(QObject):
    """System-tray presence + native toast notifications.

    Wraps ``QSystemTrayIcon`` and degrades to a no-op when no system tray is
    available (some Windows shells, remote/headless sessions). ``available``
    lets the shell decide whether minimize-to-tray behaviour is safe to enable.
    """

    show_requested = Signal()   # user asked to restore the window
    quit_requested = Signal()   # user asked to really quit

    def __init__(self, icon: QIcon, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(tooltip)
        self._menu = QMenu()
        self._show_action = self._menu.addAction("")
        self._show_action.triggered.connect(self.show_requested.emit)
        self._quit_action = self._menu.addAction("")
        self._quit_action.triggered.connect(self.quit_requested.emit)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    @property
    def available(self) -> bool:
        return self._tray is not None

    def set_labels(self, show_label: str, quit_label: str, tooltip: str = ""):
        if not self._tray:
            return
        self._show_action.setText(show_label)
        self._quit_action.setText(quit_label)
        if tooltip:
            self._tray.setToolTip(tooltip)

    def notify(self, title: str, message: str, success: bool = True, msecs: int = 6000):
        """Fire a native OS notification. Falls back silently if no tray."""
        if not self._tray:
            return
        icon = QSystemTrayIcon.Information if success else QSystemTrayIcon.Warning
        self._tray.showMessage(title, message, icon, msecs)

    def _on_activated(self, reason):
        # double-click / single trigger on the tray icon restores the window
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_requested.emit()


def enable_high_dpi():
    """Opt into crisp fractional scaling *before* the QApplication exists.

    Qt 6 already enables high-DPI scaling by default; what still matters on the
    client's 16" WQXGA @ 300Hz panel (typically 125–150% Windows scaling) is the
    rounding policy — ``PassThrough`` keeps fractional factors instead of
    rounding 1.5× down to 1×, so text/icons stay sharp rather than soft. Must be
    called before ``QApplication(...)`` or Qt ignores it.
    """
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:  # noqa: BLE001 - never block startup over a display hint
        pass
