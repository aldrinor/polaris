# Codex Brief Review — I-f8-006 (ITER 1 of 5)

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

- **Context:** I-f8-006 — jurisdictional disagreement: regulators in different countries reach different conclusions (FDA approved, Health Canada not approved, EMA pending). Add `jurisdiction: Jurisdiction` field on `ContradictionSide` so the pane renders Canada/US/EU/UK tags. Closes F8 (last issue: 6/6).
- **Constraints:** Optional + default "unspecified" for back-compat.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `Jurisdiction` Literal: `canada | us | eu | uk | who | other | unspecified`.
   - Add `jurisdiction: Jurisdiction = "unspecified"` field on `ContradictionSide`.
2. Tests: 2 new tests (default + 7 values + bogus rejected).

### Frontend
3. `web/lib/api.ts`: add `Jurisdiction` type + optional `jurisdiction?: Jurisdiction` on `ContradictionSide`.
4. `web/app/generation/components/contradiction_pane.tsx`: add `JURISDICTION_LABEL` map; render jurisdiction badge on each side card next to evidence_type; skip rendering when "unspecified".
5. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:30 with sides where source A is `jurisdiction="us"` (FDA) and source B is `jurisdiction="canada"` (Health Canada).
6. `web/tests/e2e/sentence_inspector_contradiction.spec.ts`: add 1 test — sec_x:30 pane shows "United States" and "Canada" jurisdiction tags.

## Risks for Codex Red-Team
1. **Optional + skipped default:** existing fixtures unaffected.
2. **Honest substrate:** generator does NOT yet populate jurisdiction; demo only.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~100 LOC. Under 200.

## Acceptance criteria

1. `Jurisdiction` Literal with 7 values.
2. `jurisdiction: ... = "unspecified"` field.
3. 2 backend tests.
4. Frontend pane renders jurisdiction badge per side (skip "unspecified").
5. Demo + Playwright cover Canada-vs-US case.
6. CHARTER §1 LOC cap respected (≤200 net).
7. Honest substrate framing.

**Forced enumeration:** before verdict, write one line per criterion 1-7.

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
