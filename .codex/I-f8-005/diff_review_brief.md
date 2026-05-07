# Codex Diff Review — I-f8-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f8-005 — Guideline-vs-trial conflict type tag
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `01abb5399460a952a17a2632ae47023b837c92960355b68905951dc6de157bd1`
**LOC:** 130 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py            +14 (ContradictionEvidenceType + evidence_type field on Side)
tests/polaris_graph/generator2/test_verified_report.py     +25 (3 new tests)
web/lib/api.ts                                              +9 (ContradictionEvidenceType type + ?: field)
web/app/generation/components/contradiction_pane.tsx       +27 (EVIDENCE_TYPE_LABEL + per-side badge + skip-unspecified logic)
web/app/sentence_hover_test/_demo.tsx                      +37 (sec_x:29 with trial-vs-guideline)
web/tests/e2e/sentence_inspector_contradiction.spec.ts     +14 (evidence-type tag test)
```

## What changed

### Backend
- `ContradictionEvidenceType` Literal: 7 values (trial, guideline, meta_analysis, observational, regulatory_label, expert_opinion, unspecified).
- `ContradictionSide.evidence_type: ContradictionEvidenceType = "unspecified"` field added.
- 3 new tests: default + all-7 + bogus-rejected.
- 60 generator2/test_verified_report.py tests pass.

### Frontend
- `ContradictionEvidenceType` TS type + optional `evidence_type?:` on ContradictionSide.
- `EVIDENCE_TYPE_LABEL` map; pane renders evidence-type badge per side card BEFORE the tier badge. Skips render when type is "unspecified" (defensive `?? "unspecified"` per Codex iter-1 P2).
- Demo sec_x:29: trial-vs-guideline conflict (RCT efficacy + guideline insufficient evidence).
- Playwright test asserts both evidence-type tags visible.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 60 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Optional + skipped default:** unspecified renders no badge — existing I-f8-002 fixtures unaffected.
2. **Defensive coalesce per Codex iter-1 P2.**
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 130 net. Under 200.
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
