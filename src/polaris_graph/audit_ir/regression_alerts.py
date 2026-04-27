"""Regression alerts (M-18 — Phase C).

Across-run companion to M-17 (within-run citation health). Where
M-17 catches integrity defects in a single run, M-18 catches the
opposite failure mode: the run is internally consistent but
materially worse than the baseline (prior successful run of the
same slug). Customer-facing audits must not silently regress.

Inputs: two loaded `AuditIR` objects — `ir_a` is the baseline
(prior successful run of the same slug), `ir_b` is the new run
under inspection. The function reuses M-16's `RunDiff` for delta
discovery and adds severity classification on top.

LAW VI: every threshold is env-overridable. Defaults are
conservative-strict in the false-positive direction (better to
surface a borderline regression than miss a real one).

LAW II: alerts surface as ERROR-equivalent severities (CRITICAL,
HIGH). They do not silently degrade; the operator decides whether
a HIGH-severity-flagged run still ships.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.polaris_graph.audit_ir.loader import AuditIR
from src.polaris_graph.audit_ir.run_diff import (
    ContradictionDelta,
    RunDiff,
    diff_runs,
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AlertSeverity(Enum):
    """Severity tiers for regression alerts.

    CRITICAL: ship-blocker. Examples: gate flipped from pass to
    fail; release_allowed flipped to False. Operator MUST review.

    HIGH: surface prominently. Examples: verified-sentence count
    halved; new high-severity contradiction. Operator should
    review before sign-off.

    MEDIUM: log + surface in alert pane. Material drop but inside
    normal-operations range.

    INFO: telemetry only.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"


class AlertCode(Enum):
    """Stable issue codes for regression findings."""

    ADEQUACY_REGRESSION = "adequacy_regression"
    RELEASE_NOT_ALLOWED = "release_not_allowed"
    EVALUATOR_GATE_DOWNGRADE = "evaluator_gate_downgrade"
    VERIFIED_DROP = "verified_drop"
    CITATION_DROP = "citation_drop"
    TIER_DOWNGRADE = "tier_downgrade"
    NEW_CONTRADICTION = "new_contradiction"
    NEW_HIGH_SEVERITY_CONTRADICTION = "new_high_severity_contradiction"
    CONTRADICTION_SEVERITY_ESCALATION = "contradiction_severity_escalation"
    COST_SPIKE = "cost_spike"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegressionAlert:
    """One regression finding, severity-tagged.

    `a_value` and `b_value` are the baseline and new values for
    the metric driving the alert (e.g. citation counts, cost in
    USD). Optional — set None for boolean-flip alerts.

    `threshold` is the env-overridable threshold the alert is
    evaluated against, surfaced for telemetry/audit.
    """

    severity: AlertSeverity
    code: AlertCode
    message: str
    a_value: float | int | str | bool | None = None
    b_value: float | int | str | bool | None = None
    threshold: float | str | None = None


@dataclass(frozen=True)
class RegressionReportSummary:
    """Aggregate counts + worst-severity convenience field."""

    critical_count: int
    high_count: int
    medium_count: int
    info_count: int
    worst_severity: str  # "critical" / "high" / "medium" / "info" / "ok"


@dataclass(frozen=True)
class RegressionReport:
    """Surface for the inspector endpoint + audit-bundle attachment."""

    a_run_id: str
    b_run_id: str
    slug: str
    alerts: tuple[RegressionAlert, ...]
    summary: RegressionReportSummary


# ---------------------------------------------------------------------------
# Thresholds (LAW VI — env-overridable)
# ---------------------------------------------------------------------------


def _float_env(key: str, default: float) -> float:
    """Return float env var, falling back to default on parse error
    or if unset. Matches the pattern used by run_diff / classifier."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        v = float(raw)
        if v < 0:
            return default
        return v
    except ValueError:
        return default


def _verified_drop_threshold() -> float:
    """Fraction below which a verified-sentence drop counts as
    HIGH (defaults to 0.20 — 20% drop). Above 0.50 escalates to
    CRITICAL inside the alert generator."""
    return _float_env("PG_REGRESSION_VERIFIED_DROP_PCT", 0.20)


def _citation_drop_threshold() -> float:
    """Fraction below which a citation/bibliography drop counts as
    MEDIUM (defaults to 0.20). Above 0.50 escalates to HIGH."""
    return _float_env("PG_REGRESSION_CITATION_DROP_PCT", 0.20)


def _tier_downgrade_threshold_pp() -> float:
    """Percentage-point T1+T2 fraction drop above which a tier
    downgrade alert fires (defaults to 10.0 pp)."""
    return _float_env("PG_REGRESSION_T1T2_DROP_PP", 10.0)


def _cost_spike_ratio() -> float:
    """Ratio of new/baseline cost above which a cost-spike alert
    fires (defaults to 1.5 — i.e. 50% increase). Ratios above 3.0
    escalate from MEDIUM to HIGH.

    Codex M-18 v1 review fix: clamp to >= 1.0. A ratio below 1.0
    would let an env override flag a CHEAPER run as a cost spike
    (false-positive on improvement), so we floor the user-supplied
    value at 1.0 and let the default of 1.5 stand otherwise.
    """
    raw = _float_env("PG_REGRESSION_COST_SPIKE_RATIO", 1.5)
    return max(1.0, raw)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _check_release_flip(ir_a: AuditIR, ir_b: AuditIR) -> list[RegressionAlert]:
    """release_allowed: True (a) → False (b) is a CRITICAL flip."""
    alerts: list[RegressionAlert] = []
    a = bool(ir_a.manifest.release_allowed)
    b = bool(ir_b.manifest.release_allowed)
    if a and not b:
        alerts.append(
            RegressionAlert(
                severity=AlertSeverity.CRITICAL,
                code=AlertCode.RELEASE_NOT_ALLOWED,
                message=(
                    "release_allowed flipped from True (baseline) to "
                    "False (new run); the new run cannot ship without "
                    "review even if other metrics look healthy"
                ),
                a_value=True,
                b_value=False,
            )
        )
    return alerts


def _check_evaluator_gate(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """gate_class downgrade (e.g. "pass" → "fail" / "blocked").

    Treats any gate_class change where the new class is one of
    {"fail", "blocked", "abort"} but the baseline was "pass" as
    CRITICAL.
    """
    alerts: list[RegressionAlert] = []
    a_gate = ir_a.manifest.evaluator_gate.gate_class.lower()
    b_gate = ir_b.manifest.evaluator_gate.gate_class.lower()
    failing = {"fail", "blocked", "abort", "rejected"}
    if a_gate == "pass" and b_gate in failing:
        alerts.append(
            RegressionAlert(
                severity=AlertSeverity.CRITICAL,
                code=AlertCode.EVALUATOR_GATE_DOWNGRADE,
                message=(
                    f"evaluator gate downgraded from "
                    f"{ir_a.manifest.evaluator_gate.gate_class!r} to "
                    f"{ir_b.manifest.evaluator_gate.gate_class!r}; "
                    f"new run is gate-blocked"
                ),
                a_value=ir_a.manifest.evaluator_gate.gate_class,
                b_value=ir_b.manifest.evaluator_gate.gate_class,
            )
        )
    return alerts


def _check_adequacy(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """Adequacy gate transition baseline-passing → new-failing is CRITICAL.

    Codex M-18 v1 review fix: real V30 corpus_adequacy_gate emits
    `proceed | expand | abort` (see corpus_adequacy_gate.py:29) —
    NOT `pass/fail/approved`. v1 used the wrong vocabulary, so a
    real `proceed → abort` regression produced no alert. v2 uses
    the actual decision space and treats both `expand` (corpus
    needs more sources) and `abort` (corpus rejected) as failing
    states relative to a baseline of `proceed`.
    """
    alerts: list[RegressionAlert] = []
    if ir_a.adequacy is None or ir_b.adequacy is None:
        return alerts
    a_dec = (ir_a.adequacy.decision or "").lower()
    b_dec = (ir_b.adequacy.decision or "").lower()
    # Real V30 vocabulary first (per corpus_adequacy_gate.py).
    # Legacy aliases retained for older artifact directories that
    # may still carry the prior pass/fail naming.
    passing = {"proceed", "pass", "approved", "adequate"}
    failing = {"abort", "expand", "fail", "rejected", "inadequate"}
    if a_dec in passing and b_dec in failing:
        alerts.append(
            RegressionAlert(
                severity=AlertSeverity.CRITICAL,
                code=AlertCode.ADEQUACY_REGRESSION,
                message=(
                    f"corpus adequacy decision regressed from "
                    f"{ir_a.adequacy.decision!r} to "
                    f"{ir_b.adequacy.decision!r}; the new corpus "
                    f"no longer passes the gate the baseline corpus "
                    f"passed"
                ),
                a_value=ir_a.adequacy.decision,
                b_value=ir_b.adequacy.decision,
            )
        )
    return alerts


def _check_verified_drop(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """Verified-sentence count drop relative to baseline.

    Severity ladder:
      drop_frac >= 0.50 → CRITICAL
      drop_frac >= threshold (default 0.20) → HIGH
      else → no alert
    """
    alerts: list[RegressionAlert] = []
    a_n = max(ir_a.verified_report.sentences_verified, 0)
    b_n = max(ir_b.verified_report.sentences_verified, 0)
    if a_n == 0:
        # No baseline to compare against; cannot detect a drop.
        return alerts
    drop_frac = (a_n - b_n) / a_n if a_n > 0 else 0.0
    threshold = _verified_drop_threshold()
    if drop_frac >= 0.50:
        sev = AlertSeverity.CRITICAL
    elif drop_frac >= threshold:
        sev = AlertSeverity.HIGH
    else:
        return alerts
    alerts.append(
        RegressionAlert(
            severity=sev,
            code=AlertCode.VERIFIED_DROP,
            message=(
                f"verified-sentence count dropped from {a_n} "
                f"(baseline) to {b_n} ({drop_frac*100:.1f}% drop); "
                f"the new run produces materially less audited prose"
            ),
            a_value=a_n,
            b_value=b_n,
            threshold=threshold,
        )
    )
    return alerts


def _check_citation_drop(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """Bibliography-size drop relative to baseline.

    Severity ladder:
      drop_frac >= 0.50 → HIGH
      drop_frac >= threshold (default 0.20) → MEDIUM
      else → no alert
    """
    alerts: list[RegressionAlert] = []
    a_n = len(ir_a.bibliography)
    b_n = len(ir_b.bibliography)
    if a_n == 0:
        return alerts
    drop_frac = (a_n - b_n) / a_n if a_n > 0 else 0.0
    threshold = _citation_drop_threshold()
    if drop_frac >= 0.50:
        sev = AlertSeverity.HIGH
    elif drop_frac >= threshold:
        sev = AlertSeverity.MEDIUM
    else:
        return alerts
    alerts.append(
        RegressionAlert(
            severity=sev,
            code=AlertCode.CITATION_DROP,
            message=(
                f"bibliography size dropped from {a_n} (baseline) to "
                f"{b_n} ({drop_frac*100:.1f}% drop); the new run "
                f"cites fewer sources"
            ),
            a_value=a_n,
            b_value=b_n,
            threshold=threshold,
        )
    )
    return alerts


def _high_quality_fraction(ir: AuditIR) -> float:
    """Sum of T1 + T2 fractions in the tier mix.

    Real V30 manifests use T1..T7 + UNKNOWN (real keys). Older
    manifests may use tier1..tier4. Both are tolerated; missing
    keys count as 0.
    """
    f = ir.tier_mix.fractions
    return float(
        f.get("T1", 0.0) + f.get("T2", 0.0)
        + f.get("tier1", 0.0) + f.get("tier2", 0.0)
    )


def _check_tier_downgrade(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """T1+T2 fraction drop relative to baseline.

    Sources at T1/T2 are the regulatory-grade evidence (FDA labels,
    EMA EPARs, RCT primary publications). Replacing them with T3+
    sources (reviews, news, clinic notes) materially lowers audit
    grade — even if total citation count stays the same.
    """
    alerts: list[RegressionAlert] = []
    a_hi = _high_quality_fraction(ir_a)
    b_hi = _high_quality_fraction(ir_b)
    drop_pp = (a_hi - b_hi) * 100.0
    threshold_pp = _tier_downgrade_threshold_pp()
    if drop_pp < threshold_pp:
        return alerts
    if drop_pp >= 30.0:
        sev = AlertSeverity.HIGH
    else:
        sev = AlertSeverity.MEDIUM
    alerts.append(
        RegressionAlert(
            severity=sev,
            code=AlertCode.TIER_DOWNGRADE,
            message=(
                f"high-quality (T1+T2) source share dropped from "
                f"{a_hi*100:.1f}% to {b_hi*100:.1f}% "
                f"({drop_pp:.1f}pp drop); the new run leans on "
                f"lower-tier evidence"
            ),
            a_value=round(a_hi, 4),
            b_value=round(b_hi, 4),
            threshold=threshold_pp,
        )
    )
    return alerts


# Codex M-18 v1 review: contradiction severity escalation must
# also alert. M-16 keys contradictions by (subject, predicate),
# so the same cluster persisting across runs but escalating
# severity (low → high, medium → critical) doesn't surface as
# an "added" delta. Detect escalations directly by walking both
# IR's contradictions and matching on (subject, predicate).
_SEVERITY_RANK: dict[str, int] = {
    "info": 0, "low": 1, "minor": 1,
    "medium": 2, "moderate": 2,
    "high": 3, "severe": 3, "major": 3,
    "critical": 4,
}
_HIGH_SEVERITY_KEYWORDS: frozenset[str] = frozenset({
    "high", "critical", "severe", "major",
})


def _severity_rank(s: str | None) -> int:
    """Coerce a contradiction severity string into a totally-
    ordered rank for escalation detection. Unknown strings rank 0
    so 'unknown' → 'high' looks like an escalation rather than a
    sideways move."""
    return _SEVERITY_RANK.get((s or "").strip().lower(), 0)


def _check_new_contradictions(
    diff: RunDiff,
) -> list[RegressionAlert]:
    """Surface contradictions present in B but not in A.

    A new HIGH or CRITICAL severity contradiction is a HIGH alert.
    A new MEDIUM or LOW severity contradiction is a MEDIUM alert.
    Removed contradictions (resolved disagreement) do not surface
    as regressions — they're improvements.
    """
    alerts: list[RegressionAlert] = []
    for delta in diff.contradiction_deltas:
        if delta.direction != "added":
            continue
        sev_lc = (delta.severity or "").lower()
        if sev_lc in _HIGH_SEVERITY_KEYWORDS:
            alerts.append(
                RegressionAlert(
                    severity=AlertSeverity.HIGH,
                    code=AlertCode.NEW_HIGH_SEVERITY_CONTRADICTION,
                    message=(
                        f"new {delta.severity!r}-severity contradiction "
                        f"surfaced in this run on subject "
                        f"{delta.subject!r}, predicate "
                        f"{delta.predicate!r}; absent in baseline"
                    ),
                    a_value=None,
                    b_value=delta.severity,
                )
            )
        else:
            alerts.append(
                RegressionAlert(
                    severity=AlertSeverity.MEDIUM,
                    code=AlertCode.NEW_CONTRADICTION,
                    message=(
                        f"new contradiction surfaced on subject "
                        f"{delta.subject!r}, predicate "
                        f"{delta.predicate!r}; absent in baseline"
                    ),
                    a_value=None,
                    b_value=delta.severity,
                )
            )
    return alerts


def _check_contradiction_escalation(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """Codex M-18 v1 review fix: persistent contradictions whose
    severity escalates between runs (e.g. 'low' → 'high' on the
    same (subject, predicate) cluster) must alert.

    M-16's run_diff keys contradictions by (subject, predicate),
    so escalation produces no add/remove delta — both runs have
    the same key. Walk both IRs' contradictions and match by
    (subject, predicate); if rank_b > rank_a, alert.
    """
    alerts: list[RegressionAlert] = []
    a_by_key: dict[tuple[str, str], str] = {}
    for cluster in ir_a.contradictions:
        a_by_key[(cluster.subject, cluster.predicate)] = (
            cluster.severity or ""
        )
    for cluster in ir_b.contradictions:
        key = (cluster.subject, cluster.predicate)
        if key not in a_by_key:
            continue  # added cluster — handled by _check_new_contradictions
        a_sev = a_by_key[key]
        b_sev = cluster.severity or ""
        if _severity_rank(b_sev) <= _severity_rank(a_sev):
            continue  # same or lower severity — not an escalation
        # An escalation to high/critical/severe is HIGH; otherwise
        # MEDIUM. This mirrors the new-contradiction severity ladder.
        if (b_sev or "").lower() in _HIGH_SEVERITY_KEYWORDS:
            sev = AlertSeverity.HIGH
        else:
            sev = AlertSeverity.MEDIUM
        alerts.append(
            RegressionAlert(
                severity=sev,
                code=AlertCode.CONTRADICTION_SEVERITY_ESCALATION,
                message=(
                    f"contradiction on subject {cluster.subject!r}, "
                    f"predicate {cluster.predicate!r} escalated "
                    f"severity from {a_sev!r} (baseline) to "
                    f"{b_sev!r}; the same disagreement now matters more"
                ),
                a_value=a_sev,
                b_value=b_sev,
            )
        )
    return alerts


def _check_cost_spike(
    ir_a: AuditIR, ir_b: AuditIR,
) -> list[RegressionAlert]:
    """Per-run cost (USD) spike relative to baseline.

    Severity ladder:
      ratio >= 3.0 → HIGH
      ratio >= threshold (default 1.5) → MEDIUM
      else → no alert
    """
    alerts: list[RegressionAlert] = []
    a_cost = float(ir_a.manifest.cost_usd or 0.0)
    b_cost = float(ir_b.manifest.cost_usd or 0.0)
    if a_cost <= 0:
        # No baseline cost; skip to avoid divide-by-zero noise.
        return alerts
    ratio = b_cost / a_cost
    threshold = _cost_spike_ratio()
    if ratio >= 3.0:
        sev = AlertSeverity.HIGH
    elif ratio >= threshold:
        sev = AlertSeverity.MEDIUM
    else:
        return alerts
    alerts.append(
        RegressionAlert(
            severity=sev,
            code=AlertCode.COST_SPIKE,
            message=(
                f"per-run cost rose from ${a_cost:.4f} (baseline) to "
                f"${b_cost:.4f} ({ratio:.2f}x increase); investigate "
                f"whether quality improvement justifies the spend"
            ),
            a_value=round(a_cost, 4),
            b_value=round(b_cost, 4),
            threshold=threshold,
        )
    )
    return alerts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_regressions(
    ir_a: AuditIR,
    ir_b: AuditIR,
    *,
    diff: RunDiff | None = None,
) -> RegressionReport:
    """Compare a new run (`ir_b`) against a baseline (`ir_a`).

    Both runs MUST share the same slug — otherwise the comparison
    is meaningless and we raise ValueError, mirroring `diff_runs`.

    `diff` may be passed in if the caller has already computed it
    (e.g. the inspector endpoint computes diff + regression in
    sequence and shouldn't pay for diff twice). When None, this
    function computes it inline.
    """
    if ir_a.manifest.slug != ir_b.manifest.slug:
        raise ValueError(
            f"regression compare requires same slug; got "
            f"{ir_a.manifest.slug!r} (a) vs {ir_b.manifest.slug!r} (b)"
        )

    if diff is None:
        diff = diff_runs(ir_a, ir_b)
    else:
        # Codex M-18 v1 review fix: validate caller-supplied diff
        # matches the IRs they passed. A mismatched diff would
        # inject false contradiction alerts (or hide real ones)
        # without any signal that the wires were crossed.
        if diff.slug != ir_a.manifest.slug:
            raise ValueError(
                f"caller-supplied diff has slug {diff.slug!r}; "
                f"IRs have slug {ir_a.manifest.slug!r} — refusing "
                f"to use a mismatched diff"
            )
        if diff.a_run_id != ir_a.manifest.run_id:
            raise ValueError(
                f"caller-supplied diff a_run_id "
                f"{diff.a_run_id!r} does not match ir_a.run_id "
                f"{ir_a.manifest.run_id!r}"
            )
        if diff.b_run_id != ir_b.manifest.run_id:
            raise ValueError(
                f"caller-supplied diff b_run_id "
                f"{diff.b_run_id!r} does not match ir_b.run_id "
                f"{ir_b.manifest.run_id!r}"
            )

    alerts: list[RegressionAlert] = []
    alerts.extend(_check_release_flip(ir_a, ir_b))
    alerts.extend(_check_evaluator_gate(ir_a, ir_b))
    alerts.extend(_check_adequacy(ir_a, ir_b))
    alerts.extend(_check_verified_drop(ir_a, ir_b))
    alerts.extend(_check_citation_drop(ir_a, ir_b))
    alerts.extend(_check_tier_downgrade(ir_a, ir_b))
    alerts.extend(_check_new_contradictions(diff))
    alerts.extend(_check_contradiction_escalation(ir_a, ir_b))
    alerts.extend(_check_cost_spike(ir_a, ir_b))

    crit = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
    high = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
    med = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
    info = sum(1 for a in alerts if a.severity == AlertSeverity.INFO)

    if crit:
        worst = "critical"
    elif high:
        worst = "high"
    elif med:
        worst = "medium"
    elif info:
        worst = "info"
    else:
        worst = "ok"

    summary = RegressionReportSummary(
        critical_count=crit,
        high_count=high,
        medium_count=med,
        info_count=info,
        worst_severity=worst,
    )
    return RegressionReport(
        a_run_id=ir_a.manifest.run_id,
        b_run_id=ir_b.manifest.run_id,
        slug=ir_a.manifest.slug,
        alerts=tuple(alerts),
        summary=summary,
    )


def alert_to_dict(alert: RegressionAlert) -> dict[str, Any]:
    return {
        "severity": alert.severity.value,
        "code": alert.code.value,
        "message": alert.message,
        "a_value": alert.a_value,
        "b_value": alert.b_value,
        "threshold": alert.threshold,
    }


def report_to_dict(report: RegressionReport) -> dict[str, Any]:
    return {
        "a_run_id": report.a_run_id,
        "b_run_id": report.b_run_id,
        "slug": report.slug,
        "alerts": [alert_to_dict(a) for a in report.alerts],
        "summary": {
            "critical_count": report.summary.critical_count,
            "high_count": report.summary.high_count,
            "medium_count": report.summary.medium_count,
            "info_count": report.summary.info_count,
            "worst_severity": report.summary.worst_severity,
        },
    }
