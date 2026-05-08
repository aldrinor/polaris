import { VegaChart } from "@/components/ui/vega-chart";
import { buildTimelineSpec, type TimelinePoint } from "@/lib/timeline_spec";

const QUARTERLY: TimelinePoint[] = [
  {
    period: "2010-Q1",
    value: 0.08,
    series: "Suncor",
    evidence_id: "demo-q-010",
  },
  {
    period: "2015-Q1",
    value: 0.075,
    series: "Suncor",
    evidence_id: "demo-q-015",
  },
  {
    period: "2020-Q1",
    value: 0.07,
    series: "Suncor",
    evidence_id: "demo-q-020",
  },
  {
    period: "2023-Q4",
    value: 0.066,
    series: "Suncor",
    evidence_id: "demo-q-023",
  },
];

const MONTHLY: TimelinePoint[] = [
  {
    period: "2024-01-01",
    value: 14.2,
    series: "ECCC",
    evidence_id: "demo-m-jan",
  },
  {
    period: "2024-02-01",
    value: 13.8,
    series: "ECCC",
    evidence_id: "demo-m-feb",
  },
  {
    period: "2024-03-01",
    value: 13.4,
    series: "ECCC",
    evidence_id: "demo-m-mar",
  },
  {
    period: "2024-04-01",
    value: 13.0,
    series: "ECCC",
    evidence_id: "demo-m-apr",
  },
];

export default function TimelinePage() {
  const spec_quarter = buildTimelineSpec(
    "Oil-sands GHG intensity per barrel (quarter)",
    QUARTERLY,
    "quarter",
  );
  const spec_date = buildTimelineSpec(
    "ECCC monthly emissions (date)",
    MONTHLY,
    "date",
  );
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Timeline charts — sample time-series
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Sample timelines (demo data, demo evidence_ids); same Vega-Lite
          structure produced by{" "}
          <code>polaris_v6.charts.spec_builder.build_timeline</code>.
        </p>
        <section
          data-testid="timeline-quarter"
          className="mt-6 flex flex-col gap-2"
        >
          <h2 className="text-sm font-medium">
            period_kind = &quot;quarter&quot; (ordinal X)
          </h2>
          <VegaChart spec={spec_quarter} />
        </section>
        <section
          data-testid="timeline-date"
          className="mt-6 flex flex-col gap-2"
        >
          <h2 className="text-sm font-medium">
            period_kind = &quot;date&quot; (temporal X)
          </h2>
          <VegaChart spec={spec_date} />
        </section>
      </div>
    </main>
  );
}
