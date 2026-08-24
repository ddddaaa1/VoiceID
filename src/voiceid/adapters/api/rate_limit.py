"""Small in-process fixed-window limiter for the single-node API."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable


class FixedWindowRateLimiter:
    def __init__(
        self,
        maximum_requests: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if maximum_requests <= 0 or not math.isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError("rate-limit settings must be positive")
        self._maximum = maximum_requests
        self._window = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def consume(self, key: str) -> tuple[bool, int]:
        now = self._clock()
        with self._lock:
            started_at, count = self._windows.get(key, (now, 0))
            if now - started_at >= self._window:
                started_at, count = now, 0
            if count >= self._maximum:
                retry_after = max(1, math.ceil(self._window - (now - started_at)))
                self._windows[key] = (started_at, count)
                return False, retry_after
            self._windows[key] = (started_at, count + 1)
            return True, 0
