"""Background-thread helper for PySide6 screens.

Every long-running operation (model inference, rendering, network calls,
file I/O) must run off the GUI thread or Qt marks the window "Not
Responding". `Worker` wraps a plain callable and runs it on
`QThreadPool.globalInstance()`; results/errors come back to the GUI thread
via Qt signals, which are safe to connect directly to widget slots.

Usage:
    worker = Worker(some_slow_function, arg1, kwarg=2)
    worker.signals.finished.connect(on_done)
    worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
"""

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object)  # emits the callable's return value
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced to the GUI thread, not swallowed
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(result)
