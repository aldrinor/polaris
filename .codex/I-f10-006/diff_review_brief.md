# Codex Diff Review — I-f10-006 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-006 — Click-through-to-source-data
**Brief:** APPROVED iter 2 (Codex iter-1 P1 — full source span fields — applied; iter-2 P2 testid placement applied)
**Canonical-diff-sha256:** `7de19ccf4588295f98bd32b7f3d8b21f49d1a40595eabc05f04f9e754cae51e2`
**LOC:** 235 net (over 200; CHARTER §1 LOC cap exemption justified)

## CHARTER §1 LOC cap exemption

235 net total. Substance breakdown:
- 91 LOC ChartSourceInspector — single-responsibility Sheet pane mirroring EvaluatorPane / MultiSourcePanel structure with TIER_TONE map + 4 testid'd rows.
- 107 LOC click_through demo route — 70 LOC are SOURCE_REGISTRY (3 entries × ~15 LOC each: evidence_id + url + tier + multi-line excerpt) plus the chart spec import + state plumbing.
- 37 LOC Playwright spec — role-aware mark locator with fallback + 5 assertions.

Issue breakdown estimate was 110 LOC; actual 235 reflects (a) Codex iter-1 P1 fix to render full source span (URL + tier + excerpt, not just evidence_id) which expanded the pane structure and (b) the SOURCE_REGISTRY adding ~50 LOC of mock data needed to honestly demonstrate the click-through. ~35 LOC over the 200 cap; data + assertions only, no abstractions.

## Files

```
web/app/charts_test/components/chart_source_inspector.tsx NEW +91 (Sheet pane: evidence_id + tier badge + url link + excerpt)
web/app/charts_test/click_through/page.tsx                NEW +107 (forest-plot spec + SOURCE_REGISTRY + click handler)
web/tests/e2e/chart_click_through.spec.ts                 NEW +37 (role-aware click + URL/tier/excerpt assertions)
```

## What changed

### `chart_source_inspector.tsx` (NEW)
- Exports `ChartDatumSource` type (`evidence_id`, `url`, `tier: T1|T2|T3`, `excerpt`).
- Renders Sheet with `data-testid="chart-source-pane"` on `SheetContent` per Codex iter-2 P2.
- Body: evidence_id row + tier badge + URL link (`target="_blank" rel="noopener noreferrer"`) + excerpt blockquote (≤240 chars).
- Honest fallback: `source === null` renders `data-testid="chart-source-pane-empty"` with explicit "No datum selected." text per LAW II.

### `click_through/page.tsx` (NEW route)
- `"use client"` directive.
- Reuses `buildForestPlotSpec` from I-f10-002.
- `SOURCE_REGISTRY` keyed by demo evidence_id (3 entries: MACE / MI / Stroke).
- `onPointClick={(datum) => { resolve datum.evidence_id, lookup SOURCE_REGISTRY, open inspector }}`.
- Honest-frame copy: "in production, this would fetch from `/runs/{run_id}/sources/{evidence_id}` per the I-f10-005 polaris_provenance contract."

### `chart_click_through.spec.ts` (Playwright)
- Role-aware mark locator: `g[role="graphics-object"][aria-roledescription="symbol mark container"] [role="graphics-symbol"]` `.first()`.
- Fallback: `svg [role="graphics-symbol"]` `.first()` (matches I-f10-002 pattern).
- After click: asserts `chart-source-pane` visible + `chart-source-pane-evidence-id` contains "demo-clin-" + URL href matches `https://example.org/select-trial-` + tier badge contains "T1" + excerpt contains MACE/MI/Stroke string + no error testid.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} tests/e2e/chart_click_through.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.

## Risks for Codex Red-Team

1. **Vega click handler:** existing `VegaChart.onPointClick` (line 45-49) attaches via `view.addEventListener("click", (event, item) => ...)` — already validated by I-f10-001 ship.
2. **SOURCE_REGISTRY shape:** demo-only; production fetch would replace this. Honestly framed in route copy.
3. **Click target stability:** role-aware locator with fallback handles Vega version drift.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap exemption (justified above):** 235 net, 35 LOC over 200; demo data + acceptance test substrate dominate.

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
