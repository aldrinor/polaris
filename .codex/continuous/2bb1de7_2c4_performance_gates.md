# Per-commit Codex brief — `2bb1de7`

**Commit:** `2bb1de7 PL: v6.2 Phase 2C.4 performance gates — 6/6 budget assertions PASS`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (2):**
- `web/tests/e2e/performance.spec.ts` (new, 6 tests)
- `docs/todo_list.md` (mark 2C.4 done)

## What this commit does

Adds Phase 2C.4 perf suite — 6 tests asserting concrete latency budgets against the live build:

| Surface | Measurement | Budget | Observed (local) |
|---|---|---|---|
| Inspector cold load (clinical) | `goto`→DOMContentLoaded | 2000ms | ~450ms |
| Inspector cold load (climate) | same | 2000ms | ~270ms |
| Verified-sentences tab switch | click→token visible | 250ms | passing |
| Contradictions tab switch | click→`noted_both` visible | 250ms | passing |
| Charts tab Vega-Lite SVG | click→`.polaris-vega-chart svg` | 2500ms | ~1.0s |
| Inspector FCP | PerformanceObserver `first-contentful-paint` | 1500ms | 402ms |

Implementation:
- Plain `Date.now()` deltas for click→locator-visible measurements (cheap, accurate enough for >200ms budgets).
- `PerformanceObserver` inside `page.evaluate` for FCP (real W3C Web Vitals API; observes the buffered paint entry list, falls back to a 3s setTimeout so the test never hangs).

## Acceptance criteria

1. **Real measurements, not stubs.** No `await page.evaluate(() => 50)` faking. Each measurement reads either a real `Performance` API entry or a wall-clock delta.
2. **Concrete budgets per metric.** Each test fails on a single number — `expect(loadMs).toBeLessThan(2000)`. No `expect(true).toBe(true)` placeholder assertions.
3. **Doesn't double-count setup.** The `start = Date.now()` lines run AFTER `page.goto({waitUntil: "networkidle"})` for tab-switch tests, so the budget measures only the user-action latency, not the page load.
4. **FCP test guards against the -1 case.** The observer can return -1 if FCP never fires — assertion `toBeGreaterThanOrEqual(0)` catches this and surfaces as a real failure rather than passing on -1 < 1500.
5. **Each test is hermetic.** No shared state between tests — each starts from a fresh `page` and navigates explicitly.

## Codex focus

- **P0:** The hover-latency target (<100ms from the original 2C.4 description) is NOT directly measured here because base-ui's `Tooltip` has a built-in open-delay (~600ms) that dominates any actual render time. Should we instead measure tooltip first-render-after-open via instrumentation, or accept the current proxy budgets (tab switch + page load + chart render) as the practical Phase 2C.4 deliverable?
- **P0:** The 6 budgets are loose-but-meaningful. If Codex thinks they're too loose (e.g., DOMContentLoaded < 2000ms passes even for a 1900ms render — bad UX), recommend tighter values or per-fixture differentiation.
- **P1:** Should we capture LCP (Largest Contentful Paint) in addition to FCP? LCP is a more user-meaningful Web Vital. Same PerformanceObserver pattern, different `type: "largest-contentful-paint"`.
- **P2:** Output the actual measured value (not just pass/fail) so we can track perf trends over time. Could log via `test.info().annotations.push({type:"perf", description: \`loadMs=${loadMs}\`})`.

## Cross-review

Lands at `outputs/audits/continuous/2bb1de7/cross_review.md`. Counter now **4/5** — one more substrate commit until the K=5 adversarial-reviewer subagent triggers.
