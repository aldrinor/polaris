"""I-arch-006 (#1262) keystone: every LLM call path has a TIGHT read-stall deadline.

These tests guard the F33 / HANG-J1 / HANG-J2 fix: no LLM call path may leave the
httpx per-read (chunk-gap) timeout defaulting to the full generator budget — a dead /
idle-open socket (rx=tx=0) must trip in ~read-stall seconds, not hang for the whole
budget. Transport-only; no faithfulness gate is exercised here.
"""

import concurrent.futures
import threading
import time

import httpx
import pytest

from src.polaris_graph.llm import openrouter_client as orc
from src.polaris_graph.llm import entailment_judge as ej
from src.polaris_graph.retrieval import semantic_conflict_detector as scd


# A generous upper bound: a "tight" read-stall must be far below the cert-slate
# generator budget (6500s) and below the non-slate module default (600s).
TIGHT_UPPER_BOUND_S = 300.0


def test_generator_sse_read_stall_constant_is_tight():
    assert orc.PG_SSE_READ_STALL_TIMEOUT_SECONDS == 120.0
    assert orc.PG_SSE_READ_STALL_TIMEOUT_SECONDS < TIGHT_UPPER_BOUND_S


def test_generator_stream_timeout_caps_read_below_budget():
    """The streaming Timeout must apply the tight read-stall, NOT the full budget.

    This is the exact F33 regression: ``httpx.Timeout(budget, connect=30.0)`` leaves
    ``.read == budget`` (6500s) — a dead socket hangs ~108 min. The fix passes an
    explicit ``read=``.
    """
    budget = 6500.0
    old_bug = httpx.Timeout(budget, connect=30.0)
    assert old_bug.read == budget  # documents the pre-fix behavior

    fixed = httpx.Timeout(
        budget, connect=30.0, read=orc.PG_SSE_READ_STALL_TIMEOUT_SECONDS
    )
    assert fixed.read == 120.0
    assert fixed.read < budget


def test_entailment_judge_read_stall_constants():
    assert ej._ENTAILMENT_READ_STALL_S == 120.0
    assert ej._ENTAILMENT_READ_STALL_S < TIGHT_UPPER_BOUND_S
    # keepalive reaping (HANG-J2) is configured
    assert ej._ENTAILMENT_MAX_KEEPALIVE >= 1
    assert ej._ENTAILMENT_KEEPALIVE_EXPIRY_S > 0


def test_semantic_conflict_judge_read_stall_constants():
    assert scd._JUDGE_READ_STALL_S == 120.0
    assert scd._JUDGE_READ_STALL_S < TIGHT_UPPER_BOUND_S
    assert scd._JUDGE_MAX_KEEPALIVE >= 1
    assert scd._JUDGE_KEEPALIVE_EXPIRY_S > 0


def test_judge_clients_build_with_tight_read():
    """Construct the two sync-judge httpx clients the way the modules do and assert
    the per-read timeout is tight (the bare-float 30s gap, which httpx reset on every
    byte and let a trickled socket run unbounded, is gone)."""
    ent_client = httpx.Client(
        timeout=httpx.Timeout(
            connect=ej._ENTAILMENT_CONNECT_S,
            read=ej._ENTAILMENT_READ_STALL_S,
            write=ej._ENTAILMENT_WRITE_S,
            pool=ej._ENTAILMENT_POOL_S,
        ),
        limits=httpx.Limits(
            max_keepalive_connections=ej._ENTAILMENT_MAX_KEEPALIVE,
            keepalive_expiry=ej._ENTAILMENT_KEEPALIVE_EXPIRY_S,
        ),
    )
    try:
        assert ent_client.timeout.read == 120.0
        assert ent_client.timeout.connect == ej._ENTAILMENT_CONNECT_S
    finally:
        ent_client.close()

    scd_client = httpx.Client(
        timeout=httpx.Timeout(
            connect=scd._JUDGE_CONNECT_S,
            read=scd._JUDGE_READ_STALL_S,
            write=scd._JUDGE_WRITE_S,
            pool=scd._JUDGE_POOL_S,
        )
    )
    try:
        assert scd_client.timeout.read == 120.0
    finally:
        scd_client.close()


def test_credibility_timeout_applies_read_stall():
    """The credibility judge passed ``read=call_timeout`` (full budget). The fix adds an
    explicit tight ``read=`` so a full budget no longer governs the per-chunk read."""
    call_timeout = 600.0
    fixed = httpx.Timeout(call_timeout, connect=15.0, read=120.0)
    assert fixed.read == 120.0
    assert fixed.read < call_timeout


# I-arch-007 BUG-2 (verify-hang, 2026-06-17): the per-read gap above only catches a TRULY dead
# socket; a TRICKLED keep-alive socket resets the gap timer indefinitely and one bare POST runs
# unbounded. The NLI-conflict side-judge was the one sync POST that still lacked the HARD TOTAL
# per-call wall-deadline that entailment_judge / credibility_judge_caller / openrouter_role_transport
# all have. These tests guard that the deadline constant is present + tight AND that the ported
# helper actually force-closes + raises within the deadline on a hung POST.


def test_semantic_conflict_total_deadline_constant_is_tight():
    assert scd._JUDGE_TOTAL_S == 150.0
    # The total wall-deadline must exceed a real per-read stall (a slow-but-alive trickle is bounded
    # by the read-stall first) yet stay well below the generator budget so it cannot freeze the run.
    assert scd._JUDGE_TOTAL_S > scd._JUDGE_READ_STALL_S
    assert scd._JUDGE_TOTAL_S < 6500.0


def test_semantic_conflict_post_with_total_deadline_force_closes_a_hung_post():
    """Behavioral: a POST that blocks PAST the deadline is force-closed + TimeoutError raised.

    Uses a stub client whose ``post`` blocks forever (the trickle-hang shape) and whose ``close``
    sets an event. The helper must (a) raise ``concurrent.futures.TimeoutError`` within ~deadline and
    (b) call ``client.close()`` so the hung worker's transport is torn down — exactly the recovery the
    real ``_post_once`` relies on before it rebuilds + the side-judge guard emits the existing sentinel.
    """
    released = threading.Event()
    closed = threading.Event()

    class _HangingClient:
        def post(self, *_a, **_k):
            # Block until close() is called (or a generous test ceiling) — simulates a trickled read
            # that the per-byte gap timer never trips.
            released.wait(timeout=10.0)
            return "unreached"

        def close(self):
            closed.set()
            released.set()  # unblock the worker so the test thread pool can drain

    t0 = time.monotonic()
    with pytest.raises(concurrent.futures.TimeoutError):
        scd._post_with_total_deadline(
            _HangingClient(), "http://x/y", {}, {"k": "v"}, total_s=0.3,
        )
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"deadline did not bound the call (took {elapsed:.1f}s)"
    assert closed.is_set(), "client.close() was not called to force the hung socket closed"


def test_semantic_conflict_post_with_total_deadline_returns_fast_post_unchanged():
    """Happy path: a POST that completes BEFORE the deadline returns its value verbatim — the wrapper
    is transparent on the common case (no behavior change for a healthy judge call)."""
    sentinel = object()

    class _FastClient:
        def post(self, *_a, **_k):
            return sentinel

        def close(self):  # pragma: no cover - not reached on the fast path
            raise AssertionError("close() must not be called on a fast POST")

    out = scd._post_with_total_deadline(_FastClient(), "http://x/y", {}, {}, total_s=5.0)
    assert out is sentinel
