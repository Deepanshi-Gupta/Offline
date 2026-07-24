"""Shared character-name roster so other screens (e.g. Motion Generation's
Profile Character picker) can list the characters defined in Character Packs
without importing CharacterPackScreen's Qt widgets.

Mirrors the `compliance_activity` / `connection_manager` singleton pattern
(see common/compliance.py, common/connection.py): CharacterPackScreen is the
sole owner of the roster and calls `sync()` with its full character-name list
whenever that list changes (add/remove/rename/import); any number of
listeners connect to `changed` and re-read `names()`.
"""

from PySide6.QtCore import QObject, Signal


class _CharacterRegistry(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._names = []

    def names(self) -> list:
        return list(self._names)

    def sync(self, names):
        """Replace the full roster. Owned by Character Packs — the only
        screen that adds/removes/renames characters."""
        deduped = list(dict.fromkeys(n for n in names if n))
        if deduped != self._names:
            self._names = deduped
            self.changed.emit()


character_registry = _CharacterRegistry()
