"""I-deepfix-001 (de-storm) — the shared, env-driven bounded-concurrency cap for the per-claim
mirror-chain side judges (entailment / credibility / semantic_conflict).

WHY THIS EXISTS: the 2026-07-04 super-serious deepener preflight (/root/deepener_preflight.log) hit
32x "429 Too Many Requests" on the glm-5.2 mirror-chain LEAD host (friendli) because NOTHING capped
how many per-claim entailment/side-judge provider POSTs were in flight at once — the verify burst
POSTed ~32 simultaneously, 429-stormed the one reachable host (the alternates were DNS-degraded), the
judge exhausted its retries, and the fail-CLOSED sentinel DROPPED claims -> the abstract / full-verify
collapsed to empty. The fix caps in-flight side-judge POSTs with a process-global bounded semaphore
shared across all three judges.

HERMETIC / OFFLINE: no network, no model, no OpenRouter key. Every test drives the SHARED transport
chokepoint ``_post_with_total_deadline`` (identical in all three side-judge modules) with an injected
fake client whose ``.post`` records peak concurrency deterministically: each admitted call plateaus
inside ``.post`` on a shared release ``Event`` while the test measures the peak, so the observed peak
is EXACTLY the number of POSTs the cap admits at once (no sleep-timing races on the assertion).

LOAD-BEARING PROPERTIES:
  * BOUND APPLIED (GREEN): with ``PG_SIDE_JUDGE_MAX_CONCURRENCY=N`` the real chokepoint admits EXACTLY
    N POSTs at once. RED (cap removed): the same harness admits all ``total_threads`` at once — this is
    the pre-fix ~32-simultaneous storm; the ``== N`` assertion then fails.
  * SHARED POOL: the cap is on TOTAL in-flight POSTs across ALL THREE side judges (one semaphore).
  * ENV-OVERRIDABLE (LAW VI): the cap tracks the env at call time; unset -> DEFAULT_MAX_CONCURRENCY.
  * UNBOUNDED ESCAPE HATCH == PRE-FIX: ``=0`` makes the wrapper a no-op (all POSTs run at once).
  * VERDICT-NEUTRAL: the wrapper is transparent — it returns the provider response object UNCHANGED
    and never inspects/alters it, so no verdict logic is touched.
"""
from __future__ import annotations

import threading
import time

import pytest

from src.polaris_graph.llm import judge_concurrency
from src.polaris_graph.llm import entailment_judge
from src.polaris_graph.authority import credibility_judge_caller
from src.polaris_graph.retrieval import semantic_conflict_detector

# The three side-judge modules that share the ONE global slot pool. Each exposes the identical
# ``_post_with_total_deadline(client, endpoint, headers, json_body, total_s)`` transport chokepoint.
_SIDE_JUDGE_MODULES = [
    entailment_judge,
    credibility_judge_caller,
    semantic_conflict_detector,
]

_SENTINEL_RESPONSE = {"ok": True, "marker": "pass-through-unchanged"}
_SETTLE_S = 0.5   # time for all admittable workers to enter .post and plateau before we read the peak
_HOLD_TIMEOUT_S = 20.0  # safety net so a bug can never hang the suite (< the 30s total-deadline below)


@pytest.fixture(autouse=True)
def _reset_semaphore(monkeypatch):
    """Drop the process-global semaphore before AND after each test so the bound is rebuilt from the
    test's env, and no state leaks between tests."""
    monkeypatch.delenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, raising=False)
    judge_concurrency._reset_for_test()
    yield
    judge_concurrency._reset_for_test()


class _ProbeClient:
    """A fake httpx-style client whose ``.post`` records peak concurrency deterministically.

    Each admitted ``.post`` bumps a SHARED counter (so a cross-module test measures the COMBINED
    in-flight count against the ONE shared semaphore), then blocks on a shared release ``Event`` so
    every admitted call is held INSIDE ``.post`` at the same instant. The test reads ``max_seen``
    after a short settle and then sets the event — so ``max_seen`` equals exactly how many POSTs the
    cap admits concurrently (== N when bounded to N; == total_threads when unbounded)."""

    def __init__(self, state: dict, release: threading.Event) -> None:
        self._state = state
        self._release = release

    def post(self, endpoint, headers=None, json=None):  # noqa: A002 — mirror httpx.Client.post
        state = self._state
        with state["lock"]:
            state["current"] += 1
            if state["current"] > state["max_seen"]:
                state["max_seen"] = state["current"]
        try:
            self._release.wait(timeout=_HOLD_TIMEOUT_S)
            return _SENTINEL_RESPONSE
        finally:
            with state["lock"]:
                state["current"] -= 1

    def close(self):  # the total-deadline force-close path calls this; harmless here
        pass


def _new_state() -> dict:
    return {"lock": threading.Lock(), "current": 0, "max_seen": 0}


def _drive(post_fns, state: dict, total_threads: int):
    """Start ``total_threads`` workers, each calling one of ``post_fns`` (round-robin) against a
    fresh probe client sharing ``state``. Returns (peak_concurrency, returned_values, errors).

    All admitted calls plateau inside ``.post`` on a shared release Event; after a short settle the
    peak is captured, then the event is set so every worker finishes. The peak is therefore the number
    of POSTs the cap admitted at once."""
    release = threading.Event()
    returned: list = []
    errors: list = []
    ret_lock = threading.Lock()

    def worker(idx: int) -> None:
        post_fn = post_fns[idx % len(post_fns)]
        client = _ProbeClient(state, release)
        try:
            rv = post_fn(
                client,
                "https://openrouter.test/api/v1/chat/completions",
                {"Authorization": "Bearer test", "Content-Type": "application/json"},
                {"model": "z-ai/glm-5.2", "messages": []},
                30.0,
            )
            with ret_lock:
                returned.append(rv)
        except Exception as exc:  # noqa: BLE001 — surface any worker failure to the assertion
            with ret_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(total_threads)]
    for t in threads:
        t.start()
    try:
        time.sleep(_SETTLE_S)             # let every admittable worker enter .post and plateau
        with state["lock"]:
            peak = state["max_seen"]      # the concurrency the cap allowed
    finally:
        release.set()                     # release everyone so the run always drains
        for t in threads:
            t.join()
    return peak, returned, errors


# --------------------------------------------------------------------------- resolve_max_concurrency


def test_resolve_default_when_unset():
    # Unset -> the de-storm is ON by default at DEFAULT_MAX_CONCURRENCY.
    assert judge_concurrency.resolve_max_concurrency() == judge_concurrency.DEFAULT_MAX_CONCURRENCY
    assert judge_concurrency.DEFAULT_MAX_CONCURRENCY >= 1


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3", 3),
        ("1", 1),
        (" 6 ", 6),
        ("0", 0),            # explicit unbounded escape hatch (pre-fix behavior)
        ("-5", judge_concurrency.DEFAULT_MAX_CONCURRENCY),   # negative -> safe default
        ("garbage", judge_concurrency.DEFAULT_MAX_CONCURRENCY),  # malformed -> safe default
    ],
)
def test_resolve_env_override(monkeypatch, raw, expected):
    monkeypatch.setenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, raw)
    assert judge_concurrency.resolve_max_concurrency() == expected


# ---------------------------------------------------------------- bound applied at the real chokepoint


@pytest.mark.parametrize("module", _SIDE_JUDGE_MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_bound_applied_per_module(monkeypatch, module):
    """GREEN: with the cap at N, each side-judge ``_post_with_total_deadline`` admits EXACTLY N POSTs
    at once out of 3N contending — never more (RED removes the wrap -> peak == 3N and this fails)."""
    bound = 3
    monkeypatch.setenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, str(bound))
    judge_concurrency._reset_for_test()
    state = _new_state()
    peak, returned, errors = _drive([module._post_with_total_deadline], state, total_threads=bound * 3)
    assert not errors, f"workers raised: {errors!r}"
    # The load-bearing assertion: never exceeds the cap AND utilization reaches it.
    assert peak == bound
    # VERDICT-NEUTRAL: every provider response object is returned UNCHANGED (identity), never inspected.
    assert len(returned) == bound * 3
    assert all(rv is _SENTINEL_RESPONSE for rv in returned)


def test_shared_pool_across_all_three_side_judges(monkeypatch):
    """The cap is on TOTAL in-flight POSTs across ALL THREE side judges (one shared semaphore): driving
    the three chokepoints together (3N contending) still admits only N at once."""
    bound = 3
    monkeypatch.setenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, str(bound))
    judge_concurrency._reset_for_test()
    state = _new_state()
    post_fns = [m._post_with_total_deadline for m in _SIDE_JUDGE_MODULES]
    peak, returned, errors = _drive(post_fns, state, total_threads=bound * 3)
    assert not errors, f"workers raised: {errors!r}"
    assert peak == bound
    assert all(rv is _SENTINEL_RESPONSE for rv in returned)


def test_unbounded_escape_hatch_is_pre_fix_storm(monkeypatch):
    """RED half of RED->GREEN made explicit: with the cap DISABLED (=0, the pre-fix behavior) ALL N
    POSTs run at once (the ~32-simultaneous storm the fix removes). This is exactly what the bounded
    tests above forbid."""
    monkeypatch.setenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, "0")
    judge_concurrency._reset_for_test()
    assert judge_concurrency.resolve_max_concurrency() == 0
    n = 9
    state = _new_state()
    peak, returned, errors = _drive([entailment_judge._post_with_total_deadline], state, total_threads=n)
    assert not errors, f"workers raised (unexpected under unbounded): {errors!r}"
    assert peak == n  # all n in flight at once == pre-fix storm (and > any bounded cap < n)


def test_bound_tracks_env_change_within_process(monkeypatch):
    """ENV-OVERRIDABLE (LAW VI): re-pointing the env within one process rebuilds the semaphore to the
    new bound — the cap is resolved at call time, not import time."""
    # First at 2 ...
    monkeypatch.setenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, "2")
    judge_concurrency._reset_for_test()
    state2 = _new_state()
    peak2, _, err2 = _drive([entailment_judge._post_with_total_deadline], state2, total_threads=6)
    assert not err2 and peak2 == 2, f"expected peak 2, got {peak2} (errors={err2!r})"
    # ... then at 5, same process.
    monkeypatch.setenv(judge_concurrency.ENV_SIDE_JUDGE_MAX_CONCURRENCY, "5")
    judge_concurrency._reset_for_test()
    state5 = _new_state()
    peak5, _, err5 = _drive([entailment_judge._post_with_total_deadline], state5, total_threads=10)
    assert not err5 and peak5 == 5, f"expected peak 5, got {peak5} (errors={err5!r})"
