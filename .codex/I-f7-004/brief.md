# Codex Brief Review — I-f7-004 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix:** "finite positive" → "finite non-negative" (≥ 0). Both `covered` and `gap_count` allowed = 0 to reach the 0/15 and 15/15 edge states. Both clamped to [0, 100].
- **P2 fix:** `GapReason` is a TS union, not a runtime enum — use `const GAP_REASONS: GapReason[] = [...]` literal array for cycling, not iteration over the type.

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

- **Context:** I-f7-004 — adversarial coverage for the FrameCoveragePanel. Three edge variants:
  - **0/15:** zero entities covered, all 15 are gaps. Panel must render amber with 15 gap rows.
  - **15/15:** all entities covered, no gaps. Panel must render emerald success state via `frame-coverage-complete` testid.
  - **1/15:** single covered entity, 14 gaps. Panel must render correctly with 14 gap rows.
- **Constraints:** UI-only test additions. No backend / production code changes. Need a configurable test harness to vary the coverage shape — similar to I-f5-008's stress harness.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

### Test harness
1. `web/app/sentence_hover_test/_demo_coverage.tsx` (new): `CoverageHarness({ covered, gap_count }: { covered: number; gap_count: number })`. Renders a minimal VerifiedReportView with a single section + one verified sentence + a synthetic FrameCoverage built from the params (gaps cycle through GapReason union literal values (not a runtime enum; cycle via local `const GAP_REASONS: GapReason[]` array) for variety).
2. `web/app/sentence_hover_test/coverage/page.tsx` (new): Next route reading `?covered=N&gap_count=M` from search params (defaults 14/1 to mirror sec_x:18..22). Both clamped to [0, 100] with finite non-negative guards.

### Playwright spec
3. `web/tests/e2e/frame_coverage_adversarial.spec.ts` (new):
   - Test 1 (0/15): nav `/sentence_hover_test/coverage?covered=0&gap_count=15` → assert `frame-coverage-gaps` visible + `frame-coverage-gap-14` (last) visible + count "15 gaps".
   - Test 2 (15/15): nav `/sentence_hover_test/coverage?covered=15&gap_count=0` → assert `frame-coverage-complete` visible + NO `frame-coverage-gap-0`.
   - Test 3 (1/15): nav `/sentence_hover_test/coverage?covered=1&gap_count=14` → assert `frame-coverage-gaps` visible + `frame-coverage-gap-13` (last) visible + count "14 gaps".

## Risks for Codex Red-Team
1. **Search-param parsing:** Use `Number.parseInt` + finite non-negative guards, both clamped to [0, 100] (Codex iter-1 P1 — zero must be reachable for 0/15 and 15/15 edge states).
2. **Existing tests preserved:** `_demo.tsx` 14/15 case unchanged.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~110 LOC. Under 200.

## Acceptance criteria

1. Coverage harness component + Next route both exist.
2. Search-param parsing clamps to finite non-negative integers (≥ 0; both 0/15 and 15/15 reachable).
3. Demo gap entries cycle through GapReason union literal values (not a runtime enum; cycle via local `const GAP_REASONS: GapReason[]` array) (variety, not all "no_oa").
4. Playwright covers all 3 edge variants (0/15, 15/15, 1/15).
5. Existing `_demo.tsx` + frame_coverage_panel.spec.ts unchanged.
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
