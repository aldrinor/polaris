"""Phase 3 benchmark schema — questions, systems, dimensions, scores."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CompetingSystem = Literal[
    "polaris_v6",
    "chatgpt_5_5_pro_dr",
    "gemini_3_1_pro_dr",
    "perplexity_pro",
]

ScoreDimension = Literal[
    "factual_accuracy",
    "citation_health",
    "frame_coverage",
    "contradiction_handling",
    "refusal_calibration",
    "user_traceability",
]

DifficultyLevel = Literal["routine", "novel_synthesis", "adversarial"]


class BenchmarkQuestion(BaseModel):
    """One question in the Phase 3 benchmark suite.

    Bundles the prompt text with the graders' expectations: factual anchors a
    responsible answer should contain, optional PICO keywords (preferred by the
    coverage scorer when set), and expected refusal patterns for refusal-trigger
    questions.
    """

    question_id: str
    template: str
    text: str = Field(..., min_length=10, max_length=2000)
    difficulty: DifficultyLevel
    expected_anchors: list[str] = Field(
        default_factory=list,
        description="Short factual anchors any responsible answer should include.",
    )
    expected_pico_keywords: list[str] = Field(
        default_factory=list,
        description=(
            "PICO-style keywords (Population/Intervention/Comparison/Outcome). "
            "When set, coverage_scorer prefers these over expected_anchors."
        ),
    )
    expected_refusals: list[str] = Field(
        default_factory=list,
        description="If the question contains a refusal trigger, expected refusal patterns.",
    )


class DimensionScore(BaseModel):
    """A single dimension's score with its supporting rationale.

    ``raw`` is a normalised [0.0, 1.0] score for one ``ScoreDimension``;
    ``rationale`` is a short free-text justification.
    """

    dimension: ScoreDimension
    raw: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., min_length=4)


class SystemAnswer(BaseModel):
    """One competing system's answer to a benchmark question.

    Captures the raw response text, its citation count, and whether the system
    refused, keyed by ``question_id`` and ``system`` for scoring.
    """

    question_id: str
    system: CompetingSystem
    response_text: str
    citations_count: int = Field(..., ge=0)
    refused: bool = False


class BenchmarkScore(BaseModel):
    """One scored row in the benchmark matrix."""

    question_id: str
    system: CompetingSystem
    dimensions: list[DimensionScore] = Field(..., min_length=6)
    composite: float = Field(..., ge=0.0, le=1.0)
    scored_by: str = Field(
        ...,
        description="Layer-3 paid evaluator id or 'automated' for CI gates.",
    )


class BenchmarkSuiteDesign(BaseModel):
    """Design doc bound to a fixed set of questions + systems + dimensions."""

    suite_version: str = "v6_phase3_v1"
    questions: list[BenchmarkQuestion]
    competing_systems: list[CompetingSystem] = Field(..., min_length=2)
    score_dimensions: list[ScoreDimension] = Field(..., min_length=4)
    layer_3_evaluator_required: bool = True
