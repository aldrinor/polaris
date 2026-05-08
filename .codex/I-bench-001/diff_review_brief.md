# Codex Diff Review — I-bench-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight

- **Issue:** I-bench-001 — benchmark proof-package harness. Brief APPROVE iter 4.
- **Net LOC:** 198.
- **Branch:** `bot/I-bench-001`.

## What changed

1. `scripts/benchmark_proof_package.py` (NEW, ~95 LOC): module-level sys.path bootstrap; `_score_one` always emits all 6 v6 canonical dimensions; suite.score_dimensions filters composite; layer_3_evaluator_required normalized to False on output; UTF-8 file IO.
2. `tests/v6/benchmark/test_benchmark_proof_package.py` (NEW, 6 tests, all pass).

## Test results

```
$ pytest tests/v6/benchmark/test_benchmark_proof_package.py -q
6 passed in 2.70s
```

## Acceptance — forced enumeration

1. ✅ `scripts/benchmark_proof_package.py` exists.
2. ✅ End-to-end harness reads suite + responses, writes proof_package.json + summary.md.
3. ✅ Uses I-bug-084 score_response_coverage.
4. ✅ 6 tests pass.
5. ✅ CHARTER §3 LOC (198 ≤ 200).

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

## Diff (appended)
