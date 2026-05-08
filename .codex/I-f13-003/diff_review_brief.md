# Codex Diff Review — I-f13-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f13-003 — Regression alerts inline
**Brief:** APPROVED iter 2 (units fix: pass_rate_pct = round(rate*100) — comparing percentage points)
**Canonical-diff-sha256:** `2bd980efadf45bbdbf8284b3a486fa53364ddf6411a5d6836d35478761e48532`
**LOC:** 111 net (under CHARTER §1 200-cap)

## Files

```
web/lib/pin_regression.ts                       NEW +57 (REGRESSION_THRESHOLDS + detectRegressions)
web/app/pin_replay/page.tsx                     +27  (alert div integrated above snapshot grid)
web/tests/e2e/pin_regression_alert.spec.ts      NEW +27 (regression on swap; no alert on improvement)
```

## What changed

### `pin_regression.ts` (NEW)
- `REGRESSION_THRESHOLDS = { pass_rate_pct_drop: 5, verified_sentence_count_drop: 3 }`.
- `RegressionAlert` interface.
- `detectRegressions(a, b)` returns alerts when `a − b > threshold` for each metric. Pass rate compared in percentage points (`Math.round(rate * 100)`); sentence count compared raw.

### `page.tsx`
- Imports `detectRegressions`.
- Computes `alerts = detectRegressions(snap_a, snap_b)`.
- When `alerts.length > 0`, renders an inline `<div data-testid="regression-alert" role="alert">` above the snapshot grid with one `<li data-testid="regression-alert-{metric}">` per alert.

### `pin_regression_alert.spec.ts`
- Visit `/pin_replay` — initial state (A=earlier, B=later) is improvement; assert no alert.
- Swap dates — pass rate drops 13 pct points, sentences drop 5; assert alert visible with both per-metric rows.
- Swap back — alert disappears.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} lib/**/*.ts tests/e2e/pin_regression_alert.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.

## Risks for Codex Red-Team

1. **Threshold semantics:** `drop = a − b`; positive drop means metric WORSENED. Tests cover both directions (improvement → no alert; regression → alert).
2. **Pass rate units:** percentage points (`Math.round(rate * 100)`); threshold 5 means 5pp drop fires the alert.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 111 net. Under 200.

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
