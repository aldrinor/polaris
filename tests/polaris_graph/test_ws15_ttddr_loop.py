"""WS-15 — TTD-DR coverage loop tests. OFFLINE, fake-driven, NO model / GPU / network.

Drives `ttddr_refine` (paper Algorithm 1 — denoising with retrieval) with capture-only
fakes so every branch is exercised without a real model, HTTP client, or clock:
  * convergence: gap_fn yields a gap for 2 rounds then 0 -> 2 rounds, gaps_closed=2,
    stop_reason=no_gaps; each injected retrieve/revise is called.
  * max_rounds bound stops early (retrieve/revise still fired once).
  * wall-clock bound stops early (injected fake clock — no real time passes).
  * cost bound stops early (injected cost probe over a fake spend ledger).
  * PG_TTDDR_ENABLED default-OFF -> the loop invokes NO callable and returns the
    initial draft untouched; explicit off tokens stay off, on tokens turn it on.
  * draft_fn seeds R_0 when initial_draft is None; missing both fails loud.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.retrieval.ttddr_loop import (
    STOP_COST,
    STOP_DISABLED,
    STOP_MAX_ROUNDS,
    STOP_NO_GAPS,
    STOP_WALL,
    ttddr_enabled,
    ttddr_refine,
)

_FLAG = "PG_TTDDR_ENABLED"


@pytest.fixture(autouse=True)
def _enable_ttddr():
    """Turn the default-OFF capability ON for the loop tests; restore after."""
    prev = os.environ.get(_FLAG)
    os.environ[_FLAG] = "1"
    yield
    if prev is None:
        os.environ.pop(_FLAG, None)
    else:
        os.environ[_FLAG] = prev


# ─────────────────────────────────────────────────────────────────────────────
# in-test fakes — capture-only, controlled per-round behaviour
# ─────────────────────────────────────────────────────────────────────────────
class _ScriptedGaps:
    """gap_fn fake: yields the next scripted gap list per call; [] once exhausted."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0
        self.seen_drafts = []

    def __call__(self, question, draft):
        self.seen_drafts.append(draft)
        self.calls += 1
        if self._script:
            return self._script.pop(0)
        return []


class _CountingRetrieve:
    def __init__(self):
        self.calls = 0
        self.seen = []

    def __call__(self, question, gaps):
        self.calls += 1
        self.seen.append(list(gaps))
        return {"evidence_for": list(gaps)}


class _CountingRevise:
    """revise_fn fake: appends the closed gaps to the draft so growth is observable."""

    def __init__(self):
        self.calls = 0

    def __call__(self, question, draft, gaps, evidence):
        self.calls += 1
        return f"{draft}+{'|'.join(str(g) for g in gaps)}"


def _clock_from(values):
    """Deterministic monotonic clock: returns each scripted value, then the last."""
    seq = list(values)
    state = {"i": 0}

    def _clock():
        i = state["i"]
        if i < len(seq):
            state["i"] = i + 1
            return seq[i]
        return seq[-1] if seq else 0.0

    return _clock


# ─────────────────────────────────────────────────────────────────────────────
# convergence: 2 productive rounds then no gaps
# ─────────────────────────────────────────────────────────────────────────────
def test_converges_after_two_rounds_then_no_gaps():
    gap = _ScriptedGaps([["g1"], ["g2"]])  # gap for 2 rounds, then [] (converged)
    retrieve = _CountingRetrieve()
    revise = _CountingRevise()

    result = ttddr_refine(
        "Q",
        "R0",
        gap_fn=gap,
        retrieve_fn=retrieve,
        revise_fn=revise,
        max_rounds=10,
        wall_seconds=1000.0,
        cost_budget=1000.0,
    )

    assert result["stop_reason"] == STOP_NO_GAPS
    assert result["rounds"] == 2
    assert result["gaps_closed"] == 2
    assert result["gap_history"] == [1, 1]
    # each injected role fired exactly once per productive round.
    assert retrieve.calls == 2
    assert revise.calls == 2
    # gap_fn called 3x: two productive + the converged empty check.
    assert gap.calls == 3
    # the draft grew as evidence was folded in (revise actually ran on R0).
    assert result["final_draft"] == "R0+g1+g2"
    # round 2's gap detection saw the round-1 revision (draft is threaded through).
    assert gap.seen_drafts[1] == "R0+g1"


def test_multi_gap_round_counts_all_gaps_closed():
    """gaps_closed accumulates len(gaps) per round, not just round count."""
    gap = _ScriptedGaps([["a", "b", "c"], ["d", "e"]])
    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap, retrieve_fn=_CountingRetrieve(), revise_fn=_CountingRevise(),
        max_rounds=10, wall_seconds=1e9, cost_budget=1e9,
    )
    assert result["stop_reason"] == STOP_NO_GAPS
    assert result["rounds"] == 2
    assert result["gaps_closed"] == 5
    assert result["gap_history"] == [3, 2]


# ─────────────────────────────────────────────────────────────────────────────
# max_rounds bound stops early (retrieve/revise still fired)
# ─────────────────────────────────────────────────────────────────────────────
def test_max_rounds_bound_stops_early():
    gap = _ScriptedGaps([["g"]] * 100)  # would never converge on its own
    retrieve = _CountingRetrieve()
    revise = _CountingRevise()

    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap, retrieve_fn=retrieve, revise_fn=revise,
        max_rounds=1, wall_seconds=1e9, cost_budget=1e9,
    )

    assert result["stop_reason"] == STOP_MAX_ROUNDS
    assert result["rounds"] == 1
    assert retrieve.calls == 1
    assert revise.calls == 1


def test_max_rounds_zero_fires_nothing():
    gap = _ScriptedGaps([["g"]])
    retrieve = _CountingRetrieve()
    revise = _CountingRevise()
    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap, retrieve_fn=retrieve, revise_fn=revise,
        max_rounds=0, wall_seconds=1e9, cost_budget=1e9,
    )
    assert result["stop_reason"] == STOP_MAX_ROUNDS
    assert result["rounds"] == 0
    assert gap.calls == 0
    assert retrieve.calls == 0
    assert revise.calls == 0
    assert result["final_draft"] == "R0"


# ─────────────────────────────────────────────────────────────────────────────
# wall-clock bound stops early (injected fake clock, no real time)
# ─────────────────────────────────────────────────────────────────────────────
def test_wall_bound_stops_early():
    gap = _ScriptedGaps([["g"]] * 100)
    retrieve = _CountingRetrieve()
    revise = _CountingRevise()
    # t0=0.0; round-1 top=0.0 (proceeds); round-2 top=5.0 (>= wall 1.0 -> stop).
    clock = _clock_from([0.0, 0.0, 5.0])

    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap, retrieve_fn=retrieve, revise_fn=revise,
        max_rounds=100, wall_seconds=1.0, cost_budget=1e9,
        clock=clock,
    )

    assert result["stop_reason"] == STOP_WALL
    assert result["rounds"] == 1
    assert retrieve.calls == 1
    assert revise.calls == 1
    assert result["elapsed_seconds"] == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# cost bound stops early (injected cost probe over a fake spend ledger)
# ─────────────────────────────────────────────────────────────────────────────
def test_cost_bound_stops_early():
    gap = _ScriptedGaps([["g"]] * 100)
    ledger = {"cost": 0.0}

    def retrieve(question, gaps):
        ledger["cost"] += 0.6
        return {}

    def revise(question, draft, gaps, evidence):
        ledger["cost"] += 0.6
        return draft

    calls = {"retrieve": 0, "revise": 0}

    def counting_retrieve(q, g):
        calls["retrieve"] += 1
        return retrieve(q, g)

    def counting_revise(q, d, g, e):
        calls["revise"] += 1
        return revise(q, d, g, e)

    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap, retrieve_fn=counting_retrieve, revise_fn=counting_revise,
        max_rounds=100, wall_seconds=1e9, cost_budget=1.0,
        cost_fn=lambda: ledger["cost"],
    )

    # round 1: probe 0.0 < 1.0 -> fires (+1.2); round-2 top: probe 1.2 >= 1.0 -> stop.
    assert result["stop_reason"] == STOP_COST
    assert result["rounds"] == 1
    assert calls["retrieve"] == 1
    assert calls["revise"] == 1
    assert result["cost_spent"] == pytest.approx(1.2)


# ─────────────────────────────────────────────────────────────────────────────
# draft_fn seeds R_0 when initial_draft is None; missing both fails loud
# ─────────────────────────────────────────────────────────────────────────────
def test_draft_fn_seeds_initial_draft():
    seeded = {"calls": 0}

    def draft_fn(question):
        seeded["calls"] += 1
        return f"SKELETON({question})"

    gap = _ScriptedGaps([["g1"]])
    result = ttddr_refine(
        "Q", None,
        draft_fn=draft_fn,
        gap_fn=gap, retrieve_fn=_CountingRetrieve(), revise_fn=_CountingRevise(),
        max_rounds=10, wall_seconds=1e9, cost_budget=1e9,
    )
    assert seeded["calls"] == 1
    assert result["stop_reason"] == STOP_NO_GAPS
    assert result["rounds"] == 1
    # revision ran on the draft_fn-seeded skeleton.
    assert result["final_draft"] == "SKELETON(Q)+g1"


def test_missing_both_initial_draft_and_draft_fn_fails_loud():
    with pytest.raises(ValueError):
        ttddr_refine(
            "Q", None,
            gap_fn=_ScriptedGaps([["g"]]),
            retrieve_fn=_CountingRetrieve(), revise_fn=_CountingRevise(),
            max_rounds=10,
        )


# ─────────────────────────────────────────────────────────────────────────────
# default-OFF flag: when off, the loop invokes NO callable
# ─────────────────────────────────────────────────────────────────────────────
def test_disabled_flag_invokes_nothing():
    os.environ[_FLAG] = "0"
    gap = _ScriptedGaps([["g"]])
    retrieve = _CountingRetrieve()
    revise = _CountingRevise()

    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap, retrieve_fn=retrieve, revise_fn=revise,
        max_rounds=10, wall_seconds=1e9, cost_budget=1e9,
    )

    assert result["stop_reason"] == STOP_DISABLED
    assert result["rounds"] == 0
    assert result["gaps_closed"] == 0
    assert result["final_draft"] == "R0"
    # NOT ONE callable fired while disabled.
    assert gap.calls == 0
    assert retrieve.calls == 0
    assert revise.calls == 0


def test_flag_default_off_when_unset():
    os.environ.pop(_FLAG, None)
    assert ttddr_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "yes", "on", "ON", "True", " yes "])
def test_flag_on_tokens(on):
    os.environ[_FLAG] = on
    assert ttddr_enabled() is True


@pytest.mark.parametrize("off", ["", "0", "false", "no", "off", "garbage", "  "])
def test_flag_off_tokens(off):
    os.environ[_FLAG] = off
    assert ttddr_enabled() is False
