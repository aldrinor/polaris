# Codex Brief Review — I-f9-001 (ITER 1 of 5)

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

- **Context:** I-f9-001 — when `evaluator_agrees=false` (two-family LLM judge disagrees with generator), render an INLINE ROW badge "⚠ Internal evaluator flagged this" — visible WITHOUT opening the SentenceInspector. This complements I-f5-004's pane-level Disagree badge with a row-level surface so the user sees disagreement at-a-glance while scanning the report.
- **Constraints:** No backend change — all data already on `ReportVerifiedSentence.evaluator_agrees` field from I-f5-004.
- **Done-when:** acceptance criteria 1-5 below.

## Plan

### Frontend
1. `web/app/generation/components/verified_report_view.tsx`: in `SentenceRow`, when `sentence.evaluator_agrees === false` AND `!dropped`, render `⚠ Internal evaluator flagged this` badge with testid `evaluator-flag-{sentence_id}`. Tooltip explains: "Two-family evaluator disagrees with generator's claim per CLAUDE.md §9.1 invariant 1."
2. Demo: existing sec_x:11 already has `evaluator_agrees: false` (I-f5-004 disagree case). Use it for the test.
3. `web/tests/e2e/sentence_inspector_evaluator_flag.spec.ts` (new):
   - Test 1: sec_x:11 row shows `evaluator-flag-sec_x:11` badge.
   - Test 2: sec_x:5 (agree) shows NO evaluator-flag badge.
   - Test 3: sec_x:12 (pending — null) shows NO evaluator-flag badge.

## Risks for Codex Red-Team
1. **Type:** `evaluator_agrees: boolean | null` — only render when explicitly false. null/undefined → no badge.
2. **Existing AgreementBadge in pane:** I-f5-004 already renders inside the Sheet. This Issue adds row-LEVEL badge so user doesn't need to click open pane to see the flag.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~50 LOC. Well under 200.

## Acceptance criteria

1. Row badge `evaluator-flag-{sentence_id}` renders only when `evaluator_agrees === false` AND `verifier_pass === true`.
2. Badge has tooltip explaining the two-family signal.
3. Demo sec_x:11 (false) renders badge; sec_x:5 (true) and sec_x:12 (null) do not.
4. Playwright covers all 3 cases.
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
