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
    _retrieval_fetch_wall_fraction,
    _retrieval_w2_wall_fraction,
    _retrieval_wall_seconds,
    run_live_retrieval,
)

_WALL_KNOB = "PG_RETRIEVAL_WALL_SECONDS"
_FETCH_FRAC_KNOB = "PG_RETRIEVAL_FETCH_WALL_FRACTION"
_W2_FRAC_KNOB = "PG_RETRIEVAL_W2_WALL_FRACTION"

# The set of set-but-INVALID overrides that MUST fail-safe to the legacy full-wall
# (1.0). Includes non-numeric, empty, zero, negative, non-finite, and > 1.0. This is
# the P2 fix contract: the docstring promise ("any invalid value reproduces the legacy
# full-wall") is now TRUE because the parser reads the RAW value instead of routing
# through _env_float (which silently coerced these to the 0.75 / 0.5 default).
_FRACTION_INVALID_TO_LEGACY = [
    "abc", "", "0", "0.0", "-5", "inf", "-inf", "nan", "2.0", "1.5",
]


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


# ── 1b. P2 fetch-fraction parser unit table ───────────────────────────────────
def test_fetch_wall_fraction_default_when_unset(monkeypatch):
    monkeypatch.delenv(_FETCH_FRAC_KNOB, raising=False)
    assert _retrieval_fetch_wall_fraction() == 0.75


@pytest.mark.parametrize("raw,expected", [("0.5", 0.5), ("1.0", 1.0), ("0.25", 0.25), ("1", 1.0)])
def test_fetch_wall_fraction_valid_in_range_honored(monkeypatch, raw, expected):
    monkeypatch.setenv(_FETCH_FRAC_KNOB, raw)
    assert _retrieval_fetch_wall_fraction() == expected


@pytest.mark.parametrize("raw", _FRACTION_INVALID_TO_LEGACY)
def test_fetch_wall_fraction_invalid_falls_back_to_legacy_full_wall(monkeypatch, raw):
    """P2 fix: ANY set-but-invalid override (non-numeric / empty / zero / negative /
    non-finite / > 1.0) must return 1.0 = legacy full-wall — NOT the 0.75 default the
    old _env_float route silently imposed (a hidden recall cap on a garbage env)."""
    monkeypatch.setenv(_FETCH_FRAC_KNOB, raw)
    assert _retrieval_fetch_wall_fraction() == 1.0


# ── 1c. P1b W2-fraction parser unit table (mirrors the fetch parser) ───────────
def test_w2_wall_fraction_default_when_unset(monkeypatch):
    monkeypatch.delenv(_W2_FRAC_KNOB, raising=False)
    assert _retrieval_w2_wall_fraction() == 0.5


@pytest.mark.parametrize("raw,expected", [("0.5", 0.5), ("1.0", 1.0), ("0.25", 0.25), ("1", 1.0)])
def test_w2_wall_fraction_valid_in_range_honored(monkeypatch, raw, expected):
    monkeypatch.setenv(_W2_FRAC_KNOB, raw)
    assert _retrieval_w2_wall_fraction() == expected


@pytest.mark.parametrize("raw", _FRACTION_INVALID_TO_LEGACY)
def test_w2_wall_fraction_invalid_falls_back_to_legacy_full_wall(monkeypatch, raw):
    """P1b: same fail-safe contract as the fetch parser — invalid => 1.0 = pass the
    full retrieval deadline unchanged = byte-identical to the pre-P1b threading."""
    monkeypatch.setenv(_W2_FRAC_KNOB, raw)
    assert _retrieval_w2_wall_fraction() == 1.0


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


# ── 3. P1c WIRING: the fetch subwall is threaded into parallel_fetch ──────────
#
# Shared harness: a seed_only run (one seed candidate, no search fan-out, no
# network) whose parallel_fetch is replaced by a fake that captures kwargs and
# reports configurable timeout / not_dispatched counts. W2 is disabled so no
# reranker model loads (the fetch-subwall threading is fully upstream of W2).
class _FakeParallelReport:
    def __init__(self, *, timeout_count=0, not_dispatched_count=0):
        self.success_count = 0
        self.errored_count = 0
        self.timeout_count = timeout_count
        self.not_dispatched_count = not_dispatched_count
        self.results = ()


def _run_seed_fetch(monkeypatch, *, deadline, report):
    """Drive a one-candidate seed_only fetch offline; return (result, captured)."""
    captured: dict = {}

    def _fake_parallel_fetch(tasks, fetcher, **kwargs):
        captured["kwargs"] = kwargs
        captured["n_tasks"] = len(list(tasks))
        return report

    import src.polaris_graph.audit_ir.parallel_fetch as pf_mod
    monkeypatch.setattr(pf_mod, "parallel_fetch", _fake_parallel_fetch)
    # W2 default-ON would try to load the Qwen3 reranker — disable it so the
    # fetch-subwall threading test stays offline + fast (W2 is downstream of fetch).
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "0")

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
    return result, captured


def test_fetch_wall_fraction_1p0_threads_full_deadline_byte_identical(monkeypatch):
    """P1c legacy case: PG_RETRIEVAL_FETCH_WALL_FRACTION=1.0 => the fetch deadline
    threaded into parallel_fetch equals the full retrieval deadline EXACTLY (byte-
    identical to the pre-fraction behaviour)."""
    monkeypatch.setenv(_FETCH_FRAC_KNOB, "1.0")
    deadline = time.monotonic() + 12345.0
    result, captured = _run_seed_fetch(
        monkeypatch, deadline=deadline, report=_FakeParallelReport(),
    )
    assert isinstance(result, LiveRetrievalResult)
    assert captured.get("n_tasks", 0) == 1, "the seed candidate must reach parallel_fetch"
    assert "overall_deadline_monotonic" in captured["kwargs"], (
        "run_live_retrieval did not thread the fetch deadline into parallel_fetch"
    )
    assert captured["kwargs"]["overall_deadline_monotonic"] == deadline


def test_fetch_wall_fraction_bounds_the_threaded_deadline(monkeypatch):
    """P1c fraction case: with a deterministic fraction (0.5), the fetch deadline is
    f(x) = x + frac*(deadline - x), a monotone-increasing function of the code's
    internal capture instant _fetch_now in [t0, t1]. So f(t0) <= cap <= f(t1), and cap
    is STRICTLY below the full deadline (a classify/W5 slice is reserved) — a rigorous
    sandwich with no arbitrary tolerance."""
    frac = 0.5
    monkeypatch.setenv(_FETCH_FRAC_KNOB, str(frac))
    deadline = time.monotonic() + 12345.0

    t0 = time.monotonic()
    result, captured = _run_seed_fetch(
        monkeypatch, deadline=deadline, report=_FakeParallelReport(),
    )
    t1 = time.monotonic()

    cap = captured["kwargs"]["overall_deadline_monotonic"]

    def f(x):
        return x + frac * (deadline - x)

    assert f(t0) <= cap <= f(t1), (
        f"threaded fetch deadline {cap} outside the sandwich [{f(t0)}, {f(t1)}]"
    )
    assert cap < deadline, "the fraction cap must reserve a slice below the full wall"


# ── 4. P1a: fetch-SUBWALL cutoff is DISCLOSED (separate from retrieval_wall_hit) ─
def test_fetch_subwall_hit_disclosed_when_cutoff_fires(monkeypatch):
    """P1a forced-positive: under the default fraction (0.75) with a moderate future
    retrieval deadline (so _fetch_deadline < deadline) AND a fetch report that timed
    some tasks out / left some never-dispatched, run_live_retrieval must DISCLOSE the
    cutoff: result.fetch_subwall_hit True, the counts surfaced, and a
    'fetch_subwall_hit' note appended — WITHOUT flipping retrieval_wall_hit (the full
    retrieval wall did not trip; every query fired and the classify slice survived)."""
    monkeypatch.delenv(_FETCH_FRAC_KNOB, raising=False)  # default 0.75 (< 1.0 => subwall)
    deadline = time.monotonic() + 12345.0  # far future => classify loop never trips
    report = _FakeParallelReport(timeout_count=3, not_dispatched_count=2)

    result, _captured = _run_seed_fetch(monkeypatch, deadline=deadline, report=report)

    assert isinstance(result, LiveRetrievalResult)
    assert result.fetch_subwall_hit is True
    assert result.fetch_subwall_timeout_count == 3
    assert result.fetch_subwall_not_dispatched_count == 2
    assert any("fetch_subwall_hit" in n for n in result.notes)
    # The SEPARATE-flag invariant: the full retrieval wall did NOT trip.
    assert result.retrieval_wall_hit is False
    assert not any("retrieval_wall_hit" in n for n in result.notes)


def test_fetch_subwall_hit_off_when_fraction_full_wall(monkeypatch):
    """P2 (Codex REQUEST_CHANGES): PG_RETRIEVAL_FETCH_WALL_FRACTION=1.0 => _fetch_deadline ==
    retrieval deadline => the subwall is NOT active, even with the SAME timeout/not_dispatched
    report. GENUINELY byte-identical OFF: fetch_subwall_hit False AND both counts are 0 (the
    subwall never bounded the fetch, so parallel_report's counts must NOT leak into the
    subwall fields). A real cutoff at fraction=1.0 is disclosed by the existing
    retrieval_wall_hit + parallel_fetch_timeout_count paths instead."""
    monkeypatch.setenv(_FETCH_FRAC_KNOB, "1.0")
    deadline = time.monotonic() + 12345.0
    report = _FakeParallelReport(timeout_count=3, not_dispatched_count=2)

    result, _captured = _run_seed_fetch(monkeypatch, deadline=deadline, report=report)

    assert isinstance(result, LiveRetrievalResult)
    assert result.fetch_subwall_hit is False
    # P2 fix: OFF is genuinely 0/0 — the subwall counts are NOT populated when inactive.
    assert result.fetch_subwall_timeout_count == 0
    assert result.fetch_subwall_not_dispatched_count == 0
    assert not any("fetch_subwall_hit" in n for n in result.notes)
