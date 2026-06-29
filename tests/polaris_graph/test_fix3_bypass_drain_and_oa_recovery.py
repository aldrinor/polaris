"""FIX-3 (I-deepfix-001) — bypass-worker drain/gauge split + DOI timeout recovery.

Offline, behavioral unit tests (no network, no GPU, no faithfulness mocking).

PIECE 1 (resource hygiene): a bounded best-effort drain of abandoned bypass
    worker threads + a LIVE gauge distinct from the existing CUMULATIVE counter.
    - T1: drain joins fast-finishing abandoned workers within budget; a wedged
      worker does NOT block the drain past its budget and is still counted live.
    - T2: the live gauge and the cumulative gauge are DISTINCT — the cumulative
      counter climbs monotonically on abandon, while the live gauge decrements
      when an abandoned worker deregisters.

PIECE 2 (DOI recovery on the AccessBypass TIMEOUT path):
    - T3: `_try_oa_resolution_bounded` runs the OA resolver under a hard
      wall-clock so the timeout path can recover a DOI without re-opening the
      storm; on a hit it returns the recovered content, on a wedge it registers
      the recovery thread with the abandoned registry and returns "" (fail-open).

These exercise the new public surface in `src.tools.access_bypass`
(register/deregister/bypass_live_leaked_count/drain_bypass_workers) and the new
`live_retriever._try_oa_resolution_bounded` helper directly — the cheapest,
deterministic seam (the end-to-end `run_live_retrieval` timeout path would need a
live browser cascade to wedge a real worker, which §8.4 forbids in tests).
"""
from __future__ import annotations

import threading
import time

import pytest

import src.tools.access_bypass as ab
from src.polaris_graph.retrieval import live_retriever


@pytest.fixture(autouse=True)
def _reset_bypass_state():
    """Isolate the module-level registry + gauges between tests."""
    ab.reset_bypass_leak_state()
    yield
    ab.reset_bypass_leak_state()


# ═════════════════════════════════════════════════════════════════════════════
# T1 — bounded drain: fast workers joined; a wedged worker does NOT block.
# ═════════════════════════════════════════════════════════════════════════════
def test_drain_joins_fast_abandoned_workers_within_budget():
    """A handful of fast-finishing abandoned workers are reclaimed by the drain
    and the LIVE gauge returns to 0."""
    started = threading.Event()
    release = threading.Event()

    def _fast_worker() -> None:
        started.set()
        # Wait for the test to release, then finish quickly. The drain budget is
        # large enough to join it.
        release.wait(timeout=5.0)

    workers = []
    for _ in range(20):  # > the BoundedSemaphore default (16) — proves no second bound
        t = threading.Thread(target=_fast_worker, daemon=True)
        t.start()
        ab.register_abandoned_bypass_worker(t)
        workers.append(t)

    started.wait(timeout=2.0)
    assert ab.bypass_live_leaked_count() == 20, "all registered workers alive pre-drain"

    # Let them all finish, then drain with a generous budget.
    release.set()
    residual = ab.drain_bypass_workers(budget=5.0)

    assert residual == 0, "every fast worker should be joined + pruned by the drain"
    assert ab.bypass_live_leaked_count() == 0, "live gauge back to 0 after drain"
    for t in workers:
        assert not t.is_alive()


def test_drain_does_not_block_past_budget_on_a_wedged_worker():
    """A worker wedged past the budget MUST NOT block the drain beyond the budget
    (no #554-class re-hang), and is still counted live afterwards."""
    wedge_release = threading.Event()

    def _wedged_worker() -> None:
        # Block well past the drain budget; released in finally so the test never
        # leaves a real hung thread behind.
        wedge_release.wait(timeout=30.0)

    t = threading.Thread(target=_wedged_worker, daemon=True)
    t.start()
    ab.register_abandoned_bypass_worker(t)

    assert ab.bypass_live_leaked_count() == 1

    budget = 0.5
    t0 = time.monotonic()
    residual = ab.drain_bypass_workers(budget=budget)
    elapsed = time.monotonic() - t0

    # The drain returned within (a small slack over) the budget — it did NOT wait
    # the full 30s wedge.
    assert elapsed < budget + 1.5, (
        f"drain blocked {elapsed:.2f}s — must not exceed budget {budget}s + slack"
    )
    # The wedged worker is still alive and still counted as a residual live leak.
    assert residual == 1, "the wedged worker remains a residual live leak"
    assert ab.bypass_live_leaked_count() == 1

    # Clean up the wedged worker so the test process exits cleanly.
    wedge_release.set()
    t.join(timeout=5.0)


def test_drain_budget_reads_env_knob(monkeypatch):
    """PG_BYPASS_DRAIN_SECONDS overrides the default budget (LAW VI)."""
    monkeypatch.setenv("PG_BYPASS_DRAIN_SECONDS", "0.25")
    assert ab._bypass_drain_budget_seconds() == pytest.approx(0.25)
    # Malformed / <= 0 falls back to the named default (a bad knob never disables
    # the drain).
    monkeypatch.setenv("PG_BYPASS_DRAIN_SECONDS", "not-a-number")
    assert ab._bypass_drain_budget_seconds() == ab._BYPASS_DRAIN_SECONDS_DEFAULT
    monkeypatch.setenv("PG_BYPASS_DRAIN_SECONDS", "0")
    assert ab._bypass_drain_budget_seconds() == ab._BYPASS_DRAIN_SECONDS_DEFAULT
    monkeypatch.delenv("PG_BYPASS_DRAIN_SECONDS", raising=False)
    assert ab._bypass_drain_budget_seconds() == ab._BYPASS_DRAIN_SECONDS_DEFAULT


# ═════════════════════════════════════════════════════════════════════════════
# T2 — gauge split: cumulative is monotonic, live decrements on deregister.
# ═════════════════════════════════════════════════════════════════════════════
def test_live_and_cumulative_gauges_are_distinct():
    """The CUMULATIVE `bypass_leaked_worker_count` climbs monotonically on
    abandon; the LIVE `bypass_live_leaked_count` reflects only still-registered,
    still-alive workers and decrements on deregister."""
    assert ab.bypass_leaked_worker_count() == 0
    assert ab.bypass_live_leaked_count() == 0

    release = threading.Event()

    def _worker() -> None:
        release.wait(timeout=5.0)

    t1 = threading.Thread(target=_worker, daemon=True)
    t2 = threading.Thread(target=_worker, daemon=True)
    t1.start()
    t2.start()

    # Simulate two abandonments (the live_retriever timeout path does both):
    ab.register_abandoned_bypass_worker(t1)
    ab.record_bypass_leaked_worker()
    ab.register_abandoned_bypass_worker(t2)
    ab.record_bypass_leaked_worker()

    assert ab.bypass_leaked_worker_count() == 2, "cumulative counted both abandons"
    assert ab.bypass_live_leaked_count() == 2, "both still alive + registered"

    # One worker deregisters (self-deregister in its finally after finishing).
    ab.deregister_abandoned_bypass_worker(t1)
    assert ab.bypass_live_leaked_count() == 1, "live gauge decremented on deregister"
    assert ab.bypass_leaked_worker_count() == 2, (
        "cumulative gauge is MONOTONIC — deregister must NOT decrement it"
    )

    # Clean up.
    release.set()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)


def test_live_gauge_ignores_dead_but_not_deregistered_workers():
    """A register/deregister RACE can leave a dead thread in the set; the
    `is_alive()` filter must not over-count it, and the drain prunes it."""
    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    t.join(timeout=5.0)  # thread is now DEAD
    assert not t.is_alive()

    # Register the already-dead thread (simulates the race: abandoned-then-finished
    # before deregister ran).
    ab.register_abandoned_bypass_worker(t)
    assert ab.bypass_live_leaked_count() == 0, "dead thread not counted live"

    # The drain prunes the dead entry from the registry.
    residual = ab.drain_bypass_workers(budget=0.1)
    assert residual == 0


# ═════════════════════════════════════════════════════════════════════════════
# T3 — DOI recovery on the timeout path via the bounded helper.
# ═════════════════════════════════════════════════════════════════════════════
def test_oa_recovery_bounded_returns_hit(monkeypatch):
    """`_try_oa_resolution_bounded` returns the resolver content on a fast hit."""
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "1")
    recovered = "RECOVERED FULL TEXT " * 50

    def _fake_oa(url, extracted_doi="", pmid="", max_chars=0):
        assert extracted_doi == "10.1056/test", "DOI threaded through to the resolver"
        return recovered

    monkeypatch.setattr(live_retriever, "_try_oa_resolution", _fake_oa)

    out = live_retriever._try_oa_resolution_bounded(
        url="https://doi.org/10.1056/test",
        extracted_doi="10.1056/test",
        pmid="",
        max_chars=10000,
    )
    assert out == recovered


def test_oa_recovery_bounded_off_when_resolver_disabled(monkeypatch):
    """When the OA resolver is OFF the bounded helper does nothing (byte-identical
    fall-through; the underlying resolver is never even called)."""
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")
    called = []

    def _fake_oa(*a, **k):
        called.append(1)
        return "should-not-be-used"

    monkeypatch.setattr(live_retriever, "_try_oa_resolution", _fake_oa)
    out = live_retriever._try_oa_resolution_bounded(
        url="https://doi.org/10.1056/test", extracted_doi="10.1056/test",
    )
    assert out == ""
    assert called == [], "resolver must not be invoked when disabled"


def test_oa_recovery_bounded_wedge_registers_thread_and_returns_empty(monkeypatch):
    """A resolver that WEDGES past the deadline must NOT hang the caller: the
    bounded helper returns "" within budget AND hands the wedged recovery thread
    to the abandoned-worker registry so the end-of-run drain reclaims it."""
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "1")
    monkeypatch.setenv("PG_OA_RECOVERY_DEADLINE", "0.5")
    wedge_release = threading.Event()

    def _wedged_oa(url, extracted_doi="", pmid="", max_chars=0):
        wedge_release.wait(timeout=30.0)  # block well past the 0.5s deadline
        return "late-content-never-used"

    monkeypatch.setattr(live_retriever, "_try_oa_resolution", _wedged_oa)

    t0 = time.monotonic()
    out = live_retriever._try_oa_resolution_bounded(
        url="https://doi.org/10.1056/wedge", extracted_doi="10.1056/wedge",
    )
    elapsed = time.monotonic() - t0

    assert out == "", "a wedged resolver must yield no content (fail-open)"
    assert elapsed < 2.0, (
        f"bounded helper blocked {elapsed:.2f}s — must return within the deadline"
    )
    # The wedged recovery thread was handed to the abandoned-worker registry so the
    # end-of-run bounded drain reclaims it (it is still alive right now).
    assert ab.bypass_live_leaked_count() == 1, (
        "the wedged OA recovery thread should be registered as a live leak"
    )

    # Release the wedge + drain so the test leaves no hung thread.
    wedge_release.set()
    residual = ab.drain_bypass_workers(budget=5.0)
    assert residual == 0


def test_oa_recovery_deadline_reads_env_knob(monkeypatch):
    """PG_OA_RECOVERY_DEADLINE overrides the default; bad/<=0 falls back (LAW VI)."""
    monkeypatch.setenv("PG_OA_RECOVERY_DEADLINE", "12.5")
    assert live_retriever._oa_recovery_deadline_seconds() == pytest.approx(12.5)
    monkeypatch.setenv("PG_OA_RECOVERY_DEADLINE", "garbage")
    assert (
        live_retriever._oa_recovery_deadline_seconds()
        == live_retriever._OA_RECOVERY_DEADLINE_DEFAULT
    )
    monkeypatch.setenv("PG_OA_RECOVERY_DEADLINE", "-3")
    assert (
        live_retriever._oa_recovery_deadline_seconds()
        == live_retriever._OA_RECOVERY_DEADLINE_DEFAULT
    )
    monkeypatch.delenv("PG_OA_RECOVERY_DEADLINE", raising=False)
    assert (
        live_retriever._oa_recovery_deadline_seconds()
        == live_retriever._OA_RECOVERY_DEADLINE_DEFAULT
    )
