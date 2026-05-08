"""I-bug-084 — coverage scorer tests."""

from __future__ import annotations

from polaris_v6.benchmark.coverage_scorer import score_response_coverage
from polaris_v6.benchmark.schema import BenchmarkQuestion


def _q(
    keywords: list[str] | None = None,
    anchors: list[str] | None = None,
) -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id="q1",
        template="clinical_summary",
        text="Does aspirin reduce migraine symptoms?",
        difficulty="routine",
        expected_anchors=anchors or [],
        expected_pico_keywords=keywords or [],
    )


def test_aspirin_migraine_with_keywords_scores_1() -> None:
    q = _q(keywords=["aspirin", "migraine"])
    assert score_response_coverage(q, "Aspirin reduces migraine symptoms.") == 1.0


def test_keywords_present_takes_precedence_over_anchors() -> None:
    # keywords match in response, anchors do NOT — keywords win → 1.0
    q = _q(
        keywords=["aspirin", "migraine"],
        anchors=["unrelated_anchor_token_xyz"],
    )
    assert score_response_coverage(q, "Aspirin reduces migraine symptoms.") == 1.0


def test_no_keywords_falls_back_to_anchors_pass() -> None:
    q = _q(keywords=[], anchors=["foo", "bar"])
    assert score_response_coverage(q, "the foo and bar both appear here") == 1.0


def test_no_keywords_falls_back_to_anchors_fail() -> None:
    q = _q(keywords=[], anchors=["foo", "bar"])
    assert score_response_coverage(q, "only foo appears here") == 0.0


def test_no_targets_returns_zero() -> None:
    q = _q(keywords=[], anchors=[])
    assert score_response_coverage(q, "anything goes") == 0.0
