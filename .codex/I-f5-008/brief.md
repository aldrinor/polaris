# Codex Brief Review — I-f5-008 (ITER 1 of 5)

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

- **Context:** I-f5-008 — F5 latency stress test. The Inspector-open interaction (click sentence → Sheet appears) must complete in <1000ms at sentence counts of 50, 100, 200, and 500. Real React render performance only — no backend involvement (synthesis happens in client).
- **Constraints:** Static review-time test runs are sandbox-blocked from spawning a dev server (per I-f5-007 iter-1). Test author writes a programmatic harness that constructs synthetic VerifiedReports of N sentences and uses Playwright to drive click + measure time-to-Sheet-visible.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

1. `web/app/sentence_hover_test/_demo_stress.tsx` (new): `StressHarness({ n }: { n: number })` component. Builds a synthetic VerifiedReport with N kept sentences (each with one valid token). Default exports a route `web/app/sentence_hover_test/stress/page.tsx` that reads `?n=50` from URL search params and renders the harness for that N.
2. `web/tests/e2e/sentence_inspector_latency.spec.ts` (new): 4 tests, one per N in [50, 100, 200, 500]:
   - Navigate to `/sentence_hover_test/stress?n={n}`.
   - Wait for `verified-report-view` testid.
   - `t0 = Date.now()`; click first sentence; await `sentence-inspector-sheet` visible.
   - `t1 = Date.now()`; assert `t1 - t0 < 1000`.
   - Use Playwright's built-in performance API (`page.evaluate(() => performance.now())`) for higher precision.
3. Add testid `inspector-latency-{n}` to the harness root so the test can confirm correct N rendered.
4. No backend changes. No demo `_demo.tsx` changes (preserve I-f5-001..007 spec back-compat).
5. CHARTER §1 LOC cap: estimated ~120 LOC (harness ~50, page ~10, test ~60). Under 200.

## Bundled CLAUDE.md update (separate scope, same PR for cycle-time)

This branch ALSO carries a CLAUDE.md §8.3.10 addition codifying user directive 2026-05-07: "stop is Codex's call, not Claude's." Doc-only change to a binding rules file; included same-PR per user directive "pls update all of your doc to get it right" rather than queuing a separate doc-only PR.

## Risks for Codex Red-Team
1. **Latency on cold first render:** Next.js dev mode has a cold-start tax. Test must navigate first, wait for `verified-report-view` (initial render done), THEN measure click → Sheet only.
2. **Existing Inspector code path performance:** I-f5-005 grouped tokens by source — all existing claim-row rendering for N=500 must stay performant. Plan does NOT introduce new per-row work.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** ~120 LOC for I-f5-008; +23 LOC for CLAUDE.md doc update. Total under 200.
5. **No new package dep.** Uses Playwright's built-in `Date.now()` / `performance.now()`.

## Acceptance criteria

1. Stress harness component + route both exist; `?n=50/100/200/500` all render N sentences.
2. Playwright spec tests all 4 N tiers, asserting <1000ms click-to-Sheet-visible.
3. Tests pass against the current implementation (no perf regression introduced by harness).
4. No changes to `_demo.tsx` (existing spec back-compat preserved).
5. CLAUDE.md §8.3.10 added with the verbatim §8.3.10 text from the user-approved §8.4 follow-on slot.
6. CHARTER §1 LOC cap respected (≤200 net excluding meta).

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
