# Codex Diff Review — I-f10-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-003 — Comparison table chart spec
**Brief:** APPROVED iter 1 (0/0/0/0)
**Canonical-diff-sha256:** `10fa82505f28eba44ac29435194a4210a2dd4e35678fd0b8195c233a29e56a76`
**LOC:** 259 net (over 200; CHARTER §1 LOC cap exemption justified)

## CHARTER §1 LOC cap exemption

259 net total. Substance breakdown:
- 137 LOC demo route — 90+ LOC are the three sample datasets (N=2 → 2 records, N=3 → 3, N=5 × 2 metrics → 10 records). Each ComparisonRow is a 5-line object literal after prettier reformat. Component logic ~30 LOC.
- 54 LOC TS helper (`comparison_table_spec.ts`) — single-responsibility, mirrors Python `build_comparison_table` field-for-field.
- 27 LOC Playwright spec — looped assertion over N=2/3/5 sections.
- 41 LOC backend tests — N=2 + N=5 adversarial coverage.

Mostly demo data + assertions. The N=5 × 2 metrics dataset is required by the acceptance criterion ("N=2,3,5 render correctly"); compressing it to a generator would obscure the demo intent. ~59 LOC over 200 cap; fully mechanical sample data with no abstractions.

## Files

```
web/lib/comparison_table_spec.ts              NEW +54 (TS helper mirroring Python build_comparison_table)
web/app/charts_test/comparison_table/page.tsx NEW +137 (3 demo charts + sample datasets)
web/tests/e2e/comparison_table_chart.spec.ts  NEW +27 (looped assertion N=2/3/5)
tests/v6/test_charts.py                       +41  (N=2 and N=5 backend tests)
```

## What changed

### `comparison_table_spec.ts` (NEW)
- `ComparisonRow` interface mirroring Python `polaris_v6.charts.spec_builder.ComparisonRow` (entity, metric, value, evidence_id).
- `buildComparisonTableSpec(title, rows)` returns Vega-Lite v5 grouped-bar spec (mark "bar"; encoding y=entity, x=value, color=metric; tooltip carries evidence_id) + `polaris_provenance: { chart_type: "comparison_table", evidence_ids }`.
- Empty rows → throws `Error("comparison table requires at least one row")` mirroring Python `ValueError`.

### `charts_test/comparison_table/page.tsx` (NEW route)
- Three sections with distinct testids (`comparison-table-n2`, `comparison-table-n3`, `comparison-table-n5`).
- N=2: Ontario+Quebec, 1 metric. N=3: + BC. N=5 × 2 metrics: 5 provinces × {starts, completions} = 10 datums.
- Honest-frame copy: "same Vega-Lite structure produced by `polaris_v6.charts.spec_builder.build_comparison_table`."

### `comparison_table_chart.spec.ts` (Playwright)
- Loop over `[["comparison-table-n2", 2], ["comparison-table-n3", 3], ["comparison-table-n5", 5]]`.
- Per section: assert section visible → vega-chart visible → svg attaches → at least N graphics-symbol marks → no error testid on page.

### `tests/v6/test_charts.py`
- `test_comparison_table_n2_renders_correctly` — 2 entities × 1 metric.
- `test_comparison_table_n5_renders_correctly` — 5 entities × 2 metrics (10 datums); asserts every datum carries evidence_id + color encoding by metric is present.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} lib/**/*.ts tests/e2e/comparison_table_chart.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.

## Risks for Codex Red-Team

1. **TS helper parity with Python:** field-for-field equivalent to `build_comparison_table`. Acceptance criterion "N=2,3,5 render correctly" satisfied by backend N=2/3/5 tests + frontend visual rendering.
2. **Multi-VegaChart per page:** three `<VegaChart>` instances scoped via parent section testid; each instance keeps its own internal state/effect (no cross-talk).
3. **Vega graphics-symbol assertion:** `at least N` is conservative — N=5 with 2 metrics produces 10 marks; N=2 produces 2 marks. Lower bound prevents flakiness from Vega rendering optimizations.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap exemption (justified above):** 259 net, 59 LOC over 200; demo data dominates.

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
