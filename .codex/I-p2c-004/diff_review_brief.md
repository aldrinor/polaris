# Codex Diff Review — I-p2c-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-p2c-004 — Core Web Vitals smoke baselines
**Brief:** APPROVED iter 5 (cap reached after 4 P1 iterations)
**Canonical-diff-sha256:** `6ea94426843259d79887012c12ec473c08aa21f278edbad6d9889a22c6294466`
**LOC:** 106 net (under CHARTER §3 200-cap)

## Files

```
web/tests/e2e/perf_core_web_vitals.spec.ts   NEW +106  (3 chromium-only CWV tests)
```

## What changed

### `perf_core_web_vitals.spec.ts`
- LCP test: `addInitScript` installs PerformanceObserver before `goto`; reads `__lcp_entries__[last].startTime`; asserts `< 2500`.
- Hover-render test: `/sentence_hover_test/perf` harness via `run-perf` button → wait `data-iter="100"` → parse `data-timings`. Validate `length === 100` AND `every(t => Number.isFinite(t) && t >= 0)` (rejects `-1` stuck-popup sentinels per Codex iter-4 P2). Assert `avg < 100`.
- INP test: PerformanceObserver `{ type: "event", buffered: true, durationThreshold: 16 } as PerformanceObserverInit & { durationThreshold: number }`. Trusted `page.click("[data-testid='pin-show-diff']")`. Filter `interactionId > 0`. If empty: `info.annotations.push({ type: "info", description: ... })` and return. Else: assert `Math.max(...durations) < 200`.

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint`: exit 0.
- `npx prettier --check`: exit 0.
- `npx playwright test perf_core_web_vitals.spec.ts --project chromium`: 3/3 passing in 6.6s.

## Risks for Codex Red-Team

1. **Lighthouse-CI deferred:** documented in spec docstring.
2. **Chromium-only:** all 3 tests skip on firefox/webkit per Event Timing API + LCP reliability.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** 106 net.

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
