"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getRunGraph, type GraphPayload } from "@/lib/api";

import { AccessibleGraphList } from "./components/accessible_graph_list";
import { ClaimGraph } from "./components/claim_graph";
import { useGraphState } from "./components/use_graph_state";

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
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
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
        className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-6 py-6"
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

        {payload && <GraphSurface payload={payload} runId={runId} />}
      </main>
    </div>
  );
}

interface GraphSurfaceProps {
  payload: GraphPayload;
  runId: string;
}

function GraphSurface({ payload, runId }: GraphSurfaceProps) {
  const [state, adjacency, actions] = useGraphState(payload);
  const searchInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Input
          ref={searchInputRef}
          type="search"
          placeholder="Search nodes (press / to focus)…"
          value={state.search_query}
          onChange={(e) => actions.setSearchQuery(e.target.value)}
          className="max-w-md"
          aria-label="Search graph nodes"
        />
        <span className="text-muted-foreground text-xs">
          {state.visible_node_ids.size}/{payload.elements.nodes.length} visible
        </span>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <ClaimGraph
          payload={payload}
          runId={runId}
          selectedNodeId={state.selected_node_id}
          searchQuery={state.search_query}
          setSelectedNodeId={actions.setSelectedNodeId}
        />
        <AccessibleGraphList
          payload={payload}
          state={state}
          adjacency={adjacency}
          runId={runId}
          searchInputRef={searchInputRef}
          setSelectedNodeId={actions.setSelectedNodeId}
        />
      </div>
    </div>
  );
}
