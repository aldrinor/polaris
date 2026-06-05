"""M-D9 (Phase D): Regression lab — pin + induction diffing.

Per FINAL_PLAN M-D9 + Phase D milestone plan: continuous
integration of validation-set checks. Every code change runs
the validation set; regressions block merge.

This module ships **phase 1 — bootstrap**: pin-vs-pin
configuration drift + induction-precision drift. Phase 2
(BEAT-BOTH dimension scoring) is a separate module.

## What it diffs

Two `RegressionInputs` snapshots — `baseline` and `current`:
  - `pin: ModelPin` — captured via M-D11 phase 1
  - `induction_metrics: PrecisionMetrics` — captured via M-D1
    benchmark over a validation set
  - `manifest: dict | None` — optional pipeline manifest with
    abort_status, gate verdicts, etc.

For each input pair, computes a `RegressionReport`:
  - `pin_drift: tuple[PinDriftField, ...]` — every config field
    that changed (per-role models, env vars, retrieval versions,
    inductor profile, etc.)
  - `induction_drift: tuple[InductionDriftMetric, ...]` — every
    induction metric that moved beyond a tolerance (precision,
    recall, abstain-precision, abstain-recall, silent-disagreement)
  - `manifest_drift: tuple[ManifestDriftField, ...]` — pipeline
    verdict / gate flips (abort_status, release_allowed)
  - `verdict: GREEN | YELLOW | RED`:
    * GREEN: nothing drifted beyond tolerance
    * YELLOW: env/inductor drift, but induction precision flat
    * RED: induction precision regressed OR pipeline gate flipped

CI exit code maps from verdict (RED → non-zero, blocks merge).

## Why pin diff is necessary even with content diff

Two runs with the same content can have radically different
configurations (different model, prompts, gates) that happen to
produce the same output on this validation set but diverge
elsewhere. Pin diff surfaces silent configuration drift even
when content is stable.

## Tolerance defaults

Numeric metric tolerances are env-overridable per LAW VI.
Defaults are conservative-strict in the false-positive direction
(better to flag a borderline regression than miss it).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.polaris_graph.audit_ir.model_pin import (
    ModelPin,
    pins_equivalent_for_replay,
)
from src.polaris_graph.auto_induction.precision_metrics import (
    PrecisionMetrics,
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RegressionVerdict(Enum):
    """Top-level CI verdict.

    GREEN: nothing drifted beyond tolerance — merge OK.
    YELLOW: configuration drift but induction precision flat —
       operator should review but no hard block.
    RED: induction precision regressed OR pipeline gate flipped
       — merge blocked. CI exit code non-zero.
    """

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class InductionMetric(Enum):
    """Which induction metric moved (mirrors M-D1
    PrecisionMetrics properties)."""

    PRECISION = "precision"
    ABSTAIN_PRECISION = "abstain_precision"
    ABSTAIN_RECALL = "abstain_recall"
    SILENT_DISAGREEMENT_RATE = "silent_disagreement_rate"
    OPERATOR_REVIEW_LOAD = "operator_review_load"


class ManifestDrift(Enum):
    """Which manifest field flipped.

    Field names match the live `manifest.json` schema produced
    by `scripts/run_honest_sweep_r3.py:1785-1828`:
      - `status` (unified taxonomy: success / partial_* / abort_* / error_*)
      - `release_allowed` (evaluator gate verdict)
      - `adequacy.decision` ("proceed" / "expand" / "abort")
      - `generator.sentences_verified` (count of strict-verified sentences)
    """

    STATUS = "status"
    RELEASE_ALLOWED = "release_allowed"
    ADEQUACY_DECISION = "adequacy_decision"
    SENTENCES_VERIFIED_DROPPED_TO_ZERO = "sentences_verified_dropped_to_zero"


# ---------------------------------------------------------------------------
# Drift records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PinDriftField:
    """One configuration field that drifted between baseline + current."""

    field_name: str
    baseline_value: Any
    current_value: Any
    severity: str  # "config" | "env" | "schema"


@dataclass(frozen=True)
class InductionDriftMetric:
    """One induction metric that moved beyond tolerance."""

    metric: InductionMetric
    baseline_value: float
    current_value: float
    delta: float  # current - baseline (negative = regression for
    # most metrics; for silent_disagreement and operator_review,
    # positive = regression)
    tolerance: float
    is_regression: bool


@dataclass(frozen=True)
class ManifestDriftField:
    """One pipeline manifest field that flipped."""

    field: ManifestDrift
    baseline_value: Any
    current_value: Any
    is_regression: bool


# ---------------------------------------------------------------------------
# Inputs + report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegressionInputs:
    """One snapshot for regression diffing.

    `manifest` is an optional dict mirroring the polaris_graph
    pipeline's manifest.json (abort_status, release_allowed,
    sections_verified count, etc.). When None, manifest drift is
    not checked.
    """

    pin: ModelPin
    induction_metrics: PrecisionMetrics
    manifest: dict[str, Any] | None = None


@dataclass(frozen=True)
class RegressionReport:
    """Regression diff result.

    `verdict` is the top-level CI signal. The drift tuples carry
    the per-field detail for human review.
    """

    verdict: RegressionVerdict
    pin_drift: tuple[PinDriftField, ...] = field(default_factory=tuple)
    induction_drift: tuple[InductionDriftMetric, ...] = field(default_factory=tuple)
    manifest_drift: tuple[ManifestDriftField, ...] = field(default_factory=tuple)


class RegressionLabError(ValueError):
    """Raised on malformed input / configuration error."""


# ---------------------------------------------------------------------------
# Tolerance config (LAW VI — env-overridable)
# ---------------------------------------------------------------------------


def _precision_tolerance() -> float:
    """Max allowed drop in induction precision before flagging
    regression. Default: 0.02 (2 percentage points)."""
    raw = os.getenv("PG_REGRESSION_PRECISION_TOLERANCE", "0.02")
    try:
        val = float(raw)
    except ValueError as exc:
        raise RegressionLabError(
            f"PG_REGRESSION_PRECISION_TOLERANCE must be float, got {raw!r}"
        ) from exc
    if val < 0:
        raise RegressionLabError(
            f"PG_REGRESSION_PRECISION_TOLERANCE must be >=0, got {val}"
        )
    return val


def _recall_tolerance() -> float:
    """Max allowed drop in recall (incl. abstain_recall)."""
    raw = os.getenv("PG_REGRESSION_RECALL_TOLERANCE", "0.05")
    try:
        val = float(raw)
    except ValueError as exc:
        raise RegressionLabError(
            f"PG_REGRESSION_RECALL_TOLERANCE must be float, got {raw!r}"
        ) from exc
    if val < 0:
        raise RegressionLabError(
            f"PG_REGRESSION_RECALL_TOLERANCE must be >=0, got {val}"
        )
    return val


def _silent_disagreement_tolerance() -> float:
    """Max allowed RISE in silent-disagreement rate (more is bad)."""
    raw = os.getenv("PG_REGRESSION_SILENT_DISAGREEMENT_TOLERANCE", "0.02")
    try:
        val = float(raw)
    except ValueError as exc:
        raise RegressionLabError(
            f"PG_REGRESSION_SILENT_DISAGREEMENT_TOLERANCE must be float, "
            f"got {raw!r}"
        ) from exc
    if val < 0:
        raise RegressionLabError(
            f"PG_REGRESSION_SILENT_DISAGREEMENT_TOLERANCE must be >=0, "
            f"got {val}"
        )
    return val


def _operator_review_tolerance() -> float:
    """Max allowed RISE in operator-review load (more is worse UX)."""
    raw = os.getenv("PG_REGRESSION_OPERATOR_REVIEW_TOLERANCE", "0.10")
    try:
        val = float(raw)
    except ValueError as exc:
        raise RegressionLabError(
            f"PG_REGRESSION_OPERATOR_REVIEW_TOLERANCE must be float, "
            f"got {raw!r}"
        ) from exc
    if val < 0:
        raise RegressionLabError(
            f"PG_REGRESSION_OPERATOR_REVIEW_TOLERANCE must be >=0, "
            f"got {val}"
        )
    return val


# ---------------------------------------------------------------------------
# Pin diffing
# ---------------------------------------------------------------------------


def _diff_pin(
    baseline: ModelPin, current: ModelPin
) -> tuple[PinDriftField, ...]:
    """Return every per-field difference between two pins.

    Excludes metadata (run_id, captured_at, notes) — those are
    expected to differ between runs and aren't config.
    """
    drifts: list[PinDriftField] = []

    if baseline.pin_schema_version != current.pin_schema_version:
        drifts.append(
            PinDriftField(
                field_name="pin_schema_version",
                baseline_value=baseline.pin_schema_version,
                current_value=current.pin_schema_version,
                severity="schema",
            )
        )

    if baseline.llm_models != current.llm_models:
        drifts.append(
            PinDriftField(
                field_name="llm_models",
                baseline_value=dict(baseline.llm_models),
                current_value=dict(current.llm_models),
                severity="config",
            )
        )

    if baseline.llm_providers != current.llm_providers:
        drifts.append(
            PinDriftField(
                field_name="llm_providers",
                baseline_value=dict(baseline.llm_providers),
                current_value=dict(current.llm_providers),
                severity="config",
            )
        )

    if baseline.prompt_version_hashes != current.prompt_version_hashes:
        drifts.append(
            PinDriftField(
                field_name="prompt_version_hashes",
                baseline_value=dict(baseline.prompt_version_hashes),
                current_value=dict(current.prompt_version_hashes),
                severity="config",
            )
        )

    if baseline.retrieval_source_versions != current.retrieval_source_versions:
        drifts.append(
            PinDriftField(
                field_name="retrieval_source_versions",
                baseline_value=dict(baseline.retrieval_source_versions),
                current_value=dict(current.retrieval_source_versions),
                severity="config",
            )
        )

    if baseline.inductor_type != current.inductor_type:
        drifts.append(
            PinDriftField(
                field_name="inductor_type",
                baseline_value=baseline.inductor_type,
                current_value=current.inductor_type,
                severity="config",
            )
        )

    if baseline.inductor_version_hash != current.inductor_version_hash:
        drifts.append(
            PinDriftField(
                field_name="inductor_version_hash",
                baseline_value=baseline.inductor_version_hash,
                current_value=current.inductor_version_hash,
                severity="config",
            )
        )

    if baseline.validation_set_hash != current.validation_set_hash:
        # validation_set_hash is the IDENTITY of the benchmark
        # dataset. Once it changes, induction precision/recall
        # are no longer apples-to-apples — the gate must fail
        # closed. Severity "schema" forces a RED verdict in
        # diff_regression.
        drifts.append(
            PinDriftField(
                field_name="validation_set_hash",
                baseline_value=baseline.validation_set_hash,
                current_value=current.validation_set_hash,
                severity="schema",
            )
        )

    if baseline.env_snapshot != current.env_snapshot:
        # Per-key delta so reviewers don't have to diff two big
        # dicts.
        all_keys = set(baseline.env_snapshot) | set(current.env_snapshot)
        for key in sorted(all_keys):
            b_val = baseline.env_snapshot.get(key)
            c_val = current.env_snapshot.get(key)
            if b_val != c_val:
                drifts.append(
                    PinDriftField(
                        field_name=f"env_snapshot[{key}]",
                        baseline_value=b_val,
                        current_value=c_val,
                        severity="env",
                    )
                )

    return tuple(drifts)


# ---------------------------------------------------------------------------
# Induction-metric diffing
# ---------------------------------------------------------------------------


def _diff_induction(
    baseline: PrecisionMetrics, current: PrecisionMetrics
) -> tuple[InductionDriftMetric, ...]:
    """Return every induction metric that moved beyond tolerance.

    Direction-aware: for precision/recall/abstain-precision/
    abstain-recall, a DROP is regression. For silent-disagreement
    and operator-review-load, a RISE is regression.
    """
    drifts: list[InductionDriftMetric] = []

    prec_tol = _precision_tolerance()
    rec_tol = _recall_tolerance()
    sd_tol = _silent_disagreement_tolerance()
    or_tol = _operator_review_tolerance()

    # Precision: drop is regression.
    delta = current.precision - baseline.precision
    if abs(delta) > prec_tol:
        drifts.append(
            InductionDriftMetric(
                metric=InductionMetric.PRECISION,
                baseline_value=baseline.precision,
                current_value=current.precision,
                delta=delta,
                tolerance=prec_tol,
                is_regression=delta < -prec_tol,
            )
        )

    # Abstain precision: drop is regression.
    delta = current.abstain_precision - baseline.abstain_precision
    if abs(delta) > prec_tol:
        drifts.append(
            InductionDriftMetric(
                metric=InductionMetric.ABSTAIN_PRECISION,
                baseline_value=baseline.abstain_precision,
                current_value=current.abstain_precision,
                delta=delta,
                tolerance=prec_tol,
                is_regression=delta < -prec_tol,
            )
        )

    # Abstain recall: drop is regression.
    delta = current.abstain_recall - baseline.abstain_recall
    if abs(delta) > rec_tol:
        drifts.append(
            InductionDriftMetric(
                metric=InductionMetric.ABSTAIN_RECALL,
                baseline_value=baseline.abstain_recall,
                current_value=current.abstain_recall,
                delta=delta,
                tolerance=rec_tol,
                is_regression=delta < -rec_tol,
            )
        )

    # Silent disagreement: rise is regression.
    delta = (
        current.silent_disagreement_rate - baseline.silent_disagreement_rate
    )
    if abs(delta) > sd_tol:
        drifts.append(
            InductionDriftMetric(
                metric=InductionMetric.SILENT_DISAGREEMENT_RATE,
                baseline_value=baseline.silent_disagreement_rate,
                current_value=current.silent_disagreement_rate,
                delta=delta,
                tolerance=sd_tol,
                is_regression=delta > sd_tol,
            )
        )

    # Operator review load: rise is regression (worse UX).
    delta = current.operator_review_load - baseline.operator_review_load
    if abs(delta) > or_tol:
        drifts.append(
            InductionDriftMetric(
                metric=InductionMetric.OPERATOR_REVIEW_LOAD,
                baseline_value=baseline.operator_review_load,
                current_value=current.operator_review_load,
                delta=delta,
                tolerance=or_tol,
                is_regression=delta > or_tol,
            )
        )

    return tuple(drifts)


# ---------------------------------------------------------------------------
# Manifest diffing
# ---------------------------------------------------------------------------


def _diff_manifest(
    baseline: dict[str, Any] | None, current: dict[str, Any] | None
) -> tuple[ManifestDriftField, ...]:
    """Return every pipeline-verdict field that flipped.

    Reads the LIVE manifest schema produced by
    `scripts/run_honest_sweep_r3.py` (top-level `status`,
    `release_allowed`, nested `adequacy.decision` and
    `generator.sentences_verified`).

    If either input is None, returns empty tuple (manifest check
    skipped — the caller didn't supply pipeline output).
    """
    if baseline is None or current is None:
        return ()

    drifts: list[ManifestDriftField] = []

    # `status` is the unified pipeline taxonomy:
    # success / partial_* / abort_* / error_*. Regression =
    # going from "success" to anything else, OR going from any
    # partial_* to any abort_*/error_* (degradation within the
    # taxonomy).
    b_status = baseline.get("status")
    c_status = current.get("status")
    if b_status != c_status:
        is_regression = _status_is_regression(b_status, c_status)
        drifts.append(
            ManifestDriftField(
                field=ManifestDrift.STATUS,
                baseline_value=b_status,
                current_value=c_status,
                is_regression=is_regression,
            )
        )

    # release_allowed is the evaluator-gate verdict.
    b_release = baseline.get("release_allowed")
    c_release = current.get("release_allowed")
    if b_release != c_release:
        # Regression if went from True to False.
        is_regression = b_release is True and c_release is not True
        drifts.append(
            ManifestDriftField(
                field=ManifestDrift.RELEASE_ALLOWED,
                baseline_value=b_release,
                current_value=c_release,
                is_regression=is_regression,
            )
        )

    # adequacy.decision: "proceed" / "expand" / "abort".
    # Regression = proceed -> expand or proceed -> abort, OR
    # expand -> abort.
    b_adequacy = _nested_get(baseline, "adequacy", "decision")
    c_adequacy = _nested_get(current, "adequacy", "decision")
    if b_adequacy != c_adequacy:
        is_regression = _adequacy_is_regression(b_adequacy, c_adequacy)
        drifts.append(
            ManifestDriftField(
                field=ManifestDrift.ADEQUACY_DECISION,
                baseline_value=b_adequacy,
                current_value=c_adequacy,
                is_regression=is_regression,
            )
        )

    # generator.sentences_verified dropping to zero is a hard
    # regression even if status didn't flip.
    b_verified = _nested_get(baseline, "generator", "sentences_verified")
    c_verified = _nested_get(current, "generator", "sentences_verified")
    if (
        isinstance(b_verified, int)
        and isinstance(c_verified, int)
        and b_verified > 0
        and c_verified == 0
    ):
        drifts.append(
            ManifestDriftField(
                field=ManifestDrift.SENTENCES_VERIFIED_DROPPED_TO_ZERO,
                baseline_value=b_verified,
                current_value=c_verified,
                is_regression=True,
            )
        )

    return tuple(drifts)


# Closed taxonomy of unified pipeline statuses.
# **Source of truth**: `scripts/run_honest_sweep_r3.py:95-113`
# (`UNIFIED_STATUS_VALUES`). Mirrored here so regression_lab
# doesn't depend on scripts/ at import time. A taxonomy-drift
# test in `tests/polaris_graph/test_md9_regression_lab.py`
# asserts the two sets match — adding a new status to the
# runner without updating this list will fail that test.
#
# Tiers:
#   0 = success
#   1 = partial_*  (degraded but report produced)
#   2 = abort_*    (no report)
#   3 = error_*    (unhandled exception)
_STATUS_TIERS: dict[str, int] = {
    # success
    "success": 0,
    # partial — report produced but degraded signal
    "partial_thin_corpus": 1,
    "partial_incomplete_corpus": 1,
    "partial_rule_check_warnings": 1,
    "partial_outline_fallback": 1,
    "partial_evaluator_advisory": 1,
    "partial_qwen_advisory": 1,  # legacy alias (I-modref-004 #530)
    "partial_saturation": 1,  # I-meta-005 Phase 4 (#988): pruned partial report
    # abort — pipeline refused to produce a report
    "abort_scope_rejected": 2,
    "abort_no_sources": 2,
    "abort_corpus_inadequate": 2,
    "abort_corpus_approval_denied": 2,
    "abort_no_verified_sections": 2,
    "abort_evaluator_critical": 2,
    # I-meta-008 (#1015): PG_MAX_COST_PER_RUN breach mid-run (generator OR 4-role verifier) —
    # a clean budget abort, no report produced (tier 2), NOT an unhandled error.
    "abort_budget_exceeded": 2,
    # I-ready-002 (#1071): binding verifier degraded (judge_error_rate over cap) — release-blocking
    # abort, no report. Added to UNIFIED_STATUS_VALUES by #1071 but never mirrored here until #1086.
    "abort_verifier_degraded": 2,
    # I-ready-007 (#1072): input harm-refusal — explicit harm-intent query refused before retrieval
    # (no report produced, tier 2). KNOWN_STATUS_VALUES MUST equal runner.UNIFIED_STATUS_VALUES.
    "abort_safety_refused": 2,
    # I-ready-016 (#1086): mirror the two real terminal manifest statuses that were missing from the
    # taxonomy. KNOWN_STATUS_VALUES MUST equal runner.UNIFIED_STATUS_VALUES (test_saturation_phase4 +
    # test_md9_regression_lab). 4-role-held + user-cancel are terminal aborts (tier 2, no report).
    "abort_four_role_release_held": 2,
    "cancelled": 2,
    # error — unhandled exception
    "error_unexpected": 3,
}

# Public alias of the keys for taxonomy-drift testing.
KNOWN_STATUS_VALUES: frozenset[str] = frozenset(_STATUS_TIERS)


def _status_tier(status: object) -> int:
    """Return tier index for a known status, or -1 for unknown.

    Unknown values include typos, future taxonomy additions
    that haven't been mirrored here, and non-string inputs.
    They make `_status_is_regression` return True (fail
    closed) — better to flag a borderline case than miss a
    real regression.
    """
    if not isinstance(status, str):
        return -1
    return _STATUS_TIERS.get(status, -1)


def _status_is_regression(
    baseline: object, current: object
) -> bool:
    """A status flip is regression if current is in a worse tier
    than baseline. Within-tier flips (e.g.
    partial_thin_corpus -> partial_outline_fallback) are NOT
    regressions for the bootstrap gate."""
    b_tier = _status_tier(baseline)
    c_tier = _status_tier(current)
    if b_tier < 0 or c_tier < 0:
        # Unknown taxonomy values fail closed.
        return True
    return c_tier > b_tier


def _adequacy_is_regression(
    baseline: object, current: object
) -> bool:
    """Adequacy ordering: proceed (best) < expand < abort (worst)."""
    order = {"proceed": 0, "expand": 1, "abort": 2}
    if baseline not in order or current not in order:
        return True  # unknown values fail closed
    return order[current] > order[baseline]  # type: ignore[index]


def _nested_get(d: dict[str, Any] | None, *keys: str) -> Any:
    """Walk nested dict by key path; return None if any link
    is missing or non-dict."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# ---------------------------------------------------------------------------
# Top-level diff
# ---------------------------------------------------------------------------


def diff_regression(
    baseline: RegressionInputs, current: RegressionInputs
) -> RegressionReport:
    """Compute the full regression report.

    Verdict logic:
      RED if any induction metric is_regression=True OR any
        manifest field is_regression=True OR pin_schema_version
        differs.
      YELLOW if there's any pin/env/manifest drift but no
        regression flagged.
      GREEN otherwise.
    """
    pin_drift = _diff_pin(baseline.pin, current.pin)
    induction_drift = _diff_induction(
        baseline.induction_metrics, current.induction_metrics
    )
    manifest_drift = _diff_manifest(baseline.manifest, current.manifest)

    induction_regression = any(d.is_regression for d in induction_drift)
    manifest_regression = any(d.is_regression for d in manifest_drift)
    schema_regression = any(
        d.severity == "schema" for d in pin_drift
    )

    if induction_regression or manifest_regression or schema_regression:
        verdict = RegressionVerdict.RED
    elif pin_drift or induction_drift or manifest_drift:
        verdict = RegressionVerdict.YELLOW
    else:
        verdict = RegressionVerdict.GREEN

    return RegressionReport(
        verdict=verdict,
        pin_drift=pin_drift,
        induction_drift=induction_drift,
        manifest_drift=manifest_drift,
    )


def report_to_exit_code(report: RegressionReport) -> int:
    """Map a verdict to a CI exit code.

    GREEN → 0 (merge OK)
    YELLOW → 0 (configuration drift but no regression — operator
       review only, doesn't block CI)
    RED → 1 (regression detected — block merge)
    """
    if report.verdict is RegressionVerdict.RED:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Convenience: replay-equivalence shortcut
# ---------------------------------------------------------------------------


def pins_replay_equivalent(
    baseline: ModelPin, current: ModelPin
) -> bool:
    """Wrapper around `pins_equivalent_for_replay` for callers
    that import only this module."""
    return pins_equivalent_for_replay(baseline, current)
