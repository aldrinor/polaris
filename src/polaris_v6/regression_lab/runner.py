"""Regression lab runner — fail CI if any pin in a baseline set regresses."""

from __future__ import annotations

from dataclasses import dataclass

from polaris_v6.replay.differ import compute_pin_diff
from polaris_v6.replay.schema import PinDiff, RunPin


@dataclass
class RegressionLabReport:
    baseline_count: int
    candidate_count: int
    matched_count: int
    regressions: list[PinDiff]
    warns: list[PinDiff]
    unmatched_baseline_pin_ids: list[str]
    unmatched_candidate_pin_ids: list[str]
    passed: bool


def run_regression_lab(
    *,
    baseline: list[RunPin],
    candidate: list[RunPin],
) -> RegressionLabReport:
    """Pair pins by run_id and emit a verdict.

    A pin pair is two RunPins with the same `run_id` (one from baseline,
    one from candidate replay). A baseline run_id without a candidate
    pair lands in `unmatched_baseline_pin_ids` (CI: WARN). A candidate
    run_id without a baseline lands in `unmatched_candidate_pin_ids`
    (CI: WARN, likely a new test). Any matched pair with
    `is_regression=True` lands in `regressions` (CI: FAIL).
    """
    baseline_by_run = {p.run_id: p for p in baseline}
    candidate_by_run = {p.run_id: p for p in candidate}

    regressions: list[PinDiff] = []
    warns: list[PinDiff] = []
    matched = 0

    for run_id, base_pin in baseline_by_run.items():
        cand_pin = candidate_by_run.get(run_id)
        if cand_pin is None:
            continue
        diff = compute_pin_diff(base_pin, cand_pin)
        matched += 1
        if diff.is_regression:
            regressions.append(diff)
        elif diff.fields_changed:
            warns.append(diff)

    unmatched_base = sorted(set(baseline_by_run) - set(candidate_by_run))
    unmatched_cand = sorted(set(candidate_by_run) - set(baseline_by_run))

    return RegressionLabReport(
        baseline_count=len(baseline),
        candidate_count=len(candidate),
        matched_count=matched,
        regressions=regressions,
        warns=warns,
        unmatched_baseline_pin_ids=unmatched_base,
        unmatched_candidate_pin_ids=unmatched_cand,
        passed=len(regressions) == 0,
    )


def format_ci_summary(report: RegressionLabReport) -> str:
    lines = [
        f"Regression lab: matched {report.matched_count}/{report.baseline_count} baselines",
        f"  Regressions: {len(report.regressions)}",
        f"  Warns:       {len(report.warns)}",
    ]
    if report.unmatched_baseline_pin_ids:
        lines.append(
            f"  Unmatched baselines (no candidate): {report.unmatched_baseline_pin_ids}"
        )
    if report.unmatched_candidate_pin_ids:
        lines.append(
            f"  New candidates (no baseline): {report.unmatched_candidate_pin_ids}"
        )
    if report.regressions:
        lines.append("  REGRESSION DETAILS:")
        for diff in report.regressions:
            for field in diff.fields_changed:
                if field.severity == "regression":
                    lines.append(
                        f"    {diff.original_pin_id} → {diff.replay_pin_id}: "
                        f"{field.field} {field.original!r} → {field.replay!r}"
                    )
    lines.append(
        f"  VERDICT: {'PASS — ship' if report.passed else 'FAIL — block merge'}"
    )
    return "\n".join(lines)
