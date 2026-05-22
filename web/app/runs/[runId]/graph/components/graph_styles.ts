/**
 * Cytoscape stylesheet + layout constants for ClaimGraph.
 *
 * Extracted from claim_graph.tsx in I-snowball-004 to keep the component
 * under 200 LOC after adding event handlers + hover card + a11y list.
 */

import type cytoscape from "cytoscape";

// I-p2-012 (#751): aligned to the #742 white + Canada-red system. Concrete
// values (cytoscape canvas can't read CSS vars). Red is reserved for the
// SELECTION state (scarcity); node types are muted lightness-tiered slates
// (all >=3:1 on white); contradiction is amber (NOT red, so red stays scarce).
// State selectors are ordered search-hit -> snowball -> selected so the
// Canada-red selection always wins cytoscape's source-order precedence.
export const STYLESHEET: cytoscape.StylesheetStyle[] = [
  {
    selector: "node[type='sentence']",
    style: {
      "background-color": "#475569", // slate-600
      width: 18,
      height: 18,
      label: "data(label)",
      "font-size": 8,
      color: "#1e293b", // label below node, on white
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 4,
    },
  },
  {
    selector: "node[type='source']",
    style: {
      "background-color": "#334155", // slate-700
      width: 26,
      height: 26,
      label: "data(label)",
      "font-size": 9,
      color: "#1e293b", // label below node, on white
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
      "background-color": "#1e293b", // slate-800 (anchor)
      width: 30,
      height: 30,
      label: "data(label)",
      "font-weight": "bold" as never,
      "font-size": 10,
      color: "#f8fafc", // label centered ON the dark node -> light text
    },
  },
  {
    selector: "node[type='frame']",
    style: {
      "background-color": "#64748b", // slate-500
      width: 22,
      height: 22,
      label: "data(label)",
      "font-size": 9,
      color: "#f8fafc", // label centered ON the mid node -> light text
    },
  },
  {
    selector: "node.bibliography_missing",
    style: {
      "background-color": "#94a3b8", // faded = missing
      "border-style": "dashed",
      "border-width": 1,
      "border-color": "#475569", // >=3:1 dashed marker conveys "missing"
    },
  },
  {
    selector: "node.search-hit",
    style: {
      "border-width": 3,
      "border-color": "#a16207", // amber-700 (search mode)
    },
  },
  {
    selector: "node.snowball-neighbor",
    style: {
      "border-width": 3,
      "border-color": "#1f7a44", // verified-green (connected)
      "background-opacity": 0.95,
    },
  },
  {
    // LAST among state selectors: Canada-red selection always wins (scarcity).
    selector: "node.selected",
    style: {
      "border-width": 4,
      "border-color": "#c8102e", // Canada-red (--primary)
    },
  },
  {
    selector: "edge[edge_type='cites']",
    style: {
      "line-color": "#475569", // slate-600 (proof relationship)
      width: 1,
      "curve-style": "bezier",
    },
  },
  {
    selector: "edge[edge_type='contradicts']",
    style: {
      "line-color": "#a16207", // amber (conflict; NOT red)
      width: 2,
      "curve-style": "bezier",
      "line-style": "solid",
    },
  },
  {
    selector: "edge[edge_type='section_member']",
    style: {
      "line-color": "#64748b", // slate-500 dashed, full opacity (>=3:1)
      "line-style": "dashed",
      width: 1,
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
