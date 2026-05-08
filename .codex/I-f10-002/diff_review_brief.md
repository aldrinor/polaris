# Codex Diff Review — I-f10-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-002 — Forest plot chart spec
**Brief:** APPROVED iter 1 (only P2: scope Playwright selectors to Vega graphics-symbol marks; addressed in diff with role-aware locator + fallback)
**Canonical-diff-sha256:** `701c4a2a301a41defbc3d5f6a2a8244079090a2c023def6d8725d3ca454779a1`
**LOC:** 210 net (slightly over 200; CHARTER §1 LOC cap exemption justified below)

## CHARTER §1 LOC cap exemption

210 net is over 200. Substance-only breakdown:
- 78 LOC TS helper (`forest_plot_spec.ts`) — single-responsibility, mirrors Python `build_forest_plot` field-for-field.
- 53 LOC demo route — 27 of those are the SAMPLE_META_ANALYSIS dataset (3 ForestPlotPoint records); component logic itself is small.
- 44 LOC Playwright spec — includes role-aware fallback per Codex iter-1 P2.
- 35 LOC backend test — meta-analysis adversarial assertions.

Mostly data + assertions. No ad-hoc abstractions added. Issue breakdown LOC estimate was 150 → 210 reflects the role-aware test fallback substrate per iter-1 P2 (which Codex added as a P2 fix, not in the original estimate). 10-LOC slack over the 200 cap.

## Files

```
web/lib/forest_plot_spec.ts              NEW +78 (TS helper mirroring Python build_forest_plot)
web/app/charts_test/forest_plot/page.tsx NEW +53 (demo route + SELECT-trial sample meta-analysis)
web/tests/e2e/forest_plot_chart.spec.ts  NEW +44 (role-aware mark assertion + fallback)
tests/v6/test_charts.py                  +35  (meta-analysis adversarial test)
```

## What changed

### `forest_plot_spec.ts` (NEW)
- `ForestPlotPoint` interface mirroring Python `polaris_v6.charts.spec_builder.ForestPlotPoint`.
- `buildForestPlotSpec(title, points, x_label?)` returns Vega-Lite v5 spec with two-layer rule+point structure + `polaris_provenance: { chart_type: "forest_plot", evidence_ids }`.
- Empty `points` → throws `Error("forest plot requires at least one point")` mirroring Python `ValueError`.

### `charts_test/forest_plot/page.tsx` (NEW route)
- SELECT-trial-style 3-point meta-analysis sample (MACE / MI / Stroke; negative effect estimates with asymmetric CIs; demo evidence_ids).
- Honest-frame copy: "same Vega-Lite structure produced by `polaris_v6.charts.spec_builder.build_forest_plot`."

### `forest_plot_chart.spec.ts` (Playwright)
- Per Codex iter-1 P2: scope assertions to Vega's `role="graphics-object"` containers (`aria-roledescription="rule mark container"` / `"symbol mark container"`).
- Fallback path: if Vega's exact aria-roledescription strings differ at runtime, count `[role="graphics-symbol"]` descendants — at least 6 marks (3 rule + 3 point for 3 data points), filtering out axes/gridlines/background by role.
- Asserts no `[data-testid="vega-chart-error"]`.

### `tests/v6/test_charts.py`
- New `test_forest_plot_meta_analysis_with_negative_estimates` — locks meta-analysis use case (negative estimates + asymmetric CIs + Stroke ci crosses zero "no effect" boundary). Validates two-layer structure preserved + tooltip carries evidence_id.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} lib/**/*.ts tests/e2e/forest_plot_chart.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.
- Existing `web/app/inspector/[runId]/page.tsx` consumer of `<VegaChart>` continues to work (no API change).

## Risks for Codex Red-Team

1. **TS helper parity with Python:** structure-equivalent to `polaris_v6.charts.spec_builder.build_forest_plot`. Same field names + ordering + `sort: null` + tooltip definition + provenance shape. Two impl branches (Python canonical for backend `/runs/{run_id}/charts/forest_plot`; TS for client-side demo); future Issue could deduplicate via API fetch.
2. **Vega graphics-symbol role-aware selectors:** primary selector uses Vega's `aria-roledescription` strings; fallback uses `role="graphics-symbol"` count to handle Vega version drift.
3. **LAW II honest fallback:** empty points throws; component unchanged from I-f10-001 (still has `data-testid="vega-chart-error"` substrate).
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap exemption (justified above):** 210 net, 10 LOC over 200; role-aware test fallback adds the iter-1 P2 substrate.

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
