"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { RunBroadcast } from "@/lib/run_broadcast";
import { SSEClient } from "@/lib/sse_client";
import {
  EVENT_LABELS,
  EVENT_NAMES,
  type LoggedEvent,
  type SSEEventName,
} from "@/lib/sse_events";

const MAX_EVENTS = 50;

export function LiveAuditPanels() {
  const sp = useSearchParams();
  const url = sp.get("url") ?? "/api/audit/stream";
  const run_id = sp.get("run_id") ?? "";
  const [events, setEvents] = useState<Record<SSEEventName, LoggedEvent[]>>(
    () =>
      Object.fromEntries(
        EVENT_NAMES.map((n) => [n, [] as LoggedEvent[]]),
      ) as Record<SSEEventName, LoggedEvent[]>,
  );
  const [cancelled, setCancelled] = useState(false);
  const broadcast_ref = useRef<RunBroadcast | null>(null);
  const sse_ref = useRef<SSEClient | null>(null);

  useEffect(() => {
    if (cancelled) return;
    const c = new SSEClient(url, {
      eventNames: [...EVENT_NAMES],
      onEvent: (name, data) => {
        const ev: LoggedEvent = {
          name: name as SSEEventName,
          ts: Date.now(),
          payload: data,
        };
        setEvents((prev) => {
          const next = { ...prev };
          next[ev.name] = [...prev[ev.name], ev].slice(-MAX_EVENTS);
          return next;
        });
      },
    });
    sse_ref.current = c;
    c.connect();
    let bc: RunBroadcast | null = null;
    if (run_id) {
      bc = new RunBroadcast(run_id, {
        onCancel: () => {
          c.close();
          setCancelled(true);
        },
      });
      bc.subscribe();
      broadcast_ref.current = bc;
    }
    return () => {
      c.close();
      bc?.close();
      sse_ref.current = null;
      broadcast_ref.current = null;
    };
  }, [url, run_id, cancelled]);

  function on_cancel_click() {
    sse_ref.current?.close();
    broadcast_ref.current?.broadcastCancel();
    setCancelled(true);
  }

  if (cancelled) {
    return (
      <div
        data-testid="run-cancelled"
        className="mx-auto max-w-5xl p-6 text-sm"
      >
        Run cancelled.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-3 p-6 text-sm">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Live audit run</h1>
        {run_id && (
          <button
            type="button"
            data-testid="run-cancel-btn"
            onClick={on_cancel_click}
            className="border-border rounded border px-3 py-1 text-xs hover:bg-rose-50"
          >
            Cancel run
          </button>
        )}
      </header>
      {EVENT_NAMES.map((name) => (
        <section
          key={name}
          data-testid={`panel-${name}`}
          className="border-border rounded-md border p-3"
        >
          <header className="mb-2 flex justify-between">
            <span className="font-medium">{EVENT_LABELS[name]}</span>
            <span
              data-testid={`panel-${name}-count`}
              className="text-muted-foreground text-xs"
            >
              {events[name].length} events
            </span>
          </header>
          <ul className="max-h-32 overflow-auto text-xs">
            {events[name].map((ev, i) => (
              <li
                key={i}
                data-testid={`panel-${name}-row-${i}`}
                className="border-border/40 border-t py-1"
              >
                <span className="text-muted-foreground tabular-nums">
                  {new Date(ev.ts).toISOString().slice(11, 19)}
                </span>
                <pre className="ml-2 inline whitespace-pre-wrap">
                  {ev.payload}
                </pre>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
