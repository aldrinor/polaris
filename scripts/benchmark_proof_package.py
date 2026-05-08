"""I-bench-001 — v6 benchmark proof-package harness. Deterministic internal scoring per docs/benchmark/scoring_rubric.md. Always emits all 6 v6 canonical dimensions; suite.score_dimensions filters composite (others get raw=0.0)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from polaris_v6.benchmark.coverage_scorer import score_response_coverage
from polaris_v6.benchmark.schema import (
    BenchmarkScore, BenchmarkSuiteDesign, CompetingSystem, DimensionScore,
    ScoreDimension, SystemAnswer,
)


_REFUSAL = ("i cannot", "i can't")
_ALL_DIMS: tuple[ScoreDimension, ...] = (
    "factual_accuracy", "citation_health", "frame_coverage",
    "contradiction_handling", "refusal_calibration", "user_traceability",
)


def _is_refusal(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _REFUSAL)


def _score_one(q, sys_id: CompetingSystem, response: str,
               wanted: list[ScoreDimension]) -> BenchmarkScore:
    coverage = score_response_coverage(q, response)
    cit = response.lower().count("http")
    refused = _is_refusal(response)
    pool: dict[ScoreDimension, tuple[float, str]] = {
        "factual_accuracy": (coverage, f"coverage={coverage:.2f}"),
        "citation_health": (min(1.0, cit / 5), f"{cit} citations"),
        "frame_coverage": (coverage, "internal deterministic"),
        "contradiction_handling": (0.5, "internal deterministic"),
        "refusal_calibration": (
            1.0 if refused == bool(q.expected_refusals) else 0.5,
            f"refused={refused} expected={bool(q.expected_refusals)}",
        ),
        "user_traceability": (min(1.0, cit / 3), f"{cit} cites"),
    }
    sel = set(wanted)
    dims = [
        DimensionScore(dimension=d, raw=pool[d][0], rationale=pool[d][1])
        if d in sel
        else DimensionScore(dimension=d, raw=0.0, rationale="not requested by suite")
        for d in _ALL_DIMS
    ]
    raws = [pool[d][0] for d in wanted if d in pool]
    composite = sum(raws) / max(1, len(raws))
    return BenchmarkScore(
        question_id=q.question_id, system=sys_id, dimensions=dims,
        composite=composite, scored_by="automated",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--suite-design", required=True, type=Path)
    p.add_argument("--responses-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)

    suite = BenchmarkSuiteDesign.model_validate_json(
        args.suite_design.read_text(encoding="utf-8")
    )
    args.output.mkdir(parents=True, exist_ok=True)

    answers, scores = [], []
    for q in suite.questions:
        for sys_id in suite.competing_systems:
            f = args.responses_dir / f"{q.question_id}_{sys_id}.txt"
            text = f.read_text(encoding="utf-8") if f.exists() else ""
            answers.append(SystemAnswer(
                question_id=q.question_id, system=sys_id, response_text=text,
                citations_count=text.lower().count("http"), refused=_is_refusal(text),
            ))
            scores.append(_score_one(q, sys_id, text, suite.score_dimensions))

    suite_doc = suite.model_dump()
    suite_doc["layer_3_evaluator_required"] = False
    proof = {
        "suite": suite_doc,
        "answers": [a.model_dump() for a in answers],
        "scores": [s.model_dump() for s in scores],
    }
    (args.output / "proof_package.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )
    (args.output / "summary.md").write_text(
        f"# Proof package\n\n- {len(suite.questions)} questions\n"
        f"- {len(suite.competing_systems)} systems\n- {len(scores)} scores\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
