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
        """Cache the broker's Redis client on thread-local state at boot.

        No-op if the broker exposes no ``client`` attribute (e.g. StubBroker).
        """
        client_factory = getattr(broker, "client", None)
        if client_factory is None:
            return
        self._local.client = client_factory

    def after_worker_shutdown(self, broker: dramatiq.Broker, worker: dramatiq.Worker) -> None:
        """Close and clear the cached client at shutdown.

        A ``close()`` failure is logged (never swallowed silently) and teardown
        continues, since a failed close is non-fatal.
        """
        client = getattr(self._local, "client", None)
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                # CLAUDE.md §9.4: never `except: pass` silently. Log and
                # continue; failing to close a Redis connection during worker
                # shutdown is non-fatal but operators should see it. Branch
                # is covered by tests/v6/test_sticky_connection_middleware.py
                # ::test_close_errors_are_logged_not_swallowed.
                _log.warning(
                    "StickyConnectionMiddleware: client.close() raised %s during"
                    " after_worker_shutdown; continuing teardown.",
                    type(exc).__name__,
                )
            self._local.client = None
