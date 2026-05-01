"""Run regression lab — pair baseline pins with candidate pins and gate.

Usage:
  python scripts/v6/run_pin_replay.py \
      --baseline-dir tests/v6/fixtures/baseline_pins/ \
      --candidate-dir outputs/replay/<date>/

Loads every *.json under each directory as a RunPin, pairs by run_id,
runs the regression lab, prints a summary, and exits 1 if any regression
is detected. Used by the Carney handover runbook §3 (model rotation
gate) and by CI when new weights are swapped in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from polaris_v6.regression_lab.runner import run_regression_lab
from polaris_v6.replay.schema import RunPin


def _load_pins(d: Path) -> list[RunPin]:
    pins: list[RunPin] = []
    for path in sorted(d.glob("*.json")):
        if not path.is_file():
            continue
        pins.append(RunPin.model_validate_json(path.read_text(encoding="utf-8")))
    return pins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    args = parser.parse_args()

    if not args.baseline_dir.exists():
        print(f"baseline-dir does not exist: {args.baseline_dir}")
        return 2
    if not args.candidate_dir.exists():
        print(f"candidate-dir does not exist: {args.candidate_dir}")
        return 2

    baseline = _load_pins(args.baseline_dir)
    candidate = _load_pins(args.candidate_dir)

    if not baseline:
        print(f"no baseline pins found in {args.baseline_dir}")
        return 2

    report = run_regression_lab(baseline=baseline, candidate=candidate)

    print(f"baseline pins: {report.baseline_count}")
    print(f"candidate pins: {report.candidate_count}")
    print(f"matched pairs: {report.matched_count}")
    print(f"regressions: {len(report.regressions)}")
    print(f"warns: {len(report.warns)}")
    if report.unmatched_baseline_pin_ids:
        print(
            f"unmatched_baseline_pin_ids ({len(report.unmatched_baseline_pin_ids)}): "
            f"{report.unmatched_baseline_pin_ids}"
        )
    if report.unmatched_candidate_pin_ids:
        print(
            f"unmatched_candidate_pin_ids ({len(report.unmatched_candidate_pin_ids)}): "
            f"{report.unmatched_candidate_pin_ids}"
        )

    if report.regressions:
        print("\nREGRESSIONS:")
        for diff in report.regressions:
            print(
                f"  {diff.original_pin_id} -> {diff.replay_pin_id}: "
                f"{len(diff.fields_changed)} field(s) changed"
            )

    print(f"\nverdict: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
