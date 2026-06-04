"""
BUG-M-205 regression tests: evaluator gate.

Pre-fix, the judge saw only report text and its needs_revision
verdicts didn't block success. Deterministic rule failures (PT08/11/12)
were lumped into generic rule-check counts without triggering release
refusal.

Post-fix (deep-dive R5), `compute_evaluator_gate()` produces a
structured decision with reason codes. Abort-class blocks success;
partial-class prevents clean success; advisory_unavailable (judge parse
failed) FAILS CLOSED (release_allowed=False) per I-run11-009 (#1055).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.polaris_graph.evaluator.evaluator_gate import (
    EvaluatorGateResult,
    HIGH_RISK_JUDGE_AXES,
    compute_evaluator_gate,
)


# ─────────────────────────────────────────────────────────────────
# Lightweight fakes — the gate accepts any object with the right
# attribute shape; no need to import EvaluatorOutput / JudgeResult.
# ─────────────────────────────────────────────────────────────────


@dataclass
class _FakeRuleCheck:
    item_id: str
    passed: bool
    details: str = ""


@dataclass
class _FakeEvaluatorOutput:
    rule_checks: list = field(default_factory=list)
    contradictions_missing: list = field(default_factory=list)


@dataclass
class _FakeJudgeResult:
    parse_ok: bool = True
    verdicts: dict = field(default_factory=dict)


def _verdict(v: str) -> dict:
    return {"verdict": v, "note": ""}


# ─────────────────────────────────────────────────────────────────
# 1. PT12 invalid citation marker → abort
# ─────────────────────────────────────────────────────────────────

def test_m205_evaluator_gate_blocks_pt12_invalid_citations() -> None:
    ev_out = _FakeEvaluatorOutput(
        rule_checks=[_FakeRuleCheck("PT12", False, "citation marker exceeds biblio")],
    )
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        axis: _verdict("good") for axis in
        ("citation_tightness", "hedging_appropriateness", "tone_consistency",
         "flow", "completeness")
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "abort"
    assert gate.release_allowed is False
    assert "rule_pt12_invalid_citation_marker" in gate.reasons
    assert "PT12" in gate.rule_blockers


# ─────────────────────────────────────────────────────────────────
# 2. PT08 contradiction missing → abort (even with 0 other failures)
# ─────────────────────────────────────────────────────────────────

def test_m205_evaluator_gate_blocks_missing_contradiction_disclosure() -> None:
    ev_out = _FakeEvaluatorOutput(
        rule_checks=[],
        contradictions_missing=["semaglutide / weight_loss_pct"],
    )
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": _verdict("good"),
        "hedging_appropriateness": _verdict("good"),
        "tone_consistency": _verdict("good"),
        "flow": _verdict("good"),
        "completeness": _verdict("good"),
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "abort"
    assert "rule_pt08_contradiction_missing" in gate.reasons
    assert "PT08" in gate.rule_blockers


# ─────────────────────────────────────────────────────────────────
# 3. Single judge flow:needs_revision → advisory, release allowed
# ─────────────────────────────────────────────────────────────────

def test_m205_single_judge_flow_revision_is_advisory() -> None:
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": _verdict("good"),
        "hedging_appropriateness": _verdict("good"),
        "tone_consistency": _verdict("good"),
        "flow": _verdict("needs_revision"),  # advisory only
        "completeness": _verdict("good"),
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "pass"
    assert gate.release_allowed is True
    # flow is not in judge_critical_axes
    assert "flow" not in gate.judge_critical_axes


# ─────────────────────────────────────────────────────────────────
# 4. Single judge citation_tightness:needs_revision → partial, block success
# ─────────────────────────────────────────────────────────────────

def test_m205_single_judge_citation_revision_prevents_success() -> None:
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": _verdict("needs_revision"),  # critical axis
        "hedging_appropriateness": _verdict("good"),
        "tone_consistency": _verdict("good"),
        "flow": _verdict("good"),
        "completeness": _verdict("good"),
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "partial"
    assert gate.release_allowed is False
    assert "citation_tightness" in gate.judge_critical_axes
    assert "judge_citation_tightness_needs_revision" in gate.reasons


# ─────────────────────────────────────────────────────────────────
# 5. Three judge axes needs_revision → partial (multi-axis anti-noise gate)
# ─────────────────────────────────────────────────────────────────

def test_m205_three_judge_axes_needs_revision_is_partial_gate() -> None:
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": _verdict("good"),
        "hedging_appropriateness": _verdict("needs_revision"),
        "tone_consistency": _verdict("needs_revision"),
        "flow": _verdict("needs_revision"),
        "completeness": _verdict("good"),
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "partial"
    assert gate.release_allowed is False
    assert "judge_multi_axis_needs_revision" in gate.reasons
    # The hedging+tone pair is ALSO detected as critical
    assert "judge_hedging_tone_needs_revision" in gate.reasons


# ─────────────────────────────────────────────────────────────────
# 6. Judge parse failure → advisory_unavailable, FAILS CLOSED (I-run11-009 / #1055)
# ─────────────────────────────────────────────────────────────────

def test_m205_judge_parse_failure_fails_closed() -> None:
    # I-run11-009 (#1055): a judge that failed to parse means the report's faithfulness/quality
    # cannot be certified — the gate must WITHHOLD release (§-1.1 clinical: an unjudged report
    # shipping as "ok" is lethal). The PRIOR behavior returned release_allowed=True here, which let
    # a silently-failed judge ship in the non-four-role (legacy) path. gate_class stays the honest
    # "advisory_unavailable" (the judge advisory IS unavailable) but release is now denied.
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    judge = _FakeJudgeResult(parse_ok=False, verdicts={})
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "advisory_unavailable"
    assert gate.release_allowed is False  # FAIL CLOSED — cannot certify an unjudged report
    assert "judge_parse_failed" in gate.reasons


def test_m205_judge_none_treated_as_parse_failure() -> None:
    """Pipeline can pass judge_result=None when the judge call failed — also fails closed (#1055)."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    gate = compute_evaluator_gate(ev_out, judge_result=None)
    assert gate.gate_class == "advisory_unavailable"
    assert gate.release_allowed is False  # I-run11-009 (#1055): no judge -> no release
    assert "judge_parse_failed" in gate.reasons


# ─────────────────────────────────────────────────────────────────
# M-3 (Codex pass 5 follow-up): PT13 advisory surfacing
# ─────────────────────────────────────────────────────────────────

def test_m3_pt13_failure_surfaces_in_reasons_without_gating() -> None:
    """PT13 (unhedged superlatives) is advisory — it must not change
    gate_class or release_allowed, but its failure must appear in
    `reasons` under the "advisory_" prefix so operators see it at the
    manifest level."""
    ev_out = _FakeEvaluatorOutput(
        rule_checks=[_FakeRuleCheck("PT13", False, "3 unhedged superlatives")],
    )
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        axis: _verdict("good") for axis in
        ("citation_tightness", "hedging_appropriateness", "tone_consistency",
         "flow", "completeness")
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "pass"
    assert gate.release_allowed is True
    assert "advisory_pt13_unhedged_superlatives" in gate.reasons
    # PT13 is NOT a blocker — rule_blockers must be empty.
    assert "PT13" not in gate.rule_blockers


def test_m3_pt13_passing_does_not_emit_advisory_reason() -> None:
    """When PT13 passes, no advisory reason is emitted."""
    ev_out = _FakeEvaluatorOutput(
        rule_checks=[_FakeRuleCheck("PT13", True, "")],
    )
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        axis: _verdict("good") for axis in
        ("citation_tightness", "hedging_appropriateness", "tone_consistency",
         "flow", "completeness")
    })
    gate = compute_evaluator_gate(ev_out, judge_result=judge)
    assert gate.gate_class == "pass"
    assert "advisory_pt13_unhedged_superlatives" not in gate.reasons


# ─────────────────────────────────────────────────────────────────
# Taxonomy + orchestrator wiring
# ─────────────────────────────────────────────────────────────────

def test_m205_new_statuses_in_taxonomy() -> None:
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES
    # I-modref-004 (#530): primary status is the model-neutral name;
    # the legacy qwen alias stays in the taxonomy so historical
    # manifests still validate.
    assert "partial_evaluator_advisory" in UNIFIED_STATUS_VALUES
    assert "partial_qwen_advisory" in UNIFIED_STATUS_VALUES
    assert "abort_evaluator_critical" in UNIFIED_STATUS_VALUES


def test_m205_summary_labels_map_to_new_statuses() -> None:
    from scripts.run_honest_sweep_r3 import to_unified_status
    # I-modref-004 (#530): the primary summary label maps to the
    # model-neutral unified status; the legacy label still resolves.
    assert to_unified_status("ok_evaluator_advisory") == "partial_evaluator_advisory"
    assert to_unified_status("ok_qwen_advisory") == "partial_qwen_advisory"
    assert to_unified_status("abort_evaluator_critical") == "abort_evaluator_critical"


def test_m205_orchestrator_calls_compute_evaluator_gate() -> None:
    """Source check: run_one_query imports + calls compute_evaluator_gate
    and branches on the gate_class for status selection."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    assert "compute_evaluator_gate" in source, (
        "orchestrator must call compute_evaluator_gate after evaluator + judge"
    )
    assert 'eval_gate.gate_class == "abort"' in source, (
        "orchestrator must branch on eval_gate.gate_class for abort"
    )
    assert '"abort_evaluator_critical"' in source
    assert '"ok_evaluator_advisory"' in source
