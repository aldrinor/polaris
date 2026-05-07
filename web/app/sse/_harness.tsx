"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

import { SSEClient } from "@/lib/sse_client";

declare global {
  interface Window {
    __sse__?: {
      attempts: number;
      total_connects: number;
      messages: string[];
      errors: { terminal: boolean; attempts: number }[];
    };
  }
}

export function SSEHarness() {
  const sp = useSearchParams();
  const url = sp.get("url") ?? "/api/audit/stream";
  const max = parseInt(sp.get("max") ?? "10", 10);

  useEffect(() => {
    const state = {
      attempts: 0,
      total_connects: 0,
      messages: [] as string[],
      errors: [] as { terminal: boolean; attempts: number }[],
    };
    window.__sse__ = state;
    const c = new SSEClient(url, {
      maxRetries: max,
      initialBackoffMs: 100,
      maxBackoffMs: 500,
      onMessage: (d) => {
        state.messages.push(d);
        state.total_connects = c.getTotalConnects();
      },
      onOpen: () => {
        state.total_connects = c.getTotalConnects();
      },
      onError: (e) => {
        state.attempts = c.getAttempts();
        state.errors.push(e);
      },
    });
    c.connect();
    return () => c.close();
  }, [url, max]);

  return <div data-testid="sse-harness">SSE harness ready</div>;
}
