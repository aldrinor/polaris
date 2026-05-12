/**
 * Cytoscape stylesheet + layout constants for ClaimGraph.
 *
 * Extracted from claim_graph.tsx in I-snowball-004 to keep the component
 * under 200 LOC after adding event handlers + hover card + a11y list.
 */

import type cytoscape from "cytoscape";

export const STYLESHEET: cytoscape.StylesheetStyle[] = [
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
    selector: "node.search-hit",
    style: {
      "border-width": 3,
      "border-color": "#facc15",
    },
  },
  {
    selector: "node.selected",
    style: {
      "border-width": 4,
      "border-color": "#0ea5e9",
    },
  },
  {
    selector: "node.snowball-neighbor",
    style: {
      "border-width": 3,
      "border-color": "#3b82f6",
      "background-opacity": 0.95,
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

export const LAYOUT_FCOSE = {
  name: "fcose",
  randomize: false,
  quality: "proof",
  animate: false,
  nodeSeparation: 75,
  idealEdgeLength: 50,
} as unknown as cytoscape.LayoutOptions;

export const LAYOUT_PRESET: cytoscape.LayoutOptions = { name: "preset" };
