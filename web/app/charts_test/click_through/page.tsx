"use client";

import { useState } from "react";

import { VegaChart } from "@/components/ui/vega-chart";
import {
  buildForestPlotSpec,
  type ForestPlotPoint,
} from "@/lib/forest_plot_spec";

import {
  ChartSourceInspector,
  type ChartDatumSource,
} from "../components/chart_source_inspector";

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

const SOURCE_REGISTRY: Record<string, ChartDatumSource> = {
  "demo-clin-001": {
    evidence_id: "demo-clin-001",
    url: "https://example.org/select-trial-mace",
    tier: "T1",
    excerpt:
      "MACE composite endpoint: -20% relative risk reduction (95% CI -27% to -13%) at 3-year follow-up.",
  },
  "demo-clin-002": {
    evidence_id: "demo-clin-002",
    url: "https://example.org/select-trial-mi",
    tier: "T1",
    excerpt:
      "Myocardial infarction subcomponent: -18% (95% CI -28% to -6%); statistically significant.",
  },
  "demo-clin-003": {
    evidence_id: "demo-clin-003",
    url: "https://example.org/select-trial-stroke",
    tier: "T1",
    excerpt:
      "Stroke subcomponent: -7% (95% CI -19% to +5%); CI crosses null — non-significant on its own.",
  },
};

export default function ClickThroughPage() {
  const spec = buildForestPlotSpec(
    "SELECT trial cardiovascular outcomes (click any point)",
    SAMPLE_META_ANALYSIS,
  );
  const [source, setSource] = useState<ChartDatumSource | null>(null);
  const [open, setOpen] = useState(false);

  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Click-through to source data
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Click any chart point to open the source-span inspector.{" "}
          <code>evidence_id</code> resolves against a demo SOURCE_REGISTRY (in
          production, this would fetch from{" "}
          <code>
            /runs/{"{run_id}"}/sources/{"{evidence_id}"}
          </code>{" "}
          per the I-f10-005 polaris_provenance contract).
        </p>
        <div className="mt-6">
          <VegaChart
            spec={spec}
            onPointClick={(datum) => {
              const eid = datum.evidence_id as string | undefined;
              if (eid && SOURCE_REGISTRY[eid]) {
                setSource(SOURCE_REGISTRY[eid]);
                setOpen(true);
              }
            }}
          />
        </div>
        <ChartSourceInspector
          open={open}
          onOpenChange={setOpen}
          source={source}
        />
      </div>
    </main>
  );
}
