# Codex Brief Review — I-bench-001 (ITER 4 of 5)

## Iter 4 changes per Codex iter 3

- **P1 (BenchmarkScore.dimensions all 6):** harness ALWAYS emits all 6 v6 canonical dimensions in BenchmarkScore.dimensions (matches `min_length=6` in schema.py:62). Score selection: dimensions in `suite.score_dimensions` get computed scores; un-selected dimensions get `raw=0.0` with rationale `"not requested by suite"`. Composite averages only the selected dimensions.
- **P1 (layer_3 flag normalize):** harness writes `suite_doc["layer_3_evaluator_required"] = False` after `model_dump()` and before JSON write.
- **P2 (sys.path unguarded bootstrap):** module-level `sys.path.insert(0, ...)` before polaris_v6 imports — matches `scripts/v6/run_benchmark.py` pattern.
- **P2 (test fixture lock):** new `test_score_dimensions_always_six_with_filter` parametrizes a 4-dim suite + a 6-dim suite; asserts every BenchmarkScore.dimensions has length 6, asserts un-selected dims have raw=0.0 + rationale="not requested by suite", asserts proof_package.json's `suite.layer_3_evaluator_required == False`.

```
HARD ITERATION CAP: 5 per document. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight

- **Issue:** I-bench-001 — benchmark harness `scripts/benchmark_proof_package.py`. Acceptance: harness runs end-to-end. LOC estimate 200.

## Plan

### `scripts/benchmark_proof_package.py` (NEW, ~110 LOC)

```python
"""I-bench-001 — v6 benchmark proof-package harness.

Deterministic internal scoring per docs/benchmark/scoring_rubric.md.
Always emits all 6 v6 canonical dimensions; suite.score_dimensions
filters which ones contribute to the composite (others get raw=0.0).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polaris_v6.benchmark.schema import (
    BenchmarkScore, BenchmarkSuiteDesign, CompetingSystem, DimensionScore,
    ScoreDimension, SystemAnswer,
)
from polaris_v6.benchmark.coverage_scorer import score_response_coverage


_REFUSAL_MARKERS = ("i cannot", "i can't")
_ALL_DIMS: tuple[ScoreDimension, ...] = (
    "factual_accuracy", "citation_health", "frame_coverage",
    "contradiction_handling", "refusal_calibration", "user_traceability",
)


def _is_refusal(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def _compute_pool(q, response: str) -> dict[ScoreDimension, tuple[float, str]]:
    coverage = score_response_coverage(q, response)
    cit = response.lower().count("http")
    refused = _is_refusal(response)
    return {
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


def _score_one(q, sys_id: CompetingSystem, response: str,
               wanted_dims: list[ScoreDimension]) -> BenchmarkScore:
    pool = _compute_pool(q, response)
    selected = set(wanted_dims)
    dims: list[DimensionScore] = []
    for d in _ALL_DIMS:
        if d in selected:
            raw, rat = pool[d]
            dims.append(DimensionScore(dimension=d, raw=raw, rationale=rat))
        else:
            dims.append(DimensionScore(dimension=d, raw=0.0,
                                       rationale="not requested by suite"))
    selected_raws = [pool[d][0] for d in wanted_dims if d in pool]
    composite = sum(selected_raws) / max(1, len(selected_raws))
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

    suite = BenchmarkSuiteDesign.model_validate_json(args.suite_design.read_text())
    args.output.mkdir(parents=True, exist_ok=True)

    answers: list[SystemAnswer] = []
    scores: list[BenchmarkScore] = []
    for q in suite.questions:
        for sys_id in suite.competing_systems:
            f = args.responses_dir / f"{q.question_id}_{sys_id}.txt"
            text = f.read_text() if f.exists() else ""
            answers.append(SystemAnswer(
                question_id=q.question_id, system=sys_id,
                response_text=text, citations_count=text.lower().count("http"),
                refused=_is_refusal(text),
            ))
            scores.append(_score_one(q, sys_id, text, suite.score_dimensions))

    suite_doc = suite.model_dump()
    suite_doc["layer_3_evaluator_required"] = False  # canonical: internal deterministic
    proof = {
        "suite": suite_doc,
        "answers": [a.model_dump() for a in answers],
        "scores": [s.model_dump() for s in scores],
    }
    (args.output / "proof_package.json").write_text(json.dumps(proof, indent=2))
    (args.output / "summary.md").write_text(
        f"# Proof package\n\n- {len(suite.questions)} questions\n"
        f"- {len(suite.competing_systems)} systems\n- {len(scores)} scores\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Tests `tests/v6/benchmark/test_benchmark_proof_package.py` (NEW, ~70 LOC, 5 tests)

1. `test_harness_runs_end_to_end` (acceptance) — main() with 2 questions × 2 systems + 4 response files; assert proof_package.json + summary.md exist; re-validate.
2. `test_score_uses_coverage_scorer` — `expected_pico_keywords=["aspirin","migraine"]` matching response → factual_accuracy=1.0 in BenchmarkScore.dimensions.
3. `test_missing_response_file_yields_empty_answer` — no file → empty text + 0 citations.
4. `test_score_dimensions_always_six_with_filter` (parametrized 4-dim suite + 6-dim suite) — every BenchmarkScore.dimensions has length 6; un-selected dims have raw=0.0 + rationale "not requested by suite"; composite averages selected only.
5. `test_layer_3_evaluator_required_normalized_false` — proof_package.json's `suite.layer_3_evaluator_required` is False even when input suite had it True.

## Acceptance — forced enumeration

1. ✅ `scripts/benchmark_proof_package.py`.
2. ✅ End-to-end harness reads suite + responses, writes proof_package.json + summary.md.
3. ✅ Uses I-bug-084 score_response_coverage.
4. ✅ 5 tests (incl. all-six-dims + layer_3 normalize fixture).
5. ✅ CHARTER §3 LOC ≤ 200 (~180 net).

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
