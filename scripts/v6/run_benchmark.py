"""POLARIS v6 benchmark runner — Phase 3 Task 3.5 substrate.

Reads a benchmark question fixture file (BrowseComp / GAIA / DeepResearch
Bench JSON), maps each record through the appropriate adapter, then
either:

- (Phase 0/1, NO cluster) Emits a stub `BenchmarkSuiteDesign` JSON skeleton
  so the user can inspect the schema before running anything for real.
- (Phase 3, cluster live) Each adapted question is sent to the running
  POLARIS instance, the response is graded against expected answer,
  results aggregated into a `BenchmarkSuiteDesign`.

Phase 0 ships the dry-run mode only. Real execution requires a live
backend at `POLARIS_V6_BACKEND_URL`.

Usage:
    python scripts/v6/run_benchmark.py --suite browsecomp --input bc.jsonl --dry-run
    python scripts/v6/run_benchmark.py --suite gaia --input gaia.jsonl --backend http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[2] / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from polaris_v6.benchmark.industry_adapters import IndustryBenchmark, adapt
from polaris_v6.benchmark.schema import (
    BenchmarkQuestion,
    BenchmarkSuiteDesign,
    DifficultyLevel,
)


def _load_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def _difficulty_from_metadata(metadata: dict[str, str]) -> DifficultyLevel:
    raw = (metadata.get("difficulty") or metadata.get("level") or "").lower()
    if raw in {"3", "hard", "novel_synthesis", "novel"}:
        return "novel_synthesis"
    if raw in {"adversarial", "trick"}:
        return "adversarial"
    return "routine"


def build_suite_from_records(
    *,
    suite: IndustryBenchmark,
    records: list[dict],
) -> BenchmarkSuiteDesign:
    questions: list[BenchmarkQuestion] = []
    for raw in records:
        adapted = adapt(suite, raw)
        questions.append(
            BenchmarkQuestion(
                question_id=f"{suite}:{adapted.question_id}",
                template="canada_us"
                if "canada" in adapted.question_text.lower()
                else "clinical",
                text=adapted.question_text,
                difficulty=_difficulty_from_metadata(adapted.metadata),
                expected_anchors=[adapted.expected_answer]
                if adapted.expected_answer
                else [],
            )
        )
    return BenchmarkSuiteDesign(
        suite_version=f"v6_phase3_{suite}_v1",
        questions=questions,
        competing_systems=["polaris_v6", "chatgpt_5_5_pro_dr", "gemini_3_1_pro_dr"],
        score_dimensions=[
            "factual_accuracy",
            "citation_health",
            "frame_coverage",
            "contradiction_handling",
            "refusal_calibration",
            "user_traceability",
        ],
        layer_3_evaluator_required=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=["browsecomp", "gaia", "deepresearch_bench"],
        required=True,
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Benchmark question file (.json or .jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the BenchmarkSuiteDesign JSON. Defaults to stdout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the suite design only; do not call the backend.",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help="POLARIS backend URL. Required if not --dry-run; Phase 3 work.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 2

    records = _load_records(args.input)
    suite = build_suite_from_records(suite=args.suite, records=records)
    payload = suite.model_dump_json(indent=2)

    if not args.dry_run:
        if not args.backend:
            print(
                "ERROR: --backend is required for live benchmark runs. "
                "Phase 3 work; for Phase 0 use --dry-run.",
                file=sys.stderr,
            )
            return 3
        print(
            "WARN: live benchmark execution against backend is Phase 3 work. "
            "Emitting suite design only.",
            file=sys.stderr,
        )

    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        print(f"Wrote suite design to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
