"use client";

import { VegaChart } from "@/components/ui/vega-chart";
import { buildTimelineSpec, type TimelinePoint } from "@/lib/timeline_spec";

import type { PinSnapshot } from "@/lib/pin_replay_demo";

export function PinTimeseries({ snapshots }: { snapshots: PinSnapshot[] }) {
  const sorted = [...snapshots].sort((a, b) =>
    a.pin_date.localeCompare(b.pin_date),
  );

  const pass_rate_points: TimelinePoint[] = sorted.map((s) => ({
    period: s.pin_date,
    value: Math.round(s.pass_rate * 100),
    series: "pass_rate_pct",
    evidence_id: `demo-pin-${s.pin_date}-pass`,
  }));

  const sentences_points: TimelinePoint[] = sorted.map((s) => ({
    period: s.pin_date,
    value: s.verified_sentence_count,
    series: "verified_sentences",
    evidence_id: `demo-pin-${s.pin_date}-sentences`,
  }));

  const pass_rate_spec = buildTimelineSpec(
    "Pass rate over time (%)",
    pass_rate_points,
    "date",
  );
  const sentences_spec = buildTimelineSpec(
    "Verified sentences over time",
    sentences_points,
    "date",
  );

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <section
        data-testid="pin-timeseries-pass-rate"
        className="flex flex-col gap-2"
      >
        <h3 className="text-sm font-medium">Pass rate (%)</h3>
        <VegaChart spec={pass_rate_spec} />
      </section>
      <section
        data-testid="pin-timeseries-sentence-count"
        className="flex flex-col gap-2"
      >
        <h3 className="text-sm font-medium">Verified sentence count</h3>
        <VegaChart spec={sentences_spec} />
      </section>
    </div>
  );
}
