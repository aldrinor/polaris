# Claude architect audit — I-f13-003

**Issue:** Regression alerts inline (badges when metric drops > threshold)
**Branch:** bot/I-f13-003
**Canonical-diff-sha256:** 2bd980efadf45bbdbf8284b3a486fa53364ddf6411a5d6836d35478761e48532
**Brief verdict:** APPROVE iter 2 (units fix — pass_rate compared in percentage points)
**Diff verdict:** APPROVE iter 1 (0/0/0/0, accept_remaining)

## Substrate honesty
- New `detectRegressions(a, b)` returns `RegressionAlert[]` based on hard-coded `REGRESSION_THRESHOLDS`. Pass rate compared in percentage points (`Math.round(rate * 100)`); sentence count compared raw.
- Inline alert div (`role="alert"`) renders above snapshot grid only when alerts.length > 0.
- Honest scope: thresholds are hard-coded; production reads from regression-config file (post-Carney).
- Tests cover both directions: improvement (no alert) AND regression on swap (alert with both per-metric rows).

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 111 net. Under 200.

## Verdict
APPROVE.
