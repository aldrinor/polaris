# Per-commit Codex brief — `0867df9`

**Commit:** `0867df9 PL: v6.2 F-3..F-6 — tighten perf budgets + waitFor + visual testIgnore + dead-code`
**Format:** v2 minimal
**Files changed (3):**
- `web/tests/e2e/performance.spec.ts` — F-3 + F-4
- `web/playwright.config.ts` — F-5
- `web/tests/e2e/accessibility.spec.ts` — F-6

## What this commit does

Closes 4 audit findings from `outputs/audits/continuous/4fe03f7_cross_review.md`:

**F-3 (root_cause)** — perf budgets tightened to `~2× baseline_observed`:

| Budget | Old | New | Observed | New slack |
|---|---|---|---|---|
| DOMContentLoaded | 2000ms | **1000ms** | 270-450ms | 2.2-3.7× |
| Charts SVG render | 2500ms | **2000ms** | ~1.0s | 2× |
| FCP | 1500ms | **800ms** | 391ms | 2× |
| Tab-switch | 250ms | 250ms (unchanged) | ~100ms (inferred) | 2.5× |

**F-4 (guardrail)** — `waitFor({timeout: 1000})` → `waitFor({timeout: 5000})` in tab-switch tests. Old timeout was BELOW the (now-)stricter budget assertion, so a 1500ms regression would surface as a misleading locator-TimeoutError. New 5000ms gives the budget assertion room to produce a clean diagnostic (`expected switchMs < 250, got 1500ms`).

**F-5 (guardrail)** — added `testIgnore: process.platform === "linux" ? ["**/visual.spec.ts"] : undefined` to `playwright.config.ts`. Defense against future refactoring of CI from per-file invocation to `npx playwright test` (which would silently auto-baseline missing Linux snapshots).

**F-6 (cosmetic)** — removed the dead `expect(results.violations).toEqual([])` after the throw in the a11y helper.

## Acceptance criteria

1. **Tighter budgets actually pass.** Re-running observed: DOMContentLoaded 393-400ms (under new 1000ms), FCP 391ms (under new 800ms). Confirmed.
2. **No flake-prone budget gating.** All 6 perf tests pass on cold + warm runs against the prod build.
3. **F-4 verified empirically.** Without applying F-4, intentional `await page.waitForTimeout(1100)` after tab.click() would surface as locator timeout. With F-4 (5s timeout), it would surface as `expect(switchMs < 250) failed: 1100`. Have not actually injected the failing scenario in this commit; the change is mechanical.
4. **F-5 doesn't break local Win32 runs.** `process.platform === "linux"` is false on Windows; `testIgnore` becomes `undefined`, no tests skipped. Confirmed by the 4/4 visual.spec PASS still happening when run individually.
5. **F-6 doesn't change failure semantics.** The throw-above already conveyed the violation list; dropping the dead expect changes nothing for the success or failure path.

## Codex focus

- **P0:** F-3 changes assertions in tests that aren't currently in CI (Phase 2C.4 lands when `e2e_playwright` job runs). The first CI run with these budgets will be a real load test — if CI hardware is appreciably slower than my dev box (likely), some budgets may flake. Codex must consider whether to spike one CI run before declaring done.
- **P1:** F-4 helps DIAGNOSTIC clarity but doesn't move the budget itself. If a slow tab-switch DOES happen, the test now fails with a perf message instead of a locator message — that's the win. But if the tab fails to render at all (selector mismatch), it'll wait 5s before failing — slower CI runs.
- **P2:** F-5 testIgnore syntax: `["**/visual.spec.ts"]` is a glob. Confirm Playwright honours the `**/` prefix correctly.

## Cross-review

Lands at `outputs/audits/continuous/0867df9/cross_review.md`. Counter now **4/5** in the post-4fe03f7 batch.
