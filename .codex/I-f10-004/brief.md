# Codex Brief Review — I-f10-004 (ITER 1 of 5)

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

- **Issue:** I-f10-004 — Timeline chart spec. Scope: "time-series Vega-Lite". Acceptance: "sample timeline renders". LOC estimate 130.
- **Existing substrate:** `src/polaris_v6/charts/spec_builder.py:134` already implements `build_timeline(title, points, period_kind="quarter|date|year") → dict` returning a Vega-Lite v5 line+point spec with `polaris_provenance: { chart_type: "timeline", period_kind, evidence_ids }`. `tests/v6/test_charts.py:58` covers `test_timeline_quarter_kind` AND `test_timeline_date_kind_uses_temporal`. Backend canonical generator + tests exist.
- **What's missing for "sample timeline renders":** frontend TS helper mirroring Python builder + demo route + Playwright assertion (parallel to I-f10-002 forest plot + I-f10-003 comparison table pattern).
- **Honest framing per CLAUDE.md §9.4:** Python `build_timeline` is canonical. This Issue ships frontend visualization substrate.

## Plan

### Frontend

1. `web/lib/timeline_spec.ts` (NEW):
   - Export `TimelinePoint` interface mirroring `polaris_v6.charts.spec_builder.TimelinePoint` (period: string, value: number, series: string, evidence_id: string).
   - Export type `TimelinePeriodKind = "date" | "quarter" | "year"`.
   - Export `buildTimelineSpec(title, points, period_kind = "quarter"): VegaLiteSpec` mirroring the Python builder: `mark: { type: "line", point: true }`, `encoding.x.type` = `"temporal"` if period_kind==="date" else `"ordinal"`, color by series, tooltip per field, `polaris_provenance: { chart_type: "timeline", period_kind, evidence_ids }`.
   - Empty `points` throws `Error("timeline requires at least one point")` mirroring Python `ValueError`.

2. `web/app/charts_test/timeline/page.tsx` (NEW route):
   - Render TWO `<VegaChart>` instances (illustrating both period kinds):
     - Quarter timeline: 4 quarterly Suncor GHG-intensity points (2010-Q1 → 2023-Q4).
     - Date timeline: 4 ECCC monthly emissions points.
   - Section testids `timeline-quarter` and `timeline-date`.
   - Honest-frame copy: "Sample timelines (demo data, demo evidence_ids); same Vega-Lite structure produced by `polaris_v6.charts.spec_builder.build_timeline`."

### Playwright

3. `web/tests/e2e/timeline_chart.spec.ts` (NEW):
   - Visit `/charts_test/timeline`.
   - For each of `timeline-quarter` and `timeline-date`: locate section, assert vega-chart visible, svg attaches, at least 4 graphics-symbol marks (one per data point).
   - Assert no `[data-testid="vega-chart-error"]`.

## Risks for Codex Red-Team

1. **Period type encoding:** the Python builder uses `temporal` for `date` and `ordinal` for `quarter`/`year`. The TS helper preserves this branching exactly.
2. **`mark: { type: "line", point: true }`:** Vega-Lite v5 idiom for line chart with rendered point markers. Renders BOTH a `<path>` for the line AND `<path>` symbols for points; expecting at least N point marks (one per datum) keeps the assertion conservative.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~50 LOC TS helper + ~70 LOC route (2 sample datasets) + ~30 LOC spec = ~150. Under 200. Within issue_breakdown LOC estimate of 130 + slack.

## Acceptance criteria

1. New TS helper `buildTimelineSpec` mirrors Python `build_timeline` field-for-field, including `period_kind`-driven encoding.x.type branching.
2. Demo route `/charts_test/timeline` renders 2 sample charts (quarter + date period_kind) with distinct section testids.
3. Playwright spec asserts both timelines render with ≥4 graphics-symbol marks each + no error testid.
4. Honest fallback: empty points throws (mirroring Python `ValueError`).
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
