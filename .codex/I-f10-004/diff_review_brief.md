# Codex Diff Review — I-f10-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-004 — Timeline chart spec
**Brief:** APPROVED iter 1 (0/0/0/0)
**Canonical-diff-sha256:** `f49f5e0727a5143a28d5af98456a51b43468133cac14b9be9fc390bb80fb3ed1`
**LOC:** ~140 net (under CHARTER §1 200-cap)

## Files

```
web/lib/timeline_spec.ts                  NEW +63 (TS helper mirroring Python build_timeline)
web/app/charts_test/timeline/page.tsx     NEW +63 (demo route + 2 sample timelines: quarter + date)
web/tests/e2e/timeline_chart.spec.ts      NEW +21 (looped assertion over both period_kind sections)
```

## What changed

### `timeline_spec.ts` (NEW)
- `TimelinePoint` interface mirroring Python `polaris_v6.charts.spec_builder.TimelinePoint`.
- `TimelinePeriodKind = "date" | "quarter" | "year"`.
- `buildTimelineSpec(title, points, period_kind = "quarter")` returns Vega-Lite v5 line+point spec; `encoding.x.type` = `"temporal"` if period_kind==="date" else `"ordinal"` (mirrors Python branching at `spec_builder.py:142`).
- `polaris_provenance` includes `period_kind` field.
- Empty points → throws `Error("timeline requires at least one point")`.

### `charts_test/timeline/page.tsx` (NEW route)
- Two `<VegaChart>` instances scoped via section testids `timeline-quarter` and `timeline-date`.
- Quarter sample: 4 Suncor GHG-intensity points (2010-Q1 → 2023-Q4).
- Date sample: 4 ECCC monthly emissions points (2024-01-01 → 2024-04-01).
- Honest-frame copy: "same Vega-Lite structure produced by `polaris_v6.charts.spec_builder.build_timeline`."

### `timeline_chart.spec.ts` (Playwright)
- Loop over both section testids; each section asserts vega-chart visible + svg attaches + ≥4 graphics-symbol marks (one per data point).
- Asserts no error testid on page.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} lib/**/*.ts tests/e2e/timeline_chart.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.
- Existing backend `test_timeline_quarter_kind` + `test_timeline_date_kind_uses_temporal` continue to cover the canonical Python builder; this Issue ships only the frontend visualization substrate.

## Risks for Codex Red-Team

1. **TS helper parity with Python:** field-for-field equivalent to `build_timeline`, including the `period_kind`-driven encoding.x.type branching (`temporal` vs `ordinal`).
2. **Mark `{ type: "line", point: true }`:** Vega-Lite v5 idiom for line chart with rendered point markers; renders both line `<path>` and per-datum point `<path>` symbols. The 4-mark assertion is a conservative lower bound.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 140 net. Under 200.

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
