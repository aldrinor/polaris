/**
 * I-f10-002: TypeScript helper that mirrors `polaris_v6.charts.spec_builder.build_forest_plot`
 * for client-side visualization demos. Canonical spec generator remains the
 * Python builder; the backend route `/runs/{run_id}/charts/forest_plot` returns
 * specs of the same shape this helper produces.
 */

import type { VegaLiteSpec } from "@/lib/api";

export const VEGA_LITE_SCHEMA_URL =
  "https://vega.github.io/schema/vega-lite/v5.json";

export interface ForestPlotPoint {
  label: string;
  estimate: number;
  ci_low: number;
  ci_high: number;
  evidence_id: string;
}

export function buildForestPlotSpec(
  title: string,
  points: ForestPlotPoint[],
  x_label: string = "Effect estimate (95% CI)",
): VegaLiteSpec {
  if (points.length === 0) {
    throw new Error("forest plot requires at least one point");
  }
  const data_values = points.map((p) => ({
    label: p.label,
    estimate: p.estimate,
    ci_low: p.ci_low,
    ci_high: p.ci_high,
    evidence_id: p.evidence_id,
  }));
  return {
    $schema: VEGA_LITE_SCHEMA_URL,
    title,
    data: { values: data_values },
    layer: [
      {
        mark: { type: "rule" },
        encoding: {
          y: {
            field: "label",
            type: "nominal",
            sort: null,
            axis: { title: null },
          },
          x: {
            field: "ci_low",
            type: "quantitative",
            title: x_label,
          },
          x2: { field: "ci_high" },
        },
      },
      {
        mark: { type: "point", filled: true, size: 100 },
        encoding: {
          y: { field: "label", type: "nominal" },
          x: { field: "estimate", type: "quantitative" },
          tooltip: [
            { field: "label" },
            { field: "estimate" },
            { field: "ci_low" },
            { field: "ci_high" },
            { field: "evidence_id" },
          ],
        },
      },
    ],
    polaris_provenance: {
      chart_type: "forest_plot",
      evidence_ids: points.map((p) => p.evidence_id),
    },
  };
}
