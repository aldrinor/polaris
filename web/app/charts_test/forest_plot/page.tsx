import { VegaChart } from "@/components/ui/vega-chart";
import {
  buildForestPlotSpec,
  type ForestPlotPoint,
} from "@/lib/forest_plot_spec";

const SAMPLE_META_ANALYSIS: ForestPlotPoint[] = [
  {
    label: "MACE",
    estimate: -0.2,
    ci_low: -0.27,
    ci_high: -0.13,
    evidence_id: "demo-clin-001",
  },
  {
    label: "MI",
    estimate: -0.18,
    ci_low: -0.28,
    ci_high: -0.06,
    evidence_id: "demo-clin-002",
  },
  {
    label: "Stroke",
    estimate: -0.07,
    ci_low: -0.19,
    ci_high: 0.05,
    evidence_id: "demo-clin-003",
  },
];

export default function ForestPlotPage() {
  const spec = buildForestPlotSpec(
    "SELECT trial cardiovascular outcomes (demo)",
    SAMPLE_META_ANALYSIS,
  );
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Forest plot — sample meta-analysis
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Sample SELECT-trial cardiovascular outcomes (demo data, demo
          evidence_ids); same Vega-Lite structure produced by{" "}
          <code>polaris_v6.charts.spec_builder.build_forest_plot</code>.
        </p>
        <div className="mt-6">
          <VegaChart spec={spec} />
        </div>
      </div>
    </main>
  );
}
