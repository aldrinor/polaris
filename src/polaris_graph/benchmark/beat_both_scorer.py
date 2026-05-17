"""BEAT-BOTH scorer orchestrator — wires runner + loader + dimension scorers.

Per `.codex/slices/slice_005/architecture_proposal.md` §"beat_both_scorer".

For each BenchmarkQuestion, runs all 7 dimension scorers against
(polaris_result, chatgpt_text, gemini_text) and assembles a Scoreboard
that aggregates per-system per-dimension scores.

The Scoreboard is the artifact that report_renderer turns into HTML +
Markdown for the demo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from polaris_graph.benchmark.benchmark_config import (
    BenchmarkConfig,
    BenchmarkQuestion,
)
from polaris_graph.benchmark.dimension_scorers import (
    ALL_DIMENSIONS,
    DimensionName,
    DimensionScore,
    score_auditability,
    score_coverage_completeness,
    score_latency,
    score_numeric_grounding,
    score_provenance_density,
    score_refusal_correctness,
    score_sourcing_tier_mix,
)
from polaris_graph.benchmark.polaris_runner import PolarisRunResult


# ---------------------------------------------------------------------------
# Scoreboard schema
# ---------------------------------------------------------------------------

class SystemScores(BaseModel):
    """One system's scores for a single question (one row in the scoreboard)."""

    system: str  # 'polaris' | 'chatgpt' | 'gemini'
    by_dimension: dict[DimensionName, float | None]
    evidence: dict[DimensionName, list[str]] = Field(default_factory=dict)


class QuestionScores(BaseModel):
    """All systems' scores for one question."""

    question_id: str
    question_text: str
    is_refusal_bait: bool
    polaris: SystemScores
    chatgpt: SystemScores
    gemini: SystemScores


class AggregateScoreboard(BaseModel):
    """Mean per-dimension per-system across all questions."""

    polaris_mean: dict[DimensionName, float | None]
    chatgpt_mean: dict[DimensionName, float | None]
    gemini_mean: dict[DimensionName, float | None]
    n_questions: int


class Scoreboard(BaseModel):
    """Top-level benchmark output."""

    benchmark_id: str
    ran_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    per_question: list[QuestionScores]
    aggregate: AggregateScoreboard
    polaris_wins: int          # dimensions where polaris > both externals (per-q)
    external_wins: int          # dimensions where some external > polaris (per-q)
    ties: int                   # dimensions where polaris == max external


# ---------------------------------------------------------------------------
# Per-question scoring
# ---------------------------------------------------------------------------

def _polaris_dimension_scores(
    *,
    polaris: PolarisRunResult,
    question: BenchmarkQuestion,
) -> dict[DimensionName, DimensionScore]:
    """Run all 7 scorers in 'POLARIS-side only' mode (external_text=None)."""
    pool = None
    if polaris.evidence_pool is not None:
        from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool

        pool = EvidencePool.model_validate(polaris.evidence_pool)
    report = None
    if polaris.verified_report is not None:
        from polaris_graph.clinical_generator.verified_report import VerifiedReport

        report = VerifiedReport.model_validate(polaris.verified_report)

    scores: dict[DimensionName, DimensionScore] = {}
    scores["sourcing_tier_mix"] = score_sourcing_tier_mix(
        pool=pool, external_text=None, question=question
    )
    scores["numeric_grounding"] = score_numeric_grounding(
        report=report, pool=pool, external_text=None, question=question
    )
    scores["provenance_density"] = score_provenance_density(
        report=report, external_text=None, question=question
    )
    scores["refusal_correctness"] = score_refusal_correctness(
        report=report,
        polaris_intake_status=polaris.intake_status,
        external_text=None,
        question=question,
    )
    scores["coverage_completeness"] = score_coverage_completeness(
        report=report, external_text=None, question=question
    )
    scores["latency"] = score_latency(
        polaris_latency_ms=polaris.total_latency_ms or None,
        external_latency_ms=None,
        question=question,
    )
    scores["auditability"] = score_auditability(
        polaris_bundle_available=polaris.bundle_available,
        external_bundle_available=False,
        question=question,
    )
    return scores


def _external_dimension_scores(
    *,
    external_text: str | None,
    question: BenchmarkQuestion,
) -> dict[DimensionName, DimensionScore]:
    """Run all 7 scorers in 'external-side only' mode."""
    scores: dict[DimensionName, DimensionScore] = {}
    scores["sourcing_tier_mix"] = score_sourcing_tier_mix(
        pool=None, external_text=external_text, question=question
    )
    scores["numeric_grounding"] = score_numeric_grounding(
        report=None, pool=None, external_text=external_text, question=question
    )
    scores["provenance_density"] = score_provenance_density(
        report=None, external_text=external_text, question=question
    )
    scores["refusal_correctness"] = score_refusal_correctness(
        report=None,
        polaris_intake_status=None,
        external_text=external_text,
        question=question,
    )
    scores["coverage_completeness"] = score_coverage_completeness(
        report=None, external_text=external_text, question=question
    )
    scores["latency"] = score_latency(
        polaris_latency_ms=None,
        external_latency_ms=None,  # external latencies typically not measured
        question=question,
    )
    scores["auditability"] = score_auditability(
        polaris_bundle_available=False,
        external_bundle_available=False,
        question=question,
    )
    return scores


def _to_system_scores(
    system: str,
    dim_scores: dict[DimensionName, DimensionScore],
    *,
    use_external: bool,
) -> SystemScores:
    """Convert dict[dim -> DimensionScore] to flat SystemScores."""
    by_dim: dict[DimensionName, float | None] = {}
    evidence: dict[DimensionName, list[str]] = {}
    for dim, score in dim_scores.items():
        if use_external:
            by_dim[dim] = score.external_score
            evidence[dim] = list(score.external_evidence)
        else:
            by_dim[dim] = score.polaris_score
            evidence[dim] = list(score.polaris_evidence)
    return SystemScores(system=system, by_dimension=by_dim, evidence=evidence)


def score_question(
    *,
    question: BenchmarkQuestion,
    polaris: PolarisRunResult,
    chatgpt_text: str | None,
    gemini_text: str | None,
) -> QuestionScores:
    """Score one question across all 3 systems × 7 dimensions."""
    polaris_dim_scores = _polaris_dimension_scores(
        polaris=polaris, question=question
    )
    chatgpt_dim_scores = _external_dimension_scores(
        external_text=chatgpt_text, question=question
    )
    gemini_dim_scores = _external_dimension_scores(
        external_text=gemini_text, question=question
    )

    return QuestionScores(
        question_id=question.question_id,
        question_text=question.question_text,
        is_refusal_bait=question.is_refusal_bait,
        polaris=_to_system_scores("polaris", polaris_dim_scores, use_external=False),
        chatgpt=_to_system_scores("chatgpt", chatgpt_dim_scores, use_external=True),
        gemini=_to_system_scores("gemini", gemini_dim_scores, use_external=True),
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _mean_or_none(values: list[float | None]) -> float | None:
    """Mean of non-None values; None when all are None."""
    populated = [v for v in values if v is not None]
    if not populated:
        return None
    return sum(populated) / len(populated)


def _aggregate(per_question: list[QuestionScores]) -> AggregateScoreboard:
    """Per-system per-dimension means across all questions."""

    def _means_for(system_attr: str) -> dict[DimensionName, float | None]:
        out: dict[DimensionName, float | None] = {}
        for dim in ALL_DIMENSIONS:
            values = [
                getattr(q, system_attr).by_dimension.get(dim)
                for q in per_question
            ]
            out[dim] = _mean_or_none(values)
        return out

    return AggregateScoreboard(
        polaris_mean=_means_for("polaris"),
        chatgpt_mean=_means_for("chatgpt"),
        gemini_mean=_means_for("gemini"),
        n_questions=len(per_question),
    )


def _count_wins(per_question: list[QuestionScores]) -> tuple[int, int, int]:
    """Per question, per dimension: count polaris vs max(external) outcomes."""
    polaris_wins = 0
    external_wins = 0
    ties = 0
    for q in per_question:
        for dim in ALL_DIMENSIONS:
            p = q.polaris.by_dimension.get(dim)
            c = q.chatgpt.by_dimension.get(dim)
            g = q.gemini.by_dimension.get(dim)
            externals = [v for v in (c, g) if v is not None]
            if p is None and not externals:
                continue
            if p is None:
                external_wins += 1
                continue
            if not externals:
                polaris_wins += 1
                continue
            best_external = max(externals)
            if p > best_external:
                polaris_wins += 1
            elif p < best_external:
                external_wins += 1
            else:
                ties += 1
    return polaris_wins, external_wins, ties


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_benchmark(
    *,
    config: BenchmarkConfig,
    polaris_results: dict[str, PolarisRunResult],
    chatgpt_outputs: dict[str, str],
    gemini_outputs: dict[str, str],
) -> Scoreboard:
    """Score every benchmark question across the 3 systems × 7 dimensions."""
    per_question: list[QuestionScores] = []
    for question in config.questions:
        polaris = polaris_results.get(question.question_id)
        if polaris is None:
            polaris = PolarisRunResult(
                question_id=question.question_id,
                failure="no PolarisRunResult provided",
            )
        per_question.append(
            score_question(
                question=question,
                polaris=polaris,
                chatgpt_text=chatgpt_outputs.get(question.question_id),
                gemini_text=gemini_outputs.get(question.question_id),
            )
        )

    polaris_wins, external_wins, ties = _count_wins(per_question)

    return Scoreboard(
        benchmark_id=config.benchmark_id,
        per_question=per_question,
        aggregate=_aggregate(per_question),
        polaris_wins=polaris_wins,
        external_wins=external_wins,
        ties=ties,
    )
