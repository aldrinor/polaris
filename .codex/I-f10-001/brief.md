# Codex Brief Review — I-f10-001 (ITER 4 of 5)

## Iter 4 changes per Codex iter 3

- **P1 fix (ChartType):** the existing `ChartType` enum at `@/lib/api` is `"forest_plot" | "comparison_table" | "timeline"`. The demo spec uses `chart_type: "forest_plot"` (simplest valid value; this Issue is just the renderer substrate, NOT the forest plot spec — that's I-f10-002).

## Iter 3 changes per Codex iter 2

- **P1 fix (VegaLiteSpec.polaris_provenance):** the typed `VegaLiteSpec` (in `@/lib/api`) requires `polaris_provenance: { chart_type, evidence_ids }`. The demo sample spec MUST include this field. Iter-3 plan: demo spec sets `polaris_provenance: { chart_type: "tier_mix", evidence_ids: ["demo-1", "demo-2", "demo-3"] }` (chart_type one of the valid `ChartType` values; evidence_ids are demo placeholders, honest-framed in the page header).
- **P2 fix (error retry):** revise the error-fallback to NOT remove the mount div. Instead: render the error pane ABOVE the mount div, keep the mount div present so future `spec` changes can re-trigger `useEffect`. Clear `error` at the start of each `useEffect` invocation. Guard `setError` with the existing `cancelled` flag (don't update state after unmount).

## Iter 2 changes per Codex iter 1

- **P2 fix (existing renderer):** `web/components/ui/vega-chart.tsx` already exists (with `"use client"`, vega-embed dynamic call, finalize cleanup, onPointClick wiring). Pivot iter 2 plan: do NOT create a parallel `vega_lite_chart.tsx`. Instead, **extend the existing `VegaChart`** with the error-fallback substrate that's currently missing, plus the demo route + Playwright assertion. This consolidates instead of forking the renderer (Codex iter-1 P2).
- **P1 fix (use client):** existing `vega-chart.tsx:1` already has `"use client"`. Issue resolved by pivoting to extend the existing component.
- **P1 fix (svg path vs rect):** Codex iter-1 verified Vega rect marks render as `<path>` elements (`vega-scenegraph/src/marks/rect.js`). Spec now asserts `[data-testid="vega-chart"] svg path` count > 0, not `<rect>`.
- **P2 fix (loose type):** `VegaLiteSpec` is already exported from `@/lib/api`; no internal `vega-lite/build/src/spec` path needed.
- **P2 fix (cancellation guard):** existing component already has `cancelled` flag + `viewToFinalize?.finalize()` on cleanup. Already correct.
- **P2 fix (width/height):** existing API has no width/height props — width/height should be expressed in the **Vega-Lite spec** itself (`width: 600, height: 300` top-level fields), which is the canonical Vega-Lite way. Drop the props from the new API; the demo spec sets them inline.
- **P2 fix (silent fallback per LAW II):** existing `.catch((err) => { console.error(err) })` is a silent fallback (LAW II violation — fail loudly). Iter 2 plan: add `error: string | null` React state; on catch, `setError(err.message)`; render `<div data-testid="vega-chart-error" role="alert">Vega-Lite render failed: {error}</div>` instead of empty mount div.

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

- **Issue:** I-f10-001 — Vega-Lite renderer (per breakdown text "react-vega + Vega-Lite v5"; scope: "wire react-vega"; acceptance: "sample chart renders"; LOC estimate 120).
- **Substrate:** `vega-embed: ^7.1.0` is ALREADY in `web/package.json` dependencies. Vega-embed is the official upstream library that takes a Vega-Lite v5 spec + a DOM element and renders the chart. **react-vega is a wrapper around vega/vega-lite that we can avoid in favour of vega-embed-direct mounting via a `useRef` + `useEffect`** — this saves the dep cost and keeps bundle size down. The issue title's "react-vega + Vega-Lite v5" describes upstream tooling intent; the acceptance criterion ("sample chart renders") is satisfied by either path. Vega-Lite v5 specs work with vega-embed transparently.
- **Honest framing per CLAUDE.md §9.4:** this Issue ships the renderer SUBSTRATE — a `<VegaLiteChart spec={...}>` component + sample chart on a demo route + Playwright assertion. No production wiring into the verified-report flow yet (that is a later F10 issue, e.g., I-f10-002 forest plot, I-f10-003+ specific chart specs). Substrate now; consumers later.

## Plan

### Frontend

1. Extend `web/components/ui/vega-chart.tsx` (existing component):
   - Add `data-testid="vega-chart"` to the mount div (already an unkeyed `<div ref>`; this exposes it for Playwright).
   - Add React state `error: string | null` (initialized null).
   - In the `.catch((err) => ...)` branch, replace the silent `console.error` with `setError(err instanceof Error ? err.message : String(err))`. Keep the `console.error` AS WELL for dev visibility, but the user-visible substrate is now an explicit error pane (LAW II).
   - At the start of each `useEffect` invocation: `setError(null)` (clear stale errors so future spec changes can re-attempt).
   - On `.catch`: only call `setError(...)` if `!cancelled` (guard against unmount race).
   - In the render JSX: render `<div data-testid="vega-chart">` (mount target, ALWAYS present so future `useEffect` can re-mount) with the error pane rendered as a SIBLING above it: `{error !== null && <div data-testid="vega-chart-error" role="alert" className="...">Vega-Lite render failed: {error}</div>}`. Keeping the mount div present per Codex iter-2 P2.
   - All existing API (props `spec`, `className`, `onPointClick`) preserved unchanged — back-compat with `web/app/inspector/[runId]/page.tsx` consumer.

2. New demo route `web/app/charts_test/page.tsx`:
   - Renders ONE `<VegaChart>` with a hand-authored Vega-Lite v5 sample spec — a small bar chart of 3 data points (mock benchmark scores). The spec sets `$schema`, `width: 600`, `height: 300`, `data.values`, `mark: "bar"`, `encoding`, AND `polaris_provenance: { chart_type: "forest_plot", evidence_ids: ["demo-1","demo-2","demo-3"] }` (per VegaLiteSpec contract; "forest_plot" is one of the three valid `ChartType` values per `@/lib/api`. We use it as the simplest valid placeholder — the actual forest-plot SPEC is I-f10-002, while THIS Issue ships only the renderer substrate exercised by a generic bar chart).
   - Honest-frame: a small `<p>` above states "Sample chart — demo evidence_ids only; renders the Vega-Lite v5 substrate (consumed by the real forest-plot spec in I-f10-002)."
   - Route path `/charts_test`.

### Playwright

3. `web/tests/e2e/vega_lite_chart.spec.ts` (NEW):
   - Visit `/charts_test`.
   - Wait for `[data-testid="vega-chart"]` visible.
   - Wait for `[data-testid="vega-chart"] svg` element to attach (vegaEmbed with `renderer: "svg"` mounts an SVG root after the async embed resolves).
   - Assert `[data-testid="vega-chart"] svg path` has count > 0 (Vega rect marks render as `<path>`, per Codex iter-1 P1 verification).
   - Assert NO `[data-testid="vega-chart-error"]` rendered.

## Risks for Codex Red-Team

1. **`vega-embed` is the one we already have:** confirmed in `web/package.json` line ~"vega-embed". No new dependency added; bundle size impact is zero-delta from current state.
2. **SSR safety:** vega-embed depends on browser globals (canvas, D3 DOM). The component `useEffect` defers import to client-only mount; the `<div ref>` SSR-renders empty.
3. **Vega-Lite v5 spec format:** the sample spec is hand-authored against v5 docs (`$schema: "https://vega.github.io/schema/vega-lite/v5.json"`).
4. **Honest fallback per LAW II:** when vega-embed throws, we render an explicit error message, not a silent empty chart.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap:** estimated ~80 LOC component + ~30 LOC route + sample spec + ~25 LOC spec = ~135. Under 200. Within issue_breakdown LOC estimate of 120 + slack.

## Acceptance criteria

1. Existing `VegaChart` component (already client + SSR-safe + cancellation guarded) gains an explicit error-fallback substrate per LAW II.
2. `VegaChart` mount div has `data-testid="vega-chart"` for Playwright.
3. On vega-embed catch, `<div data-testid="vega-chart-error" role="alert">` renders the error message instead of an empty mount div.
4. Demo route `/charts_test` renders `<VegaChart>` with a hand-authored Vega-Lite v5 sample spec (bar chart, 3 data points, `width: 600`, `height: 300`).
5. Playwright spec asserts `[data-testid="vega-chart"] svg` attaches + `svg path` count > 0 (Vega rect marks render as SVG `<path>`) + no error testid.
6. CHARTER §1 LOC cap respected (≤200 net). No new npm dependency added (vega-embed already in package.json). Existing inspector consumer at `web/app/inspector/[runId]/page.tsx` continues to work (testid added; existing API preserved).

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
