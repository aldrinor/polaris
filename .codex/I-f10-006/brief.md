# Codex Brief Review — I-f10-006 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (source-span acceptance):** the iter-1 plan only rendered evidence_id text — that doesn't satisfy "source span" semantics. Iter-2 plan: demo route exports `SOURCE_REGISTRY: Record<string, { url: string; tier: "T1"|"T2"|"T3"; excerpt: string }>` keyed by demo evidence_id. The click handler resolves `datum.evidence_id` against the registry and passes the FULL source object to the inspector pane. The pane renders URL, tier badge, and excerpt blockquote. Playwright asserts all three fields visible.
- **P2 fix (click selector):** use Vega's role-aware container `g[role="graphics-object"][aria-roledescription="symbol mark container"]` and `.first()` (matching the I-f10-002 forest-plot spec pattern with fallback to `[role="graphics-symbol"]`).
- **P2 fix (callback wording):** the brief's `setOpen(true) + setDatum(datum)` shorthand becomes a proper arrow function in implementation: `(datum) => { setDatum(datum); setOpen(true); }`.

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

- **Issue:** I-f10-006 — Click-through-to-source-data. Scope: "click chart point → opens Inspector with source span". Acceptance: "Playwright click-through". LOC estimate 110.
- **Existing substrate:**
  - `web/components/ui/vega-chart.tsx` already accepts `onPointClick(datum)` callback (per I-f10-001 wiring). When user clicks a Vega datum, vega-embed's `view.addEventListener("click", ...)` fires and the callback receives the datum (which includes `evidence_id` per the spec_builder.py tooltip encoding).
  - `web/app/inspector/[runId]/page.tsx` already consumes `<VegaChart>` with `onPointClick`.
- **What's missing for "click chart point → opens Inspector with source span":** a demo route that wires the click event to a `<SentenceInspector>`-style pane. Plus Playwright assertion that clicking a datum opens a side pane showing the source span (URL, tier, excerpt).
- **Honest framing per CLAUDE.md §9.4:** the click→open-pane substrate already exists in inspector page. This Issue ships a self-contained `/charts_test/click_through` demo + Playwright spec, plus a small `<ChartSourceInspector>` Sheet pane that any chart consumer can use.

## Plan

### Frontend

1. New component `web/app/charts_test/components/chart_source_inspector.tsx` (NEW client component):
   - Imports `Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle`.
   - Define exported type `ChartDatumSource = { evidence_id: string; url: string; tier: "T1"|"T2"|"T3"; excerpt: string }`.
   - Props: `open: boolean`, `onOpenChange(open: boolean)`, `source: ChartDatumSource | null`.
   - Renders a Sheet (right side, ~40% width) with header "Chart datum source" + description "Source span derived from clicked Vega datum." Body when `source !== null`:
     - `evidence_id` row (`data-testid="chart-source-pane-evidence-id"`).
     - `url` link (`data-testid="chart-source-pane-url"`, target=_blank, rel=noopener noreferrer).
     - `tier` badge (`data-testid="chart-source-pane-tier"`).
     - `excerpt` blockquote (`data-testid="chart-source-pane-excerpt"`, italic, ≤240 chars).
   - Honest fallback: if `source === null`, render `<div data-testid="chart-source-pane-empty">No datum selected.</div>` per LAW II.

2. New demo route `web/app/charts_test/click_through/page.tsx` (NEW, `"use client"`):
   - Defines `SOURCE_REGISTRY: Record<string, ChartDatumSource>` keyed by demo evidence_id (3 entries — MACE/MI/Stroke for SELECT-trial mock).
   - Reuses `buildForestPlotSpec` from `@/lib/forest_plot_spec` (already shipped in I-f10-002).
   - State: `[source, setSource] = useState<ChartDatumSource | null>(null)`, `[open, setOpen] = useState(false)`.
   - `<VegaChart spec={spec} onPointClick={(datum) => { const eid = datum.evidence_id as string | undefined; if (eid && SOURCE_REGISTRY[eid]) { setSource(SOURCE_REGISTRY[eid]); setOpen(true); } }}>`.
   - Renders `<ChartSourceInspector open={open} onOpenChange={setOpen} source={source}>`.
   - Honest-frame copy: "Click any chart point to open the source-span inspector. evidence_id resolves against a demo SOURCE_REGISTRY (in production, this would fetch from `/runs/{run_id}/sources/{evidence_id}` per the I-f10-005 polaris_provenance contract)."

### Playwright

3. `web/tests/e2e/chart_click_through.spec.ts` (NEW):
   - Visit `/charts_test/click_through`.
   - Wait for `[data-testid="vega-chart"] svg` visible.
   - Locate a Vega graphics-symbol mark via `g[role="graphics-object"][aria-roledescription="symbol mark container"] [role="graphics-symbol"]` `.first()`. Fallback: `svg [role="graphics-symbol"]` `.first()`.
   - Click the located mark.
   - Assert `[data-testid="chart-source-pane"]` becomes visible.
   - Assert `[data-testid="chart-source-pane-evidence-id"]` contains the expected demo evidence_id.
   - Assert `[data-testid="chart-source-pane-url"]` has `href` matching demo URL.
   - Assert `[data-testid="chart-source-pane-tier"]` text matches "T1" / "T2" / "T3" badge.
   - Assert `[data-testid="chart-source-pane-excerpt"]` contains the expected excerpt fragment.
   - Assert no `[data-testid="vega-chart-error"]`.

## Risks for Codex Red-Team

1. **Vega click event contract:** vega-embed's `view.addEventListener("click", (event, item) => ...)` fires when user clicks a mark. The `item.datum` carries the row dict. The existing `VegaChart` already handles this (line 45-49). Demo route just consumes the callback.
2. **Playwright click target:** `svg [role="graphics-symbol"]:first-child` selects the first mark. Vega may render the mark inside a `<g>` group — Playwright's `.click()` should still trigger the synthetic click handler attached by vega-embed.
3. **Click event timing:** vega-embed attaches its click listener after the async render completes. Spec must `waitFor svg first().toBeVisible({ timeout: 10_000 })` BEFORE clicking, or risk clicking an unattached element.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~70 LOC ChartSourceInspector + ~50 LOC demo route + ~30 LOC spec = ~150. Under 200. Within issue_breakdown LOC estimate of 110 + slack.

## Acceptance criteria

1. New `<ChartSourceInspector>` Sheet pane component renders evidence_id, url, tier badge, excerpt blockquote (per Codex iter-1 P1 — full source span, not just evidence_id).
2. Demo route `/charts_test/click_through` defines a `SOURCE_REGISTRY` keyed by demo evidence_id; click handler resolves datum.evidence_id and opens the inspector with the resolved source object.
3. Playwright spec clicks a Vega graphics-symbol mark via role-aware locator (with fallback) and asserts evidence_id, url href, tier badge text, excerpt visible.
4. Honest fallback: `source === null` renders an explicit empty state, not a silent empty pane.
5. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-5.

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
