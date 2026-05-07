"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

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
  const [events, setEvents] = useState<Record<SSEEventName, LoggedEvent[]>>(
    () =>
      Object.fromEntries(
        EVENT_NAMES.map((n) => [n, [] as LoggedEvent[]]),
      ) as Record<SSEEventName, LoggedEvent[]>,
  );

  useEffect(() => {
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
    c.connect();
    return () => c.close();
  }, [url]);

  return (
    <div className="mx-auto max-w-5xl space-y-3 p-6 text-sm">
      <h1 className="text-xl font-semibold">Live audit run</h1>
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
