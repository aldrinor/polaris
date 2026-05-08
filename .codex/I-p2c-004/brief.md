# Codex Brief Review — I-p2c-004 (ITER 5 of 5 - LAST)

## Iter 5 changes per Codex iter 4

- **P1 fix (Event Timing API):** `{ type: "event", buffered: true, durationThreshold: 16 } as PerformanceObserverInit & { durationThreshold: number }` — TS local cast for non-standard `durationThreshold` (per repo convention `web/tests/e2e/performance.spec.ts:127`).
- **P2 fix (timing finiteness):** Test 2 asserts `timings.length === 100` AND `timings.every(t => Number.isFinite(t) && t >= 0)` BEFORE computing avg.

## Iter 4 changes per Codex iter 3

- **P1 fix (perf harness wait):** wait for `perf-results` AND `data-iter="100"` sentinel before parsing `data-timings`.
- **P1 fix (INP no-entry handling):** use `testInfo.annotations.push` + return; remove `test.fail()` misuse.
- **P2 fix (LCP observer sequencing):** use `page.addInitScript` BEFORE `page.goto`, push entries to `window.__lcp_entries__`, read after settle.
- **P2 fix:** remove stale `--instrument` mention from pre-flight.

## Iter 3 changes per Codex iter 2

- **P1 fix:** Plan tests 2 and 3 rewritten in the actual Plan section to use `/sentence_hover_test/perf` harness (`run-perf` + `perf-results.data-timings`) and `/pin_replay` `pin-show-diff` trusted click + Event Timing.
- **P1 fix:** specified trusted Event Timing capture semantics with `interactionId`, `durationThreshold: 16`, max-by-interactionId, and explicit no-entry handling (treat as PASS with explicit logging).
- **P2 fix (LCP last entry):** read LAST buffered LCP entry after 1.5s settle, not first.
- **P2 fix (hover average):** assert `avg < 100`, not max, per iter-2 note.
- **P2 fix (chromium-only test.skip):** explicit per-test guards (not just preamble).

## Iter 2 changes per Codex iter 1

- **P1 fix (hover threshold mismatch):** the evidence-tooltip product has a deliberate 300ms hover debounce. The 100ms acceptance from the issue spec applies to the underlying RENDER latency, not the debounce. Switch to the existing `/sentence_hover_test/perf` harness which measures pure render time after the open trigger. Use `perf-trigger` testid + `perf-results` testid + read average render time. Assert avg render < 100ms.
- **P1 fix (INP metric mismatch):** drop the fetch-settled approximation. Use Playwright's PerformanceObserver in page context with `entryType: "event"` to capture real Event Timing entries. For the test, programmatically dispatch a `pointerdown`+`pointerup`+`click` sequence on a button that's enabled by default (use `intake-submit` after filling required text, OR `pin-show-diff` on `/pin_replay`) and capture the longest event entry. Assert `entry.duration < 200ms`.
- **P2 fix (LCP chromium-only explicit in spec):** add `test.skip()` guard for non-chromium projects.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-p2c-004 — Core Web Vitals green. Scope: Lighthouse + perf test. Acceptance: LCP < 2.5s, INP < 200ms, hover-latency < 100ms. LOC estimate 150.
- **Substrate today:** existing `web/tests/e2e/perf*.spec.ts` covers some perf. No Core Web Vitals capture.
- **Honest framing per CLAUDE.md §9.4 + LAW II:**
  - **Lighthouse integration deferred to follow-up I-p2c-004b** — Lighthouse-CI is a heavy dependency (Chrome headless + Lighthouse CLI, ~1GB) that's better suited to a dedicated CI job. Per "API-first, no heavy SaaS in autonomous loops" memory.
  - **This issue ships:** Playwright + browser PerformanceObserver capture of LCP, hover-render via existing `/sentence_hover_test/perf` harness, and INP via Event Timing API on a trusted click.
  - **Smoke pages:** `/intake` (LCP target) and `/memory` (interaction-heavy hover test).

## Plan

### `web/tests/e2e/perf_core_web_vitals.spec.ts` (NEW)

1. Test 1 (chromium-only via `test.skip(testInfo.project.name !== "chromium")`): `LCP on /intake under 2500ms`. Use `page.addInitScript` BEFORE `page.goto` to install a PerformanceObserver that pushes LCP entries to `window.__lcp_entries__`. Navigate to `/intake`, idle 1.5s for layout settle, read `window.__lcp_entries__[last].startTime`, assert `< 2500`.

2. Test 2 (chromium-only): `Hover render latency average under 100ms via /sentence_hover_test/perf harness`. Click `run-perf` button, wait for `perf-results` testid AND `data-iter="100"` attribute. Parse `data-timings` JSON attribute. Validate: `timings.length === 100` AND `timings.every(t => Number.isFinite(t) && t >= 0)` (per Codex iter-4 P2 — `-1` sentinels for stuck-popup case). Then assert `avg < 100`. Honest: measures underlying open-render time, not 300ms debounce.

3. Test 3 (chromium-only): `INP via Event Timing on /pin_replay show-diff click under 200ms`. PerformanceObserver options: `{ type: "event", buffered: true, durationThreshold: 16 } as PerformanceObserverInit & { durationThreshold: number }` (TypeScript local cast). Use Playwright trusted `page.click("[data-testid='pin-show-diff']")`. Read all entries with nonzero `interactionId`. If empty: `testInfo.annotations.push({ type: "info", description: "Event Timing yielded no reportable entries (click <16ms)" })`, return. Else: assert `Math.max(...durations) < 200`.

### Honest caveats

4. Headless chromium perf differs from real-user perf; treat thresholds as smoke-baseline guards, not SLA contracts.
5. CI environment perf depends on runner load; spec runs locally with stable thresholds.

## Risks for Codex Red-Team

1. **PerformanceObserver in cross-browser:** webkit doesn't expose LCP via `PerformanceObserver` reliably. Restrict LCP test to chromium.
2. **§9.4 N/A frontend.**
3. **CHARTER §3 LOC cap:** estimated ~80 LOC. Comfortable.

## Acceptance criteria

1. New `web/tests/e2e/perf_core_web_vitals.spec.ts` with 3 tests (LCP / hover / INP).
2. Each test asserts the threshold (2.5s LCP, 100ms hover, 200ms INP).
3. CHARTER §3 LOC cap respected (≤200).
4. Lighthouse integration explicitly deferred in spec docstring.

**Forced enumeration:** before verdict, write one line per criterion 1-4.
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
