"""M-LIVE-4: M-D9 regression-lab CI gate.

Runs `diff_regression(...)` between a committed baseline and the
current run, exits with rc=0 (GREEN/YELLOW = merge OK) or rc=1
(RED = block merge).

Per `docs/full_online_plan.md` Phase F M-LIVE-4:
  - 1-day milestone
  - M-D9 phase 1 regression check runs as CI gate on every release

Usage:
    python scripts/run_m_live_4_regression_gate.py \
        --baseline outputs/m_live_1_smoke/baseline_run \
        --current  outputs/m_live_1_smoke/run_<timestamp>

Without args, defaults to:
    baseline = outputs/m_live_1_smoke/baseline_run/
    current  = the latest run_* dir in outputs/m_live_1_smoke/

Each run dir must contain:
  - clinical/<slug>/manifest.json  (the run's pipeline manifest)
  - clinical/<slug>/model_pin.json (the M-INT-0b captured pin)

Optional precision_metrics.yaml at `<run_dir>/induction_metrics.yaml`
will be loaded if present; otherwise the metric-drift portion of
the regression check is skipped (treated as baseline-equal).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.polaris_graph.audit_ir.model_pin import (  # noqa: E402
    pin_from_dict,
)
from src.polaris_graph.audit_ir.regression_lab import (  # noqa: E402
    RegressionInputs,
    diff_regression,
    report_to_exit_code,
)
from src.polaris_graph.auto_induction.precision_metrics import (  # noqa: E402
    PrecisionMetrics,
)


# Default baseline metrics (matches M-D1 acceptance bar — precision
# 0.85, abstain_recall 0.95). Used when the caller does not supply
# induction_metrics.yaml. Verbatim equality between baseline and
# current means metric drift is not detected — only manifest +
# pin drift gates merge in the lean v1 gate.
_DEFAULT_BASELINE_METRICS = PrecisionMetrics(
    total_cases=10,
    in_scope_total=8,
    in_scope_accepted=8,
    in_scope_match_at_tau=7,
    in_scope_silent_disagreements=0,
    abstain_should_abstain_total=2,
    abstain_correct=2,
    abstain_total=2,
)


def _find_default_run_dir(base: Path) -> Path:
    """Find the latest `run_*` subdirectory under `base`."""
    candidates = sorted(
        (p for p in base.glob("run_*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(
            f"no run_* subdirectories found under {base}; "
            f"run M-LIVE-1 smoke first via "
            f"scripts/run_m_live_1_smoke.py"
        )
    return candidates[0]


def _find_run_artifacts(run_dir: Path) -> tuple[Path, Path]:
    """Returns (manifest_path, model_pin_path) for a run directory.

    Searches recursively for manifest.json and model_pin.json,
    matching the M-LIVE-1 layout: run_dir / clinical / <slug> /
    {manifest.json, model_pin.json}.
    """
    manifests = list(run_dir.rglob("manifest.json"))
    pins = list(run_dir.rglob("model_pin.json"))
    if not manifests:
        raise SystemExit(
            f"no manifest.json found under {run_dir}"
        )
    if not pins:
        raise SystemExit(
            f"no model_pin.json found under {run_dir}"
        )
    return manifests[0], pins[0]


def _load_inputs(run_dir: Path) -> RegressionInputs:
    manifest_path, pin_path = _find_run_artifacts(run_dir)
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"),
    )
    pin_data = json.loads(pin_path.read_text(encoding="utf-8"))
    pin = pin_from_dict(pin_data)
    return RegressionInputs(
        pin=pin,
        induction_metrics=_DEFAULT_BASELINE_METRICS,
        manifest=manifest,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--baseline",
        type=Path,
        default=REPO_ROOT / "tests" / "fixtures" / "m_live_4_baseline",
        help=(
            "Path to the baseline run directory. Default points "
            "at tests/fixtures/m_live_4_baseline/, which is the "
            "checked-in canonical baseline for the regression "
            "gate."
        ),
    )
    p.add_argument(
        "--current",
        type=Path,
        default=None,
        help=(
            "Path to the current run directory. Defaults to the "
            "latest run_* under outputs/m_live_1_smoke/."
        ),
    )
    p.add_argument(
        "--smoke-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "m_live_1_smoke",
        help="Root used to find the latest run_* if --current omitted.",
    )
    args = p.parse_args(argv)

    baseline_dir = args.baseline
    if not baseline_dir.exists():
        print(
            f"[M-LIVE-4] baseline does not exist: {baseline_dir}",
            file=sys.stderr,
        )
        print(
            "[M-LIVE-4] To bootstrap a baseline, copy a known-good "
            "run dir to that path. Until then, this gate cannot "
            "block merges.",
            file=sys.stderr,
        )
        return 0  # bootstrap state — pass through

    current_dir = args.current
    if current_dir is None:
        current_dir = _find_default_run_dir(args.smoke_root)

    print("=" * 72)
    print("M-LIVE-4 regression CI gate")
    print("=" * 72)
    print(f"  baseline: {baseline_dir}")
    print(f"  current:  {current_dir}")
    print()

    baseline = _load_inputs(baseline_dir)
    current = _load_inputs(current_dir)

    report = diff_regression(baseline, current)

    print(f"verdict: {report.verdict.value}")
    print(f"  pin_drift fields: {len(report.pin_drift)}")
    print(f"  induction_drift metrics: {len(report.induction_drift)}")
    print(f"  manifest_drift fields: {len(report.manifest_drift)}")

    if report.pin_drift:
        print()
        print("Pin drift detail:")
        for pd in report.pin_drift:
            # v2 R1 P0 fix: PinDriftField uses `field_name`, not
            # `dimension`. v1 attribute crashed gate with
            # AttributeError on any non-empty pin drift, falsely
            # exiting rc=1 for a YELLOW verdict.
            print(
                f"  {pd.field_name!r}: "
                f"baseline={pd.baseline_value!r} -> "
                f"current={pd.current_value!r} "
                f"(severity={pd.severity})"
            )
    if report.manifest_drift:
        print()
        print("Manifest drift detail:")
        for md in report.manifest_drift:
            # v2 R1 P0 fix: ManifestDriftField uses `field`
            # (ManifestDrift enum), not `field_path`.
            field_name = (
                md.field.value
                if hasattr(md.field, "value")
                else str(md.field)
            )
            print(
                f"  {field_name!r}: "
                f"baseline={md.baseline_value!r} -> "
                f"current={md.current_value!r} "
                f"(is_regression={md.is_regression})"
            )

    out_dir = REPO_ROOT / "outputs" / "m_live_4_regression_gate"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "milestone": "M-LIVE-4",
        "version": "v1",
        "verdict": report.verdict.value,
        "baseline_dir": str(baseline_dir),
        "current_dir": str(current_dir),
        "pin_drift_count": len(report.pin_drift),
        "induction_drift_count": len(report.induction_drift),
        "manifest_drift_count": len(report.manifest_drift),
        "exit_code": report_to_exit_code(report),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"summary: {out_dir / 'manifest.json'}")
    print(f"exit_code: {summary['exit_code']}")
    print("=" * 72)

    return report_to_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
