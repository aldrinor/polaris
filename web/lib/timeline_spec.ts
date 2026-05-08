/**
 * I-f10-004: TypeScript helper that mirrors `polaris_v6.charts.spec_builder.build_timeline`
 * for client-side visualization demos. Canonical spec generator remains the
 * Python builder; the backend route `/runs/{run_id}/charts/timeline` returns
 * specs of the same shape this helper produces.
 */

import type { VegaLiteSpec } from "@/lib/api";

export const VEGA_LITE_SCHEMA_URL =
  "https://vega.github.io/schema/vega-lite/v5.json";

export type TimelinePeriodKind = "date" | "quarter" | "year";

export interface TimelinePoint {
  period: string;
  value: number;
  series: string;
  evidence_id: string;
}

export function buildTimelineSpec(
  title: string,
  points: TimelinePoint[],
  period_kind: TimelinePeriodKind = "quarter",
): VegaLiteSpec {
  if (points.length === 0) {
    throw new Error("timeline requires at least one point");
  }
  const temporal_type = period_kind === "date" ? "temporal" : "ordinal";
  const data_values = points.map((p) => ({
    period: p.period,
    value: p.value,
    series: p.series,
    evidence_id: p.evidence_id,
  }));
  return {
    $schema: VEGA_LITE_SCHEMA_URL,
    title,
    data: { values: data_values },
    mark: { type: "line", point: true },
    encoding: {
      x: {
        field: "period",
        type: temporal_type,
        axis: { title: "Period" },
      },
      y: { field: "value", type: "quantitative" },
      color: { field: "series", type: "nominal" },
      tooltip: [
        { field: "period" },
        { field: "value" },
        { field: "series" },
        { field: "evidence_id" },
      ],
    },
    polaris_provenance: {
      chart_type: "timeline",
      period_kind,
      evidence_ids: points.map((p) => p.evidence_id),
    },
  };
}
