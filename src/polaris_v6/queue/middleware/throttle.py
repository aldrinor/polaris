"""Throttle middleware — caps degradation under high retry rates.

Per docs/backend_modernization.md §1: high retry rates (>50%) degrade all
queues by 40%, mitigated by throttling. This middleware tracks recent
failure ratio per actor and inserts a backoff delay when the ratio
exceeds the threshold.
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Any

import dramatiq


class ThrottleMiddleware(dramatiq.Middleware):
    """Per-actor failure-rate throttle.

    Tracks rolling failures over a window and adds a backoff delay when
    the failure ratio exceeds `failure_threshold`.
    """

    def __init__(
        self,
        *,
        window_size: int = 100,
        failure_threshold: float = 0.5,
        backoff_ms: int = 250,
    ) -> None:
        self._window_size = window_size
        self._failure_threshold = failure_threshold
        self._backoff_ms = backoff_ms
        self._lock = threading.Lock()
        self._outcomes: dict[str, collections.deque[bool]] = {}

    def _record(self, actor_name: str, failed: bool) -> float:
        with self._lock:
            window = self._outcomes.setdefault(
                actor_name, collections.deque(maxlen=self._window_size)
            )
            window.append(failed)
            if not window:
                return 0.0
            return sum(window) / len(window)

    def after_process_message(
        self,
        broker: dramatiq.Broker,
        message: dramatiq.Message,
        *,
        result: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        failure_ratio = self._record(message.actor_name, exception is not None)
        if failure_ratio >= self._failure_threshold:
            time.sleep(self._backoff_ms / 1000.0)
