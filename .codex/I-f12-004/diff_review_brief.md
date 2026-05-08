# Codex Diff Review — I-f12-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight

- **Issue:** I-f12-004 — jurisdictional diff. Brief APPROVE iter 1.
- **Net LOC:** 124.
- **Branch:** `bot/I-f12-004`.

## What changed

1. `src/polaris_v6/compare/jurisdictional_diff.py` (NEW, 53 LOC):
   - `JurisdictionalDiffPair` and `JurisdictionalDiffReport` frozen dataclasses.
   - `compute_jurisdictional_diff(contracts: dict[str, EvidenceContract])`:
     - Rejects `< 2` contracts and divergent `question` strings via `ValueError`.
     - `combinations(sorted(contracts), 2)` → pairwise `compute_claim_diff` calls.

2. `tests/v6/compare/test_jurisdictional_diff.py` (NEW, 71 LOC, 5 tests):
   - `two_jurisdictions_one_pair` (asserts actual `claim_diff` counts non-stub)
   - `three_jurisdictions_three_pairs`
   - `pairs_sorted_alphabetically_by_jurisdiction`
   - `question_mismatch_rejected`
   - `single_jurisdiction_rejected`

## Test results

```
$ pytest tests/v6/compare/ -q
14 passed in 1.05s   (5 new + 9 prior I-f12-003)
```

## Acceptance — forced enumeration

1. ✅ `jurisdictional_diff.py` with both dataclasses + `compute_jurisdictional_diff`.
2. ✅ Pairwise via `compute_claim_diff` (existing).
3. ✅ Question mismatch + single-jurisdiction → `ValueError`.
4. ✅ 5 tests pass.
5. ✅ CHARTER §3 LOC (124 ≤ 200).

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

## Diff (appended below)
