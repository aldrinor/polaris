/**
 * I-f10-003: TypeScript helper that mirrors `polaris_v6.charts.spec_builder.build_comparison_table`
 * for client-side visualization demos. Canonical spec generator remains the
 * Python builder; the backend route `/runs/{run_id}/charts/comparison_table`
 * returns specs of the same shape this helper produces.
 */

import type { VegaLiteSpec } from "@/lib/api";

export const VEGA_LITE_SCHEMA_URL =
  "https://vega.github.io/schema/vega-lite/v5.json";

export interface ComparisonRow {
  entity: string;
  metric: string;
  value: number;
  evidence_id: string;
}

export function buildComparisonTableSpec(
  title: string,
  rows: ComparisonRow[],
): VegaLiteSpec {
  if (rows.length === 0) {
    throw new Error("comparison table requires at least one row");
  }
  const data_values = rows.map((r) => ({
    entity: r.entity,
    metric: r.metric,
    value: r.value,
    evidence_id: r.evidence_id,
  }));
  return {
    $schema: VEGA_LITE_SCHEMA_URL,
    title,
    data: { values: data_values },
    mark: { type: "bar" },
    encoding: {
      y: { field: "entity", type: "nominal", axis: { title: null } },
      x: { field: "value", type: "quantitative" },
      color: { field: "metric", type: "nominal" },
      tooltip: [
        { field: "entity" },
        { field: "metric" },
        { field: "value" },
        { field: "evidence_id" },
      ],
    },
    polaris_provenance: {
      chart_type: "comparison_table",
      evidence_ids: rows.map((r) => r.evidence_id),
    },
  };
}
