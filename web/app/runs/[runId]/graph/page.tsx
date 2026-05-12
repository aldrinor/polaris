"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getRunGraph, type GraphPayload } from "@/lib/api";

import { ClaimGraph } from "./components/claim_graph";

interface GraphPageProps {
  params: Promise<{ runId: string }>;
}

export default function GraphPage({ params }: GraphPageProps) {
  const { runId } = use(params);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRunGraph(runId)
      .then((p) => {
        if (!cancelled) setPayload(p);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS — F-snowball
            </span>
            <span className="text-foreground text-base font-semibold">
              Claim graph: {runId}
            </span>
          </div>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href={`/inspector/${runId}`} />}
          >
            Back to Inspector
          </Button>
        </div>
      </header>

      <main
        data-testid="graph-page"
        className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 px-6 py-6"
      >
        {error && (
          <div
            role="alert"
            className="border-destructive text-destructive rounded-md border p-4"
          >
            Failed to load graph: {error}
          </div>
        )}

        {!payload && !error && (
          <div
            role="status"
            className="text-muted-foreground flex items-center gap-2"
          >
            <span
              aria-hidden
              className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
            />
            Loading graph for run {runId}…
          </div>
        )}

        {payload && <ClaimGraph payload={payload} />}
      </main>
    </div>
  );
}
