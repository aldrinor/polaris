# Codex Brief Review — I-f6-005 (ITER 4 of 5)

## Iter 4 changes per Codex iter 3

- **P1 fix (CI inert spec):** Codex iter-3 verified `web_ci.yml` `e2e_playwright` job runs only `tests/e2e/inspector.spec.ts`, `tests/e2e/accessibility.spec.ts`, `tests/e2e/performance.spec.ts`. A new spec at `tests/e2e/evidence_tooltip_perf.spec.ts` would not execute in CI. Iter-4 plan: ALSO add a step `run_e2e_evidence_tooltip_perf` to `.github/workflows/web_ci.yml` that runs `npx playwright test --project=chromium tests/e2e/evidence_tooltip_perf.spec.ts` after the existing perf step. Reuses the same backend + frontend startup steps; no new build/dependency cost.
- **P2 fix (observer self-or-descendant):** the MutationObserver scan checks BOTH `node.matches?.(selector)` AND `node.querySelector?.(selector)` so the popup can be matched whether it's the directly-added node or a descendant of a Portal wrapper.

## Iter 3 changes per Codex iter 2

- **P1 fix (Base UI async unmount):** Codex iter-2 verified Base UI's Tooltip unmount is async via `useOpenChangeComplete` + `useAnimationsFinished`. One `requestAnimationFrame` after `setOpenOverride(false)` is insufficient — the popup may still be in the DOM when the next iteration calls `setOpenOverride(true)`, defeating the MutationObserver. Iter-3 plan: poll `document.querySelector('[data-testid="evidence-tooltip-popup"]')` after each `setOpenOverride(false)` until it returns `null`, then continue. Use `await new Promise(r => requestAnimationFrame(r))` between polls; bail out at 50 polls with a recorded "stuck-popup" sentinel that the spec asserts against.
- **P2 fix (added-node descendants):** the MutationObserver scans `addedNode.querySelector('[data-testid="evidence-tooltip-popup"]')` to handle Base UI's Portal wrapper/Positioner nesting (the popup is several layers deep, not a direct addedNode).
- **P2 cleanup:** the obsolete HarnessTooltip/Profiler text below was already removed in iter-2; if any vestige remains, this is the iter-3 final cleanup.

## Iter 2 changes per Codex iter 1

- **P1 fix (React.Profiler is dev-only):** abandon `React.Profiler.onRender`. Use `performance.now()` markers around each cycle, capturing the time from `setOpen(true)` → MutationObserver firing on popup-mount in the React Portal target.
- **P1 fix (must exercise REAL EvidenceTooltip path):** add ONE small opt-in prop `openOverride?: boolean` to `EvidenceTooltip` (default `undefined` — no behavior change for existing callers). When defined, bypasses the internal hover/touch state machine and feeds Tooltip.Root directly: `const final_open = openOverride ?? open;`. The harness then drives the real production component's render path via the override; this guarantees production-component perf regression is locked.
- **P2 fix (open-commit filter):** since we count cycles ourselves (loop iterations) and use performance.now() pairs (one start per cycle, one end on first MutationObserver "popup added" notification), we don't rely on Profiler — we get exactly 100 cycle timings by construction.

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

- **Issue:** I-f6-005 — F6 perf: 100x hover consistent <100ms.
- **Acceptance from `state/polaris_restart/issue_breakdown.md`:** "rendering perf test" + "consistent under threshold".
- **What "100ms" means:** the 300ms hover-debounce (I-f6-001 baseline + I-f6-003 internalization) precludes hover-to-popup-visible <100ms. The 100ms target therefore measures **render commit time** of the popup content — i.e., the JSX-→-DOM mounting cost — repeated 100 times, asserting consistent <100ms per render.
- **Why this matters:** the F6 evidence overlay must scale to long reports (200+ sentences, each potentially hovered). A regression in `EvidenceTooltip` popup render cost (e.g., adding a heavy child component or re-rendering the whole pool list per hover) would violate this implicitly. This issue locks the regression budget at 100ms per popup mount.
- **Scope:** test-only + a small perf harness route. NO production code change to `EvidenceTooltip` (its current render cost is the baseline we're locking).

## Plan

### Production component (small opt-in prop)

1. `web/components/ui/evidence-tooltip.tsx`:
   - Add optional `openOverride?: boolean` to `EvidenceTooltipProps`.
   - In the body: `const final_open = openOverride ?? open;` and pass `final_open` to `<Tooltip.Root open={final_open}>`. `onOpenChange={handleOpenChange}` stays the same — when `openOverride` is defined, Base UI still calls back but our `setOpen` updates internal state harmlessly; the rendered `open` value remains driven by `openOverride`.
   - Default `undefined` — no behavior change for existing callers (existing harness routes, inspector page, demo, multi-source pane). Verified by the existing 3+ Playwright specs that don't pass the new prop.

### Frontend perf harness

2. `web/app/sentence_hover_test/_demo_perf.tsx` (NEW client component):
   - Imports `EvidenceTooltipProvider`, `EvidenceTooltip` from `@/components/ui/evidence-tooltip`.
   - State: `[openOverride, setOpenOverride] = useState<boolean | undefined>(undefined)`, `[iter, setIter] = useState(0)`, `[timings, setTimings] = useState<number[]>([])`.
   - Renders ONE production `<EvidenceTooltip openOverride={openOverride} ...>` (note: `EvidenceTooltipProvider` wrapper is outside).
   - Button `data-testid="run-perf"` clicks: runs an async loop of 100 iterations. Per iteration:
     1. Set up a `MutationObserver` on `document.body` (subtree) — its callback iterates added nodes and runs `node.querySelector?.('[data-testid="evidence-tooltip-popup"]')` to handle Base UI's Portal/Positioner wrapper nesting. First match resolves the iter promise.
     2. Capture `t_start = performance.now()`.
     3. Call `setOpenOverride(true)`. React schedules the commit.
     4. Wait for the MutationObserver `popup-added` callback; capture `t_end = performance.now()`. Disconnect the observer. Record `t_end - t_start` into `timings_ref.current`.
     5. Call `setOpenOverride(false)`. Poll `document.querySelector('[data-testid="evidence-tooltip-popup"]')` after each `requestAnimationFrame` until it returns `null` (Base UI's async unmount via `useOpenChangeComplete` + `useAnimationsFinished` is honoured). Bail out at 50 polls with a sentinel `-1` timing if popup never unmounts (spec asserts no sentinels appear).
     6. Increment `iter` (every 5 iterations to avoid React thrashing) so Playwright can poll progress.
   - After 100 iterations: `setTimings([...timings_ref.current])`, `setIter(100)`.
   - Render `<div data-testid="perf-results" data-iter={iter} data-timings={JSON.stringify(timings)} />`.

3. `web/app/sentence_hover_test/perf/page.tsx` (NEW route): mounts the harness inside `<EvidenceTooltipProvider>`.

### Playwright perf spec + CI wiring

3. `web/tests/e2e/evidence_tooltip_perf.spec.ts` (NEW):
   - Visit `/sentence_hover_test/perf`.
   - Click `[data-testid="run-perf"]`.
   - Wait for `[data-testid="perf-results"]` to have `data-iter="100"` (timeout 30s — generous so CI noise doesn't flake; the rAF loop should complete in ~3-5s on a reasonable machine).
   - Read `data-timings` JSON; assert:
     - `timings.length === 100`
     - **every t satisfies `Number.isFinite(t) && t >= 0 && t < 100`** — sentinel `-1` (popup-stuck) is explicitly excluded.
   - On failure, log the offending timing(s).

4. `.github/workflows/web_ci.yml` — add a new step in `e2e_playwright` job after `run_e2e_performance`:
   ```yaml
   - name: run_e2e_evidence_tooltip_perf
     env:
       SCREENSHOT_BASE_URL: http://127.0.0.1:3738
       POLARIS_V6_BACKEND_URL: http://127.0.0.1:8000
     run: npx playwright test --project=chromium tests/e2e/evidence_tooltip_perf.spec.ts
   ```
   This wires the new perf gate into the existing CI path without adding a new job.

## Risks for Codex Red-Team

1. **CI noise headroom:** 100ms is per-render. CI runners (GitHub Actions ubuntu-latest) sometimes spike on cold renders. The test asserts ALL 100 < 100ms; the first render after JS warmup may be a P99 outlier. If flaky, we may need to bump to 150ms, but per the spec letter we keep 100ms initially and tune only if CI flakes.
2. **Real production component:** harness mounts the real `EvidenceTooltip` via `openOverride` so production-component perf regression is locked. No clone, no Profiler bundle dependency.
3. **MutationObserver subtree depth:** Base UI portals add wrapper nodes; observer scans `addedNode.querySelector(...)` to find the popup at any descendant depth.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~5 LOC openOverride prop + ~70 LOC harness + ~30 LOC spec + ~5 LOC route = ~110. Under 200. Within issue_breakdown LOC estimate of 70 + slack.

## Acceptance criteria

1. `EvidenceTooltip` accepts a new optional `openOverride?: boolean` prop. When undefined (default), behavior is byte-equivalent to the iter pre-I-f6-005 component. When defined, drives the controlled `open` directly.
2. New harness route `/sentence_hover_test/perf` exposes a `[data-testid="run-perf"]` button.
3. Clicking the button runs 100 mount-cycles via `setOpenOverride(true/false)`, measuring `performance.now()` from setOpenOverride(true) to MutationObserver popup-added callback.
4. On completion, `[data-testid="perf-results"]` has `data-iter="100"` and `data-timings` JSON list of 100 numbers.
5. New Playwright spec asserts every timing satisfies `Number.isFinite(t) && t >= 0 && t < 100`. The sentinel `-1` (set when popup-unmount poll bails out at 50 polls) is explicitly excluded by `t >= 0`, so a stuck-popup cannot pass the gate as a false green.
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
