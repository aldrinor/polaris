# Codex Diff Review — I-p2c-002 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix:** F15 benchmark mock corrected to return real `/api/benchmark/health` contract (`{ available_benchmarks: [], results_root: "/seeded/benchmarks" }`). F15 baselines regenerated (4 PNGs replaced); all 60 still pass.
- **P2 acknowledged:** F6 and F8 share path `/sentence_hover_test`; baselines are identical because both render the same page. Distinct visual coverage for F8 contradiction-rows requires a fixture page that auto-scrolls to those rows — deferred to follow-up I-p2c-002e.

## Updated SHA: `ef59a1b0b0ea26f4fc321bc2f53337b8ee7ec829a47978c19c590ada0c693452`

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-p2c-002 — Visual baselines 4 viewports × 15 features
**Brief:** APPROVED iter 5 (after 4 rounds of testid + readiness fixes)
**Canonical-diff-sha256:** `7e2ecc2242fa77a2c1e01297336fd26c6249999c90305e0c9093fbaaa73fd81c`
**LOC:** 132 net text additions (60 PNG binaries are NOT line-counted; total ≈1.6 MB)

## Files

```
web/tests/e2e/visual_60_baselines.spec.ts                                     NEW +132 (parametrized matrix spec)
web/tests/e2e/visual_60_baselines.spec.ts-snapshots/F1..F15-{mobile,tablet,laptop,desktop}-chromium-win32.png   NEW 60 PNG binaries
```

## What changed

### `visual_60_baselines.spec.ts`
- Defines 4 viewports × 15 PAGES = 60 tests.
- Per-test: `test.skip()` unless platform=win32 AND project=chromium (per CLAUDE.md F-5 visual-baseline convention).
- F14 `/memory` mocks `/workspaces/ws_demo/memory` to empty array.
- F15 `/benchmark` mocks `/api/benchmark/**` to empty runs.
- `setViewportSize()` per viewport.
- `goto(p.path, { waitUntil: "domcontentloaded" })`.
- Sanity-test: primary testid visible.
- Vega-chart pages: wait for `vega-chart svg` count to reach `wait_svg_count` before screenshot.
- `expect(page).toHaveScreenshot(...)` with `animations: "disabled"`, `maxDiffPixelRatio: 0.01`.
- Iter-1-actual-runtime fix: F6/F8/F9 originally targeted `kept-sentence`; that testid isn't present on `/sentence_hover_test{,/evaluator_edge}` until VerifiedReportView populates. Switched to `verified-report-view`. Code reflects this.

### `*-snapshots/*.png` (NEW, 60 files)
- Initial chromium-win32 baselines committed.
- Re-runs (`npx playwright test visual_60_baselines.spec.ts --project chromium`) assert pixel-equality against these.

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint`: exit 0.
- `npx prettier --check`: exit 0.
- `npx playwright test visual_60_baselines.spec.ts --project chromium --update-snapshots`: 60/60 generated.
- `npx playwright test visual_60_baselines.spec.ts --project chromium`: 60/60 passing in 24.2s against committed baselines.

## Risks for Codex Red-Team

1. **Baseline regeneration:** any UI change to a fixture page breaks its 4 baselines (1/viewport). Expected — that's the regression detection.
2. **Cross-OS skipping:** Linux + firefox/webkit baselines are follow-up I-p2c-002d.
3. **Percy.io:** deferred to I-p2c-002b (paid SaaS).
4. **§9.4 N/A frontend.**
5. **CHARTER §3 LOC cap:** 132 net text additions. Under 200. PNG binaries ≈1.6 MB total.

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
