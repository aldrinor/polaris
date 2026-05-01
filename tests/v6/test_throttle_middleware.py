"""Tests for queue.middleware.throttle.ThrottleMiddleware.

Verifies the per-actor failure-rate throttle inserts a backoff delay
when failure ratio exceeds the threshold and stays silent below it.
Uses the public after_process_message hook — same surface Dramatiq
invokes in production — with synthetic Message objects (no real broker).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("dramatiq")

from polaris_v6.queue.middleware.throttle import ThrottleMiddleware  # noqa: E402


def _msg(actor_name: str) -> MagicMock:
    m = MagicMock()
    m.actor_name = actor_name
    return m


def test_no_backoff_when_failure_ratio_below_threshold():
    mw = ThrottleMiddleware(window_size=10, failure_threshold=0.5, backoff_ms=200)

    start = time.monotonic()
    # 4 successes, 1 failure → ratio 0.2 < 0.5; no sleep.
    for _ in range(4):
        mw.after_process_message(MagicMock(), _msg("a"), exception=None)
    mw.after_process_message(MagicMock(), _msg("a"), exception=Exception("boom"))
    elapsed_ms = (time.monotonic() - start) * 1000

    # Allow generous CI slack but well below backoff_ms.
    assert elapsed_ms < 100, f"unexpected backoff applied: {elapsed_ms:.1f}ms"


def test_backoff_applied_when_ratio_at_or_above_threshold():
    mw = ThrottleMiddleware(window_size=4, failure_threshold=0.5, backoff_ms=150)
    # 2 failures + 2 successes = ratio 0.5, equals threshold (>=) → backoff fires
    # on the LAST message (the one that brings ratio to 0.5).
    mw.after_process_message(MagicMock(), _msg("a"), exception=None)
    mw.after_process_message(MagicMock(), _msg("a"), exception=None)
    mw.after_process_message(MagicMock(), _msg("a"), exception=Exception("e1"))

    start = time.monotonic()
    mw.after_process_message(MagicMock(), _msg("a"), exception=Exception("e2"))
    elapsed_ms = (time.monotonic() - start) * 1000

    # Should be near 150ms; allow up to 80ms scheduling jitter on top.
    assert elapsed_ms >= 140, f"expected backoff ~150ms, got {elapsed_ms:.1f}ms"
    assert elapsed_ms < 250, f"backoff overshoot: {elapsed_ms:.1f}ms"


def test_per_actor_isolation():
    """Failure rate on actor X must not throttle actor Y."""
    mw = ThrottleMiddleware(window_size=4, failure_threshold=0.5, backoff_ms=200)
    # Saturate failures on actor X.
    for _ in range(4):
        mw.after_process_message(MagicMock(), _msg("x"), exception=Exception("x"))
    # Actor Y has clean record → no backoff.
    start = time.monotonic()
    mw.after_process_message(MagicMock(), _msg("y"), exception=None)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 50, f"Y unexpectedly throttled: {elapsed_ms:.1f}ms"


def test_window_size_caps_history():
    """Old failures roll out of the window so a healthy run recovers."""
    mw = ThrottleMiddleware(window_size=4, failure_threshold=0.5, backoff_ms=200)
    # Fill the window with failures.
    for _ in range(4):
        mw.after_process_message(MagicMock(), _msg("a"), exception=Exception("e"))
    # Now push 4 successes — they evict the failures one by one.
    for _ in range(4):
        mw.after_process_message(MagicMock(), _msg("a"), exception=None)
    # Window now has 4 successes. Adding 1 more success should not trigger backoff.
    start = time.monotonic()
    mw.after_process_message(MagicMock(), _msg("a"), exception=None)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 50, f"unexpected backoff after recovery: {elapsed_ms:.1f}ms"


@pytest.mark.parametrize(
    "threshold,expected_backoff",
    [(0.25, True), (0.50, True), (0.75, False)],
)
def test_threshold_parameterized(threshold: float, expected_backoff: bool):
    """At a given failure ratio (0.5), only thresholds <= 0.5 should backoff."""
    mw = ThrottleMiddleware(window_size=4, failure_threshold=threshold, backoff_ms=120)
    mw.after_process_message(MagicMock(), _msg("a"), exception=None)
    mw.after_process_message(MagicMock(), _msg("a"), exception=Exception("e"))
    mw.after_process_message(MagicMock(), _msg("a"), exception=None)

    start = time.monotonic()
    mw.after_process_message(MagicMock(), _msg("a"), exception=Exception("e"))
    elapsed_ms = (time.monotonic() - start) * 1000
    if expected_backoff:
        assert elapsed_ms >= 110, f"backoff missing at threshold={threshold}"
    else:
        assert elapsed_ms < 50, f"unexpected backoff at threshold={threshold}"
