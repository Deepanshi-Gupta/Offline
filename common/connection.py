"""App-wide Smart Internet Access connection state.

A shared singleton so every place that shows or drives this state — the
persistent header toggle (every screen), the panel embedded in Settings
(§14), and the dedicated showcase screen — reflect and mutate the same
Local / Online / Cloud state instead of each keeping an independent copy.
Flipping it from the header instantly shows up in Settings, and vice
versa, exactly like the offline/online indicator being "globally visible
at all times" the audit doc calls for.

    from common.connection import connection_manager, ConnectionState

    connection_manager.changed.connect(self._render)   # live updates
    connection_manager.go_online()                      # user action

Async transitions (the "connecting" handshake, the pre-handoff encrypted
snapshot save) run on QThreadPool via common/workers.Worker — centralized
here rather than duplicated in every view that can trigger them — so the
GUI thread is never blocked.
"""

import time
from enum import Enum

from PySide6.QtCore import QObject, QThreadPool, Signal

from common.workers import Worker


class ConnectionState(Enum):
    LOCAL = "a"
    ONLINE = "b"
    CLOUD = "c"


class ConnectionManager(QObject):
    changed = Signal()  # state, or the transient "connecting" flag, changed
    snapshot_saved = Signal()  # cloud handoff just engaged — views show the toast

    def __init__(self):
        super().__init__()
        self.state = ConnectionState.LOCAL
        self.connecting = False
        self._op_token = 0
        self._workers = []  # keeps Worker objects alive until they finish

    def is_online(self) -> bool:
        return self.state in (ConnectionState.ONLINE, ConnectionState.CLOUD)

    # ------------------------------------------------------------------
    def _run_worker(self, fn, on_done):
        worker = Worker(fn)
        self._workers.append(worker)

        def _settle(handler, *args):
            if worker in self._workers:
                self._workers.remove(worker)
            handler(*args)

        worker.signals.finished.connect(lambda result=None: _settle(on_done, result))
        worker.signals.error.connect(lambda msg: _settle(lambda _m: None, msg))
        QThreadPool.globalInstance().start(worker)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def go_online(self):
        if self.state != ConnectionState.LOCAL or self.connecting:
            return
        self.connecting = True
        self._op_token += 1
        token = self._op_token
        self.changed.emit()
        self._run_worker(self._simulate_handshake, lambda _r, tok=token: self._finish_connecting(tok))

    @staticmethod
    def _simulate_handshake():
        # placeholder for a real network handshake — runs off the GUI thread
        time.sleep(0.6)

    def _finish_connecting(self, token: int):
        if token != self._op_token or not self.connecting:
            return  # disconnected before the handshake finished
        self.connecting = False
        self.state = ConnectionState.ONLINE
        self.changed.emit()

    def engage_handoff(self):
        if self.state != ConnectionState.ONLINE:
            return
        self._op_token += 1
        token = self._op_token
        self._run_worker(self._simulate_snapshot_save, lambda _r, tok=token: self._finish_handoff(tok))

    @staticmethod
    def _simulate_snapshot_save():
        # placeholder for a real encrypted local-session snapshot write — off the GUI thread
        time.sleep(0.4)

    def _finish_handoff(self, token: int):
        if token != self._op_token:
            return  # backed out before the snapshot finished saving
        self.state = ConnectionState.CLOUD
        self.changed.emit()
        self.snapshot_saved.emit()

    def disengage_handoff(self):
        if self.state != ConnectionState.CLOUD:
            return
        self._op_token += 1
        self.state = ConnectionState.ONLINE
        self.changed.emit()

    def disconnect(self):
        self._op_token += 1
        self.connecting = False
        self.state = ConnectionState.LOCAL
        self.changed.emit()


# The one instance every screen imports.
connection_manager = ConnectionManager()
