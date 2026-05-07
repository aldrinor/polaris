# Codex Diff Review — I-f5-008 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only

DO NOT spawn dev servers, browsers, or Playwright runs (sandbox blocks them per I-f5-007 iter 1). Static review only.

**Issue:** I-f5-008 — F5 latency stress test at 50/100/200/500 sentences
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `c6c6a5a13c2b276e803d1588f5aafaeaf4129486da530d2832544f26d695074d`
**LOC:** 172 net (under CHARTER §1 200-cap)

## Files

```
CLAUDE.md                                                +23 (§8.3.10 stop-is-Codex's-call rule)
web/app/sentence_hover_test/_demo_stress.tsx             NEW +89 (StressHarness component)
web/app/sentence_hover_test/stress/page.tsx              NEW +13 (Next route reading ?n=...)
web/tests/e2e/sentence_inspector_latency.spec.ts         NEW +47 (4 latency tests, performance.now())
```

## What changed

### CLAUDE.md §8.3.10
Codifies user directive 2026-05-07: stops are decided by Codex/halt-conditions/user, not by Claude judging "natural cadence checkpoint." Five forbidden self-initiated stop framings enumerated; self-check before yielding the turn.

### Stress harness
- `_demo_stress.tsx`: `StressHarness({n})` builds a synthetic VerifiedReport with N kept sentences, each citing one of up to 50 sources (cycled). Wraps VerifiedReportView with same testid (`inspector-latency-{n}`).
- `stress/page.tsx`: Next 16 server-component reading `?n=` from search params, clamped to [1, 1000], default 50.

### Latency Playwright spec
- 4 tests, one per N in [50, 100, 200, 500].
- Per Codex iter-1 P2: asserts `kept-sentence` count matches N before timing.
- Per Codex iter-1 P2: uses `page.evaluate(() => performance.now())` for tighter precision than Playwright wall-clock.
- MutationObserver waits for `[data-testid="sentence-inspector-sheet"]` to attach, then captures `t1 - t0`.
- Asserts `elapsed_ms < 1000`.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- No backend changes; backend tests not impacted.

## Risks for Codex Red-Team

1. **Cold-start tax:** initial page navigation is excluded from timing — only the click → Sheet visibility window is measured.
2. **Sources cycle (max 50):** N=500 sentences cite source_id mod 50 (10 sentences per source). Honest test of rendering throughput; sentence count is what we're stressing.
3. **MutationObserver reliability:** after attaching observer, also synchronously checks if the Sheet already exists (race). Disconnects cleanly on resolve.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 172 net (incl. CLAUDE.md). Under 200.
6. **No new package dep.**
7. **CLAUDE.md change:** doc-only addition to a binding rules file, scoped to a single new section §8.3.10, sandwiched between existing §8.3.9 and §8.4. No edits to existing rules.

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
