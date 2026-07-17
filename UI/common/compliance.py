"""Session-wide compliance-activity counter (task B3).

The platform silently auto-corrects content that trips a compliance guard
(e.g. an image scene re-generated to satisfy the modesty filter, a motion
scene whose quality-guard detected drift and auto-fixed it). The client
asked for a small, persistent indicator — "2 items auto-corrected this
session" — so these silent corrections are visible during generation
rather than happening invisibly.

`compliance_activity` is a process-wide singleton, mirroring how
`lang_manager` (common/i18n.py) is the single source of truth for the
language toggle. Screens call `compliance_activity.record()` at the point
an auto-correction actually happens; any number of
`ComplianceActivityIndicator` widgets (see common/qt_widgets.py) connect to
`changed` and update themselves. "Session" = process lifetime; there is no
persistence to disk.
"""

from PySide6.QtCore import QObject, Signal


class _ComplianceActivity(QObject):
    changed = Signal(int)  # emits the new total

    def __init__(self):
        super().__init__()
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def record(self, n: int = 1):
        """Record `n` auto-corrections and notify listeners."""
        if n <= 0:
            return
        self._count += n
        self.changed.emit(self._count)

    def reset(self):
        self._count = 0
        self.changed.emit(0)


compliance_activity = _ComplianceActivity()
