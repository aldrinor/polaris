# Codex Diff Review — I-cj-006 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-006 — Budget cap Crown Jewel test. Brief APPROVE'd iter 1 (zero P0/P1/P2).
- **Diff under review:** `.codex/I-cj-006/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/test_cj_006_budget_imputation.py` (~75 LOC, 6 tests)
  - MODIFY `docs/crown_jewels.md` (~1-row change)

## Acceptance criteria

1. ✅ 6 tests cover known-model+positive / unknown-fallback / zero / negative-clamp / reasoning-rate / empty-model.
2. ✅ Registry doc row 6 updated.
3. ✅ All 6 tests pass locally.
4. ✅ ~75 LOC under 200.

## Red-team checklist

1. **Negative-clamp tooth** — test 4 is THE critical Crown Jewel binding: corrupted -5M tokens MUST yield 0.0, not negative cost.
2. **Loose-bound assertions** — test 2 uses `17 < cost < 19`, test 6 uses `2.5 < cost < 3.5` so future re-pricing of `_DEFAULT_PRICE_PER_M` won't break the binding while still catching a regression that zeros out the fallback.
3. **§9.4 hygiene** — clean.
4. **CHARTER §3 LOC cap** — under 200.

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
