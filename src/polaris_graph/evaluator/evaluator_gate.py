"""
Evaluator gate — BUG-M-205 fix (deep-dive R5).

Pre-fix, the orchestrator selected `success` / `partial_*` status from
outline + rule_check_fail_count + adequacy + completeness. The Qwen
judge's `needs_revision` verdicts were logged but never blocked a
release. Some deterministic rule failures (PT08 contradiction
disclosure, PT11 uncited numeric claims, PT12 invalid citation markers)
should also block release but were lumped into a generic
`warn_rule_checks` after three total failures.

Post-fix, `compute_evaluator_gate()` produces a structured gate
decision with stable reason codes:
  pass                - no blocking issues
  partial             - report ships but release_allowed=False
  abort               - release-blocking integrity failure
  advisory_unavailable - Qwen parse failed; preserve other status

The orchestrator reads `gate_class` + `reasons` to select manifest
status. Two new manifest statuses are added to the taxonomy:
  partial_qwen_advisory    - report ships, Qwen flagged critical axes
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

# Qwen axes that are in the high-risk set (evidence-integrity adjacent).
HIGH_RISK_QWEN_AXES = frozenset({
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
    stable, greppable identifier list; `qwen_critical_axes` and
    `rule_blockers` give more detail.
    """
    release_allowed: bool
    gate_class: str                              # pass | partial | abort | advisory_unavailable
    reasons: list[str] = field(default_factory=list)
    qwen_critical_axes: list[str] = field(default_factory=list)
    rule_blockers: list[str] = field(default_factory=list)
    qwen_parse_ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_allowed": self.release_allowed,
            "gate_class": self.gate_class,
            "reasons": list(self.reasons),
            "qwen_critical_axes": list(self.qwen_critical_axes),
            "rule_blockers": list(self.rule_blockers),
            "qwen_parse_ok": self.qwen_parse_ok,
        }


def compute_evaluator_gate(
    ev_out,
    qwen_result=None,
    adequacy=None,
    completeness=None,
) -> EvaluatorGateResult:
    """Compute release-gating decision from evaluator outputs.

    Args:
        ev_out: an EvaluatorOutput-like object with `rule_checks` list
            of objects carrying .item_id, .passed, .details.
            `contradictions_missing` list is consulted for PT08.
        qwen_result: optional live_qwen_judge.JudgeResult-like with
            `parse_ok` bool and `verdicts` dict mapping axis name to
            {"verdict": "good"|"acceptable"|"needs_revision", "note": str}.
            None or parse_ok=False → advisory_unavailable contribution.
        adequacy: corpus_adequacy_gate output (used to interpret
            Qwen completeness: if deterministic completeness is already
            thin, a solo Qwen completeness flag is more meaningful).
        completeness: optional; completeness_checker.covered_fraction
            informs Qwen completeness severity.

    Returns:
        EvaluatorGateResult with gate_class, reasons, etc.
    """
    reasons: list[str] = []
    rule_blockers: list[str] = []
    qwen_critical_axes: list[str] = []

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

    # Also catch the PT08 special case: contradictions_missing list non-empty.
    if getattr(ev_out, "contradictions_missing", None):
        if "PT08" not in rule_blockers:
            abort_on_rule = True
            rule_blockers.append("PT08")
            code = RELEASE_BLOCKING_RULES["PT08"]
            if code not in reasons:
                reasons.append(code)

    # ── 2. Qwen verdicts ──
    qwen_parse_ok = True
    qwen_revision_axes: list[str] = []
    if qwen_result is None:
        qwen_parse_ok = False
        reasons.append("qwen_parse_failed")
    elif not getattr(qwen_result, "parse_ok", False):
        qwen_parse_ok = False
        reasons.append("qwen_parse_failed")
    else:
        verdicts = getattr(qwen_result, "verdicts", {}) or {}
        for axis, data in verdicts.items():
            if not isinstance(data, dict):
                continue
            if data.get("verdict") == "needs_revision":
                qwen_revision_axes.append(axis)

        # Qwen critical conditions (from R5 findings §3):
        needs = set(qwen_revision_axes)
        high_risk_hits = needs & HIGH_RISK_QWEN_AXES
        if "citation_tightness" in needs:
            qwen_critical_axes.append("citation_tightness")
            if "qwen_citation_tightness_needs_revision" not in reasons:
                reasons.append("qwen_citation_tightness_needs_revision")
        if "hedging_appropriateness" in needs and "tone_consistency" in needs:
            if "hedging_appropriateness" not in qwen_critical_axes:
                qwen_critical_axes.append("hedging_appropriateness")
            if "tone_consistency" not in qwen_critical_axes:
                qwen_critical_axes.append("tone_consistency")
            if "qwen_hedging_tone_needs_revision" not in reasons:
                reasons.append("qwen_hedging_tone_needs_revision")
        if "completeness" in needs:
            comp_thin = (
                completeness is not None
                and getattr(completeness, "covered_fraction", 1.0) < 0.5
            )
            if comp_thin:
                qwen_critical_axes.append("completeness")
                if "qwen_completeness_needs_revision" not in reasons:
                    reasons.append("qwen_completeness_needs_revision")
        # Aggregate multi-axis anti-noise gate
        if len(needs) >= 3:
            if "qwen_multi_axis_needs_revision" not in reasons:
                reasons.append("qwen_multi_axis_needs_revision")
            for axis in needs:
                if axis not in qwen_critical_axes:
                    qwen_critical_axes.append(axis)
        elif len(needs) >= 2 and high_risk_hits:
            # 2 axes including at least one high-risk → critical
            if "qwen_multi_axis_needs_revision" not in reasons:
                reasons.append("qwen_multi_axis_needs_revision")
            for axis in needs:
                if axis not in qwen_critical_axes:
                    qwen_critical_axes.append(axis)

    # ── 3. Decide gate_class ──
    if abort_on_rule:
        return EvaluatorGateResult(
            release_allowed=False,
            gate_class="abort",
            reasons=reasons,
            qwen_critical_axes=qwen_critical_axes,
            rule_blockers=rule_blockers,
            qwen_parse_ok=qwen_parse_ok,
        )

    if qwen_critical_axes or any(
        r in reasons for r in (
            "rule_model_disclosure_missing",
        )
    ):
        return EvaluatorGateResult(
            release_allowed=False,
            gate_class="partial",
            reasons=reasons,
            qwen_critical_axes=qwen_critical_axes,
            rule_blockers=rule_blockers,
            qwen_parse_ok=qwen_parse_ok,
        )

    if not qwen_parse_ok:
        # Qwen unavailable but no rule blockers; preserve other status.
        return EvaluatorGateResult(
            release_allowed=True,
            gate_class="advisory_unavailable",
            reasons=reasons,
            qwen_critical_axes=qwen_critical_axes,
            rule_blockers=rule_blockers,
            qwen_parse_ok=False,
        )

    return EvaluatorGateResult(
        release_allowed=True,
        gate_class="pass",
        reasons=reasons,
        qwen_critical_axes=qwen_critical_axes,
        rule_blockers=rule_blockers,
        qwen_parse_ok=qwen_parse_ok,
    )
