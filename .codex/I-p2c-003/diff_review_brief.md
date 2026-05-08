# Codex Diff Review — I-p2c-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-p2c-003 — Cross-browser: chromium / firefox / webkit
**Brief:** APPROVED iter 1 (zero P0/P1)
**Canonical-diff-sha256:** `189a2500f64817accdc79e35bf979ed8a4d9c8843055ae1313e26e8abd273f74`
**LOC:** 50 net (well under CHARTER §3 200-cap)

## Files

```
web/tests/e2e/cross_browser_smoke.spec.ts   NEW +50  (5 pages × 3 browsers = 15 page-render tests)
```

## What changed

### `cross_browser_smoke.spec.ts`
- 5 stable pages: F1 `/intake`, F3 `/upload`, F4 `/sse`, F11 `/contracts`, F12 `/sentence_hover_test/perf`.
- Per page: `page.route("**/api/audit/stream**", ...)` stubs SSE so the harness doesn't hang (Codex iter-1 P2).
- `goto(p.path, { waitUntil: "domcontentloaded" })`; assert `getByTestId(p.testid).toBeVisible()`.
- Asserts no error testids visible (`intake-error`, `contract-errors`, `preview-error`, `vega-chart-error`) — Codex iter-1 P2 specific suffixed-id list.
- No `--project` flag in spec → exercises all 3 chromium/firefox/webkit projects per playwright.config.ts:37-49.

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint`: exit 0.
- `npx prettier --check`: exit 0.
- `npx playwright test cross_browser_smoke.spec.ts` (no --project): 15/15 passing in 13.0s on chromium / firefox / webkit.

## Risks for Codex Red-Team

1. **No backend coupling:** all 5 pages render without backend; SSE stream stubbed.
2. **Stable page selection:** these 5 are deliberately Vega-free, PDF-free; cross-browser parity for those is follow-up.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** 50 net. Well under 200.

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
