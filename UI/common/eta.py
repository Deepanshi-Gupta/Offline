"""Time-remaining estimation for long-running operations.

Every operation that can run longer than ~10s (export/render queue, image
batch generation, voice generation, motion generation, …) must show the
user a time estimate, not just a percentage. This module centralizes both
halves of that:

* `EtaEstimator` — a backend-agnostic estimator. It does NOT need to know
  a screen's tick math or the real model's throughput; it extrapolates
  wall-clock elapsed against the reported progress fraction
  (remaining = elapsed * (1 - p) / p). That means the same helper works
  for a simulated QTimer loop today and a real GPU queue later, with no
  per-screen tuning.

* `format_remaining` — turns a seconds estimate into a short, localized,
  RTL-safe label ("~45 sec left" / "يتبقّى ~45 ثانية"), or an
  "Estimating…" placeholder while there isn't enough signal yet.

Usage in a screen:

    from common.eta import EtaEstimator, format_remaining

    self._eta = EtaEstimator()
    ...
    self._eta.start()                       # when the operation begins
    ...
    # each tick / progress callback:
    label.setText(format_remaining(self._eta.remaining(overall_progress)))
    ...
    self._eta.reset()                       # when it finishes / is cancelled

`remaining()` deliberately returns None (→ "Estimating…") until at least
`min_elapsed` seconds have passed and some progress is reported, so the
first, wildly-inaccurate extrapolation is never shown.
"""

import time

from common.i18n import t


class EtaEstimator:
    """Elapsed-vs-progress estimator with pause/resume support. Time spent
    paused is not counted against the estimate — `pause()`/`resume()` bank
    the elapsed time of each running segment, so an operation the user
    paused for a minute doesn't report a wildly inflated ETA on resume."""

    def __init__(self, min_elapsed: float = 1.5):
        self._min_elapsed = min_elapsed
        self._segment_start = None  # monotonic clock at start of current segment
        self._accumulated = 0.0     # banked running time from prior segments
        self._active = False

    def start(self):
        self._accumulated = 0.0
        self._segment_start = time.monotonic()
        self._active = True

    def pause(self):
        if self._segment_start is not None:
            self._accumulated += time.monotonic() - self._segment_start
            self._segment_start = None

    def resume(self):
        if self._active and self._segment_start is None:
            self._segment_start = time.monotonic()

    def reset(self):
        self._segment_start = None
        self._accumulated = 0.0
        self._active = False

    @property
    def running(self) -> bool:
        return self._active

    def _elapsed(self) -> float:
        elapsed = self._accumulated
        if self._segment_start is not None:
            elapsed += time.monotonic() - self._segment_start
        return elapsed

    def remaining(self, progress: float):
        """Seconds remaining for `progress` in [0, 1], or None if there is
        not yet enough signal to estimate (not started, no progress, too
        little elapsed time, or already complete)."""
        if not self._active or progress <= 0.0 or progress >= 1.0:
            return None
        elapsed = self._elapsed()
        if elapsed < self._min_elapsed:
            return None
        return elapsed * (1.0 - progress) / progress


def format_remaining(seconds) -> str:
    """Localized short 'time left' label. `seconds` is None → 'Estimating…'."""
    if seconds is None:
        return t("common.eta.calculating")
    seconds = max(1, int(round(seconds)))
    if seconds < 90:
        value = t("common.eta.sec", n=seconds)
    else:
        value = t("common.eta.min", n=int(round(seconds / 60.0)))
    return t("common.eta.remaining", v=value)


def format_progress(progress: float, seconds) -> str:
    """Percent + time-remaining in one string: '42% · ~45 sec left'."""
    return t("common.eta.progress", pct=int(round(progress * 100)), rem=format_remaining(seconds))
