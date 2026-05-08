"use client";

import { useEffect, useState } from "react";

import {
  forgetMemory,
  listMemory,
  rememberMemory,
  type MemoryEntry,
  type MemoryKind,
} from "@/lib/api";
import { formatRelative } from "@/lib/relative_time";

const WS = "ws_demo";
const KINDS: MemoryKind[] = [
  "user_preference",
  "domain_assumption",
  "prior_run_summary",
  "rejected_source",
  "preferred_source",
];

export default function MemoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [content, setContent] = useState("");
  const [kind, setKind] = useState<MemoryKind>("user_preference");

  useEffect(() => {
    listMemory(WS).then((d) => queueMicrotask(() => setEntries(d)));
  }, []);

  const reload = async () => setEntries(await listMemory(WS));

  const onSave = async () => {
    await rememberMemory(WS, { kind, content });
    setContent("");
    await reload();
  };

  const onForget = async (id: string) => {
    await forgetMemory(WS, id);
    await reload();
  };

  const sorted = [...entries].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );
  const recent_runs = sorted.filter((e) => e.kind === "prior_run_summary");

  return (
    <main className="bg-background text-foreground mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        Workspace memory
      </h1>
      <p
        data-testid="memory-banner"
        className="text-muted-foreground mt-2 text-sm"
      >
        Demo workspace <code>{WS}</code>. Save + forget shipped here; pin
        controls land in I-f14-002b once the localStorage pattern is reviewed.
      </p>
      {recent_runs.length > 0 ? (
        <section
          data-testid="recent-runs"
          className="border-border mt-4 rounded border p-3"
        >
          <h2 className="text-sm font-semibold">Recent research</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {recent_runs.map((e) => (
              <li
                key={e.entry_id}
                data-testid={`recent-run-${e.entry_id}`}
                className="text-muted-foreground"
              >
                <span className="text-foreground">{e.content}</span>{" "}
                <span>· {formatRelative(e.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <div className="border-border mt-4 space-y-2 rounded border p-3">
        <select
          data-testid="memory-save-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as MemoryKind)}
          className="border-border bg-background w-full rounded border px-2 py-1 text-sm"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <textarea
          data-testid="memory-save-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={2}
          placeholder="What should the workspace remember?"
          className="border-border bg-background w-full rounded border px-2 py-1 text-sm"
        />
        <button
          type="button"
          data-testid="memory-save"
          onClick={onSave}
          disabled={content.length < 4}
          className="border-border rounded border px-3 py-1 text-sm hover:bg-blue-500/10 disabled:opacity-50"
        >
          Save
        </button>
      </div>
      <ul className="mt-4 space-y-2" data-testid="memory-list">
        {sorted.map((e) => (
          <li
            key={e.entry_id}
            data-testid={`memory-row-${e.entry_id}`}
            className="border-border flex items-start justify-between gap-3 rounded border p-3 text-sm"
          >
            <div>
              <div className="text-muted-foreground text-xs">
                {e.kind} · {e.entry_id.slice(0, 8)}
              </div>
              <div>{e.content}</div>
            </div>
            <button
              type="button"
              data-testid={`memory-forget-${e.entry_id}`}
              onClick={() => onForget(e.entry_id)}
              className="border-border shrink-0 rounded border px-2 py-1 text-xs hover:bg-rose-500/10"
            >
              Forget
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
