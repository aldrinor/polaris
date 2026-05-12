"use client";

/**
 * ClaimGraph — cytoscape canvas component (I-snowball-003 + I-snowball-004).
 *
 * Stylesheet + layout constants extracted to graph_styles.ts to keep file
 * under 200 LOC after adding hover + click + search-highlight + selection
 * sync handlers (I-snowball-004 brief iter 2 P2-1.4).
 */

import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type { GraphPayload } from "@/lib/api";

import { LAYOUT_FCOSE, LAYOUT_PRESET, STYLESHEET } from "./graph_styles";
import { nodeMatchesQuery } from "./use_graph_state";

// Idempotent fcose registration (guards against double-register on HMR).
const _cy = cytoscape as unknown as { _fcoseRegistered?: boolean };
if (!_cy._fcoseRegistered) {
  cytoscape.use(fcose);
  _cy._fcoseRegistered = true;
}

// `react-cytoscapejs` is SSR-unsafe; dynamic-import as client-only.
const CytoscapeComponent = dynamic(() => import("react-cytoscapejs"), {
  ssr: false,
});

interface HoverState {
  id: string;
  type: string;
  label: string;
  tier?: string;
  source_url?: string;
  x: number;
  y: number;
}

interface ClaimGraphProps {
  payload: GraphPayload;
  runId: string;
  selectedNodeId: string | null;
  searchQuery: string;
  setSelectedNodeId: (id: string | null) => void;
}

export function ClaimGraph({
  payload,
  runId,
  selectedNodeId,
  searchQuery,
  setSelectedNodeId,
}: ClaimGraphProps) {
  const router = useRouter();
  const [cyInstance, setCyInstance] = useState<cytoscape.Core | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  const { elements, layout } = useMemo(() => {
    const hasPositions =
      payload.elements.nodes.length > 0 &&
      payload.elements.nodes.every((n) => n.position != null);

    const cyNodes = payload.elements.nodes.map((n) => ({
      data: n.data,
      position: n.position ?? undefined,
      classes: n.data.classes ?? undefined,
    }));
    const cyEdges = payload.elements.edges.map((e) => ({ data: e.data }));

    return {
      elements: [...cyNodes, ...cyEdges],
      layout: hasPositions ? LAYOUT_PRESET : LAYOUT_FCOSE,
    };
  }, [payload]);

  // Idempotent event registration (Codex iter-1 P1-1.1 fix).
  useEffect(() => {
    if (!cyInstance) return;
    const onTap = (evt: cytoscape.EventObject) => {
      const id = evt.target.id();
      setSelectedNodeId(id);
      router.push(
        `/inspector/${runId}?${new URLSearchParams({ focused_node: id }).toString()}`,
      );
    };
    const onMouseover = (evt: cytoscape.EventObject) => {
      const node = evt.target;
      const data = node.data();
      const rendered = node.renderedPosition();
      setHover({
        id: data.id,
        type: data.type,
        label: data.label,
        tier: data.tier,
        source_url: data.source_url,
        x: rendered.x,
        y: rendered.y,
      });
    };
    const onMouseout = () => setHover(null);
    cyInstance.on("tap", "node", onTap);
    cyInstance.on("mouseover", "node", onMouseover);
    cyInstance.on("mouseout", "node", onMouseout);
    return () => {
      cyInstance.off("tap", "node", onTap);
      cyInstance.off("mouseover", "node", onMouseover);
      cyInstance.off("mouseout", "node", onMouseout);
    };
  }, [cyInstance, runId, router, setSelectedNodeId]);

  // Search-highlight (Codex iter-2 P2-1.5 + iter-3 share-predicate fix:
  // use the same `nodeMatchesQuery` helper as the list filter).
  useEffect(() => {
    if (!cyInstance) return;
    cyInstance.nodes().removeClass("search-hit");
    if (!searchQuery.trim()) return;
    cyInstance
      .nodes()
      .filter((n) =>
        nodeMatchesQuery(
          {
            data: {
              id: n.data("id") as string,
              type: n.data("type") as
                | "sentence"
                | "source"
                | "section"
                | "frame",
              label: n.data("label") as string,
            },
          },
          searchQuery,
        ),
      )
      .addClass("search-hit");
  }, [cyInstance, searchQuery]);

  // Selection sync — selected node gets a halo via .selected class.
  useEffect(() => {
    if (!cyInstance) return;
    cyInstance.nodes().removeClass("selected");
    if (selectedNodeId) {
      cyInstance.getElementById(selectedNodeId).addClass("selected");
    }
  }, [cyInstance, selectedNodeId]);

  return (
    <section
      aria-label="Claim graph canvas"
      data-testid="claim-graph"
      className="border-border relative flex w-full flex-col overflow-hidden rounded-md border"
    >
      <div className="relative h-[600px] w-full">
        <CytoscapeComponent
          elements={elements}
          style={{ width: "100%", height: "100%" }}
          layout={layout}
          stylesheet={STYLESHEET}
          cy={(cy) => setCyInstance(cy)}
        />
        {hover && (
          <div
            role="tooltip"
            className="bg-popover text-popover-foreground border-border pointer-events-none absolute z-50 max-w-xs rounded-md border px-3 py-2 text-xs shadow-md"
            style={{ left: hover.x + 12, top: hover.y + 12 }}
          >
            <div className="font-medium">{hover.label}</div>
            <div className="text-muted-foreground">{hover.type}</div>
            {hover.tier && (
              <div className="text-muted-foreground">{hover.tier}</div>
            )}
            {hover.source_url && (
              <div className="text-muted-foreground truncate">
                {hover.source_url}
              </div>
            )}
          </div>
        )}
      </div>
      <p className="text-muted-foreground border-border border-t p-2 text-xs">
        {payload.elements.nodes.length} nodes · {payload.elements.edges.length}{" "}
        edges · hash {payload.elements_hash.slice(0, 12)}…
      </p>
    </section>
  );
}
