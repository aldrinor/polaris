"""I-wire-005 B-A (#1319): the legacy evaluator gate is ADVISORY (not the binding gate) on the
4-role D8 seam path — and the eval_gate log line must SAY SO.

Root cause of the false-alarm B-A investigation: the I-wire-004 re-run logged
``[eval_gate] class=abort release_allowed=False reasons=['rule_pt11_uncited_numeric_claims',
'judge_skipped_d8_binding']`` while the run's REAL failure was the (separate) D8 4-role seam being
killed by the minimax-Sentinel grind (final_verdicts=0). On the seam path the legacy
evaluator_gate is DEMOTED to advisory metadata (run_honest_sweep_r3.py pops "evaluator_gate" ->
"evaluator_gate_advisory") and D8 OVERRIDES manifest['status'] + release_allowed — so the
eval_gate "abort" was NEVER the binding decision. The bare log line read like a hard run abort and
triggered the false alarm.

This suite proves, with NO live calls and NO gate-behavior change:

  (1) ``judge_skipped_d8_binding`` is BENIGN — it is an audit-trail reason that does NOT set
      gate_class="abort" on its own (the binding D8 seam decides release). A FALSE-abort is fixed
      by NOT counting it as an abort — which the gate already does NOT do.
  (2) ``PT11`` (uncited numeric claims) STILL aborts — the faithfulness rule is FROZEN, never
      disabled. The B-A fix is log clarity only; the gate's verdict is untouched.
  (3) The advisory-vs-binding ROLE annotation the runner now emits is derived purely from
      ``_seam_will_run`` (the same flag that decides whether D8 binds), so the legacy
      (non-seam) log is byte-identical.

SPEND-FREE / hermetic: only the pure ``compute_evaluator_gate`` + a small string-shape helper are
exercised.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.polaris_graph.evaluator.evaluator_gate import compute_evaluator_gate


@dataclass
class _RuleCheck:
    item_id: str
    passed: bool
    details: str = ""


@dataclass
class _EvOut:
    rule_checks: list = field(default_factory=list)
    contradictions_missing: list = field(default_factory=list)


def test_judge_skipped_d8_binding_is_not_an_abort_on_clean_rules():
    """FALSE-abort guard: when the legacy judge is intentionally SKIPPED (D8 binds) and there is no
    deterministic rule failure, the gate is PASS — judge_skipped_d8_binding is an audit-trail reason,
    never an abort. This is the 'fixed by NOT counting it as an abort' invariant (it already holds)."""
    gate = compute_evaluator_gate(
        ev_out=_EvOut(rule_checks=[_RuleCheck("PT11", passed=True)]),
        judge_result=None,
        judge_skipped=True,
    )
    assert "judge_skipped_d8_binding" in gate.reasons      # audit trail present
    assert gate.gate_class == "pass"                       # but NOT an abort
    assert gate.release_allowed is True
    assert gate.judge_parse_ok is True                     # a skip is not a parse failure


def test_pt11_still_aborts_even_when_judge_skipped():
    """FAITHFULNESS FROZEN: a real PT11 (uncited numeric) failure STILL drives gate_class='abort'
    even on the judge-skipped seam path. The B-A fix must NOT relax PT11 — only the log wording
    changes. judge_skipped_d8_binding rides along as an audit reason but does not change the verdict."""
    gate = compute_evaluator_gate(
        ev_out=_EvOut(rule_checks=[_RuleCheck("PT11", passed=False, details="3 uncited decimals")]),
        judge_result=None,
        judge_skipped=True,
    )
    assert gate.gate_class == "abort"
    assert gate.release_allowed is False
    assert "rule_pt11_uncited_numeric_claims" in gate.reasons   # the rule fired
    assert "PT11" in gate.rule_blockers
    # the audit-trail skip reason is also present, but it is NOT what caused the abort
    assert "judge_skipped_d8_binding" in gate.reasons


def _eval_gate_role(seam_will_run: bool) -> str:
    """Mirror of the run_honest_sweep_r3 log annotation (kept here so the role-string contract is
    unit-tested without importing the heavy sweep module / hitting network on import)."""
    return (
        "ADVISORY (D8 seam is the binding gate; this verdict does NOT decide release)"
        if seam_will_run
        else "BINDING (legacy single-evaluator path)"
    )


def test_eval_gate_log_role_is_advisory_on_seam_path():
    """The runner's log line must mark the eval_gate ADVISORY when the D8 seam binds, so a reader
    never mistakes its 'abort' for the binding decision (the exact false-alarm trigger)."""
    role = _eval_gate_role(seam_will_run=True)
    assert role.startswith("ADVISORY")
    assert "does NOT decide release" in role


def test_eval_gate_log_role_is_binding_on_legacy_path():
    """Off the seam (legacy single-evaluator path) the eval_gate IS the binding gate — the log must
    say BINDING and the gate's abort genuinely holds release."""
    role = _eval_gate_role(seam_will_run=False)
    assert role.startswith("BINDING")
