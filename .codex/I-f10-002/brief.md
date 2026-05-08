# Codex Brief Review — I-f10-002 (ITER 1 of 5)

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

- **Issue:** I-f10-002 — Forest plot chart spec. Scope: "spec generator + tests". Acceptance: "sample meta-analysis renders". LOC estimate 150.
- **Existing substrate:** `src/polaris_v6/charts/spec_builder.py:42` already implements `build_forest_plot(title, points, x_label) → dict` returning a Vega-Lite v5 spec with `polaris_provenance: { chart_type: "forest_plot", evidence_ids: [...] }`. `tests/v6/test_charts.py:19` covers `test_forest_plot_basic_shape` + `test_forest_plot_empty_raises`. The Python generator IS the canonical spec generator.
- **What's missing for "sample meta-analysis renders":** a demo route on the frontend that renders an actual forest-plot spec via `<VegaChart>`, plus a Playwright spec asserting the meta-analysis chart renders correctly.
- **Honest framing per CLAUDE.md §9.4:** the spec generator + tests already exist on the backend. This Issue ships the **frontend visualization substrate** for the forest-plot path: a dedicated demo route + a TypeScript helper that mirrors `build_forest_plot`'s output (so the demo isn't dependent on a live backend run) + Playwright assertions on the rendered SVG. The TS helper is honest about its substrate role: it parallels the Python generator's structure for client-side visual demonstrations.

## Plan

### Backend — additional adversarial test

1. `tests/v6/test_charts.py`:
   - Add `test_forest_plot_meta_analysis_with_negative_estimates` — exercises the SELECT-trial-style real meta-analysis input (negative estimates, asymmetric CIs) and asserts the spec's two-layer structure (rule + point) is preserved + each point's tooltip carries `evidence_id`. This locks the meta-analysis use case the acceptance criterion calls out, beyond the basic-shape test that already exists.

### Frontend

2. `web/lib/forest_plot_spec.ts` (NEW):
   - Export `ForestPlotPoint` interface mirroring `polaris_v6.charts.spec_builder.ForestPlotPoint` (label, estimate, ci_low, ci_high, evidence_id).
   - Export `buildForestPlotSpec(title, points, x_label?): VegaLiteSpec` that returns a spec equivalent to the Python builder (same `$schema`, two-layer rule+point Vega-Lite structure, `polaris_provenance: { chart_type: "forest_plot", evidence_ids }`).
   - Empty `points` throws `Error("forest plot requires at least one point")` to mirror Python `ValueError`.
   - This is substrate-honest: TS-side helper for client-side visualization demos; the canonical spec generator remains Python (used by backend `/runs/{run_id}/charts/{chart_type}`).

3. `web/app/charts_test/forest_plot/page.tsx` (NEW route):
   - Imports `buildForestPlotSpec` + sample SELECT-trial-style meta-analysis data (3 outcomes: MACE, MI, Stroke; effect estimates with 95% CIs; demo `evidence_ids`).
   - Renders `<VegaChart spec={spec}>`.
   - Honest-frame: "Sample SELECT-trial meta-analysis (demo data, demo evidence_ids); same Vega-Lite structure produced by `polaris_v6.charts.spec_builder.build_forest_plot`."

### Playwright

4. `web/tests/e2e/forest_plot_chart.spec.ts` (NEW):
   - Visit `/charts_test/forest_plot`.
   - Assert `[data-testid="vega-chart"]` visible + `svg` mounts (≤10s).
   - Assert SVG contains both `<line>` elements (rule layer for CI bars) AND `<path>` or `<symbol>` elements (point layer for point estimates). Vega rule marks render as SVG `<line>` per `vega-scenegraph/src/marks/rule.js` (will verify path during diff review); point marks render as `<path>`.
   - Assert NO `[data-testid="vega-chart-error"]`.

## Risks for Codex Red-Team

1. **Vega-Lite mark types:** rule layer in Vega-Lite v5 is rendered by Vega as `<line>` elements (vega-scenegraph rule marks). Point marks render as `<path>` (filled circle). Spec assertion validates the meta-analysis structure (CI bars + point estimates) via these two SVG element types.
2. **TS helper parity with Python:** the TS `buildForestPlotSpec` mirrors the Python `build_forest_plot` field-for-field. Both produce identical JSON shape (modulo whitespace). A future Issue could de-duplicate via a shared spec via backend `/runs/{run_id}/charts/forest_plot` fetch, but for the demo route the TS helper avoids backend coupling.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~50 LOC TS helper + ~40 LOC route + ~30 LOC spec + ~15 LOC backend test = ~135. Under 200. Within issue_breakdown LOC estimate of 150.

## Acceptance criteria

1. New backend test exercises meta-analysis input (SELECT-trial style with negative estimates + asymmetric CIs).
2. New TS helper `buildForestPlotSpec` mirrors Python `build_forest_plot` output structure.
3. New demo route `/charts_test/forest_plot` renders a sample meta-analysis chart via `<VegaChart>`.
4. Playwright spec asserts the rendered chart includes BOTH rule (CI bars) and point (estimates) marks.
5. Honest fallback: empty `points` throws (mirroring Python `ValueError`).
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
