# Per-commit Codex brief — `909eb4c`

**Commit:** `909eb4c PL: v6.2 F-2 root-cause — real hover-latency test (closes audit P1.2)`
**Format:** v2 minimal
**Files changed (1):** `web/tests/e2e/performance_hover.spec.ts` (new, 89 lines, 2 tests)

## What this commit does

Closes audit P1.2 from `outputs/audits/continuous/4fe03f7_audit.md`. The 2C.4 perf gate suite previously documented "Hover → tooltip visible after open-delay completes < 1.0s" in its docstring but no test file actually measured hover latency.

This commit adds a separate spec file with 2 budget tests:

1. **Token hover → tooltip visible < 1000ms** — wall-clock from `trigger.hover()` until the popup's `evidence_id · tier T1` text becomes visible. Budget = ~600ms (base-ui v1.4 default open-delay) + ~400ms (react render budget).
2. **Hover-out → tooltip hidden < 500ms** — wall-clock from `mouse.move(0, 0)` until popup vanishes. base-ui's close transition has its own delay (~300ms typical); 500ms is a 1.7× cushion.

**Selector engineering note**: I tried `[role="tooltip"]` first and it failed because base-ui's `TooltipPopup` does NOT set `role="tooltip"` (verified by reading `node_modules/@base-ui/react/esm/tooltip/popup/TooltipPopup.js` — no role attribute set). Switched to content-based selector (`ev_clin_001 · tier T1`) which is unique per evidence id.

Verified: 2/2 PASS in 5.4s on chromium against the rebuilt prod server.

## Acceptance criteria

1. **Real hover, not synthesized event.** Test uses `trigger.hover()` (Playwright's high-level API that dispatches mouseenter+mouseover+mousemove sequence) — not a synthesized `mouseenter` event that bypasses base-ui's open-delay logic.
2. **Selector matches what users actually see.** The `ev_clin_001 · tier T1` text appears INSIDE the popup the user sees on hover. Asserting on this proves the popup actually rendered with content, not just an empty positioner.
3. **Hover-out path tested.** Many tooltip libs have asymmetric open/close logic; covering close-delay is independent value.
4. **Budget includes the lib's own delays, not just our code.** A perf regression in base-ui itself (e.g., a future version with longer open-delay) would also trip the budget — that's intentional; user perceives the total.
5. **Spec lives in its own file.** Hover tests are slower (~3s each) than other perf gates because of the open-delay; isolating them lets us run the fast suite + this one independently in CI when needed.

## Codex focus

- **P0:** Did I just paper over the original "<100ms hover-latency" target by accepting 1000ms? The 100ms target was unrealistic given the base-ui open-delay; the real question users care about is "feels responsive" which the lib's 600ms delay is the dominant factor. Should we either (a) configure Tooltip.Provider with delay=0 and assert <100ms render-only, or (b) document explicitly that the user-perceived latency is bounded by the lib's open-delay?
- **P1:** Two tests both target the same provenance token. If that token disappears (fixture changes, runId rotates), both fail. Should we parametrize across multiple tokens?
- **P2:** No test for keyboard focus → tooltip (a11y users hit Tab not hover). Different code path in base-ui — worth covering.

## Cross-review

Lands at `outputs/audits/continuous/909eb4c/cross_review.md`. **Counter at 5/5 — A+C trigger.** Next action: spawn adversarial-reviewer subagent on the 5 commits since 4fe03f7 (9ccd286, 9bf7346, e331b08, 0867df9, 909eb4c).
