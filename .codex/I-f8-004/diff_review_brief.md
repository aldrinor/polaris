# Codex Diff Review — I-f8-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f8-004 — Non-numeric contradictions (regulatory/categorical etc.)
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `2b7fca5d74b6c3feba8be03a8eb4b5dcd970c4f348fa3fbc999d6481fb099809`
**LOC:** 122 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py            +14 (ContradictionCategory + category field)
tests/polaris_graph/generator2/test_verified_report.py     +30 (3 new tests)
web/lib/api.ts                                              +8 (ContradictionCategory + category? field)
web/app/generation/components/contradiction_pane.tsx       +18 (CATEGORY_LABEL + badge in pane description)
web/app/sentence_hover_test/_demo.tsx                      +33 (sec_x:28 regulatory + categories on existing fixtures)
web/tests/e2e/sentence_inspector_contradiction.spec.ts     +20 (regulatory category test)
```

## What changed

### Backend
- `ContradictionCategory` Literal: 6 values (numeric, categorical, regulatory, temporal, jurisdictional, other).
- `category: ContradictionCategory = "other"` field added to ContradictionSignal.
- 3 new tests: default "other", all 6 values accepted, bogus rejected.
- 57 generator2/test_verified_report.py tests pass.

### Frontend
- `ContradictionCategory` TS type + optional `category?: ContradictionCategory`.
- `CATEGORY_LABEL` map; pane description renders category badge with defensive `?? "other"` per Codex iter-1 P2.
- Demo: sec_x:26 → "numeric", sec_x:27 → "categorical", new sec_x:28 → "regulatory" (FDA approved vs not).
- Playwright test asserts "Regulatory" badge + claim-0/1 text.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 57 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Optional + defaulted:** existing fixtures default to "other"; no fixture sweep needed. Updated I-f8-001/002/003 demos to label categories for variety, NOT for back-compat.
2. **Defensive normalize:** `signal.category ?? "other"` per Codex iter-1 P2.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 122 net. Under 200.
5. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
