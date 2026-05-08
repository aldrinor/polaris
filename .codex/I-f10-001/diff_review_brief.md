# Codex Diff Review — I-f10-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-001 — Vega-Lite renderer (react-vega + Vega-Lite v5)
**Brief:** APPROVED iter 4 (consolidated to extend existing `VegaChart`; ChartType "forest_plot" valid; error-fallback retains mount div per iter-2 P2)
**Canonical-diff-sha256:** `a564baa6fb1f5b87269f010fe377d39ce0fde9e6fa4ad23e2ef215db0f14bfc7`
**LOC:** 93 net (well under CHARTER §1 200-cap)

## Files

```
web/components/ui/vega-chart.tsx           +27 -5 (error state, data-testid, sibling alert pane, retry-friendly mount div)
web/app/charts_test/page.tsx               NEW +43 (demo route + Vega-Lite v5 sample bar chart spec with polaris_provenance)
web/tests/e2e/vega_lite_chart.spec.ts      NEW +23 (assert svg mount, path mark count > 0, no error testid)
```

## What changed

### `vega-chart.tsx` (production)
- Added `useState<string | null>` for `error`.
- `setError(null)` at start of each `useEffect` invocation (clear stale; per Codex iter-2 P2).
- `.catch` block now calls `setError(...)` only when `!cancelled` (avoid post-unmount state update).
- Render a sibling `<div data-testid="vega-chart-error" role="alert">` ABOVE the mount div when `error !== null`. Mount div remains permanently in JSX so future spec changes can re-trigger embed.
- Added `data-testid="vega-chart"` to mount div for Playwright.
- Existing API (`spec`, `className`, `onPointClick`) preserved unchanged → existing inspector consumer at `web/app/inspector/[runId]/page.tsx` continues to work without source modification.

### `charts_test/page.tsx` (NEW demo route)
- Hand-authored Vega-Lite v5 sample spec: `$schema` v5 URL; bar chart of 3 data points (POLARIS / ChatGPT DR / Gemini DR scores on "Sourcing" dimension); `width`/`height` set in spec; `polaris_provenance: { chart_type: "forest_plot", evidence_ids: ["demo-1","demo-2","demo-3"] }` (per `VegaLiteSpec` contract; "forest_plot" is one of the 3 valid `ChartType` values).
- Honest-frame copy explains "demo evidence_ids only; consumed by real forest-plot in I-f10-002."

### `vega_lite_chart.spec.ts` (Playwright)
- Visit `/charts_test`, assert `[data-testid="vega-chart"]` visible, wait for `svg` to attach (≤10s), assert `svg path` count > 0 (Vega rect marks are SVG paths per Codex iter-1 P1 verification), assert no `[data-testid="vega-chart-error"]`.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} components/**/*.{ts,tsx} tests/e2e/vega_lite_chart.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.
- Existing inspector consumer untouched (existing `<VegaChart>` callsite continues to work; new `data-testid` is metadata, no API change).

## Risks for Codex Red-Team

1. **API back-compat:** `VegaChart` props unchanged (`spec`, `className`, `onPointClick`). Existing inspector consumer (`web/app/inspector/[runId]/page.tsx`) compiles without modification.
2. **SSR safety:** `"use client"` directive preserved (line 1).
3. **LAW II honest fallback:** vega-embed catch now triggers explicit visible error pane instead of silent console.error.
4. **Cancellation guard:** `setError` only fires when `!cancelled` — no post-unmount state update.
5. **Retry-friendly:** mount div is always rendered (sibling to error pane), so future `spec` changes re-trigger `useEffect` and can recover.
6. **Vega path mark assertion:** rect marks render as SVG `<path>` (per Codex iter-1 P1 + vega-scenegraph SVGRenderer source). Spec asserts `svg path` count > 0, not `<rect>`.
7. **§9.4 N/A frontend.**
8. **CHARTER §1 LOC cap:** 93 net. Under 200.
9. **No new npm dependency:** vega-embed already in package.json.

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
