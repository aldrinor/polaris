"""Seed a demo benchmark artifact for the /benchmark UI.

Wraps `scripts/run_benchmark.py --skip-polaris` against
`config/benchmark/clinical_n10.json` with no external outputs, producing a
reproducible scoreboard.json + summary.md + report.html under the output
directory.

This is the artifact that the /benchmark page renders on first visit when
`POLARIS_BENCHMARK_RESULTS_DIR` points at the parent dir.

Usage:
    python scripts/seed_demo_benchmark.py \
        --output outputs/demo_benchmark/clinical_n10_demo

For a real (billed) BEAT-BOTH demo, use `run_benchmark.py` directly without
`--skip-polaris`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import run_benchmark  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "benchmark" / "clinical_n10.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed a demo BEAT-BOTH artifact (skip-polaris, no externals)"
    )
    p.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help=f"Benchmark config (default: {_DEFAULT_CONFIG.relative_to(_REPO_ROOT)})",
    )
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for scoreboard.json + summary.md + report.html",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.config.is_file():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    rc = run_benchmark.main(
        [
            "--config", str(args.config),
            "--output", str(args.output),
            "--skip-polaris",
        ]
    )
    if rc != 0:
        return rc
    sb = args.output / "scoreboard.json"
    summary = args.output / "summary.md"
    report = args.output / "report.html"
    missing = [p.name for p in (sb, summary, report) if not p.is_file()]
    if missing:
        print(
            f"ERROR: seed run completed but missing artifacts: {missing}",
            file=sys.stderr,
        )
        return 3
    print(f"Demo artifact seeded at: {args.output}")
    print(f"  scoreboard.json: {sb.stat().st_size} bytes")
    print(f"  summary.md:      {summary.stat().st_size} bytes")
    print(f"  report.html:     {report.stat().st_size} bytes")
    print("")
    print("To wire into the /benchmark UI:")
    print(
        f"  export POLARIS_BENCHMARK_RESULTS_DIR={args.output.resolve().parent}"
    )
    print("  (then reboot uvicorn so create_app() picks up the env var)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
