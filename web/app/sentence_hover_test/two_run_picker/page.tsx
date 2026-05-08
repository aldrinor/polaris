"use client";

import { useState } from "react";

import {
  RunListItem,
  TwoRunPicker,
} from "@/app/generation/components/two_run_picker";

const STUB_RUNS: RunListItem[] = [
  {
    run_id: "r1",
    template: "clinical_summary",
    question: "Drug X efficacy?",
    finished_at: "2026-05-08T00:00:00Z",
  },
  {
    run_id: "r2",
    template: "regulatory_review",
    question: "FDA Q1 update?",
    finished_at: "2026-05-08T01:00:00Z",
  },
  {
    run_id: "r3",
    template: "clinical_summary",
    question: "Drug Y safety?",
    finished_at: "2026-05-08T02:00:00Z",
  },
  {
    run_id: "r4",
    template: "trade_brief",
    question: "Tariff B impact?",
    finished_at: "2026-05-08T03:00:00Z",
  },
];

export default function TwoRunPickerFixturePage() {
  const [last, setLast] = useState<string>("");
  return (
    <main className="bg-background text-foreground mx-auto max-w-2xl px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        Two-run picker fixture (I-f12-001)
      </h1>
      <div className="mt-6">
        <TwoRunPicker runs={STUB_RUNS} onCompare={([a, b]) => setLast(`${a},${b}`)} />
      </div>
      <p
        data-testid="last-compared-pair"
        className="text-muted-foreground mt-6 text-sm"
      >
        {last}
      </p>
    </main>
  );
}
