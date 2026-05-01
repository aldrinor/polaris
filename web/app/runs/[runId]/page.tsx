"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  downloadBundleAsJson,
  getBundle,
  getRun,
  subscribeToRun,
  type RunStatusResponse,
  type StreamEvent,
} from "@/lib/api";

interface RunPageProps {
  params: Promise<{ runId: string }>;
}

export default function RunDetailPage({ params }: RunPageProps) {
  const { runId } = use(params);
  const [status, setStatus] = useState<RunStatusResponse | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRun(runId)
      .then((value) => {
        if (!cancelled) setStatus(value);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      });

    const source = subscribeToRun(
      runId,
      (event) => {
        setEvents((prev) => [...prev, event]);
      },
      () => {
        // SSE error: backend may have closed the stream after run_complete.
        source.close();
      },
    );

    return () => {
      cancelled = true;
      source.close();
    };
  }, [runId]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada
            </span>
            <span className="text-foreground text-base font-semibold">
              Sovereign Deep Research
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  const bundle = await getBundle(runId);
                  downloadBundleAsJson(bundle);
                } catch (err) {
                  setError(
                    err instanceof Error
                      ? `Bundle export failed: ${err.message}`
                      : "Bundle export failed",
                  );
                }
              }}
            >
              Export bundle
            </Button>
            <Button
              variant="default"
              nativeButton={false}
              render={<Link href="/dashboard" />}
            >
              New run
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
        <section className="flex flex-col gap-2">
          <span className="text-muted-foreground text-xs tracking-widest uppercase">
            Run {runId}
          </span>
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            {status?.question ?? "Loading…"}
          </h1>
          {status && (
            <p className="text-muted-foreground text-sm">
              Template:{" "}
              <span className="text-foreground">{status.template}</span>
              {" · "}
              Status:{" "}
              <span className="text-foreground font-mono">{status.status}</span>
              {" · "}
              Queued at <time>{status.queued_at}</time>
            </p>
          )}
          {error && (
            <p
              role="alert"
              className="text-destructive border-destructive/50 bg-destructive/10 rounded-md border p-3 text-sm"
            >
              {error}
            </p>
          )}
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-foreground text-lg font-semibold">
            Live events ({events.length})
          </h2>
          <div className="flex flex-col gap-2">
            {events.length === 0 && (
              <p className="text-muted-foreground text-sm">
                Waiting for the first event from the verifier pipeline…
              </p>
            )}
            {events.map((evt, idx) => (
              <Card key={idx}>
                <CardHeader>
                  <CardDescription className="text-xs tracking-widest uppercase">
                    Event {idx + 1}
                  </CardDescription>
                  <CardTitle className="font-mono text-sm">
                    {evt.event}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="bg-muted text-muted-foreground overflow-x-auto rounded-md p-3 text-xs">
                    {JSON.stringify(evt.data, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Phase 0 scaffold</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
