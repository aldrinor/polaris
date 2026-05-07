# Codex Brief Review — I-f8-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan.

## Pre-flight

- **Context:** I-f8-004 — extend ContradictionSignal to label NON-NUMERIC contradictions: "is approved" vs "is not approved", "is safe" vs "is unsafe", binary categorical disagreements (vs the dose-response numeric kind from I-f8-001). Add `category: ContradictionCategory` enum: `numeric | categorical | regulatory | temporal | jurisdictional | other`.
- **Constraints:** Backward-compat: existing fixtures default `category="other"` so they keep passing.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `ContradictionCategory` Literal: 6 values.
   - Add `category: ContradictionCategory = "other"` field to `ContradictionSignal`.
2. Tests: 2 new tests — default == "other", all 6 values accepted, bogus rejected.

### Frontend
3. `web/lib/api.ts`: add `ContradictionCategory` type + optional `category?: ContradictionCategory` on `ContradictionSignal`.
4. `web/app/generation/components/contradiction_pane.tsx`: render category badge in pane header; `CATEGORY_LABEL` map.
5. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:28 with `category: "regulatory"` (FDA approved vs not-approved). Update sec_x:26 to set `category: "numeric"` and sec_x:27 to set `category: "categorical"` for variety.
6. `web/tests/e2e/sentence_inspector_contradiction.spec.ts`: add 1 test — sec_x:28 pane shows "Regulatory" category badge.

## Risks for Codex Red-Team
1. **Optional + defaulted:** existing payloads → "other" implicit; no fixture sweep needed.
2. **Honest substrate:** generator does NOT yet populate category; demo only.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~80 LOC. Under 200.

## Acceptance criteria

1. `ContradictionCategory` Literal with exactly 6 values.
2. `category: ContradictionCategory = "other"` field.
3. 2 backend tests cover default + all-6-acceptance + bogus-rejection.
4. Frontend renders category badge in pane.
5. Demo + Playwright cover regulatory category.
6. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-6.

**Completeness check:** list files actually read.

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

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
