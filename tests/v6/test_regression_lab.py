"""Tests for the regression-lab CI gate runner."""

from __future__ import annotations

from polaris_v6.regression_lab.runner import (
    format_ci_summary,
    run_regression_lab,
)
from polaris_v6.replay.schema import RunPin


def _pin(
    run_id: str,
    *,
    pin_id: str | None = None,
    sentence_count: int = 10,
    status: str = "success",
    template: str = "clinical",
    question: str = "What does the data show on cardiovascular outcomes?",
) -> RunPin:
    return RunPin(
        pin_id=pin_id or f"pin_{run_id}",
        workspace_id="ws_x",
        run_id=run_id,
        template=template,
        question=question,
        document_ids=[],
        pinned_at="2026-05-01T10:00:00Z",
        generator_model="deepseek-v4-flash",
        verifier_model="gemma-4-31b-it",
        generator_seed=42,
        sealed_evidence_pool_ids=["ev_a", "ev_b", "ev_c"],
        sealed_verified_sentence_count=sentence_count,
        sealed_pipeline_status=status,
        sealed_cost_usd=0.42,
    )


def test_clean_baseline_passes():
    baseline = [_pin("r1"), _pin("r2"), _pin("r3")]
    candidate = [
        _pin("r1", pin_id="pin_r1_replay"),
        _pin("r2", pin_id="pin_r2_replay"),
        _pin("r3", pin_id="pin_r3_replay"),
    ]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    assert report.passed is True
    assert report.matched_count == 3
    assert report.regressions == []


def test_one_regression_fails_ci():
    baseline = [_pin("r1", sentence_count=10), _pin("r2")]
    candidate = [
        _pin("r1", pin_id="pin_r1_replay", sentence_count=10),
        _pin(
            "r2",
            pin_id="pin_r2_replay",
            status="abort_no_verified_sections",
            sentence_count=0,
        ),
    ]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    assert report.passed is False
    assert len(report.regressions) == 1


def test_unmatched_baseline_does_not_fail():
    baseline = [_pin("r1"), _pin("r2_dropped")]
    candidate = [_pin("r1", pin_id="pin_r1_replay")]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    assert report.passed is True
    assert "r2_dropped" in report.unmatched_baseline_pin_ids
    assert report.matched_count == 1


def test_unmatched_candidate_is_new_test():
    baseline = [_pin("r1")]
    candidate = [
        _pin("r1", pin_id="pin_r1_replay"),
        _pin("r_new"),
    ]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    assert report.passed is True
    assert "r_new" in report.unmatched_candidate_pin_ids


def test_warns_recorded_separately_from_regressions():
    baseline = [_pin("r1")]
    candidate = [
        _pin(
            "r1",
            pin_id="pin_r1_replay",
            template="clinical",  # same
            question="What does the data show on cardiovascular outcomes?",
        ),
    ]
    # Add a warn-level change: generator model swap
    candidate[0].generator_model = "deepseek-v4-pro"
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    assert report.passed is True
    assert len(report.warns) == 1
    assert len(report.regressions) == 0


def test_format_ci_summary_includes_verdict():
    baseline = [_pin("r1")]
    candidate = [_pin("r1", pin_id="pin_r1_replay")]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    summary = format_ci_summary(report)
    assert "PASS" in summary
    assert "matched 1/1" in summary


def test_format_ci_summary_lists_unmatched_baselines():
    """Cover regression_lab/runner.py:77 — Unmatched baseline section."""
    baseline = [_pin("r1"), _pin("r_dropped")]
    candidate = [_pin("r1", pin_id="pin_r1_replay")]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    summary = format_ci_summary(report)
    assert "Unmatched baselines" in summary
    assert "r_dropped" in summary


def test_format_ci_summary_lists_new_candidates():
    """Cover regression_lab/runner.py:81 — New candidate section."""
    baseline = [_pin("r1")]
    candidate = [_pin("r1", pin_id="pin_r1_replay"), _pin("r_brand_new")]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    summary = format_ci_summary(report)
    assert "New candidates" in summary
    assert "r_brand_new" in summary


def test_format_ci_summary_lists_regression_details():
    """Cover regression_lab/runner.py:85-89 — REGRESSION DETAILS section.

    Per-field regression formatting only fires when a matched pair has at
    least one field with severity='regression' (not 'warn'). Pipeline-status
    success → abort_no_verified_sections produces a regression-severity field.
    """
    baseline = [_pin("r1", sentence_count=10)]
    candidate = [
        _pin(
            "r1",
            pin_id="pin_r1_replay",
            status="abort_no_verified_sections",
            sentence_count=0,
        )
    ]
    report = run_regression_lab(baseline=baseline, candidate=candidate)
    assert report.passed is False
    summary = format_ci_summary(report)
    assert "REGRESSION DETAILS" in summary
    assert "FAIL" in summary
    # The arrow + field-level diff must include both pin_ids and the
    # field name that regressed.
    assert "pin_r1" in summary
    assert "pin_r1_replay" in summary
