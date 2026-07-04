"""w6-I4 — TTD-DR source-yield saturation bound. OFFLINE, fake-driven, $0.

The WS-15 loop already stops on rounds / wall / cost / no-gaps. I4 adds the
saturation-keyed COMPUTE bound the beat-both plan §2 calls for: once a revision
round's TARGETED retrieval stops yielding NEW sources, firing more rounds only
re-fetches sources the draft already carries, so the loop must STOP SPENDING.

These tests prove the EFFECT on the loop's real stopping behaviour, driven by
realistic per-round retrieved rows shaped like the live retriever's output
(`source_url` dicts). Each is RED before I4 (no `STOP_SATURATION`, no
`saturation_eps`/`rows_of` params, no source-yield bound) and GREEN after.

DNA guard (§-1.3): saturation is a spend bound, NEVER a breadth cap. The tests
assert that a saturating round's OWN evidence is still folded into the draft
(consolidate, never drop) — the bound only stops FURTHER rounds.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.retrieval.ttddr_loop import (
    STOP_MAX_ROUNDS,
    STOP_NO_GAPS,
    STOP_SATURATION,
    ttddr_refine,
    ttddr_saturation_eps,
)

_FLAG = "PG_TTDDR_ENABLED"
_EPS_ENV = "PG_TTDDR_SATURATION_EPS"


@pytest.fixture(autouse=True)
def _enable_ttddr():
    prev = os.environ.get(_FLAG)
    os.environ[_FLAG] = "1"
    yield
    if prev is None:
        os.environ.pop(_FLAG, None)
    else:
        os.environ[_FLAG] = prev


def _rows(*urls):
    """A retrieved-evidence payload shaped like the live retriever's rows."""
    return {"rows": [{"source_url": u} for u in urls]}


def _rows_of(evidence):
    return list((evidence or {}).get("rows", []))


class _ScriptedRetrieve:
    """retrieve_fn fake: returns the next scripted row-payload per round."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = 0

    def __call__(self, question, gaps):
        self.calls += 1
        if self._payloads:
            return self._payloads.pop(0)
        return _rows()


def _always_gap(_q, _draft):
    """gap_fn that never converges — so ONLY a bound can stop the loop."""
    return ["gap"]


def _revise(question, draft, gaps, evidence):
    """Fold every retrieved source URL into the draft (observable consolidation)."""
    urls = [r["source_url"] for r in _rows_of(evidence)]
    return f"{draft}+[{'|'.join(urls)}]"


# ─────────────────────────────────────────────────────────────────────────────
# saturation FIRES: round 2 re-fetches the same sources -> novelty 0 -> STOP
# ─────────────────────────────────────────────────────────────────────────────
def test_saturation_stops_when_new_rounds_yield_no_new_sources():
    # Round 1 brings two fresh sources; round 2 re-fetches the SAME two (0 new).
    retrieve = _ScriptedRetrieve([
        _rows("http://a.com", "http://b.com"),   # round 1 — novelty 1.0
        _rows("http://a.com", "http://b.com"),   # round 2 — novelty 0.0 -> STOP
        _rows("http://c.com"),                    # would fire if not stopped
    ])
    result = ttddr_refine(
        "Q", "R0",
        gap_fn=_always_gap, retrieve_fn=retrieve, revise_fn=_revise,
        max_rounds=50, wall_seconds=1e9, cost_budget=1e9,
        saturation_eps=0.05, rows_of=_rows_of,
    )

    assert result["stop_reason"] == STOP_SATURATION
    assert result["rounds"] == 2                       # stopped after round 2
    assert retrieve.calls == 2                          # round 3 never fired
    assert result["novelty_history"] == [1.0, 0.0]
    # Consolidate-not-drop: round 2's re-fetched evidence was STILL folded in.
    assert result["final_draft"] == "R0+[http://a.com|http://b.com]+[http://a.com|http://b.com]"


# ─────────────────────────────────────────────────────────────────────────────
# saturation does NOT fire while every round keeps bringing fresh sources
# ─────────────────────────────────────────────────────────────────────────────
def test_saturation_does_not_fire_while_sources_stay_novel():
    retrieve = _ScriptedRetrieve([
        _rows("http://a.com"),   # round 1 — novelty 1.0
        _rows("http://b.com"),   # round 2 — novelty 1.0
        _rows("http://c.com"),   # round 3 — novelty 1.0
    ])
    # Converge via gap_fn after 3 productive rounds so the run ends on NO_GAPS,
    # proving saturation never tripped despite a low eps.
    script = {"n": 0}

    def gap_fn(_q, _draft):
        script["n"] += 1
        return ["g"] if script["n"] <= 3 else []

    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap_fn, retrieve_fn=retrieve, revise_fn=_revise,
        max_rounds=50, wall_seconds=1e9, cost_budget=1e9,
        saturation_eps=0.05, rows_of=_rows_of,
    )

    assert result["stop_reason"] == STOP_NO_GAPS      # NOT saturation
    assert result["rounds"] == 3
    assert result["novelty_history"] == [1.0, 1.0, 1.0]


# ─────────────────────────────────────────────────────────────────────────────
# partial-overlap round below the floor stops; above the floor continues
# ─────────────────────────────────────────────────────────────────────────────
def test_saturation_floor_is_a_fraction_not_all_or_nothing():
    # Round 2 brings 1 novel of 4 rows (0.25 novelty). With eps=0.30 that is
    # below the floor -> STOP; the bound is a fraction, not "zero new sources".
    retrieve = _ScriptedRetrieve([
        _rows("http://a.com", "http://b.com", "http://c.com"),           # r1 novelty 1.0
        _rows("http://a.com", "http://b.com", "http://c.com", "http://d.com"),  # r2 novelty 0.25
    ])
    result = ttddr_refine(
        "Q", "R0",
        gap_fn=_always_gap, retrieve_fn=retrieve, revise_fn=_revise,
        max_rounds=50, wall_seconds=1e9, cost_budget=1e9,
        saturation_eps=0.30, rows_of=_rows_of,
    )
    assert result["stop_reason"] == STOP_SATURATION
    assert result["rounds"] == 2
    assert result["novelty_history"][0] == 1.0
    assert result["novelty_history"][1] == pytest.approx(0.25)


# ─────────────────────────────────────────────────────────────────────────────
# the bound never trips on the FIRST round (needs a prior round to compare)
# ─────────────────────────────────────────────────────────────────────────────
def test_first_round_never_saturates_even_with_zero_rows():
    # Round 1 retrieves NOTHING (novelty 0.0), but with no prior round to compare
    # the loop must NOT read that as saturation — it keeps going. Round 2 then
    # brings fresh sources; convergence ends it on NO_GAPS.
    retrieve = _ScriptedRetrieve([
        _rows(),                  # round 1 — 0 rows, novelty 0.0, must NOT stop
        _rows("http://x.com"),    # round 2 — fresh source
    ])
    script = {"n": 0}

    def gap_fn(_q, _draft):
        script["n"] += 1
        return ["g"] if script["n"] <= 2 else []

    result = ttddr_refine(
        "Q", "R0",
        gap_fn=gap_fn, retrieve_fn=retrieve, revise_fn=_revise,
        max_rounds=50, wall_seconds=1e9, cost_budget=1e9,
        saturation_eps=0.05, rows_of=_rows_of,
    )
    assert result["stop_reason"] == STOP_NO_GAPS
    assert result["rounds"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# the bound is INERT unless BOTH eps and rows_of are wired (back-compat)
# ─────────────────────────────────────────────────────────────────────────────
def test_bound_inert_without_rows_extractor():
    # eps set but rows_of missing -> the loop cannot measure yield, so the bound
    # stays off and max_rounds is the only stop. Proves the opt-in contract.
    retrieve = _ScriptedRetrieve([_rows("http://a.com")] * 10)
    result = ttddr_refine(
        "Q", "R0",
        gap_fn=_always_gap, retrieve_fn=retrieve, revise_fn=_revise,
        max_rounds=3, wall_seconds=1e9, cost_budget=1e9,
        saturation_eps=0.05, rows_of=None,
    )
    assert result["stop_reason"] == STOP_MAX_ROUNDS
    assert result["rounds"] == 3
    assert result["novelty_history"] == []


# ─────────────────────────────────────────────────────────────────────────────
# env resolver: config-driven floor (LAW VI), sane default + clamps
# ─────────────────────────────────────────────────────────────────────────────
def test_saturation_eps_env_resolver_default_and_clamps():
    prev = os.environ.get(_EPS_ENV)
    try:
        os.environ.pop(_EPS_ENV, None)
        assert ttddr_saturation_eps() == 0.05           # default when unset
        os.environ[_EPS_ENV] = "0.2"
        assert ttddr_saturation_eps() == pytest.approx(0.2)
        os.environ[_EPS_ENV] = "9.0"                     # > 1 clamps to 1.0
        assert ttddr_saturation_eps() == 1.0
        os.environ[_EPS_ENV] = "-3"                      # < 0 clamps to 0.0
        assert ttddr_saturation_eps() == 0.0
        os.environ[_EPS_ENV] = "garbage"                 # invalid -> default
        assert ttddr_saturation_eps() == 0.05
    finally:
        if prev is None:
            os.environ.pop(_EPS_ENV, None)
        else:
            os.environ[_EPS_ENV] = prev
