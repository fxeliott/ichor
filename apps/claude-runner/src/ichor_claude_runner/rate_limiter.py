"""In-memory rate limiter — prevent runaway Hetzner cron from exhausting
the Max 20x weekly cap.

Design: simple sliding window (last hour) per request type.
Persistence: NOT durable across restarts — that's intentional for Phase 0
(restarts are rare; cap is conservative).
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock


class HourlyRateLimiter:
    """Allow up to N events per rolling hour."""

    def __init__(self, max_per_hour: int) -> None:
        self._max = max_per_hour
        self._events: deque[float] = deque()
        self._lock = Lock()

    def try_acquire(self) -> bool:
        """Returns True if accepted, False if over quota."""
        now = time.monotonic()
        cutoff = now - 3600.0

        with self._lock:
            # Drop expired events from the left
            while self._events and self._events[0] < cutoff:
                self._events.popleft()

            if len(self._events) >= self._max:
                return False

            self._events.append(now)
            return True

    def current_count(self) -> int:
        with self._lock:
            return len(self._events)

    def remaining(self) -> int:
        return max(0, self._max - self.current_count())
