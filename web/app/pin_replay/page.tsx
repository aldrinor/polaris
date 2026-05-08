"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEMO_PIN_REGISTRY, type PinSnapshot } from "@/lib/pin_replay_demo";
import { detectRegressions } from "@/lib/pin_regression";

import { DiffSidePanel } from "./components/diff_side_panel";
import { PinTimeseries } from "./components/pin_timeseries";

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
  // I-f13-004: pin default-B so adding a later registry date doesn't shift the
  // initial state and break existing tests.
  const [date_b, set_date_b] = useState("2026-04-30");
  const [diff_open, set_diff_open] = useState(false);
  const snap_a = DEMO_PIN_REGISTRY[date_a];
  const snap_b = DEMO_PIN_REGISTRY[date_b];
  const all_snapshots = Object.values(DEMO_PIN_REGISTRY);
  const alerts = detectRegressions(snap_a, snap_b);

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
        {alerts.length > 0 ? (
          <div
            data-testid="regression-alert"
            role="alert"
            className="mt-4 rounded border border-rose-500/40 bg-rose-500/5 p-3 text-sm text-rose-700 dark:text-rose-300"
          >
            <strong className="block">⚠ Regression detected</strong>
            <ul className="mt-1 space-y-1 text-xs">
              {alerts.map((alert) => (
                <li
                  key={alert.metric}
                  data-testid={`regression-alert-${alert.metric}`}
                >
                  {alert.metric}: dropped {alert.drop}
                  {alert.unit === "pct" ? " pct points" : " sentences"} ( A=
                  {alert.a_value}
                  {alert.unit === "pct" ? "%" : ""}, B=
                  {alert.b_value}
                  {alert.unit === "pct" ? "%" : ""}, threshold=
                  {alert.threshold}
                  {alert.unit === "pct" ? " pct" : ""})
                  {alert.attributed_to_retraction &&
                  alert.attributed_to_retraction.length > 0 ? (
                    <span
                      data-testid="regression-retraction-attribution"
                      className="text-muted-foreground ml-1"
                    >
                      (attributed to retraction of:{" "}
                      {alert.attributed_to_retraction.join(", ")})
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
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
        <div className="mt-6">
          <PinTimeseries snapshots={all_snapshots} />
        </div>
        <button
          type="button"
          data-testid="pin-show-diff"
          onClick={() => set_diff_open(true)}
          className="border-border mt-4 rounded border px-4 py-2 text-sm hover:bg-blue-500/10"
        >
          Show snapshot diff
        </button>
        <DiffSidePanel
          open={diff_open}
          onOpenChange={set_diff_open}
          snapshot_a={snap_a}
          snapshot_b={snap_b}
        />
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
