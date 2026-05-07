# Codex Diff Review — I-f9-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only. DO NOT spawn dev servers / Playwright runs (sandbox blocks them per CLAUDE.md §8.4).

**Issue:** I-f9-003 — F9 edge: no disagreements / all disagreements (closes F9: 3/3)
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `5593a0688b247efcc0079939bc79e9bb6941818027cdb18dac5c56e43ef246d5`
**LOC:** 153 net (under CHARTER §1 200-cap)

## Files

```
web/app/sentence_hover_test/_demo_evaluator_edge.tsx   NEW +106 (EvaluatorEdgeHarness, 12 rows, mode=all|none)
web/app/sentence_hover_test/evaluator_edge/page.tsx    NEW +12 (Next route reading ?mode=)
web/tests/e2e/sentence_inspector_evaluator_edge.spec.ts NEW +35 (3 tests: none-zero, all-twelve, click-opens-pane)
```

## What changed

### Test harness
- `EvaluatorEdgeHarness({mode})` builds 12 kept sentences. mode=none → all `evaluator_agrees=true`. mode=all → all flagged with full `evaluator_disagreement` payload.
- Route validates mode against `"all"|"none"` literal set; default "none". Invalid values fall back to "none".

### Playwright
- Test 1 (mode=none): `kept-sentence` count == 12 (Codex iter-1 P2 explicit count check), `[data-testid^="evaluator-flag-"]` count == 0.
- Test 2 (mode=all): `kept-sentence` count == 12, evaluator-flag count == 12.
- Test 3 (mode=all click): badge opens EvaluatorPane with generator + evaluator readings.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- No backend changes.

## Risks for Codex Red-Team

1. **Mode literal narrowing:** unknown `?mode=` values fall back to "none" — same defensive pattern as I-f5-008 stress + I-f7-004 coverage harnesses.
2. **No production code changes:** harness lives at separate route; existing `/sentence_hover_test` demo unchanged.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 153 net. Under 200.
5. **No new package dep.**
6. **Closes F9** (3/3 issues).

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
