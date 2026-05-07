"""Tests for beat_both_scorer — orchestrator + aggregation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.benchmark.beat_both_scorer import (
    QuestionScores,
    Scoreboard,
    SystemScores,
    run_benchmark,
    score_question,
)
from polaris_graph.benchmark.benchmark_config import (
    BenchmarkConfig,
    BenchmarkQuestion,
)
from polaris_graph.benchmark.dimension_scorers import ALL_DIMENSIONS
from polaris_graph.benchmark.polaris_runner import PolarisRunResult


def _q(qid: str = "Q1", refusal_bait: bool = False) -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id=qid,
        question_text="text",
        scope_class="out_of_scope" if refusal_bait else "clinical_efficacy",
        is_refusal_bait=refusal_bait,
        expected_pico_axes=[] if refusal_bait else ["population", "intervention", "outcome"],
    )


def _polaris_success(qid: str = "Q1", latency_ms: int = 60_000) -> PolarisRunResult:
    iso = datetime.now(timezone.utc).isoformat()
    return PolarisRunResult(
        question_id=qid,
        intake_status="in_scope",
        intake_scope_class="clinical_efficacy",
        evidence_pool={
            "pool_id": "pool-1",
            "decision_id": "dec-1",
            "sources": [
                {
                    "source_id": "src-A",
                    "url": "https://www.cochrane.org/CD001",
                    "domain": "cochrane.org",
                    "tier": "T1",
                    "title": "Source",
                    "publication_date": None,
                    "authors": [],
                    "snippet": "snippet",
                    "full_text_available": True,
                    "full_text": "trial of aspirin in adults with intervention outcome",
                    "fetched_at_utc": iso,
                    "provenance": {},
                }
            ],
            "adequacy": {
                "is_adequate": True,
                "sources_per_tier": {"T1": 1, "T2": 0, "T3": 0},
                "min_required_per_tier": {"T1": 0, "T2": 0, "T3": 0},
                "failure_reason": None,
            },
            "queries_executed": [],
            "retrieval_started_at_utc": iso,
            "retrieval_finished_at_utc": iso,
            "latency_ms": 100,
            "cost_usd": 0.0,
        },
        verified_report={
            "report_id": "report-1",
            "pool_id": "pool-1",
            "decision_id": "dec-1",
            "sections": [
                {
                    "section_id": "sec_x",
                    "section_title": "X",
                    "verified_sentences": [
                        {
                            "section_id": "sec_x",
                            "sentence_text": "Adults with intervention had outcome [#ev:src-A:0-50].",
                            "provenance_tokens": ["[#ev:src-A:0-50]"],
                            "verifier_pass": True,
                            "drop_reason": None,
                        }
                    ],
                    "section_verify_pass_rate": 1.0,
                    "section_status": "verified",
                }
            ],
            "overall_verify_pass_rate": 1.0,
            "pipeline_verdict": "success",
            "generator_model": "test/m",
            "evaluator_model": "strict_verify_v1",
            "verifier_pass_threshold": 0.4,
            "started_at_utc": iso,
            "finished_at_utc": iso,
            "latency_ms": 1000,
            "cost_usd": 0.01,
        },
        bundle_available=True,
        total_latency_ms=latency_ms,
    )


# ---------- score_question ----------

def test_score_question_returns_all_dimensions():
    polaris = _polaris_success()
    qs = score_question(
        question=_q(),
        polaris=polaris,
        chatgpt_text="Adults received intervention; outcomes reported. https://nejm.org/a",
        gemini_text="Adults studied https://cochrane.org/CD001 with intervention outcome.",
    )
    for dim in ALL_DIMENSIONS:
        assert dim in qs.polaris.by_dimension
        assert dim in qs.chatgpt.by_dimension
        assert dim in qs.gemini.by_dimension


def test_score_question_polaris_auto_wins_auditability():
    polaris = _polaris_success()
    qs = score_question(
        question=_q(),
        polaris=polaris,
        chatgpt_text="some text",
        gemini_text="some text",
    )
    assert qs.polaris.by_dimension["auditability"] == 1.0
    assert qs.chatgpt.by_dimension["auditability"] == 0.0
    assert qs.gemini.by_dimension["auditability"] == 0.0


def test_score_question_refusal_bait_polaris_correct():
    polaris = PolarisRunResult(
        question_id="Q1",
        intake_status="refused",
    )
    qs = score_question(
        question=_q(refusal_bait=True),
        polaris=polaris,
        chatgpt_text="The 2024 election...",
        gemini_text="I can't help with that.",
    )
    assert qs.polaris.by_dimension["refusal_correctness"] == 1.0
    assert qs.chatgpt.by_dimension["refusal_correctness"] == 0.0
    assert qs.gemini.by_dimension["refusal_correctness"] == 1.0


def test_score_question_missing_external_text_yields_none_scores():
    """Missing external output -> external_score=None for affected dims."""
    polaris = _polaris_success()
    qs = score_question(
        question=_q(),
        polaris=polaris,
        chatgpt_text=None,
        gemini_text=None,
    )
    # Some dimensions return None when external_text missing
    assert qs.chatgpt.by_dimension["sourcing_tier_mix"] is None
    assert qs.gemini.by_dimension["sourcing_tier_mix"] is None


def test_score_question_polaris_failure_still_produces_row():
    """Polaris that failed (no pool/report) still yields scoreable row."""
    polaris = PolarisRunResult(
        question_id="Q1",
        failure="intake HTTP 500",
    )
    qs = score_question(
        question=_q(),
        polaris=polaris,
        chatgpt_text="output",
        gemini_text="output",
    )
    # Dimensions degrade gracefully
    assert qs.polaris.by_dimension["sourcing_tier_mix"] == 0.0


# ---------- run_benchmark ----------

def test_run_benchmark_per_question_count():
    config = BenchmarkConfig(
        benchmark_id="test",
        questions=[_q("Q1"), _q("Q2"), _q("Q3")],
    )
    sb = run_benchmark(
        config=config,
        polaris_results={
            "Q1": _polaris_success("Q1"),
            "Q2": _polaris_success("Q2"),
            # Q3 missing — should still produce a row
        },
        chatgpt_outputs={"Q1": "text"},
        gemini_outputs={},
    )
    assert len(sb.per_question) == 3
    assert sb.aggregate.n_questions == 3


def test_run_benchmark_aggregate_means():
    config = BenchmarkConfig(
        benchmark_id="test",
        questions=[_q("Q1"), _q("Q2")],
    )
    sb = run_benchmark(
        config=config,
        polaris_results={
            "Q1": _polaris_success("Q1"),
            "Q2": _polaris_success("Q2"),
        },
        chatgpt_outputs={},
        gemini_outputs={},
    )
    # POLARIS auto-wins auditability for both questions
    assert sb.aggregate.polaris_mean["auditability"] == 1.0
    # External missing -> None mean
    assert sb.aggregate.chatgpt_mean["sourcing_tier_mix"] is None


def test_run_benchmark_win_count_polaris_dominates_when_externals_missing():
    """With no external outputs, polaris auto-wins every dimension."""
    config = BenchmarkConfig(
        benchmark_id="test",
        questions=[_q("Q1")],
    )
    sb = run_benchmark(
        config=config,
        polaris_results={"Q1": _polaris_success("Q1")},
        chatgpt_outputs={},
        gemini_outputs={},
    )
    assert sb.polaris_wins == len(ALL_DIMENSIONS)
    assert sb.external_wins == 0
    assert sb.ties == 0


def test_run_benchmark_includes_benchmark_id():
    config = BenchmarkConfig(
        benchmark_id="my_benchmark_v1",
        questions=[_q()],
    )
    sb = run_benchmark(
        config=config,
        polaris_results={"Q1": _polaris_success()},
        chatgpt_outputs={},
        gemini_outputs={},
    )
    assert sb.benchmark_id == "my_benchmark_v1"


def test_run_benchmark_serializes_to_json():
    config = BenchmarkConfig(benchmark_id="test", questions=[_q()])
    sb = run_benchmark(
        config=config,
        polaris_results={"Q1": _polaris_success()},
        chatgpt_outputs={},
        gemini_outputs={},
    )
    payload = sb.model_dump(mode="json")
    assert payload["benchmark_id"] == "test"
    assert "per_question" in payload
    assert "aggregate" in payload


def test_run_benchmark_handles_missing_polaris_result():
    """If polaris_results dict missing a question_id, score with failure row."""
    config = BenchmarkConfig(
        benchmark_id="test",
        questions=[_q("Q1"), _q("Q2")],
    )
    sb = run_benchmark(
        config=config,
        polaris_results={"Q1": _polaris_success("Q1")},  # Q2 missing
        chatgpt_outputs={},
        gemini_outputs={},
    )
    assert len(sb.per_question) == 2
    q2_row = next(q for q in sb.per_question if q.question_id == "Q2")
    # Auditability still 0.0 for Q2 since no bundle
    assert q2_row.polaris.by_dimension["auditability"] == 0.0
