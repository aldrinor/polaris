import { VegaChart } from "@/components/ui/vega-chart";
import type { VegaLiteSpec } from "@/lib/api";

const SAMPLE_SPEC: VegaLiteSpec = {
  $schema: "https://vega.github.io/schema/vega-lite/v5.json",
  title: "Sample bar chart — POLARIS vs ChatGPT vs Gemini (demo only)",
  data: {
    values: [
      { dimension: "Sourcing", system: "POLARIS", score: 0.92 },
      { dimension: "Sourcing", system: "ChatGPT DR", score: 0.78 },
      { dimension: "Sourcing", system: "Gemini DR", score: 0.74 },
    ],
  },
  mark: "bar",
  encoding: {
    x: { field: "system", type: "nominal" },
    y: { field: "score", type: "quantitative" },
    color: { field: "system", type: "nominal" },
  },
  polaris_provenance: {
    chart_type: "forest_plot",
    evidence_ids: ["demo-1", "demo-2", "demo-3"],
  },
};

export default function ChartsTestPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Charts substrate test
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Sample chart — demo evidence_ids only; renders the Vega-Lite v5
          substrate (consumed by the real forest-plot spec in I-f10-002).
        </p>
        <div className="mt-6">
          <VegaChart spec={SAMPLE_SPEC} />
        </div>
      </div>
    </main>
  );
}
