"use client";

/**
 * AccessibleGraphList — `<ol>` parallel to the cytoscape canvas.
 *
 * Canonical a11y surface (canvas is decorative-equivalent). Order: section
 * nodes first, then sentence nodes (grouped by section), then source nodes
 * (sorted by tier then id), then frame nodes. Each row has an "Open
 * Inspector" button that fires the router push.
 *
 * Keyboard nav (handled at outer wrapper): ArrowRight=outgoing edge target,
 * ArrowLeft=incoming, ArrowUp/Down=prev/next visible in list order,
 * Enter=open Inspector, Esc=clear selection, `/`=focus search.
 */

import Link from "next/link";
import { useMemo, type KeyboardEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import type { GraphNode, GraphPayload } from "@/lib/api";

import type { GraphAdjacency, GraphState } from "./use_graph_state";

interface AccessibleGraphListProps {
  payload: GraphPayload;
  state: GraphState;
  adjacency: GraphAdjacency;
  runId: string;
  searchInputRef: RefObject<HTMLInputElement | null>;
  setSelectedNodeId: (id: string | null) => void;
}

const TYPE_ORDER: Record<string, number> = {
  section: 0,
  sentence: 1,
  source: 2,
  frame: 3,
};

const TIER_ORDER: Record<string, number> = {
  T1: 0,
  T2: 1,
  T3: 2,
  T4: 3,
  T5: 4,
  T6: 5,
  T7: 6,
};

function orderedNodes(payload: GraphPayload): GraphNode[] {
  return [...payload.elements.nodes].sort((a, b) => {
    const ta = TYPE_ORDER[a.data.type] ?? 99;
    const tb = TYPE_ORDER[b.data.type] ?? 99;
    if (ta !== tb) return ta - tb;
    if (a.data.type === "source" && b.data.type === "source") {
      const ka = TIER_ORDER[a.data.tier ?? ""] ?? 99;
      const kb = TIER_ORDER[b.data.tier ?? ""] ?? 99;
      if (ka !== kb) return ka - kb;
    }
    return a.data.id.localeCompare(b.data.id);
  });
}

export function AccessibleGraphList({
  payload,
  state,
  adjacency,
  runId,
  searchInputRef,
  setSelectedNodeId,
}: AccessibleGraphListProps) {
  const ordered = useMemo(() => orderedNodes(payload), [payload]);
  const visibleOrdered = useMemo(
    () => ordered.filter((n) => state.visible_node_ids.has(n.data.id)),
    [ordered, state.visible_node_ids],
  );

  const inspectorHref = (id: string) =>
    `/inspector/${runId}?${new URLSearchParams({ focused_node: id }).toString()}`;

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
      e.preventDefault();
      searchInputRef.current?.focus();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setSelectedNodeId(null);
      return;
    }
    if (!state.selected_node_id) return;
    const idx = visibleOrdered.findIndex(
      (n) => n.data.id === state.selected_node_id,
    );
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = visibleOrdered[Math.min(idx + 1, visibleOrdered.length - 1)];
      if (next) setSelectedNodeId(next.data.id);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = visibleOrdered[Math.max(idx - 1, 0)];
      if (prev) setSelectedNodeId(prev.data.id);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      const outs = adjacency.out.get(state.selected_node_id) ?? [];
      const target = outs.find((t) => state.visible_node_ids.has(t));
      if (target) setSelectedNodeId(target);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const ins = adjacency.in.get(state.selected_node_id) ?? [];
      const source = ins.find((t) => state.visible_node_ids.has(t));
      if (source) setSelectedNodeId(source);
    }
  };

  return (
    <section
      role="region"
      aria-label="Claim graph"
      onKeyDown={onKeyDown}
      tabIndex={-1}
      className="border-border flex max-h-[600px] flex-col overflow-y-auto rounded-md border"
    >
      <ol aria-label="Graph nodes" className="divide-border divide-y">
        {visibleOrdered.map((n) => {
          const isSelected = state.selected_node_id === n.data.id;
          return (
            <li
              key={n.data.id}
              data-testid={`graph-list-row-${n.data.id}`}
              aria-current={isSelected ? "true" : undefined}
              className={`flex items-center justify-between gap-3 px-3 py-2 text-xs ${
                isSelected ? "bg-accent" : ""
              }`}
            >
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <span className="text-muted-foreground font-mono text-[10px] uppercase">
                  {n.data.type}
                </span>
                {n.data.tier && (
                  <span className="rounded bg-green-100 px-1 text-[10px] font-medium text-green-800">
                    {n.data.tier}
                  </span>
                )}
                <span className="truncate" title={n.data.label}>
                  {n.data.label}
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onFocus={() => setSelectedNodeId(n.data.id)}
                nativeButton={false}
                render={<Link href={inspectorHref(n.data.id)} />}
              >
                Inspect
              </Button>
            </li>
          );
        })}
        {visibleOrdered.length === 0 && (
          <li className="text-muted-foreground p-3 text-xs">
            No nodes match the search filter.
          </li>
        )}
      </ol>
    </section>
  );
}
