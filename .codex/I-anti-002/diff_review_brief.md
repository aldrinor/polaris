# Codex Diff Review — I-anti-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight
- **Issue:** I-anti-002. Brief APPROVE iter 2.
- **Net LOC:** 174.
- **Branch:** `bot/I-anti-002`.

## What changed
1. `src/polaris_graph/anti_sycophancy/stance_delta.py` (NEW): `classify_stance` + `compute_stance_delta` with framing-set validation.
2. `tests/polaris_graph/anti_sycophancy/test_stance_delta.py` (NEW, 9 tests).

## Test results
```
$ pytest tests/polaris_graph/anti_sycophancy/test_stance_delta.py -q
9 passed
```

## Acceptance — forced enumeration
1. ✅ stance_delta.py with all required types/functions.
2. ✅ 5-label classifier.
3. ✅ stance_delta_score = shifts / 6.
4. ✅ 9 tests pass; corpus loop covers all 20 I-anti-001 entries.
5. ✅ CHARTER §3 LOC (174 ≤ 200).

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
