"use client";

import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import dynamic from "next/dynamic";
import { useMemo } from "react";

import type { GraphPayload } from "@/lib/api";

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

interface ClaimGraphProps {
  payload: GraphPayload;
}

const STYLESHEET: cytoscape.StylesheetStyle[] = [
  {
    selector: "node[type='sentence']",
    style: {
      "background-color": "#3b82f6",
      width: 18,
      height: 18,
      label: "data(label)",
      "font-size": 8,
      color: "#1e293b",
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 4,
    },
  },
  {
    selector: "node[type='source']",
    style: {
      "background-color": "#22c55e",
      width: 26,
      height: 26,
      label: "data(label)",
      "font-size": 9,
      color: "#1e293b",
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 4,
      "text-max-width": "180px",
      "text-wrap": "ellipsis",
    },
  },
  {
    selector: "node[type='section']",
    style: {
      "background-color": "#a3a3a3",
      width: 30,
      height: 30,
      label: "data(label)",
      "font-weight": "bold" as never,
      "font-size": 10,
      color: "#0f172a",
    },
  },
  {
    selector: "node[type='frame']",
    style: {
      "background-color": "#f59e0b",
      width: 22,
      height: 22,
      label: "data(label)",
      "font-size": 9,
      color: "#1e293b",
    },
  },
  {
    selector: "node.bibliography_missing",
    style: {
      "background-color": "#9ca3af",
      "border-style": "dashed",
      "border-width": 1,
      "border-color": "#6b7280",
    },
  },
  {
    selector: "edge[edge_type='cites']",
    style: {
      "line-color": "#60a5fa",
      width: 1,
      "curve-style": "bezier",
    },
  },
  {
    selector: "edge[edge_type='contradicts']",
    style: {
      "line-color": "#ef4444",
      width: 2,
      "curve-style": "bezier",
      "line-style": "solid",
    },
  },
  {
    selector: "edge[edge_type='section_member']",
    style: {
      "line-color": "#d4d4d4",
      "line-style": "dashed",
      width: 1,
      opacity: 0.5,
    },
  },
];

const LAYOUT_FCOSE = {
  name: "fcose",
  randomize: false,
  quality: "proof",
  animate: false,
  nodeSeparation: 75,
  idealEdgeLength: 50,
} as unknown as cytoscape.LayoutOptions;

const LAYOUT_PRESET: cytoscape.LayoutOptions = { name: "preset" };

export function ClaimGraph({ payload }: ClaimGraphProps) {
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

  return (
    <section
      aria-label="Claim graph"
      data-testid="claim-graph"
      className="border-border flex w-full flex-col overflow-hidden rounded-md border"
    >
      <div className="h-[600px] w-full">
        <CytoscapeComponent
          elements={elements}
          style={{ width: "100%", height: "100%" }}
          layout={layout}
          stylesheet={STYLESHEET}
        />
      </div>
      <p className="text-muted-foreground border-border border-t p-2 text-xs">
        {payload.elements.nodes.length} nodes · {payload.elements.edges.length}{" "}
        edges · hash {payload.elements_hash.slice(0, 12)}…
      </p>
    </section>
  );
}
