"""Aggregate per-run cost from EvidenceContract bundles.

Usage:
  python scripts/v6/cost_summary.py [--bundles-dir DIR] [--since YYYY-MM-DD]

Walks every .json under --bundles-dir (default: outputs/runs/), parses each
as an EvidenceContract, and prints sum/avg/min/max/p50/p95 of cost_usd
across the matching set. With --since, only includes bundles whose
finished_at is >= the given ISO date.

Used by the Carney handover runbook §5 (cost monitoring).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

from polaris_v6.schemas.evidence_contract import EvidenceContract


def _iter_bundle_paths(bundles_dir: Path) -> Iterable[Path]:
    if not bundles_dir.exists():
        return
    for path in sorted(bundles_dir.rglob("*.json")):
        if path.is_file():
            yield path


def _parse_since(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundles-dir",
        type=Path,
        default=Path("outputs/runs"),
        help="Directory containing EvidenceContract JSON bundles (recursive).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO date (YYYY-MM-DD) — only include bundles finished_at >= this.",
    )
    args = parser.parse_args()

    since = _parse_since(args.since)

    costs: list[float] = []
    skipped = 0
    for path in _iter_bundle_paths(args.bundles_dir):
        try:
            contract = EvidenceContract.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            skipped += 1
            continue
        if since is not None:
            try:
                finished = datetime.fromisoformat(
                    contract.finished_at.rstrip("Z")
                )
            except Exception:
                skipped += 1
                continue
            if finished < since:
                continue
        costs.append(float(contract.cost_usd))

    if not costs:
        print(
            f"no bundles matched in {args.bundles_dir.resolve()}"
            + (f" since {args.since}" if args.since else "")
            + (f" ({skipped} skipped)" if skipped else "")
        )
        return 1

    n = len(costs)
    print(f"bundles_dir: {args.bundles_dir.resolve()}")
    if since:
        print(f"since: {args.since}")
    print(f"matched_runs: {n}")
    print(f"sum_cost_usd: {sum(costs):.4f}")
    print(f"avg_cost_usd: {sum(costs) / n:.4f}")
    print(f"min_cost_usd: {min(costs):.4f}")
    print(f"max_cost_usd: {max(costs):.4f}")
    if n >= 2:
        print(f"p50_cost_usd: {statistics.median(costs):.4f}")
    if n >= 20:
        print(
            f"p95_cost_usd: {statistics.quantiles(costs, n=20)[-1]:.4f}"
        )
    if skipped:
        print(f"skipped_unparseable: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
