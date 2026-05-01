"""Sticky Redis connection middleware (cookbook pattern).

Without this, Dramatiq workers may rotate connections under load,
causing connection-establish overhead per message. The cookbook pattern
is to attach a single Redis client to the worker thread and reuse it.

This is a no-op for StubBroker; useful only against RedisBroker.
"""

from __future__ import annotations

import logging
import threading

import dramatiq

_log = logging.getLogger(__name__)


class StickyConnectionMiddleware(dramatiq.Middleware):
    """Reuse one Redis connection per worker thread."""

    def __init__(self) -> None:
        self._local = threading.local()

    def before_worker_boot(self, broker: dramatiq.Broker, worker: dramatiq.Worker) -> None:
        client_factory = getattr(broker, "client", None)
        if client_factory is None:
            return
        self._local.client = client_factory

    def after_worker_shutdown(self, broker: dramatiq.Broker, worker: dramatiq.Worker) -> None:
        client = getattr(self._local, "client", None)
        if client is not None:
            try:
                client.close()
            except Exception as exc:  # pragma: no cover - cleanup-time guard
                # CLAUDE.md §9.4: never `except: pass` silently. Log and
                # continue; failing to close a Redis connection during worker
                # shutdown is non-fatal but operators should see it.
                _log.warning(
                    "StickyConnectionMiddleware: client.close() raised %s during"
                    " after_worker_shutdown; continuing teardown.",
                    type(exc).__name__,
                )
            self._local.client = None
