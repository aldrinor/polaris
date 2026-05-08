# Codex Diff Review — I-bug-084 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight

- **Issue:** I-bug-084 — coverage scorer keywords. Brief APPROVE iter 1.
- **Net LOC:** 74.
- **Branch:** `bot/I-bug-084`.

## What changed

1. `src/polaris_v6/benchmark/schema.py` (+5 LOC): added `expected_pico_keywords: list[str] = Field(default_factory=list, ...)` to `BenchmarkQuestion`.
2. `src/polaris_v6/benchmark/coverage_scorer.py` (NEW, ~17 LOC): `score_response_coverage(question, response_text)` returns 1.0 if all targets present (case-insensitive substring), else 0.0; targets are keywords if non-empty else anchors; empty both → 0.0.
3. `tests/v6/benchmark/test_coverage_scorer.py` (NEW, 5 tests, all pass).

## Test results

```
5 passed in 1.30s
```

## Acceptance — forced enumeration

1. ✅ `expected_pico_keywords` field added.
2. ✅ `score_response_coverage` implemented.
3. ✅ Keywords preferred over anchors when set.
4. ✅ aspirin/migraine acceptance test passes; fallback tests pass.
5. ✅ CHARTER §3 LOC (74 ≤ 200).

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
