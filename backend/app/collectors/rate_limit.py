"""单进程串行频控。延迟只为降低空响与封禁，不是合规义务。"""

from __future__ import annotations

import random
import threading
import time


class RateLimiter:
    def __init__(self, delay_seconds: float, *, jitter: bool = False, min_seconds: float = 0.0):
        self._delay = max(delay_seconds, min_seconds)
        self._jitter = jitter
        self._min = min_seconds
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = self._delay
            if self._jitter:
                delay = max(delay, self._min) * (1.0 + random.uniform(0.0, 0.3))
            now = time.monotonic()
            gap = delay - (now - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()
