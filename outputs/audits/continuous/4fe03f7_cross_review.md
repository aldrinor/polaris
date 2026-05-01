# Cross-review — `4fe03f7` batch (Claude vs Codex-as-subagent)

**Cross-review of:** `outputs/audits/continuous/4fe03f7_audit.md` (P0=0, P1=3, P2=4, P3=4)
**Author of audit:** general-purpose subagent (cleared context, adversarial role)
**Author of cross-review (me):** Claude Opus 4.7 (the original author of the 5 commits in scope)
**Triangle protocol:** `memory/autoloop_v2_audit_cross_review.md` — both GREEN ship; either dissents → fix plan tagged root_cause/guardrail/band_aid; band_aid = always RED.

## Verdict alignment

| | Claude self-assessment | Subagent verdict |
|---|---|---|
| Verdict | APPROVE_WITH_FIXES (per per-commit briefs flagging own P0s) | **APPROVE_WITH_FIXES** |
| Honesty / no fake-working | OK (per LAW II) | **OK** — no rule suppression, no `page.route` mocking, no stubbed perf measurements |
| Production-breaking | none | **none (P0=0)** |

**Triangle status: BOTH agree.** Subagent dissent is on scope-completeness (P1.1, P1.2, P1.3), not integrity. Per protocol, fixes land in the same author-branch; no Codex round-2 needed unless a fix reintroduces a problem.

## Subagent confirmed my self-flagged P0s

These are reasons to be confident in the substrate work, not just the audit:

1. **dae2a9f P0** ("are there other surfaces using the same pattern?") → confirmed P1.1: 4 more surfaces.
2. **2bb1de7 P0** ("budgets are loose-but-meaningful") → confirmed P1.3: 4-5x slack on most budgets.
3. **2bb1de7 P0** ("hover-latency target NOT directly measured") → confirmed P1.2: docstring promises a metric the test file doesn't measure.
4. **4fe03f7 P0** ("requirements.txt may pull Linux-incompatible pins") → partially confirmed P2.2: install-time bloat is the firmer concern.

## Subagent disagreed with my self-flagged P0s (instructive)

The subagent independently verified and rejected three of my own concerns. I take this seriously — if it's reading the same code as me and reaching opposite conclusions on a verifiable fact, the disagreement is grist:

1. **4fe03f7 P0 (`/health` race)** — Subagent: "I read `app.py`. `app = create_app()` runs at module load; `health_router` is included alongside all other routers BEFORE uvicorn binds. No race." → I accept this. My P0 was hypothetical, not based on reading the actual app factory.
2. **4fe03f7 P0 (`PYTHONPATH=src` propagation)** — Subagent: "single shell line, env var sets correctly". → Accepted.
3. **2057fac P0 (2% threshold absorbing 30px banner)** — Subagent: "30px banner shift = 30px × width changed = ~3.3% of image area, which EXCEEDS the 2% threshold". → Accepted; I'd done the arithmetic wrong.

These three disagreements MOVE my prior beliefs and tighten my priors for future briefs.

## Fix plan with root_cause / guardrail / band_aid tags

Per `memory/autoloop_v2_audit_cross_review.md`: **band_aid = always RED**, never proceed; root_cause + guardrail OK.

| ID | Source | Fix | Tag | Rationale |
|---|---|---|---|---|
| F-1 | P1.1 | Refactor 4 untouched destructive surfaces to the same `border-only + text-foreground + font-medium` pattern dae2a9f/07d6c30 used; add 1 a11y test per failure path triggering each banner. | **root_cause** | The pattern is the cause; suppressing/disabling axe rule would be band_aid. Extracting a shared component would be also valid root_cause but bigger lift; tier-2 follow-up. |
| F-2 | P1.2 | Either (a) remove the docstring line that promises a hover budget the file doesn't measure, OR (b) add a real hover test. Pick (b) — instrument a `Tooltip.Provider` zero-delay test mode + measure `mouseenter`→`[role="tooltip"]` visible. | **root_cause** | (a) is honest but ships a regression in observability. (b) closes the gap properly. |
| F-3 | P1.3 | Tighten budgets to `max(2 × baseline_observed, hard_floor)`. DOMContentLoaded → 1000ms; FCP → 800ms; Vega → 2000ms. Tab-switch (250ms) is already 2.5x of observed (~100ms inferred from sub-1s test wall-clock minus setup); leave at 250ms. | **root_cause** | Budgets that pass at 4-5x slack don't catch regressions. |
| F-4 | P2.1 | Bump `waitFor({timeout:1_000})` to `waitFor({timeout:5_000})` so the perf assertion always runs and produces a clean diagnostic. | **guardrail** | Fix the FAILURE-MODE diagnostic (locator-timeout vs budget-fail), not the gate itself. |
| F-5 | P2.3 | Add `testIgnore: process.platform === 'linux' ? ['**/visual.spec.ts'] : []` to `playwright.config.ts` so a CI refactor that uses `npx playwright test` (no file arg) silently skips the visual suite on Linux instead of auto-snapshotting. | **guardrail** | The current file-list invocation isn't fragile right NOW; this prevents future-Claude from accidentally introducing a silent snapshot regression. |
| F-6 | P3.4 | Remove the dead `expect(results.violations).toEqual([])` line in the helper. | **cosmetic** | Pure dead code. |

## Items NOT taken up this cycle

- **P2.2** `requirements-api.txt` minimal subset — useful but adds a maintenance burden (now we have to keep TWO requirements files in sync). Defer until CI install-time becomes an actual bottleneck. Logged as a future item.
- **P2.4** `package-lock.json` cross-platform deps — the sub-agent flagged "TO VERIFY"; until I see an actual CI install failure, this is hypothetical.
- **P3.1, P3.2** orphan-process patterns — runners are ephemeral; not worth the noise.
- **P3.3** counter-file derivability from git log — I'll address this once the next 5-commit cycle completes; for now the JSON file + per-commit briefs in `.codex/continuous/*` give two redundant sources of truth.

## Closure

Ship the F-1..F-6 fixes as a small new batch. **Counter resets to 0** after the fixes land (per scheme); the 5-commit cycle that just closed counted dae2a9f → 4fe03f7. The F-1..F-6 commits start the new batch. Per K=5, the NEXT subagent fires after the 5th post-audit substrate commit lands.

**Date:** 2026-05-01
**Subagent invocation cost:** 100,945 tokens / 78 tool uses / 398s wall (per task notification)
