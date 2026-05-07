# Codex Diff Review — I-f8-006 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f8-006 — Jurisdictional disagreement display (closes F8: 6/6 issues)
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `164ef7b72dc03236c61964a7886885f9aa39cbea4e82bbb9ec0bdd39f2255775`
**LOC:** 114 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py            +16 (Jurisdiction Literal + jurisdiction field)
tests/polaris_graph/generator2/test_verified_report.py     +16 (3 new tests)
web/lib/api.ts                                              +11 (Jurisdiction type + ?: field)
web/app/generation/components/contradiction_pane.tsx       +25 (JURISDICTION_LABEL + per-side badge with skip-unspecified)
web/app/sentence_hover_test/_demo.tsx                      +37 (sec_x:30 FDA-vs-Health-Canada)
web/tests/e2e/sentence_inspector_contradiction.spec.ts     +14 (US/Canada jurisdiction tag test)
```

## What changed

### Backend
- `Jurisdiction` Literal: 7 values (canada, us, eu, uk, who, other, unspecified).
- `ContradictionSide.jurisdiction: Jurisdiction = "unspecified"` field added.
- 3 new tests: default + all-7 + bogus-rejected.
- 63 generator2/test_verified_report.py tests pass.

### Frontend
- `Jurisdiction` TS type + optional `jurisdiction?:` on ContradictionSide.
- `JURISDICTION_LABEL` map; pane renders jurisdiction badge after evidence-type, before tier badge. Skips render when "unspecified" (defensive `?? "unspecified"`).
- Demo sec_x:30: FDA-approved (US) vs Health-Canada-not-approved.
- Playwright test asserts both jurisdiction tags visible.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 63 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Optional + skip-default:** existing fixtures unaffected.
2. **F8 closed:** 6/6 issues shipped (001-006).
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 114 net. Under 200.
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
