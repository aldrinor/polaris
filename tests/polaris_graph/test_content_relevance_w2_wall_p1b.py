"""I-deepfix-001 (wall/tiering-abort fix, #1344) P1b — bound the W2 content-relevance
batch to a RESERVED slice of the remaining retrieval wall + the pre-scoring deadline
guard that skips the un-deadline-checked Stage-1 reranker one-pass.

Two surfaces, all OFFLINE (no network, no GPU — the reranker is injected):

  1. ``content_relevance_judge.score_passages`` PRE-SCORING guard: when the threaded
     ``deadline_monotonic`` is ALREADY past at entry, the batched reranker one-pass
     (which has no mid-flight cancel) must be SKIPPED and every passage released at
     FULL weight (always-release; §-1.3 never demote-on-timeout, never drop). The
     negative control proves that with a live (future) deadline the reranker DOES run
     and scores normally — byte-identical to the pre-P1b behaviour.

  2. ``run_live_retrieval`` threads a RESERVED-slice deadline (default 0.5 of the
     remaining wall) into ``score_passages`` instead of the full retrieval deadline;
     the =1.0 legacy knob threads the full deadline unchanged (byte-identical).
"""
from __future__ import annotations

import time

import pytest

from src.polaris_graph.retrieval.content_relevance_judge import (
    LABEL_RELEVANT,
    RelevanceReport,
    _DEFAULT_RERANKER_MARGIN_S,
    _reranker_margin_seconds,
    score_passages,
)
from src.polaris_graph.retrieval.live_retriever import (
    LiveRetrievalResult,
    run_live_retrieval,
)

_W2_FRAC_KNOB = "PG_RETRIEVAL_W2_WALL_FRACTION"
_RERANKER_MARGIN_KNOB = "PG_RETRIEVAL_W2_RERANKER_MARGIN_S"


# ── 1. pre-scoring guard: reranker SKIPPED when the reserved slice is already spent ─
def test_prescoring_guard_skips_reranker_and_releases_full_weight(monkeypatch):
    """Forced-positive: an ALREADY-PAST deadline_monotonic at entry => the injected
    reranker_predict_fn is NEVER called, EVERY passage comes back at full weight 1.0,
    and scoring_skipped_wall_hit is disclosed True (always-release, no drop)."""
    calls: list = []

    def _recording_reranker(pairs):
        calls.append(list(pairs))
        raise AssertionError("reranker must NOT be called after the reserved slice is spent")

    passages = [
        (0, "https://a.example/one", "body one with real evidence words"),
        (1, "https://b.example/two", "body two with more evidence words"),
        (2, "https://c.example/three", "third passage body here"),
    ]
    past_deadline = time.monotonic() - 10.0  # already expired at entry

    report = score_passages(
        "does drug X reduce mortality",
        passages,
        reranker_predict_fn=_recording_reranker,
        deadline_monotonic=past_deadline,
    )

    assert calls == [], "the un-deadline-checked reranker one-pass was NOT skipped"
    assert report.scoring_skipped_wall_hit is True
    assert report.n_scored == 3
    assert report.n_relevant == 3
    assert report.n_demoted == 0
    # every verdict is full weight, kept (never demoted / dropped — §-1.3).
    assert [v.idx for v in report.verdicts] == [0, 1, 2]  # stable idx order
    assert all(v.weight == 1.0 for v in report.verdicts)
    assert all(v.label == LABEL_RELEVANT for v in report.verdicts)
    assert all(v.escalated is False for v in report.verdicts)
    assert report.to_dict()["scoring_skipped_wall_hit"] is True


def test_prescoring_guard_off_when_deadline_in_future(monkeypatch):
    """Negative control: with a GENEROUS future deadline the guard does NOT fire —
    the injected reranker IS called and scores normally, scoring_skipped_wall_hit
    stays False (byte-identical to the pre-P1b path)."""
    calls: list = []

    def _scoring_reranker(pairs):
        pairs = list(pairs)
        calls.append(pairs)
        # High relevance for every window -> LABEL_RELEVANT, no GLM escalation.
        return [0.99] * len(pairs)

    passages = [
        (0, "https://a.example/one", "body one with real evidence words"),
        (1, "https://b.example/two", "body two with more evidence words"),
    ]
    future_deadline = time.monotonic() + 3600.0

    report = score_passages(
        "does drug X reduce mortality",
        passages,
        reranker_predict_fn=_scoring_reranker,
        deadline_monotonic=future_deadline,
    )

    assert len(calls) == 1, "the reranker MUST run when the deadline is still in the future"
    assert report.scoring_skipped_wall_hit is False
    assert report.n_scored == 2
    assert report.n_relevant == 2
    assert report.to_dict()["scoring_skipped_wall_hit"] is False


def test_prescoring_guard_no_deadline_scores_normally(monkeypatch):
    """deadline_monotonic=None (the guard's other byte-identical branch): scoring runs
    normally regardless of the wall (the guard only fires on a genuinely past instant)."""
    calls: list = []

    def _scoring_reranker(pairs):
        pairs = list(pairs)
        calls.append(pairs)
        return [0.99] * len(pairs)

    report = score_passages(
        "q", [(0, "https://a.example/one", "evidence body")],
        reranker_predict_fn=_scoring_reranker,
        deadline_monotonic=None,
    )
    assert len(calls) == 1
    assert report.scoring_skipped_wall_hit is False


# ── 2. run_live_retrieval threads a RESERVED W2 slice into score_passages ──────
def _drive_seed_run_capturing_w2_deadline(monkeypatch, *, deadline):
    """Seed_only, one candidate, offline. Fakes parallel_fetch AND score_passages,
    capturing the deadline_monotonic that run_live_retrieval threads into W2."""
    captured: dict = {}

    class _FakeParallelReport:
        success_count = 0
        errored_count = 0
        timeout_count = 0
        not_dispatched_count = 0
        results = ()

    def _fake_parallel_fetch(tasks, fetcher, **kwargs):
        list(tasks)
        return _FakeParallelReport()

    def _fake_score_passages(question, passages, **kwargs):
        captured["deadline_monotonic"] = kwargs.get("deadline_monotonic")
        return RelevanceReport()

    import src.polaris_graph.audit_ir.parallel_fetch as pf_mod
    import src.polaris_graph.retrieval.content_relevance_judge as crj

    monkeypatch.setattr(pf_mod, "parallel_fetch", _fake_parallel_fetch)
    monkeypatch.setattr(crj, "score_passages", _fake_score_passages)
    # W2 must be ON (default) so the block fires; be explicit for determinism.
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "1")

    result = run_live_retrieval(
        research_question="w2 slice probe",
        amplified_queries=None,
        protocol=None,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        seed_only=True,
        seed_urls=["https://example.org/seed-doc"],
        retrieval_deadline_monotonic=deadline,
    )
    return result, captured


def test_w2_default_fraction_reserves_a_slice_below_the_wall(monkeypatch):
    """Default PG_RETRIEVAL_W2_WALL_FRACTION (0.5): the deadline threaded into W2 is
    STRICTLY below the full retrieval deadline (a classify/W5 slice is reserved)."""
    monkeypatch.delenv(_W2_FRAC_KNOB, raising=False)
    deadline = time.monotonic() + 12345.0
    result, captured = _drive_seed_run_capturing_w2_deadline(monkeypatch, deadline=deadline)

    assert isinstance(result, LiveRetrievalResult)
    assert "deadline_monotonic" in captured, "W2 score_passages was not reached"
    assert captured["deadline_monotonic"] is not None
    assert captured["deadline_monotonic"] < deadline


def test_w2_fraction_1p0_threads_full_wall_byte_identical(monkeypatch):
    """PG_RETRIEVAL_W2_WALL_FRACTION=1.0 => the deadline threaded into W2 equals the
    full retrieval deadline EXACTLY (byte-identical to the pre-P1b threading)."""
    monkeypatch.setenv(_W2_FRAC_KNOB, "1.0")
    deadline = time.monotonic() + 12345.0
    result, captured = _drive_seed_run_capturing_w2_deadline(monkeypatch, deadline=deadline)

    assert isinstance(result, LiveRetrievalResult)
    assert captured["deadline_monotonic"] == deadline


# ── 3. P1 (Codex REQUEST_CHANGES): reranker ENTRY SAFETY MARGIN ────────────────
def test_prescoring_guard_skips_reranker_within_safety_margin(monkeypatch):
    """P1 forced-positive: a BARELY-FUTURE deadline (remaining budget < the margin, but
    NOT yet past) must ALSO skip the uninterruptible reranker one-pass. The base already-past
    guard alone would NOT fire here (the deadline is in the future) — proving the margin is
    what closes the start-and-overrun window. Every passage released at full weight."""
    monkeypatch.delenv(_RERANKER_MARGIN_KNOB, raising=False)  # default 30.0s margin

    def _recording_reranker(pairs):
        raise AssertionError(
            "reranker must NOT start when remaining budget is within the safety margin"
        )

    passages = [
        (0, "https://a.example/one", "body one with real evidence words"),
        (1, "https://b.example/two", "body two with more evidence words"),
    ]
    # 2.0s of budget left — strictly IN THE FUTURE, but far under the 30.0s default margin.
    barely_future = time.monotonic() + 2.0

    report = score_passages(
        "does drug X reduce mortality",
        passages,
        reranker_predict_fn=_recording_reranker,
        deadline_monotonic=barely_future,
    )

    assert report.scoring_skipped_wall_hit is True
    assert report.n_scored == 2
    assert report.n_relevant == 2
    assert report.n_demoted == 0
    assert [v.idx for v in report.verdicts] == [0, 1]
    assert all(v.weight == 1.0 for v in report.verdicts)
    assert all(v.label == LABEL_RELEVANT for v in report.verdicts)


def test_prescoring_guard_margin_zero_runs_reranker_when_barely_future(monkeypatch):
    """Byte-identical control: PG_RETRIEVAL_W2_RERANKER_MARGIN_S=0 disables the margin, so a
    barely-future (not-yet-past) deadline behaves EXACTLY like the base guard — the reranker
    DOES run (the guard only fires once the deadline is actually reached)."""
    monkeypatch.setenv(_RERANKER_MARGIN_KNOB, "0")
    calls: list = []

    def _scoring_reranker(pairs):
        pairs = list(pairs)
        calls.append(pairs)
        return [0.99] * len(pairs)

    barely_future = time.monotonic() + 5.0
    report = score_passages(
        "q", [(0, "https://a.example/one", "evidence body words here")],
        reranker_predict_fn=_scoring_reranker,
        deadline_monotonic=barely_future,
    )
    assert len(calls) == 1, "margin=0 must reproduce the base guard (reranker runs)"
    assert report.scoring_skipped_wall_hit is False


def test_prescoring_guard_margin_zero_still_fires_on_past_deadline(monkeypatch):
    """margin=0 preserves the base already-past guard exactly: an already-past deadline still
    skips the reranker and releases at full weight."""
    monkeypatch.setenv(_RERANKER_MARGIN_KNOB, "0")

    def _recording_reranker(pairs):
        raise AssertionError("reranker must be skipped on an already-past deadline")

    report = score_passages(
        "q", [(0, "https://a.example/one", "evidence body words here")],
        reranker_predict_fn=_recording_reranker,
        deadline_monotonic=time.monotonic() - 10.0,
    )
    assert report.scoring_skipped_wall_hit is True
    assert all(v.weight == 1.0 for v in report.verdicts)


# ── 3b. _reranker_margin_seconds parser unit table ────────────────────────────
def test_reranker_margin_seconds_default_when_unset(monkeypatch):
    monkeypatch.delenv(_RERANKER_MARGIN_KNOB, raising=False)
    assert _reranker_margin_seconds() == _DEFAULT_RERANKER_MARGIN_S


@pytest.mark.parametrize("raw,expected", [("0", 0.0), ("5", 5.0), ("45.5", 45.5), ("60", 60.0)])
def test_reranker_margin_seconds_valid_nonnegative_honored(monkeypatch, raw, expected):
    monkeypatch.setenv(_RERANKER_MARGIN_KNOB, raw)
    assert _reranker_margin_seconds() == expected


@pytest.mark.parametrize("raw", ["abc", "", "-5", "-0.1", "inf", "-inf", "nan"])
def test_reranker_margin_seconds_invalid_falls_back_to_default(monkeypatch, raw):
    """Fail-SAFE: any non-numeric / non-finite / NEGATIVE override returns the conservative
    default (protect the classify/W5 reserve rather than weaken the guard). Only a finite
    value >= 0 is honored (0 = explicitly disable the margin)."""
    monkeypatch.setenv(_RERANKER_MARGIN_KNOB, raw)
    assert _reranker_margin_seconds() == _DEFAULT_RERANKER_MARGIN_S
