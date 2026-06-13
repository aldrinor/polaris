"""I-pipe-011 (#1236): completeness 0/0 must not pass vacuously under benchmark strict mode.

Empty checklist (no planner facet / 0 applicable topics) yields a vacuous
``covered_fraction == 1.0`` (``completeness_state == "not_applicable"``). Pre-fix every
consumer read that as complete; the evaluator gate only blocked a MEASURED low coverage.

Fix (SHARED flag ``PG_BENCHMARK_STRICT_GATES``, default "0"/off):
  * flag OFF (default): byte-identical to current behaviour — 0/0 is advisory, never a
    blocker; a measured fraction yields the measured decision.
  * flag ON (benchmark strict): a 0/0 (not_applicable) completeness is NOT-READY /
    NOT-COMPLETE, so ``completeness_ready`` is False and the evaluator gate withholds
    release. A real denominator yields the SAME measured fraction in both flag states.

Faithfulness: this only ADDS a fail-loud held verdict for an empty denominator. It does
NOT touch strict_verify / NLI / the 4-role D8 audit and never alters a measured fraction.

Offline, no network, no heavy ML. Drives the real ``CompletenessReport`` property and the
real ``compute_evaluator_gate`` with fake ev_out/judge inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.polaris_graph.evaluator.evaluator_gate import compute_evaluator_gate
from src.polaris_graph.nodes.completeness_checker import CompletenessReport

_STRICT_ENV = "PG_BENCHMARK_STRICT_GATES"


# --------------------------------------------------------------------------- fixtures
@pytest.fixture()
def strict_off(monkeypatch):
    """Ensure the strict flag is UNSET (default-off path)."""
    monkeypatch.delenv(_STRICT_ENV, raising=False)


@pytest.fixture()
def strict_on(monkeypatch):
    """Turn the shared benchmark strict flag ON."""
    monkeypatch.setenv(_STRICT_ENV, "1")


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


def _clean_judge() -> _FakeJudgeResult:
    """Judge with every axis good (no needs_revision) → isolates the completeness gate."""
    return _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": {"verdict": "good", "note": ""},
        "hedging_appropriateness": {"verdict": "good", "note": ""},
        "tone_consistency": {"verdict": "good", "note": ""},
        "flow": {"verdict": "good", "note": ""},
        "completeness": {"verdict": "good", "note": ""},
    })


# ============================================================ completeness_checker.py
# ---- not_applicable (empty checklist / 0 of 0) -------------------------------------
def test_empty_checklist_state_is_not_applicable() -> None:
    rep = CompletenessReport(domain="clinical")  # total_applicable defaults to 0
    assert rep.total_applicable == 0
    assert rep.completeness_state == "not_applicable"
    # numeric stays a vacuous 1.0 (consumers compare it; must never be None)
    assert rep.covered_fraction == 1.0


def test_empty_checklist_ready_flag_off_is_advisory_pass(strict_off) -> None:
    """flag OFF: a 0/0 completeness stays READY (advisory pass) — current behaviour."""
    rep = CompletenessReport(domain="clinical")
    assert rep.completeness_ready is True
    assert rep.is_complete() is True


def test_empty_checklist_ready_flag_on_is_not_ready(strict_on) -> None:
    """flag ON: a 0/0 completeness is NOT-READY (no measured denominator)."""
    rep = CompletenessReport(domain="clinical")
    assert rep.completeness_ready is False
    assert rep.is_complete() is False
    # the numeric is untouched — only the readiness verdict changed
    assert rep.covered_fraction == 1.0
    assert rep.completeness_state == "not_applicable"


# ---- measured (real denominator) — identical in BOTH flag states ------------------
def test_measured_high_fraction_ready_in_both_states(strict_off, monkeypatch) -> None:
    """A measured PASS (>=0.5) is READY regardless of the flag."""
    rep = CompletenessReport(domain="clinical", total_applicable=4, total_covered=3)  # 0.75
    assert rep.completeness_state == "measured"
    assert rep.completeness_ready is True
    monkeypatch.setenv(_STRICT_ENV, "1")
    assert rep.completeness_ready is True  # measured branch unchanged by the flag


def test_measured_thin_fraction_not_ready_in_both_states(strict_off, monkeypatch) -> None:
    """A measured FAIL (<0.5) is NOT-READY regardless of the flag — the measured
    decision never depends on PG_BENCHMARK_STRICT_GATES."""
    rep = CompletenessReport(domain="clinical", total_applicable=10, total_covered=3)  # 0.3
    assert rep.completeness_state == "measured"
    assert rep.completeness_ready is False
    monkeypatch.setenv(_STRICT_ENV, "1")
    assert rep.completeness_ready is False
    # measured fraction itself is byte-identical
    assert rep.covered_fraction == pytest.approx(0.3)


def test_is_complete_threshold_only_affects_measured_branch(strict_on) -> None:
    """A custom min_covered_fraction tunes the MEASURED branch; the not_applicable
    branch is decided solely by the flag (here ON → not complete)."""
    measured = CompletenessReport(domain="clinical", total_applicable=4, total_covered=2)  # 0.5
    assert measured.is_complete(min_covered_fraction=0.5) is True
    assert measured.is_complete(min_covered_fraction=0.6) is False
    not_applicable = CompletenessReport(domain="clinical")  # 0/0
    # threshold is irrelevant for not_applicable; flag ON → not complete
    assert not_applicable.is_complete(min_covered_fraction=0.0) is False


# ============================================================ evaluator_gate.py
# ---- flag OFF: vacuous 0/0 is advisory, gate passes (current behaviour) -----------
def test_gate_empty_completeness_flag_off_passes(strict_off) -> None:
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    not_applicable = CompletenessReport(domain="clinical")  # 0/0
    gate = compute_evaluator_gate(
        ev_out, judge_result=_clean_judge(), completeness=not_applicable,
    )
    assert gate.gate_class == "pass"
    assert gate.release_allowed is True
    assert "completeness_vacuous_zero_denominator" not in gate.reasons
    assert "completeness" not in gate.judge_critical_axes


# ---- flag ON: vacuous 0/0 withholds release ---------------------------------------
def test_gate_empty_completeness_flag_on_withholds_release(strict_on) -> None:
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    not_applicable = CompletenessReport(domain="clinical")  # 0/0
    gate = compute_evaluator_gate(
        ev_out, judge_result=_clean_judge(), completeness=not_applicable,
    )
    assert gate.release_allowed is False
    assert gate.gate_class == "partial"
    assert "completeness_vacuous_zero_denominator" in gate.reasons
    assert "completeness" in gate.judge_critical_axes


def test_gate_strict_fires_even_when_judge_did_not_flag_completeness(strict_on) -> None:
    """The empty denominator looks complete to the judge too, so the strict 0/0 gate
    must fire INDEPENDENT of whether the judge flagged completeness."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    not_applicable = CompletenessReport(domain="clinical")
    # _clean_judge() marks completeness "good" — judge does NOT flag it.
    gate = compute_evaluator_gate(
        ev_out, judge_result=_clean_judge(), completeness=not_applicable,
    )
    assert gate.release_allowed is False
    assert "completeness_vacuous_zero_denominator" in gate.reasons


# ---- flag ON: a MEASURED completeness is unchanged by the strict 0/0 gate ----------
def test_gate_measured_good_completeness_flag_on_still_passes(strict_on) -> None:
    """A run WITH a real denominator (measured, healthy fraction) must not trip the
    vacuous-0/0 gate — the strict gate targets the empty denominator only."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    measured_good = CompletenessReport(
        domain="clinical", total_applicable=4, total_covered=3,  # 0.75, measured
    )
    gate = compute_evaluator_gate(
        ev_out, judge_result=_clean_judge(), completeness=measured_good,
    )
    assert gate.gate_class == "pass"
    assert gate.release_allowed is True
    assert "completeness_vacuous_zero_denominator" not in gate.reasons


def test_gate_no_completeness_object_flag_on_does_not_raise(strict_on) -> None:
    """Strict mode with completeness=None must not raise and must not invent a blocker
    (no completeness object → nothing to assert vacuous about)."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    gate = compute_evaluator_gate(
        ev_out, judge_result=_clean_judge(), completeness=None,
    )
    assert gate.gate_class == "pass"
    assert gate.release_allowed is True
    assert "completeness_vacuous_zero_denominator" not in gate.reasons


# ---- measured-thin path is the SAME with the strict flag on or off ----------------
def test_gate_measured_thin_judge_flagged_is_flagged_in_both_states(
    strict_off, monkeypatch,
) -> None:
    """A judge-flagged MEASURED thin coverage stays flagged via the existing FX-10 path
    regardless of the strict flag — the strict gate adds the 0/0 case, it does not
    change the measured-thin case."""
    ev_out = _FakeEvaluatorOutput(rule_checks=[])
    measured_thin = CompletenessReport(
        domain="clinical", total_applicable=10, total_covered=3,  # 0.3
    )
    judge = _FakeJudgeResult(parse_ok=True, verdicts={
        "citation_tightness": {"verdict": "good", "note": ""},
        "completeness": {"verdict": "needs_revision", "note": ""},
    })
    gate_off = compute_evaluator_gate(ev_out, judge_result=judge, completeness=measured_thin)
    assert "judge_completeness_needs_revision" in gate_off.reasons
    monkeypatch.setenv(_STRICT_ENV, "1")
    gate_on = compute_evaluator_gate(ev_out, judge_result=judge, completeness=measured_thin)
    assert "judge_completeness_needs_revision" in gate_on.reasons
    # the measured-thin path does NOT additionally emit the 0/0 vacuous reason
    assert "completeness_vacuous_zero_denominator" not in gate_on.reasons
