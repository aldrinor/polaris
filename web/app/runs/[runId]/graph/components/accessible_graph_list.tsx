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

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, type KeyboardEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { GraphNode, GraphNodeData, GraphPayload } from "@/lib/api";

import type { GraphAdjacency, GraphState } from "./use_graph_state";

// A small glyph that mirrors the canvas grammar (hexagon section / dot claim /
// pill source / status diamond frame) so the rail reads as a navigator of the
// same graph, not a detached admin table (Codex frontier audit iter-2 P1).
function TypeGlyph({ data }: { data: GraphNodeData }) {
  if (data.type === "section")
    return (
      <span
        aria-hidden
        className="size-2.5 shrink-0 rotate-12 rounded-sm bg-slate-900"
      />
    );
  if (data.type === "source")
    return (
      <span
        aria-hidden
        className="h-2 w-3.5 shrink-0 rounded-sm bg-slate-700"
      />
    );
  if (data.type === "frame") {
    const tone =
      data.frame_status === "pass"
        ? "bg-verified"
        : data.frame_status === "partial"
          ? "bg-contradiction"
          : data.frame_status === "fail"
            ? "bg-destructive"
            : "bg-slate-500";
    return (
      <span aria-hidden className={cn("size-2.5 shrink-0 rotate-45", tone)} />
    );
  }
  return (
    <span aria-hidden className="size-2 shrink-0 rounded-full bg-slate-600" />
  );
}

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
  const router = useRouter();
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
    // Enter opens Inspector on the SELECTED node (Codex diff iter-1 P1 fix:
    // selection-vs-focus desync; navigate by state, not focused link).
    if (e.key === "Enter" && state.selected_node_id) {
      e.preventDefault();
      router.push(inspectorHref(state.selected_node_id));
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
              className={`ease-standard flex items-center justify-between gap-3 px-3 py-2 text-xs transition-colors duration-150 ${
                isSelected ? "bg-accent" : "hover:bg-muted/40"
              }`}
            >
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <TypeGlyph data={n.data} />
                <span className="text-muted-foreground w-11 shrink-0 font-mono text-[10px] uppercase">
                  {n.data.type}
                </span>
                {n.data.tier && (
                  <span className="border-border bg-muted/60 text-foreground shrink-0 rounded border px-1 font-mono text-[10px] font-medium tabular-nums">
                    {n.data.tier}
                  </span>
                )}
                <span className="text-foreground truncate" title={n.data.label}>
                  {n.data.label}
                </span>
              </div>
              {/* Inspect de-emphasized to an arrow so the node label is the
                  focus, not a column of repeated "Inspect" links (Codex P1). */}
              <Button
                variant="ghost"
                size="icon"
                className="text-muted-foreground hover:text-primary size-7 shrink-0"
                onFocus={() => setSelectedNodeId(n.data.id)}
                nativeButton={false}
                render={
                  <Link
                    href={inspectorHref(n.data.id)}
                    aria-label={`Inspect ${n.data.label}`}
                  >
                    <ArrowUpRight aria-hidden className="h-4 w-4" />
                  </Link>
                }
              />
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
