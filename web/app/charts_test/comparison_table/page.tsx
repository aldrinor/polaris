import { VegaChart } from "@/components/ui/vega-chart";
import {
  buildComparisonTableSpec,
  type ComparisonRow,
} from "@/lib/comparison_table_spec";

const ROWS_N2: ComparisonRow[] = [
  {
    entity: "Ontario",
    metric: "starts_thousands",
    value: 18.4,
    evidence_id: "demo-h-on",
  },
  {
    entity: "Quebec",
    metric: "starts_thousands",
    value: 9.7,
    evidence_id: "demo-h-qc",
  },
];

const ROWS_N3: ComparisonRow[] = [
  ...ROWS_N2,
  {
    entity: "BC",
    metric: "starts_thousands",
    value: 7.2,
    evidence_id: "demo-h-bc",
  },
];

const ROWS_N5: ComparisonRow[] = [
  {
    entity: "Ontario",
    metric: "starts_thousands",
    value: 18.4,
    evidence_id: "demo-h-on",
  },
  {
    entity: "Quebec",
    metric: "starts_thousands",
    value: 9.7,
    evidence_id: "demo-h-qc",
  },
  {
    entity: "BC",
    metric: "starts_thousands",
    value: 7.2,
    evidence_id: "demo-h-bc",
  },
  {
    entity: "Alberta",
    metric: "starts_thousands",
    value: 5.8,
    evidence_id: "demo-h-ab",
  },
  {
    entity: "Manitoba",
    metric: "starts_thousands",
    value: 1.4,
    evidence_id: "demo-h-mb",
  },
  {
    entity: "Ontario",
    metric: "completions_thousands",
    value: 14.1,
    evidence_id: "demo-c-on",
  },
  {
    entity: "Quebec",
    metric: "completions_thousands",
    value: 8.0,
    evidence_id: "demo-c-qc",
  },
  {
    entity: "BC",
    metric: "completions_thousands",
    value: 5.9,
    evidence_id: "demo-c-bc",
  },
  {
    entity: "Alberta",
    metric: "completions_thousands",
    value: 4.7,
    evidence_id: "demo-c-ab",
  },
  {
    entity: "Manitoba",
    metric: "completions_thousands",
    value: 1.1,
    evidence_id: "demo-c-mb",
  },
];

export default function ComparisonTablePage() {
  const spec_n2 = buildComparisonTableSpec("Q3 housing starts (N=2)", ROWS_N2);
  const spec_n3 = buildComparisonTableSpec("Q3 housing starts (N=3)", ROWS_N3);
  const spec_n5 = buildComparisonTableSpec(
    "Q3 housing starts + completions (N=5 entities × 2 metrics)",
    ROWS_N5,
  );
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Comparison table — N=2/3/5 demos
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Sample comparison tables (demo data, demo evidence_ids); same
          Vega-Lite structure produced by{" "}
          <code>polaris_v6.charts.spec_builder.build_comparison_table</code>.
        </p>
        <section
          data-testid="comparison-table-n2"
          className="mt-6 flex flex-col gap-2"
        >
          <h2 className="text-sm font-medium">N=2 entities × 1 metric</h2>
          <VegaChart spec={spec_n2} />
        </section>
        <section
          data-testid="comparison-table-n3"
          className="mt-6 flex flex-col gap-2"
        >
          <h2 className="text-sm font-medium">N=3 entities × 1 metric</h2>
          <VegaChart spec={spec_n3} />
        </section>
        <section
          data-testid="comparison-table-n5"
          className="mt-6 flex flex-col gap-2"
        >
          <h2 className="text-sm font-medium">N=5 entities × 2 metrics</h2>
          <VegaChart spec={spec_n5} />
        </section>
      </div>
    </main>
  );
}
