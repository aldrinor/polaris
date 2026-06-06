"""
Evaluator gate — BUG-M-205 fix (deep-dive R5).

Pre-fix, the orchestrator selected `success` / `partial_*` status from
outline + rule_check_fail_count + adequacy + completeness. The judge's
`needs_revision` verdicts were logged but never blocked a
release. Some deterministic rule failures (PT08 contradiction
disclosure, PT11 uncited numeric claims, PT12 invalid citation markers)
should also block release but were lumped into a generic
`warn_rule_checks` after three total failures.

Post-fix, `compute_evaluator_gate()` produces a structured gate
decision with stable reason codes:
  pass                - no blocking issues
  partial             - report ships but release_allowed=False
  abort               - release-blocking integrity failure
  advisory_unavailable - judge parse failed; FAILS CLOSED (release_allowed=False, #1055)

The orchestrator reads `gate_class` + `reasons` to select manifest
status. Two new manifest statuses are added to the taxonomy:
  partial_evaluator_advisory    - report ships, judge flagged critical axes
  abort_evaluator_critical - deterministic integrity failure (PT08/11/12)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Reason codes that map rule-check item IDs to stable gate reasons.
# Release-blocking deterministic rules:
RELEASE_BLOCKING_RULES: dict[str, str] = {
    "PT08": "rule_pt08_contradiction_missing",
    "PT11": "rule_pt11_uncited_numeric_claims",
    "PT12": "rule_pt12_invalid_citation_marker",
}

# Rules that prevent clean success but don't abort.
COMPLIANCE_BLOCKING_RULES: dict[str, str] = {
    "PT02": "rule_model_disclosure_missing",
    "PT03": "rule_model_disclosure_missing",
}

# M-3 (Codex pass 5 follow-up): advisory rules that do NOT gate
# release but whose failures should surface in `reasons` so operators
# can see them in the manifest without opening evaluator_rule_checks.json.
# Prefix is "advisory_" so downstream grep patterns that look for
# "rule_*" or "judge_*" don't accidentally treat these as blocking.
ADVISORY_RULES: dict[str, str] = {
    "PT13": "advisory_pt13_unhedged_superlatives",
}

# Judge axes that are in the high-risk set (evidence-integrity adjacent).
HIGH_RISK_JUDGE_AXES = frozenset({
    "citation_tightness",
    "hedging_appropriateness",
    "completeness",
})


@dataclass
class EvaluatorGateResult:
    """Structured decision from compute_evaluator_gate.

    `release_allowed` is the headline: False means the release consumer
    should NOT treat this run as shippable even if `gate_class=="partial"`.
    `gate_class` drives manifest status selection. `reasons` is the
    stable, greppable identifier list; `judge_critical_axes` and
    `rule_blockers` give more detail.
    """
    release_allowed: bool
    gate_class: str                              # pass | partial | abort | advisory_unavailable
    reasons: list[str] = field(default_factory=list)
    judge_critical_axes: list[str] = field(default_factory=list)
    rule_blockers: list[str] = field(default_factory=list)
    judge_parse_ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_allowed": self.release_allowed,
            "gate_class": self.gate_class,
            "reasons": list(self.reasons),
            "judge_critical_axes": list(self.judge_critical_axes),
            "rule_blockers": list(self.rule_blockers),
            "judge_parse_ok": self.judge_parse_ok,
        }


def compute_evaluator_gate(
    ev_out,
    judge_result=None,
    adequacy=None,
    completeness=None,
) -> EvaluatorGateResult:
    """Compute release-gating decision from evaluator outputs.

    Args:
        ev_out: an EvaluatorOutput-like object with `rule_checks` list
            of objects carrying .item_id, .passed, .details.
            `contradictions_missing` list is consulted for PT08.
        judge_result: optional live_judge.JudgeResult-like with
            `parse_ok` bool and `verdicts` dict mapping axis name to
            {"verdict": "good"|"acceptable"|"needs_revision", "note": str}.
            None or parse_ok=False → advisory_unavailable contribution.
        adequacy: corpus_adequacy_gate output (used to interpret
            judge completeness: if deterministic completeness is already
            thin, a solo judge completeness flag is more meaningful).
        completeness: optional; completeness_checker.covered_fraction
            informs judge completeness severity.

    Returns:
        EvaluatorGateResult with gate_class, reasons, etc.
    """
    reasons: list[str] = []
    rule_blockers: list[str] = []
    judge_critical_axes: list[str] = []

    # ── 1. Deterministic release-blocking rule failures ──
    # Any PT08/PT11/PT12 failure aborts the release regardless of total.
    abort_on_rule = False
    for rule in getattr(ev_out, "rule_checks", []) or []:
        if rule.passed:
            continue
        item_id = getattr(rule, "item_id", "")
        if item_id in RELEASE_BLOCKING_RULES:
            abort_on_rule = True
            rule_blockers.append(item_id)
            code = RELEASE_BLOCKING_RULES[item_id]
            if code not in reasons:
                reasons.append(code)
        elif item_id in COMPLIANCE_BLOCKING_RULES:
            rule_blockers.append(item_id)
            code = COMPLIANCE_BLOCKING_RULES[item_id]
            if code not in reasons:
                reasons.append(code)
        elif item_id in ADVISORY_RULES:
            # Advisory: surface in reasons for operator visibility,
            # but do NOT add to rule_blockers (gate_class stays pass).
            code = ADVISORY_RULES[item_id]
            if code not in reasons:
                reasons.append(code)

    # Also catch the PT08 special case: contradictions_missing list non-empty.
    if getattr(ev_out, "contradictions_missing", None):
        if "PT08" not in rule_blockers:
            abort_on_rule = True
            rule_blockers.append("PT08")
            code = RELEASE_BLOCKING_RULES["PT08"]
            if code not in reasons:
                reasons.append(code)

    # ── 2. Judge verdicts ──
    judge_parse_ok = True
    judge_revision_axes: list[str] = []
    if judge_result is None:
        judge_parse_ok = False
        reasons.append("judge_parse_failed")
    elif not getattr(judge_result, "parse_ok", False):
        judge_parse_ok = False
        reasons.append("judge_parse_failed")
    else:
        verdicts = getattr(judge_result, "verdicts", {}) or {}
        for axis, data in verdicts.items():
            if not isinstance(data, dict):
                continue
            if data.get("verdict") == "needs_revision":
                judge_revision_axes.append(axis)

        # Judge critical conditions (from R5 findings §3):
        needs = set(judge_revision_axes)
        high_risk_hits = needs & HIGH_RISK_JUDGE_AXES
        if "citation_tightness" in needs:
            judge_critical_axes.append("citation_tightness")
            if "judge_citation_tightness_needs_revision" not in reasons:
                reasons.append("judge_citation_tightness_needs_revision")
        if "hedging_appropriateness" in needs and "tone_consistency" in needs:
            if "hedging_appropriateness" not in judge_critical_axes:
                judge_critical_axes.append("hedging_appropriateness")
            if "tone_consistency" not in judge_critical_axes:
                judge_critical_axes.append("tone_consistency")
            if "judge_hedging_tone_needs_revision" not in reasons:
                reasons.append("judge_hedging_tone_needs_revision")
        if "completeness" in needs:
            # FX-10 (I-ready-017): a not_applicable completeness (no checklist applied →
            # vacuous covered_fraction=1.0) is ADVISORY — never flag it as thin coverage.
            # Only a MEASURED fraction below threshold is a real completeness concern; the
            # state guard keeps this correct even if a future not_applicable carried a low
            # numeric (covered_fraction stays numeric, so the comparison never TypeErrors).
            comp_thin = (
                completeness is not None
                and getattr(completeness, "completeness_state", "measured") == "measured"
                and getattr(completeness, "covered_fraction", 1.0) < 0.5
            )
            if comp_thin:
                judge_critical_axes.append("completeness")
                if "judge_completeness_needs_revision" not in reasons:
                    reasons.append("judge_completeness_needs_revision")
        # Aggregate multi-axis anti-noise gate
        if len(needs) >= 3:
            if "judge_multi_axis_needs_revision" not in reasons:
                reasons.append("judge_multi_axis_needs_revision")
            for axis in needs:
                if axis not in judge_critical_axes:
                    judge_critical_axes.append(axis)
        elif len(needs) >= 2 and high_risk_hits:
            # 2 axes including at least one high-risk → critical
            if "judge_multi_axis_needs_revision" not in reasons:
                reasons.append("judge_multi_axis_needs_revision")
            for axis in needs:
                if axis not in judge_critical_axes:
                    judge_critical_axes.append(axis)

    # ── 3. Decide gate_class ──
    if abort_on_rule:
        return EvaluatorGateResult(
            release_allowed=False,
            gate_class="abort",
            reasons=reasons,
            judge_critical_axes=judge_critical_axes,
            rule_blockers=rule_blockers,
            judge_parse_ok=judge_parse_ok,
        )

    if judge_critical_axes or any(
        r in reasons for r in (
            "rule_model_disclosure_missing",
        )
    ):
        return EvaluatorGateResult(
            release_allowed=False,
            gate_class="partial",
            reasons=reasons,
            judge_critical_axes=judge_critical_axes,
            rule_blockers=rule_blockers,
            judge_parse_ok=judge_parse_ok,
        )

    if not judge_parse_ok:
        # I-run11-009 (#1055): a judge that failed to parse means we CANNOT certify the report's
        # faithfulness/quality — FAIL CLOSED (LAW II no-silent-downgrade; §-1.1 clinical: an
        # unjudged report shipping as "ok" is lethal). The PRIOR behavior returned
        # release_allowed=True here, so in the NON-four-role (legacy honest_sweep) path — where
        # this gate is the BINDING release gate — a silently-failed judge let the report ship.
        # In four-role-seam mode this gate is demoted to `evaluator_gate_advisory` and the seam
        # decides release, so flipping it to fail-closed does NOT over-hold the seam path; it only
        # closes the legacy fail-open. `gate_class` stays "advisory_unavailable" (the judge advisory
        # IS unavailable) but release is now withheld; `reasons` already carries "judge_parse_failed".
        return EvaluatorGateResult(
            release_allowed=False,
            gate_class="advisory_unavailable",
            reasons=reasons,
            judge_critical_axes=judge_critical_axes,
            rule_blockers=rule_blockers,
            judge_parse_ok=False,
        )

    return EvaluatorGateResult(
        release_allowed=True,
        gate_class="pass",
        reasons=reasons,
        judge_critical_axes=judge_critical_axes,
        rule_blockers=rule_blockers,
        judge_parse_ok=judge_parse_ok,
    )
