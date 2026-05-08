# Codex Brief Review — I-f13-003 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (units):** `PinSnapshot.pass_rate` is a fraction (0.0-1.0). Iter-2 plan: convert to percentage points before comparing. `detectRegressions(a, b)` computes `pass_rate_pct_drop = Math.round(a.pass_rate * 100) - Math.round(b.pass_rate * 100)`. Threshold remains 5 (percentage points). For sentence count, `verified_sentence_count_drop = a.verified_sentence_count - b.verified_sentence_count`, threshold 3.

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

- **Issue:** I-f13-003 — Regression alerts inline. Scope: "alert badges when metric drops > threshold". Acceptance: "alert fires on test fixture". LOC estimate 100.
- **What's needed:** alert badges that fire when comparing two pin snapshots if a metric (pass_rate or verified_sentence_count) drops by more than a configured threshold.
- **Honest framing per CLAUDE.md §9.4:** the threshold is hard-coded; production wiring would read from a regression-config file. The alert renders inline on `/pin_replay`.

## Plan

### Frontend

1. New `web/lib/pin_regression.ts` (NEW):
   - `REGRESSION_THRESHOLDS = { pass_rate_pct_drop: 5, verified_sentence_count_drop: 3 }` (hard-coded; production reads from config).
   - `detectRegressions(a, b): RegressionAlert[]` — for each numeric metric, if `(a − b) > threshold`, emit `{ metric, a_value, b_value, drop, threshold }`.

2. Update `web/app/pin_replay/page.tsx`:
   - Import `detectRegressions`.
   - Compute `alerts = detectRegressions(snap_a, snap_b)`.
   - When `alerts.length > 0`, render an inline `<div data-testid="regression-alert" role="alert">` ABOVE the snapshot cards listing each alert. Each alert has `data-testid="regression-alert-{metric}"`.

### Playwright

3. `web/tests/e2e/pin_regression_alert.spec.ts` (NEW):
   - Visit `/pin_replay`.
   - Switch A to `2026-04-30` and B to `2026-01-15` — a regression scenario (B's pass rate is LOWER than A's).
   - Assert `regression-alert` is visible.
   - Assert `regression-alert-pass_rate` contains the drop info.
   - Switch back to A=2026-01-15, B=2026-04-30 (improvement scenario): assert `regression-alert` has count 0 (no regression).

## Risks for Codex Red-Team

1. **Threshold semantics:** drop is `a − b`. Positive drop means metric WORSENED (B is lower). Tests verify both directions.
2. **Alert dismissibility:** not in scope; future polish.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~30 LOC regression lib + ~40 LOC page integration + ~30 LOC spec = ~100. At cap. Should fit.

## Acceptance criteria

1. New `detectRegressions(a, b) → RegressionAlert[]` in `web/lib/pin_regression.ts`.
2. `/pin_replay` renders inline `regression-alert` div when alerts exist.
3. Per-metric `regression-alert-{metric}` testids.
4. Playwright spec asserts alert fires on regression scenario AND does NOT fire on improvement scenario.
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
