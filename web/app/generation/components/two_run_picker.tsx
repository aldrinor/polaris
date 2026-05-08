"use client";

import { useState } from "react";

export type RunListItem = {
  run_id: string;
  template: string;
  question: string;
  finished_at: string;
};

export function TwoRunPicker({
  runs,
  onCompare,
}: {
  runs: RunListItem[];
  onCompare: (ids: [string, string]) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);

  function toggle(run_id: string, want_checked: boolean): void {
    setSelected((prev) => {
      if (want_checked) {
        if (prev.includes(run_id)) return prev;
        if (prev.length >= 2) return prev;
        return [...prev, run_id];
      }
      return prev.filter((id) => id !== run_id);
    });
  }

  const ready = selected.length === 2;

  return (
    <div className="space-y-4">
      <p
        data-testid="selection-count"
        className="text-muted-foreground text-sm"
      >
        {selected.length} of 2 selected
      </p>
      <ul className="border-border divide-y divide-border rounded-md border">
        {runs.map((r) => {
          const checked = selected.includes(r.run_id);
          return (
            <li key={r.run_id} className="flex items-center gap-3 p-3">
              <input
                type="checkbox"
                id={`chk-${r.run_id}`}
                data-testid={`run-checkbox-${r.run_id}`}
                checked={checked}
                onChange={(e) => toggle(r.run_id, e.target.checked)}
                className="h-4 w-4"
              />
              <label htmlFor={`chk-${r.run_id}`} className="flex-1 cursor-pointer">
                <span className="block font-medium">{r.run_id}</span>
                <span className="text-muted-foreground block text-xs">
                  {r.template} — {r.question}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        data-testid="compare-button"
        disabled={!ready}
        onClick={() => {
          if (ready) {
            onCompare([selected[0], selected[1]]);
          }
        }}
        className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground inline-flex items-center rounded-md px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
      >
        Compare
      </button>
    </div>
  );
}
