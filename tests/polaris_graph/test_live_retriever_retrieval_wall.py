"""I-deepfix-001 item 4 (#1344): retrieval-phase wall-deadline + partial-fetch HANDOFF.

These tests are OFFLINE (no network, no GPU). They prove the relaunch-blocking
fix: a per-question retrieval-phase deadline that, on expiry, STOPS the search
fan-out and HANDS OFF the already-gathered partial corpus to the downstream WITH
explicit disclosure — letting the run COMPLETE+RENDER on a partial fetch rather
than dying on a bare timeout, and CRUCIALLY without setting ``corpus_truncated``
(which the Path-B gate rejects).

Two pieces:
  1. ``_retrieval_wall_seconds`` env-knob: honored / garbage falls back / default.
  2. Behavioral: an already-past deadline trips the wall on the FIRST search-loop
     iteration; the function returns a ``LiveRetrievalResult`` WITHOUT raising,
     ``corpus_truncated`` stays False (the render-PASS proof — NOT the gate-out
     path), and a disclosure note records the unfired-query count.
"""
from __future__ import annotations

import time

import pytest

from src.polaris_graph.retrieval.live_retriever import (
    LiveRetrievalResult,
    _retrieval_wall_seconds,
    run_live_retrieval,
)

_WALL_KNOB = "PG_RETRIEVAL_WALL_SECONDS"


# ── 1. env-knob unit tests ────────────────────────────────────────────────────
def test_retrieval_wall_seconds_default_when_unset(monkeypatch):
    monkeypatch.delenv(_WALL_KNOB, raising=False)
    assert _retrieval_wall_seconds() == 1800.0


@pytest.mark.parametrize("raw,expected", [("60", 60.0), ("900.5", 900.5), ("1", 1.0)])
def test_retrieval_wall_seconds_honored(monkeypatch, raw, expected):
    monkeypatch.setenv(_WALL_KNOB, raw)
    assert _retrieval_wall_seconds() == expected


@pytest.mark.parametrize("raw", ["abc", "", "0", "0.0", "-5", "inf", "-inf", "nan"])
def test_retrieval_wall_seconds_falls_back_on_garbage_or_non_positive(monkeypatch, raw):
    """Mirrors ``_env_float`` finiteness/positivity guard — a bad knob never
    yields a non-finite or non-positive wall (which would defeat the deadline)."""
    monkeypatch.setenv(_WALL_KNOB, raw)
    assert _retrieval_wall_seconds() == 1800.0


# ── 2. behavioral handoff test (offline) ──────────────────────────────────────
def test_retrieval_wall_partial_handoff_renders_not_truncated(monkeypatch):
    """An ALREADY-PAST retrieval deadline trips the wall on the first search-loop
    iteration. The function must (a) return a LiveRetrievalResult without raising,
    (b) NOT set corpus_truncated (render-PASS, not the gate-out path), (c) disclose
    the unfired-query count via notes + the retrieval_wall_hit telemetry.

    Fully offline: with a past deadline the Step-2 loop breaks at iteration 0, so
    ZERO candidates are gathered → parallel_fetch is never reached → no network is
    touched. As a belt-and-suspenders guard, the search helpers are also stubbed to
    raise so a regression that fired a query before the wall check would FAIL LOUD.
    """
    import src.polaris_graph.retrieval.live_retriever as lr

    def _boom(*_a, **_k):  # any network helper firing == a wall-check regression
        raise AssertionError("search helper called AFTER the wall should have tripped")

    monkeypatch.setattr(lr, "_serper_search", _boom)
    monkeypatch.setattr(lr, "_s2_bulk_search", _boom)

    past_deadline = time.monotonic() - 10.0  # already expired

    result = run_live_retrieval(
        research_question="does drug X reduce mortality in condition Y",
        amplified_queries=["drug X mortality RCT", "condition Y guideline"],
        protocol=None,                 # skip scope validation (no extra path)
        enable_openalex_enrich=False,  # no enrich network
        enable_prefetch_filter=False,
        anchor_seed=True,
        retrieval_deadline_monotonic=past_deadline,
    )

    # (a) completed+returned, did not raise / die on a bare timeout.
    assert isinstance(result, LiveRetrievalResult)
    # (b) the discriminating assertion: render-PASS partial, NOT the gate-out path.
    assert result.corpus_truncated is False
    # (c) disclosure: the wall fired and the unfired-query count is surfaced.
    assert result.retrieval_wall_hit is True
    # anchor + 2 amplified = 3 planned sub-queries, all unfired (wall at iter 0).
    assert result.retrieval_queries_skipped == 3
    # disclosed on the manifest `notes` channel (§-1.3 — never a silent drop).
    assert any("retrieval_wall_hit" in n for n in result.notes)
    # no sources survived a zero-candidate partial, but the run still RENDERS.
    assert result.classified_sources == []


def test_no_wall_no_disclosure_off_path(monkeypatch):
    """OFF path: with a generous future deadline and an empty query set (seed_only
    with no seeds → no search, no fetch), the wall never trips and no wall
    disclosure is emitted — the byte-identical no-op guarantee."""
    monkeypatch.delenv(_WALL_KNOB, raising=False)

    result = run_live_retrieval(
        research_question="benign question",
        amplified_queries=None,
        protocol=None,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        seed_only=True,   # no search fan-out, no candidates → trivially offline
    )

    assert isinstance(result, LiveRetrievalResult)
    assert result.retrieval_wall_hit is False
    assert result.retrieval_queries_skipped == 0
    assert result.corpus_truncated is False
    assert not any("retrieval_wall_hit" in n for n in result.notes)


# ── 3. P1-3 WIRING: the wall is THREADED into parallel_fetch as its deadline ───
def test_retrieval_wall_threaded_into_parallel_fetch_deadline(monkeypatch):
    """I-deepfix-001 P1-3 (#1344): run_live_retrieval MUST pass the retrieval-phase
    deadline (`_retrieval_deadline`) as `overall_deadline_monotonic` to parallel_fetch
    so the wall actually caps the fetch batch budget. We drive a seed_only fetch (a
    single seed candidate, no search fan-out, no network) and capture parallel_fetch's
    kwargs WITHOUT performing any real fetch. The asserted value is the ABSOLUTE
    monotonic instant derived from the explicit `retrieval_deadline_monotonic`.
    """
    import src.polaris_graph.retrieval.live_retriever as lr

    captured: dict = {}

    class _FakeReport:
        success_count = 0
        errored_count = 0
        timeout_count = 0
        not_dispatched_count = 0
        results = ()

    def _fake_parallel_fetch(tasks, fetcher, **kwargs):
        captured["kwargs"] = kwargs
        captured["n_tasks"] = len(list(tasks))
        return _FakeReport()

    # parallel_fetch is imported INSIDE run_live_retrieval from the audit_ir module;
    # patch it at the source module so the local `from ... import parallel_fetch`
    # binding resolves to the fake.
    import src.polaris_graph.audit_ir.parallel_fetch as pf_mod
    monkeypatch.setattr(pf_mod, "parallel_fetch", _fake_parallel_fetch)

    # An explicit absolute deadline so the assertion is deterministic.
    deadline = time.monotonic() + 12345.0

    result = run_live_retrieval(
        research_question="seed fetch wiring probe",
        amplified_queries=None,
        protocol=None,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        seed_only=True,
        seed_urls=["https://example.org/seed-doc"],  # one candidate -> reaches fetch
        retrieval_deadline_monotonic=deadline,
    )

    assert isinstance(result, LiveRetrievalResult)
    assert captured.get("n_tasks", 0) == 1, "the seed candidate must reach parallel_fetch"
    assert "overall_deadline_monotonic" in captured["kwargs"], (
        "run_live_retrieval did not thread the retrieval wall into parallel_fetch"
    )
    assert captured["kwargs"]["overall_deadline_monotonic"] == deadline
