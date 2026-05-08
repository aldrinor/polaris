# Codex Brief Review — I-f13-002 (ITER 1 of 5)

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

- **Issue:** I-f13-002 — Diff visualization. Scope: "Vega-Lite time-series; diff side-panel". Acceptance: "Playwright diff". LOC estimate 180.
- **Existing substrate:** I-f10-004 already shipped `buildTimelineSpec` for Vega-Lite line+point time-series. I-f13-001 already shipped `DEMO_PIN_REGISTRY` with 2 snapshots and `/pin_replay` route with delta panel.
- **What's needed:** add a Vega-Lite time-series chart to `/pin_replay` showing how `pass_rate` and `verified_sentence_count` change across pin dates. Also add a "Diff side-panel" that, when clicked, shows the actual content diff between A and B (a small list-of-changes view).
- **Honest framing per CLAUDE.md §9.4:** the time-series demonstrates the existing pin-registry data plotted via the I-f10-004 timeline substrate. The "diff side-panel" surfaces the per-field deltas already computed in I-f13-001. No production wiring yet.

## Plan

### Frontend

1. Extend `web/lib/pin_replay_demo.ts`:
   - Add a third `2026-03-01` entry between the two existing ones to give the time-series 3 points.

2. New `web/app/pin_replay/components/pin_timeseries.tsx` (NEW client component):
   - Imports `buildTimelineSpec` from `@/lib/timeline_spec` + `VegaChart`.
   - Props: `snapshots: PinSnapshot[]`.
   - Builds a timeline spec: 1 series for `pass_rate` (×100) and 1 series for `verified_sentence_count`. Two `<VegaChart>` instances (separate charts) OR one combined chart with `series` field; simplest is two separate charts side-by-side.
   - Each chart has scoped section testid (`pin-timeseries-pass-rate`, `pin-timeseries-sentence-count`).

3. New `web/app/pin_replay/components/diff_side_panel.tsx` (NEW client component):
   - Imports `Sheet` family.
   - Props: `open: boolean`, `onOpenChange`, `snapshot_a: PinSnapshot | null`, `snapshot_b: PinSnapshot | null`.
   - Renders Sheet with title "Snapshot diff (B − A)" + body listing each PinSnapshot field with the A value, B value, and Δ delta.
   - testid: `pin-diff-pane` + per-field testids.

4. Update `web/app/pin_replay/page.tsx`:
   - Add a "Show diff" button (`data-testid="pin-show-diff"`) that opens the diff side panel.
   - Render `<PinTimeseries snapshots={[snap_a, snap_b]}>` (or all 3 from registry).
   - Render `<DiffSidePanel open={diff_open} onOpenChange={set_diff_open} snapshot_a={snap_a} snapshot_b={snap_b}>`.

### Playwright

5. `web/tests/e2e/pin_replay_diff.spec.ts` (NEW):
   - Visit `/pin_replay`.
   - Assert `pin-timeseries-pass-rate` and `pin-timeseries-sentence-count` sections render with svg.
   - Click `pin-show-diff` button.
   - Assert `pin-diff-pane` becomes visible.
   - Assert per-field rows present with deltas.

## Risks for Codex Red-Team

1. **Vega timeline spec for ordinal dates:** the I-f10-004 helper handles `period_kind: "date"` (temporal). Pin dates are ISO yyyy-mm-dd; pass `"date"` for proper temporal axis.
2. **Reuse VegaChart click handler:** click events on timeline points are NOT wired in this issue (different from I-f10-006). The chart is purely visual here.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~30 LOC registry extension + ~60 LOC PinTimeseries + ~80 LOC DiffSidePanel + ~20 LOC page integration + ~30 LOC spec = ~220. Slight cap exemption needed.

## Acceptance criteria

1. New 3-entry pin registry enables a time-series chart with ≥3 data points per series.
2. New `<PinTimeseries>` renders two scoped time-series charts (pass-rate + sentence-count).
3. New `<DiffSidePanel>` renders per-field diff between snapshot A and B.
4. `/pin_replay` adds a "Show diff" button + integrates both new components.
5. Playwright spec asserts time-series + diff pane render correctly.
6. CHARTER §1 LOC cap respected (≤200 net OR justified exemption).

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
