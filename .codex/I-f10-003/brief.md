# Codex Brief Review — I-f10-003 (ITER 1 of 5)

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

- **Issue:** I-f10-003 — Comparison table chart spec. Scope: "auto-table when comparing N entities". Acceptance: "N=2,3,5 render correctly". LOC estimate 130.
- **Existing substrate:** `src/polaris_v6/charts/spec_builder.py:95` already implements `build_comparison_table(title, rows: list[ComparisonRow]) → dict` returning a Vega-Lite v5 grouped-bar spec with `polaris_provenance: { chart_type: "comparison_table", evidence_ids }`. `tests/v6/test_charts.py:43` covers `test_comparison_table_basic_shape` (3 rows). Backend canonical generator + basic test exist.
- **What's missing for "N=2,3,5 render correctly":** (a) backend tests for N=2 and N=5 (only N=3 covered); (b) frontend TS helper mirroring Python (parallel to I-f10-002 forest-plot helper); (c) demo route exercising N=2/3/5; (d) Playwright spec asserting all three Ns render.
- **Honest framing per CLAUDE.md §9.4:** Python `build_comparison_table` is canonical. This Issue ships frontend visualization substrate + N-coverage hardening on the backend test.

## Plan

### Backend — N=2 and N=5 coverage

1. `tests/v6/test_charts.py` — add two tests:
   - `test_comparison_table_n2_renders_correctly` — 2 entities × 1 metric → assert spec has 2 data rows + bar mark + grouped-by-entity Y axis.
   - `test_comparison_table_n5_renders_correctly` — 5 entities × 2 metrics → 10 data rows, color-by-metric encoding present, every row carries `evidence_id`.
   - The existing `test_comparison_table_basic_shape` covers N=3 with 1 metric; together they cover acceptance "N=2,3,5".

### Frontend

2. `web/lib/comparison_table_spec.ts` (NEW):
   - Export `ComparisonRow` interface mirroring `polaris_v6.charts.spec_builder.ComparisonRow` (entity, metric, value, evidence_id).
   - Export `buildComparisonTableSpec(title, rows): VegaLiteSpec` returning the same Vega-Lite v5 grouped-bar shape produced by the Python builder.
   - Empty rows throws `Error("comparison table requires at least one row")` mirroring Python `ValueError`.

3. `web/app/charts_test/comparison_table/page.tsx` (NEW route):
   - Render THREE `<VegaChart>` instances: N=2 (Ontario vs Quebec housing starts), N=3 (Ontario/Quebec/BC), N=5 (5 provinces × 2 metrics: starts and completions).
   - Each chart wrapped in a section with `data-testid="comparison-table-n2"`, `comparison-table-n3`, `comparison-table-n5` to make Playwright assertions distinct.
   - Honest-frame: "Sample comparison tables (demo data, demo evidence_ids); same Vega-Lite structure produced by `polaris_v6.charts.spec_builder.build_comparison_table`."

### Playwright

4. `web/tests/e2e/comparison_table_chart.spec.ts` (NEW):
   - Visit `/charts_test/comparison_table`.
   - For each of `n2`, `n3`, `n5`: locate the section, assert `[data-testid="vega-chart"]` inside it has visible svg, assert at least N graphics-symbol marks (per N count, conservative — could be more on grouped-bar with multiple metrics).
   - Use the same role-aware selector pattern as I-f10-002 (`role="graphics-object"` containers + fallback to `role="graphics-symbol"` count).
   - Assert no `[data-testid="vega-chart-error"]` rendered on the page.

## Risks for Codex Red-Team

1. **Multi-VegaChart per page:** three `<VegaChart>` instances on `/charts_test/comparison_table`. Each gets its own scoped `data-testid="vega-chart"` (locator scoping via parent section testid handles that — `section[data-testid="comparison-table-n3"] [data-testid="vega-chart"]`).
2. **Grouped-bar (N×2 metrics) at N=5:** the existing Python builder uses `color: { field: "metric", type: "nominal" }` so multiple metrics produce stacked or side-by-side bars; the TS helper mirrors this. Vega-Lite v5 default is stacking; the spec doesn't override → 5×2 = 10 datums = up to 10 bar marks.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~50 LOC TS helper + ~80 LOC route (3 sample datasets) + ~40 LOC spec + ~30 LOC backend tests = ~200. AT cap. May need to trim sample data inline or use compact array literals.

## Acceptance criteria

1. New backend tests assert N=2 and N=5 spec correctness (existing test covers N=3 — together: acceptance "N=2,3,5").
2. New `buildComparisonTableSpec` TS helper mirrors Python `build_comparison_table` field-for-field.
3. Demo route `/charts_test/comparison_table` renders 3 charts (N=2/3/5) with distinct section testids.
4. Playwright spec asserts each of N=2/3/5 charts has visible svg + at least N marks.
5. Honest fallback: empty rows throws (mirroring Python `ValueError`).
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
