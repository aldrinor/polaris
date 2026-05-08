# Codex Diff Review — I-f6-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f6-005 — F6 perf: 100x hover consistent <100ms
**Brief:** APPROVED iter 5 (force-APPROVE'd at cap with P2 carryover acknowledged in implementation; iter-5 schema returned APPROVE 0/0/0/2)
**Canonical-diff-sha256:** `9e66fb37113d43d78527a5689a571631f7b721c82eabc7c0a5ace9e8404d8140`
**LOC:** 180 net (under CHARTER §1 200-cap)

## Files

```
web/components/ui/evidence-tooltip.tsx     +10 -1 (optional openOverride?: boolean prop, default undefined → no behavior change)
web/app/sentence_hover_test/_demo_perf.tsx NEW +133 (PerfHarness: setOpenOverride loop + MutationObserver + popup-removed poll)
web/app/sentence_hover_test/perf/page.tsx  NEW +5  (Next route mounting PerfHarness)
web/tests/e2e/evidence_tooltip_perf.spec.ts NEW +26 (assert all 100 timings finite, >=0, <100)
.github/workflows/web_ci.yml               +7  (run_e2e_evidence_tooltip_perf step in e2e_playwright job)
```

## What changed

### `evidence-tooltip.tsx` (production)
- New optional prop `openOverride?: boolean`. When defined, drives Tooltip.Root's `open` directly via `const final_open = openOverride ?? open`. Default `undefined` = no behavior change (existing harness routes, inspector, demo, multi-source pane all compile unchanged with no logic delta).

### `_demo_perf.tsx` (harness)
- `PerfHarness` mounts ONE production `EvidenceTooltip` with `openOverride` controlled.
- Run-perf button runs 100 cycles:
  1. Set up MutationObserver on `document.body` (subtree). Callback walks added nodes, calling `el.matches?.(POPUP_SELECTOR) || el.querySelector?.(POPUP_SELECTOR)` (per Codex iter-2 P2: self-or-descendant scan).
  2. Capture `t_start = performance.now()`. `setOpenOverride(true)`.
  3. Resolve when MutationObserver fires; capture `t_end`. Push delta to `timings_ref`.
  4. `setOpenOverride(false)`. Poll `document.querySelector(POPUP_SELECTOR)` after each rAF until null OR 50 polls; if poll bails, push sentinel `STUCK_POPUP_SENTINEL = -1` and break the loop (Codex iter-2 P1).
- Final state: `<div data-testid="perf-results" data-iter={iter} data-timings={JSON.stringify(timings)} />`.

### `evidence_tooltip_perf.spec.ts`
- Visit `/sentence_hover_test/perf`, click `[data-testid="run-perf"]`.
- Wait for `[data-testid="perf-results"]` to have `data-iter="100"` (timeout 30s).
- Read `data-timings` JSON. Filter by `!(Number.isFinite(t) && t >= 0 && t < 100)` to find offending entries; assert empty (sentinel `-1` excluded by `t >= 0` per Codex iter-3 P1).

### `web_ci.yml`
- New step `run_e2e_evidence_tooltip_perf` runs after `run_e2e_performance` in the existing `e2e_playwright` job. Reuses backend + frontend startup (no new job).

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} components/**/*.{ts,tsx} tests/e2e/evidence_tooltip_perf.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.
- Existing 35+ Playwright specs that use EvidenceTooltip continue to work (openOverride defaults to undefined → no behavior change).

## Risks for Codex Red-Team

1. **`openOverride` opt-in:** undefined → byte-equivalent to pre-I-f6-005 component. Verified: no existing `EvidenceTooltip` callsite passes the prop. The only consumer of the new prop is `_demo_perf.tsx`.
2. **Real production component path:** PerfHarness mounts the production `EvidenceTooltip`, not a clone. Future regressions inside `EvidenceTooltip`'s render path (e.g., heavy child) would surface in the timings.
3. **MutationObserver self-or-descendant:** the scan handles both portal-direct and portal-wrapper scenarios.
4. **Async-unmount poll:** 50 polls * ~16ms rAF ≈ 800ms ceiling per cycle for unmount; if Base UI unmount hangs, sentinel `-1` is recorded and the spec FAILS by `t >= 0` filter.
5. **CI wiring:** the new spec runs in `e2e_playwright` job after `run_e2e_performance`; no path-filter exclusion needed (web_ci.yml `paths:` already includes `web/**`).
6. **§9.4 N/A frontend.**
7. **CHARTER §1 LOC cap:** 180 net. Under 200.

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
