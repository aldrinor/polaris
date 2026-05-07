# Codex Diff Review — I-f9-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f9-001 — Per-claim row-inline ⚠ Internal evaluator flagged badge
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `406664fc4a89e7666293f17316d49497bc079566f5d71deead722e5b5db3a794`
**LOC:** 33 net (well under CHARTER §1 200-cap)

## Files

```
web/app/generation/components/verified_report_view.tsx     +9 (inline ⚠ badge gated on evaluator_agrees=false)
web/tests/e2e/sentence_inspector_evaluator_flag.spec.ts    NEW +24 (3 tests: false/true/null)
```

## What changed

- `SentenceRow` renders inline `evaluator-flag-{sentence_id}` badge when `evaluator_agrees === false` AND `!dropped`. Tooltip cites CLAUDE.md §9.1 invariant 1.
- 3 Playwright tests covering false (sec_x:11 visible), true (sec_x:5 absent), null (sec_x:12 absent).
- Reuses existing demo fixtures from I-f5-004 (no demo changes needed).

## Verification
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Strict equality `=== false`:** correctly excludes null/undefined which are "pending" not "disagreed."
2. **`!dropped` gate:** matches I-f5-004 AgreementBadge convention; dropped sentences don't surface the flag (drop_reason already covers).
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 33 net. Comfortably under 200.
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
