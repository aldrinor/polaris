"""I-wire-007 (#1321): the ADAPTIVE AIMD concurrency controller — pure TCP-congestion math.

The controller replaces the FIXED per-role concurrency cap (PG_FOUR_ROLE_JUDGE_CONCURRENCY=4,
PG_FOUR_ROLE_CLAIM_WORKERS=6) with Additive-Increase / Multiplicative-Decrease so it auto-finds and
rides the live OpenRouter ceiling: probe UP after a clean window, HALVE on a 429 / force-close. These
tests pin the AIMD math DIRECTLY (no threads, no network, no spend) — the acceptance gate per the
task: ramps on success, halves on a 429/timeout, respects [min, max] bounds. Concurrency-only;
FAITHFULNESS is untouched (a throttled limit only delays work, never changes a verdict).
"""

from __future__ import annotations

import threading

import pytest

from src.polaris_graph.roles.adaptive_concurrency import (
    AdaptiveConcurrencyController,
    adaptive_concurrency_enabled,
    build_role_controller,
)


def _controller(**kw) -> AdaptiveConcurrencyController:
    base = dict(min_limit=2, max_limit=10, step=1, backoff=0.5, probe_window=3)
    base.update(kw)
    return AdaptiveConcurrencyController(**base)


# --- additive-increase ---------------------------------------------------------------------------
def test_starts_at_the_floor_not_the_ceiling():
    """Slow-start analogue: begin at MIN and probe UP, never start at MAX and provoke a storm."""
    c = _controller()
    assert c.limit == 2
    assert c.bounds == (2, 10)


def test_additive_increase_after_a_clean_probe_window():
    """After `probe_window` consecutive clean successes the limit rises by exactly `step`."""
    c = _controller(min_limit=2, max_limit=10, step=1, probe_window=3)
    c.on_success()
    c.on_success()
    assert c.limit == 2, "no ramp before the window completes"
    c.on_success()  # third clean success completes the window.
    assert c.limit == 3, "additive-increase: +step after one clean probe window"


def test_increase_is_clamped_at_max():
    """The limit can NEVER exceed max_limit no matter how many clean windows pass."""
    c = _controller(min_limit=2, max_limit=4, step=1, probe_window=1)
    for _ in range(50):
        c.on_success()
    assert c.limit == 4, "additive-increase clamps hard at max_limit"


def test_a_throttle_resets_the_clean_streak():
    """A congestion signal mid-window resets the streak so the NEXT ramp needs a fresh full window."""
    c = _controller(min_limit=2, max_limit=10, step=1, probe_window=3)
    c.on_success()
    c.on_success()  # 2/3 toward a ramp.
    c.on_throttle()  # resets the streak (and decreases — min floor, stays 2).
    c.on_success()
    c.on_success()
    assert c.limit == 2, "the pre-throttle partial streak must NOT count toward the next ramp"
    c.on_success()
    assert c.limit == 3, "a FULL fresh window after the reset ramps once"


# --- multiplicative-decrease ---------------------------------------------------------------------
def test_throttle_halves_the_limit():
    """on_throttle (a 429/503) multiplicatively decreases the limit by the backoff factor."""
    c = _controller(min_limit=1, max_limit=16, backoff=0.5, probe_window=1)
    for _ in range(15):
        c.on_success()  # +1 per clean call (probe_window=1) -> ramp 1 -> 16 (the ceiling).
    assert c.limit == 16
    c.on_throttle()
    assert c.limit == 8, "x0.5 multiplicative-decrease on a 429"


def test_timeout_halves_the_limit_identically():
    """on_timeout (a force-close / total-deadline) backs off the SAME as a 429 — both are congestion."""
    c = _controller(min_limit=1, max_limit=16, backoff=0.5, probe_window=1)
    for _ in range(15):
        c.on_success()
    assert c.limit == 16
    c.on_timeout()
    assert c.limit == 8


def test_decrease_is_clamped_at_min():
    """Repeated congestion can NEVER drive the limit below min_limit (never collapses to zero)."""
    c = _controller(min_limit=3, max_limit=16, backoff=0.5)
    for _ in range(20):
        c.on_throttle()
    assert c.limit == 3, "multiplicative-decrease clamps hard at min_limit (never 0)"


def test_backoff_factor_is_honored():
    """A non-0.5 backoff is respected (x0.25 here): the AIMD ratio is configurable (LAW VI)."""
    c = _controller(min_limit=1, max_limit=20, backoff=0.25, probe_window=1)
    for _ in range(20):
        c.on_success()
    assert c.limit == 20
    c.on_throttle()
    assert c.limit == 5, "20 * 0.25 = 5"


# --- the gate (acquire/release under the dynamic limit) ------------------------------------------
def test_acquire_release_track_in_flight():
    c = _controller(min_limit=2, max_limit=4)
    assert c.in_flight == 0
    c.acquire()
    c.acquire()
    assert c.in_flight == 2
    c.release()
    assert c.in_flight == 1
    c.release()
    assert c.in_flight == 0


def test_acquire_blocks_at_the_limit_then_proceeds_on_release():
    """A third acquire at limit=2 BLOCKS until a slot frees — the gate genuinely bounds concurrency."""
    c = _controller(min_limit=2, max_limit=2)  # fixed at 2 (min==max, no ramp).
    c.acquire()
    c.acquire()
    assert c.in_flight == 2

    proceeded = threading.Event()

    def _third():
        c.acquire()
        proceeded.set()

    t = threading.Thread(target=_third, daemon=True)
    t.start()
    assert not proceeded.wait(timeout=0.2), "the third acquire must BLOCK while in_flight >= limit"
    c.release()  # free a slot -> the blocked acquire proceeds.
    assert proceeded.wait(timeout=2.0), "the blocked acquire must proceed once a slot frees"
    t.join(timeout=2.0)
    c.release()


def test_growing_the_limit_wakes_a_blocked_acquirer():
    """on_success ramp must NOTIFY a blocked acquirer so new headroom is used immediately."""
    c = _controller(min_limit=1, max_limit=4, step=1, probe_window=1)
    c.acquire()  # in_flight=1, limit=1 -> a second acquire blocks.
    assert c.in_flight == 1

    proceeded = threading.Event()

    def _second():
        c.acquire()
        proceeded.set()

    t = threading.Thread(target=_second, daemon=True)
    t.start()
    assert not proceeded.wait(timeout=0.2), "the second acquire blocks at limit=1"
    c.on_success()  # ramps limit 1 -> 2 and notifies; the blocked acquire now proceeds.
    assert proceeded.wait(timeout=2.0), "growing the limit must wake the blocked acquirer"
    t.join(timeout=2.0)
    c.release()
    c.release()


# --- env resolution + enable flag ----------------------------------------------------------------
def test_enabled_by_default_and_off_switch(monkeypatch):
    monkeypatch.delenv("PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY", raising=False)
    assert adaptive_concurrency_enabled() is True, "default ON (concurrency-only)"
    for off in ("0", "false", "no", "off"):
        monkeypatch.setenv("PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY", off)
        assert adaptive_concurrency_enabled() is False


def test_role_floor_equals_the_static_baseline(monkeypatch):
    """The judge MIN floor must equal its proven static cap (4) so an adaptive run never starts BELOW
    the baseline it replaces — the OFF path can never be worse than ON at t=0."""
    for var in list(__import__("os").environ):
        if var.startswith("PG_FOUR_ROLE_ADAPTIVE"):
            monkeypatch.delenv(var, raising=False)
    judge = build_role_controller("judge")
    assert judge.bounds[0] == 4, "judge adaptive MIN == the static PG_FOUR_ROLE_JUDGE_CONCURRENCY=4"
    assert judge.bounds[1] >= judge.bounds[0]


def test_env_overrides_are_honored(monkeypatch):
    monkeypatch.setenv("PG_FOUR_ROLE_ADAPTIVE_JUDGE_MIN", "2")
    monkeypatch.setenv("PG_FOUR_ROLE_ADAPTIVE_JUDGE_MAX", "32")
    monkeypatch.setenv("PG_FOUR_ROLE_ADAPTIVE_JUDGE_STEP", "2")
    monkeypatch.setenv("PG_FOUR_ROLE_ADAPTIVE_JUDGE_PROBE_WINDOW", "1")
    judge = build_role_controller("judge")
    assert judge.bounds == (2, 32)
    judge.on_success()  # probe_window=1 + step=2 -> +2 per clean call.
    assert judge.limit == 4


def test_malformed_backoff_falls_back_to_default():
    """A backoff outside (0,1) is rejected and falls to a safe default (never >=1, never <=0)."""
    c = AdaptiveConcurrencyController(min_limit=1, max_limit=10, backoff=2.0, probe_window=1)
    for _ in range(10):
        c.on_success()
    before = c.limit
    c.on_throttle()
    assert c.limit < before, "a >=1 backoff would never shrink; it must fall back to a real decrease"
