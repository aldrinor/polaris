"""Tests for queue.middleware.connection.StickyConnectionMiddleware.

Covers the worker-boot / worker-shutdown lifecycle hooks, including the
CLAUDE.md §9.4 fix where `client.close()` errors are now LOGGED rather
than silently swallowed.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

pytest.importorskip("dramatiq")

from polaris_v6.queue.middleware.connection import StickyConnectionMiddleware  # noqa: E402


def test_no_op_when_broker_lacks_client_attribute():
    """Stub-style brokers without `.client` should be silently allowed."""
    mw = StickyConnectionMiddleware()
    broker = MagicMock(spec=[])  # no `client` attribute
    worker = MagicMock()
    mw.before_worker_boot(broker, worker)
    # _local.client should NOT have been set.
    assert not hasattr(mw._local, "client")


def test_pins_client_on_worker_boot_when_broker_has_one():
    mw = StickyConnectionMiddleware()
    fake_client = MagicMock(name="redis_client")
    broker = MagicMock()
    broker.client = fake_client
    worker = MagicMock()

    mw.before_worker_boot(broker, worker)

    assert mw._local.client is fake_client


def test_clean_close_on_worker_shutdown():
    mw = StickyConnectionMiddleware()
    fake_client = MagicMock(name="redis_client")
    mw._local.client = fake_client

    mw.after_worker_shutdown(MagicMock(), MagicMock())

    fake_client.close.assert_called_once()
    assert mw._local.client is None


def test_close_errors_are_logged_not_swallowed(caplog: pytest.LogCaptureFixture):
    """Regression for CLAUDE.md §9.4 — old code did `except Exception: pass`.
    New code must emit a WARNING log line."""
    mw = StickyConnectionMiddleware()
    failing_client = MagicMock(name="redis_client")
    failing_client.close.side_effect = ConnectionResetError("redis closed mid-shutdown")
    mw._local.client = failing_client

    with caplog.at_level(logging.WARNING, logger="polaris_v6.queue.middleware.connection"):
        # Must NOT raise.
        mw.after_worker_shutdown(MagicMock(), MagicMock())

    # _local.client cleared even though close() failed.
    assert mw._local.client is None

    # WARNING was logged with the exception type name.
    matching = [r for r in caplog.records if "ConnectionResetError" in r.getMessage()]
    assert matching, f"expected warning log mentioning ConnectionResetError, got: {[r.getMessage() for r in caplog.records]}"


def test_no_op_on_shutdown_when_no_client_pinned():
    mw = StickyConnectionMiddleware()
    # Don't set _local.client.
    mw.after_worker_shutdown(MagicMock(), MagicMock())
    # No exception, no state change.
    assert not hasattr(mw._local, "client") or mw._local.client is None
