# Codex Diff Review — I-f12-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-003 — Claim-level diff. Brief APPROVE iter 3.
- **Net LOC:** 200 (at cap).
- **Branch:** `bot/I-f12-003`.

## What changed

1. `src/polaris_v6/compare/claim_diff.py` (NEW, 108 LOC):
   - `ClaimVerdict` enum + `ClaimDiffEntry`/`ClaimDiffReport` dataclasses.
   - `compute_claim_diff(left, right)`: rejects same-run-id; per-section best-Jaccard pairing.
   - Filter `_shipped`: only `drop_reason is None AND verifier_local_pass AND verifier_global_pass` enter pairing.
   - Provenance parsing via regex `\[#ev:([^:\]]+):\d+-\d+\]` (any id format).
   - `_classify` 2-axis matrix (text-overlap × evidence-id-overlap).
2. `tests/v6/compare/__init__.py` + `tests/v6/compare/test_claim_diff.py` (8 tests):
   - agreement (high-overlap shared)
   - partial mid-overlap (parametrized: shared & disjoint evidence)
   - partial low-overlap shared evidence (no false disagreement)
   - disagreement low-overlap disjoint
   - only_left section missing right
   - counts aggregated multi-section
   - dropped sentences excluded + same-run-id rejected (combined)

## Test results

```
$ pytest tests/v6/compare/test_claim_diff.py -q
8 passed in 1.10s
```

## Risks for Codex Red-Team

1. **Threshold heuristic:** 0.7/0.3 documented MVP per F12 calibration debt.
2. **Best-greedy pairing:** within section, each left sentence pairs with highest-Jaccard remaining right sentence; non-optimal but deterministic.
3. **§9.4 hygiene:** module constants, no try/except: pass, no magic numbers, no time.sleep, no TODO.
4. **CHARTER §3 LOC:** 200 net (at cap).

## Acceptance criteria — forced enumeration

1. ✅ `claim_diff.py` with `ClaimVerdict`, `ClaimDiffEntry`, `ClaimDiffReport`, `compute_claim_diff`.
2. ✅ Token-Jaccard text overlap + provenance-id parsing (any id format).
3. ✅ Complete classification matrix; every paired claim classified.
4. ✅ 8 tests pass covering matrix + only_left + counts + drop filter + same-run guard.
5. ✅ CHARTER §3 LOC cap (200 ≤ 200).

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
