"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEMO_PIN_REGISTRY, type PinSnapshot } from "@/lib/pin_replay_demo";

const PIN_DATES = Object.keys(DEMO_PIN_REGISTRY).sort();

function SnapshotCard({
  testid,
  label,
  selected_date,
  on_change,
  snapshot,
}: {
  testid: string;
  label: string;
  selected_date: string;
  on_change: (next: string) => void;
  snapshot: PinSnapshot;
}) {
  return (
    <Card data-testid={testid}>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-base">{label}</CardTitle>
        <select
          data-testid={`${testid}-date`}
          value={selected_date}
          onChange={(e) => on_change(e.target.value)}
          className="border-border bg-background rounded border px-2 py-1 text-sm"
        >
          {PIN_DATES.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </CardHeader>
      <CardContent className="text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
          <dt className="text-muted-foreground">Query</dt>
          <dd
            data-testid={`${testid}-query`}
            className="text-foreground truncate"
          >
            {snapshot.query}
          </dd>
          <dt className="text-muted-foreground">Verdict</dt>
          <dd data-testid={`${testid}-verdict`} className="text-foreground">
            {snapshot.verdict}
          </dd>
          <dt className="text-muted-foreground">Sections kept / dropped</dt>
          <dd data-testid={`${testid}-sections`} className="text-foreground">
            {snapshot.section_count_kept} / {snapshot.section_count_dropped}
          </dd>
          <dt className="text-muted-foreground">Verified sentences</dt>
          <dd data-testid={`${testid}-sentences`} className="text-foreground">
            {snapshot.verified_sentence_count}
          </dd>
          <dt className="text-muted-foreground">Pass rate</dt>
          <dd data-testid={`${testid}-pass-rate`} className="text-foreground">
            {Math.round(snapshot.pass_rate * 100)}%
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

export default function PinReplayPage() {
  const [date_a, set_date_a] = useState(PIN_DATES[0]);
  const [date_b, set_date_b] = useState(PIN_DATES[PIN_DATES.length - 1]);
  const snap_a = DEMO_PIN_REGISTRY[date_a];
  const snap_b = DEMO_PIN_REGISTRY[date_b];

  const delta_pass_rate =
    Math.round(snap_b.pass_rate * 100) - Math.round(snap_a.pass_rate * 100);
  const delta_sentences =
    snap_b.verified_sentence_count - snap_a.verified_sentence_count;

  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Pin replay — same query on different dates
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Sample pin-replay (demo data); production fetch from{" "}
          <code>
            /runs/{"{run_id}"}/pins/{"{date}"}
          </code>{" "}
          per M-INT-0b post-Carney.
        </p>
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          <SnapshotCard
            testid="pin-snapshot-a"
            label="Snapshot A"
            selected_date={date_a}
            on_change={set_date_a}
            snapshot={snap_a}
          />
          <SnapshotCard
            testid="pin-snapshot-b"
            label="Snapshot B"
            selected_date={date_b}
            on_change={set_date_b}
            snapshot={snap_b}
          />
        </div>
        <Card data-testid="pin-replay-delta" className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">Delta (B − A)</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              Pass rate:{" "}
              <span data-testid="pin-replay-delta-pass-rate">
                {delta_pass_rate >= 0 ? "+" : ""}
                {delta_pass_rate}%
              </span>
            </p>
            <p>
              Verified sentences:{" "}
              <span data-testid="pin-replay-delta-sentences">
                {delta_sentences >= 0 ? "+" : ""}
                {delta_sentences}
              </span>
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
