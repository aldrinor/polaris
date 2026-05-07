# Codex Brief Review — I-f9-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Context:** I-f9-003 — boundary tests for the two-family disagreement signal (closes F9: 3/3). Verify UI handles two edges:
  - **0% disagreement (all agree):** every kept sentence has `evaluator_agrees=true`. Zero `evaluator-flag-*` badges should render.
  - **100% disagreement (all flagged):** every kept sentence has `evaluator_agrees=false` + `evaluator_disagreement` payload. Every kept sentence row shows the badge AND every badge opens a working pane.
- **Constraints:** Test-only Issue. Reuses I-f5-008 stress harness pattern with new `?disagree=all|none` query param. No backend / production code changes.
- **Done-when:** acceptance criteria 1-5 below.

## Plan

### Frontend test harness
1. `web/app/sentence_hover_test/_demo_evaluator_edge.tsx` (new): `EvaluatorEdgeHarness({ mode }: { mode: "all" | "none" })`. Builds a synthetic VerifiedReport with N=12 kept sentences:
   - mode="none" → all `evaluator_agrees=true`, no `evaluator_disagreement`.
   - mode="all" → all `evaluator_agrees=false` with full payload.
2. `web/app/sentence_hover_test/evaluator_edge/page.tsx` (new): Next route reading `?mode=all|none` from search params. Defaults to "none". Validates against the literal set.

### Playwright spec
3. `web/tests/e2e/sentence_inspector_evaluator_edge.spec.ts` (new): 3 tests:
   - mode=none → assert ZERO `evaluator-flag-sec_x:*` badges across 12 rows (`getByTestId(/^evaluator-flag-/)` count == 0).
   - mode=all → assert TWELVE flagged rows (count == 12).
   - mode=all → click first flagged row's badge → assert EvaluatorPane opens with both readings.

## Risks for Codex Red-Team
1. **Mode union literal:** TypeScript-narrow `mode: "all" | "none"` rejects bogus search-param values; default to "none".
2. **Demo back-compat:** new harness lives at separate route; existing `/sentence_hover_test` demo unchanged.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~120 LOC. Under 200.

## Acceptance criteria

1. Harness component + Next route both exist; `?mode=` parsed against literal set.
2. mode=none renders 12 rows, zero evaluator-flag badges.
3. mode=all renders 12 rows, twelve evaluator-flag badges.
4. Click first badge in mode=all → pane opens with generator + evaluator readings.
5. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-5.

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
