"""Tests for F13 pin replay diff (Phase 2B Task 2B.5 substrate)."""

from __future__ import annotations

import pytest

from polaris_v6.replay.differ import compute_pin_diff
from polaris_v6.replay.schema import RunPin


def _pin(**overrides) -> RunPin:
    base = dict(
        pin_id="pin_001",
        workspace_id="ws_x",
        run_id="run_001",
        template="clinical",
        question="What does the SELECT trial show on cardiovascular outcomes?",
        document_ids=[],
        pinned_at="2026-05-01T10:00:00Z",
        generator_model="deepseek-v4-flash",
        verifier_model="gemma-4-31b-it",
        generator_seed=42,
        sealed_evidence_pool_ids=["ev_a", "ev_b", "ev_c"],
        sealed_verified_sentence_count=10,
        sealed_pipeline_status="success",
        sealed_cost_usd=0.42,
    )
    base.update(overrides)
    return RunPin(**base)


def test_identical_pins_produce_empty_diff_modulo_ids():
    a = _pin(pin_id="pin_a", run_id="run_a")
    b = _pin(pin_id="pin_b", run_id="run_b")
    diff = compute_pin_diff(a, b)
    assert diff.fields_changed == []
    assert diff.evidence_pool_added == []
    assert diff.evidence_pool_dropped == []
    assert diff.verified_sentence_count_delta == 0
    assert diff.is_regression is False


def test_same_pin_id_raises():
    p = _pin()
    with pytest.raises(ValueError):
        compute_pin_diff(p, p)


def test_generator_model_swap_is_warn():
    a = _pin(pin_id="pin_a", run_id="run_a")
    b = _pin(
        pin_id="pin_b",
        run_id="run_b",
        generator_model="deepseek-v4-pro",
    )
    diff = compute_pin_diff(a, b)
    gen_change = next(f for f in diff.fields_changed if f.field == "generator_model")
    assert gen_change.severity == "warn"
    assert diff.is_regression is False


def test_question_change_is_regression():
    a = _pin(pin_id="pin_a", run_id="run_a")
    b = _pin(
        pin_id="pin_b",
        run_id="run_b",
        question="A different question entirely.",
    )
    diff = compute_pin_diff(a, b)
    assert diff.is_regression is True


def test_pipeline_status_success_to_abort_is_regression():
    a = _pin(pin_id="pin_a", run_id="run_a", sealed_pipeline_status="success")
    b = _pin(
        pin_id="pin_b",
        run_id="run_b",
        sealed_pipeline_status="abort_no_verified_sections",
        sealed_verified_sentence_count=0,
    )
    diff = compute_pin_diff(a, b)
    assert diff.pipeline_status_changed is True
    assert diff.is_regression is True
    statuses = [f for f in diff.fields_changed if f.field == "pipeline_status"]
    assert statuses[0].severity == "regression"


def test_sentence_count_drop_over_10pct_is_regression():
    a = _pin(pin_id="pin_a", run_id="run_a", sealed_verified_sentence_count=10)
    b = _pin(pin_id="pin_b", run_id="run_b", sealed_verified_sentence_count=8)
    diff = compute_pin_diff(a, b)
    assert diff.verified_sentence_count_delta == -2
    assert diff.is_regression is True


def test_sentence_count_small_drop_not_regression():
    a = _pin(pin_id="pin_a", run_id="run_a", sealed_verified_sentence_count=100)
    b = _pin(pin_id="pin_b", run_id="run_b", sealed_verified_sentence_count=95)
    diff = compute_pin_diff(a, b)
    assert diff.is_regression is False


def test_evidence_pool_added_and_dropped():
    a = _pin(
        pin_id="pin_a",
        run_id="run_a",
        sealed_evidence_pool_ids=["ev_a", "ev_b", "ev_c"],
    )
    b = _pin(
        pin_id="pin_b",
        run_id="run_b",
        sealed_evidence_pool_ids=["ev_b", "ev_c", "ev_d", "ev_e"],
    )
    diff = compute_pin_diff(a, b)
    assert diff.evidence_pool_added == ["ev_d", "ev_e"]
    assert diff.evidence_pool_dropped == ["ev_a"]
