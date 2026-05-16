"""Tests for Phase 3 benchmark suite design schema (Task 3.4)."""

from __future__ import annotations

import pytest

from polaris_v6.benchmark.schema import (
    BenchmarkQuestion,
    BenchmarkScore,
    BenchmarkSuiteDesign,
    DimensionScore,
)


def test_minimum_question_validates():
    q = BenchmarkQuestion(
        question_id="q_clin_001",
        template="clinical",
        text="What does the SELECT trial show on MACE outcomes?",
        difficulty="novel_synthesis",
        expected_anchors=["22% reduction"],
    )
    assert q.template == "clinical"


def test_dimension_score_clamps():
    with pytest.raises(Exception):
        DimensionScore(dimension="factual_accuracy", raw=1.5, rationale="oob")


def test_benchmark_score_requires_six_dimensions():
    common = dict(rationale="rationale text exceeds minimum")
    with pytest.raises(Exception):
        BenchmarkScore(
            question_id="q1",
            system="polaris_v6",
            dimensions=[
                DimensionScore(dimension="factual_accuracy", raw=0.8, **common),
            ],
            composite=0.8,
            scored_by="automated",
        )

    full_dimensions = [
        DimensionScore(dimension=d, raw=0.8, **common)
        for d in [
            "factual_accuracy",
            "citation_health",
            "frame_coverage",
            "contradiction_handling",
            "refusal_calibration",
            "user_traceability",
        ]
    ]
    score = BenchmarkScore(
        question_id="q1",
        system="polaris_v6",
        dimensions=full_dimensions,
        composite=0.8,
        scored_by="layer3_eval_001",
    )
    assert len(score.dimensions) == 6


def test_suite_design_requires_min_two_systems():
    with pytest.raises(Exception):
        BenchmarkSuiteDesign(
            questions=[],
            competing_systems=["polaris_v6"],
            score_dimensions=[
                "factual_accuracy",
                "citation_health",
                "frame_coverage",
                "contradiction_handling",
            ],
        )


def test_suite_design_minimum_valid():
    suite = BenchmarkSuiteDesign(
        questions=[],
        competing_systems=["polaris_v6", "chatgpt_5_5_pro_dr"],
        score_dimensions=[
            "factual_accuracy",
            "citation_health",
            "frame_coverage",
            "contradiction_handling",
        ],
    )
    assert suite.suite_version == "v6_phase3_v1"
    assert suite.layer_3_evaluator_required is True


def test_difficulty_levels_enum_only():
    with pytest.raises(Exception):
        BenchmarkQuestion(
            question_id="q1",
            template="policy",
            text="Some question that meets length minimum",
            difficulty="trivial",  # not in the Literal
        )
