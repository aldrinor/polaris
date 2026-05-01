"""Replay a previously saved pin and emit a PinDiff.

Usage:
  python scripts/v6/replay_pin.py --original PATH --replay PATH [--json]

Loads two RunPin JSON files and prints the field-level diff (or full JSON
with --json). Exits 1 if the diff flags any regression, 0 otherwise. Used
by the Carney handover runbook §6 (backup + replay).

This script is the deterministic comparator — it does NOT regenerate the
replay pin. To regenerate a pin against new model weights, use
`scripts/v6/run_pin_replay.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from polaris_v6.replay.differ import compute_pin_diff
from polaris_v6.replay.schema import RunPin


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--original",
        type=Path,
        required=True,
        help="Path to the baseline RunPin JSON.",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        required=True,
        help="Path to the replay RunPin JSON (post regen against new model).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full PinDiff as JSON (default: human-readable summary).",
    )
    args = parser.parse_args()

    original = RunPin.model_validate_json(args.original.read_text(encoding="utf-8"))
    replay = RunPin.model_validate_json(args.replay.read_text(encoding="utf-8"))

    diff = compute_pin_diff(original, replay)

    if args.json:
        print(diff.model_dump_json(indent=2))
    else:
        print(f"original_pin_id: {diff.original_pin_id}")
        print(f"replay_pin_id:   {diff.replay_pin_id}")
        print(f"is_regression:   {diff.is_regression}")
        print(
            f"verified_sentence_count_delta: "
            f"{diff.verified_sentence_count_delta:+d}"
        )
        print(f"pipeline_status_changed: {diff.pipeline_status_changed}")
        print(
            f"evidence_pool: +{len(diff.evidence_pool_added)} added, "
            f"-{len(diff.evidence_pool_dropped)} dropped"
        )
        print(f"fields_changed: {len(diff.fields_changed)}")
        for field in diff.fields_changed:
            print(
                f"  [{field.severity}] {field.field}: "
                f"{field.original!r} -> {field.replay!r}"
            )

    return 1 if diff.is_regression else 0


if __name__ == "__main__":
    sys.exit(main())
