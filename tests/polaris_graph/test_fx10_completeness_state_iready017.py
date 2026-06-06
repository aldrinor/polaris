"""FX-10 (I-ready-017): completeness NOT_APPLICABLE three-valued-logic state.

`covered_fraction` returns a vacuous 1.0 when `total_applicable == 0` (no checklist
applied). That is NOT_APPLICABLE, not a measured 100% pass. The new
`completeness_state` property disambiguates it, and the evaluator_gate consumer must
treat not_applicable as advisory (never flag thin coverage) — while covered_fraction
stays numeric so the comparison never TypeErrors.

Offline, no network: exercises the CompletenessReport property + drives the real
`compute_evaluator_gate` with fake ev_out/judge inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.polaris_graph.evaluator.evaluator_gate import compute_evaluator_gate
from src.polaris_graph.nodes.completeness_checker import CompletenessReport


# ----------------------------------------------------------------- property (legs 1)
def test_not_applicable_state_when_zero_applicable() -> None:
    rep = CompletenessReport(domain="workforce")  # total_applicable defaults to 0
    assert rep.total_applicable == 0
    assert rep.completeness_state == "not_applicable"
    assert rep.covered_fraction == 1.0  # numeric stays 1.0 (no None — consumers compare it)


def test_measured_state_when_applicable() -> None:
    rep = CompletenessReport(domain="clinical", total_applicable=4, total_covered=2)
    assert rep.completeness_state == "measured"
    assert rep.covered_fraction == 0.5


# ----------------------------------------------------------------- consumer safety
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


def _judge_flagging_completeness() -> _FakeJudgeResult:
    # judge says completeness needs_revision (so "completeness" enters `needs`),
    # everything else good.
    return _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": {"verdict": "good", "note": ""},
        "hedging_appropriateness": {"verdict": "good", "note": ""},
        "tone_consistency": {"verdict": "good", "note": ""},
        "flow": {"verdict": "good", "note": ""},
        "completeness": {"verdict": "needs_revision", "note": ""},
    })


def test_not_applicable_completeness_is_advisory_not_flagged() -> None:
    """A not_applicable completeness (vacuous 1.0) must NOT be flagged as thin coverage
    even when the judge flags completeness — and must not TypeError."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    not_applicable = CompletenessReport(domain="workforce")  # state=not_applicable
    gate = compute_evaluator_gate(
        ev_out, judge_result=_judge_flagging_completeness(), completeness=not_applicable,
    )
    assert "judge_completeness_needs_revision" not in gate.reasons, (
        "not_applicable completeness must be advisory, never a thin-coverage block"
    )


def test_measured_thin_completeness_is_flagged() -> None:
    """A MEASURED low coverage (0.3) IS a real completeness concern → flagged."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    measured_thin = CompletenessReport(
        domain="clinical", total_applicable=10, total_covered=3,  # 0.3
    )
    assert measured_thin.completeness_state == "measured"
    gate = compute_evaluator_gate(
        ev_out, judge_result=_judge_flagging_completeness(), completeness=measured_thin,
    )
    assert "judge_completeness_needs_revision" in gate.reasons
