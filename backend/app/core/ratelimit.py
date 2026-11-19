"""In-process sliding-window rate limiter with lockout backoff.

Single-owner deployment: one process, so memory is a legitimate store. If this ever runs
multi-worker, move the buckets to Redis behind the same interface.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int, lockout_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._events: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Seconds the caller must wait, or None when the request may proceed."""
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(key)
            if until and until > now:
                return max(1, int(until - now))
            if until:
                self._locked_until.pop(key, None)

            events = self._events.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while events and events[0] < cutoff:
                events.popleft()

            if len(events) >= self.max_attempts:
                # Exponential lockout: 1x, 2x, 4x ... capped at 8x the base value.
                over = len(events) - self.max_attempts + 1
                seconds = min(self.lockout_seconds * (2 ** (over - 1)), self.lockout_seconds * 8)
                self._locked_until[key] = now + seconds
                return max(1, int(seconds))
            return None

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._events.setdefault(key, deque()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
            self._locked_until.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._locked_until.clear()
