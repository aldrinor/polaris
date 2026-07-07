"""UNIT 6 (I-wire-001 TRACK-2 fetch robustness) — offline unit tests for the
fetch-yield HALT gate + the WAVE-B default bumps.

RED before the patch / GREEN after. Offline ONLY (no network, no GPU, no model
load) per §8.4 resource discipline. Per
``feedback_offline_tests_not_real_preflight_2026_07_02``: these prove the
WIRING only — the real cure (the 922/990-timeout hang-and-leak cascade) is
proven on the fresh VM run, not here.

Covers:
  1. WAVE-B new defaults resolve + stay env-overridable
     (``_BYPASS_INFLIGHT_DEFAULT_LIMIT`` = 32, ``PG_RETRIEVAL_WALL_SECONDS`` =
     2700.0, ``PG_MIN_FETCH_YIELD`` = 0.30).
  2. The yield gate HALTS (raises ``FetchStarvationError``) when
     success/(success+timeout) < floor and PASSES (returns the rate) when
     >= floor. Div0 is guarded (an empty batch cannot be "starved").
  3. A malformed ``PG_MIN_FETCH_YIELD`` fails LOUD (raises), never silently
     defaults — a bad safety-gate knob must not mask a starved run.
"""

import pytest


def _fresh_live_retriever(monkeypatch, **env):
    """Import live_retriever with a clean set of the knobs under test applied.

    Every knob here is read at CALL time, so no module reload is needed — we
    just clear then optionally set the env vars before returning the module.
    """
    for key in (
        "PG_RETRIEVAL_WALL_SECONDS",
        "PG_MIN_FETCH_YIELD",
        "PG_MIN_FETCH_YIELD_MIN_ATTEMPTS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import src.polaris_graph.retrieval.live_retriever as live_retriever
    return live_retriever


def test_wave_b_defaults_resolve(monkeypatch):
    import src.tools.access_bypass as access_bypass
    live_retriever = _fresh_live_retriever(monkeypatch)
    assert access_bypass._BYPASS_INFLIGHT_DEFAULT_LIMIT == 32
    assert live_retriever._retrieval_wall_seconds() == 2700.0
    assert live_retriever._min_fetch_yield() == pytest.approx(0.30)


def test_defaults_env_overridable(monkeypatch):
    live_retriever = _fresh_live_retriever(
        monkeypatch,
        PG_RETRIEVAL_WALL_SECONDS="3600",
        PG_MIN_FETCH_YIELD="0.5",
    )
    assert live_retriever._retrieval_wall_seconds() == 3600.0
    assert live_retriever._min_fetch_yield() == pytest.approx(0.5)
    # And the in-flight bypass bound honors its env override too.
    import src.tools.access_bypass as access_bypass
    monkeypatch.setenv("PG_BYPASS_MAX_INFLIGHT", "48")
    access_bypass.reset_bypass_leak_state()
    semaphore = access_bypass._get_bypass_inflight_semaphore()
    acquired = 0
    while semaphore.acquire(blocking=False):
        acquired += 1
        if acquired > 60:
            break
    for _ in range(acquired):
        semaphore.release()
    access_bypass.reset_bypass_leak_state()
    assert acquired == 48


def test_yield_gate_halts_below_floor(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)  # floor 0.30
    # The starved run: 5 usable, 95 timed out -> rate 0.05 < 0.30 -> HALT.
    with pytest.raises(live_retriever.FetchStarvationError):
        live_retriever._fetch_yield_gate(5, 95)


def test_yield_gate_passes_at_or_above_floor(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)
    # Healthy: 80 usable, 20 timed out -> rate 0.80 >= 0.30 -> pass, returns rate.
    assert live_retriever._fetch_yield_gate(80, 20) == pytest.approx(0.80)
    # Exactly AT the floor passes (comparison is strictly-below).
    monkeypatch.setenv("PG_MIN_FETCH_YIELD", "0.30")
    assert live_retriever._fetch_yield_gate(30, 70) == pytest.approx(0.30)


def test_yield_gate_div0_guard_passes(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)
    # No fetch attempts at all -> denom 0 -> cannot be "starved" -> pass.
    assert live_retriever._fetch_yield_gate(0, 0) == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1369) FIX 3 — MIN-ATTEMPTS floor + failures in denominator.
# A tiny auxiliary batch (rate 0.0 from a single timeout) must NOT hard-kill an
# otherwise-healthy paid run; the gate only HALTS once total_attempted reaches
# PG_MIN_FETCH_YIELD_MIN_ATTEMPTS (default 50).
# ─────────────────────────────────────────────────────────────────────
def test_min_attempts_default_resolves(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)
    monkeypatch.delenv("PG_MIN_FETCH_YIELD_MIN_ATTEMPTS", raising=False)
    assert live_retriever._min_fetch_yield_min_attempts() == 50


def test_tiny_batch_below_floor_does_not_raise(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)  # floor 0.30, min 50
    # 1 timeout / 0 success -> rate 0.0 but total_attempted 1 < 50 -> skip, no raise.
    assert live_retriever._fetch_yield_gate(0, 1) == pytest.approx(0.0)
    # 1 success + 3 timeouts -> rate 0.25 < 0.30 but 4 < 50 -> skip, no raise.
    assert live_retriever._fetch_yield_gate(1, 3) == pytest.approx(0.25)


def test_sixty_attempt_starved_batch_raises(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)  # floor 0.30, min 50
    # 3 usable / 57 timed out -> 60 attempts >= 50, rate 0.05 < 0.30 -> HALT.
    with pytest.raises(live_retriever.FetchStarvationError):
        live_retriever._fetch_yield_gate(3, 57)


def test_sixty_attempt_healthy_batch_passes(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)  # floor 0.30, min 50
    # 30 usable / 30 timed out -> 60 attempts >= 50, rate 0.50 >= 0.30 -> pass.
    assert live_retriever._fetch_yield_gate(30, 30) == pytest.approx(0.50)


def test_failures_count_against_yield(monkeypatch):
    live_retriever = _fresh_live_retriever(monkeypatch)  # floor 0.30, min 50
    # 10 usable, 5 timeouts, 55 non-timeout FAILURES -> total 70 >= 50,
    # rate 10/70 = 0.143 < 0.30 -> HALT (a failure-thinned corpus is caught).
    with pytest.raises(live_retriever.FetchStarvationError):
        live_retriever._fetch_yield_gate(10, 5, 55)


def test_malformed_min_attempts_raises(monkeypatch):
    live_retriever = _fresh_live_retriever(
        monkeypatch, PG_MIN_FETCH_YIELD_MIN_ATTEMPTS="not-an-int"
    )
    with pytest.raises(ValueError):
        live_retriever._min_fetch_yield_min_attempts()
    monkeypatch.setenv("PG_MIN_FETCH_YIELD_MIN_ATTEMPTS", "-5")
    with pytest.raises(ValueError):
        live_retriever._min_fetch_yield_min_attempts()


def test_malformed_min_fetch_yield_raises(monkeypatch):
    live_retriever = _fresh_live_retriever(
        monkeypatch, PG_MIN_FETCH_YIELD="not-a-float"
    )
    with pytest.raises(ValueError):
        live_retriever._min_fetch_yield()
    # A non-finite override also fails loud (inf/nan must never disable the gate).
    monkeypatch.setenv("PG_MIN_FETCH_YIELD", "inf")
    with pytest.raises(ValueError):
        live_retriever._min_fetch_yield()
