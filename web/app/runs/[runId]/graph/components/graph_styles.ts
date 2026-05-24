/**
 * Cytoscape stylesheet + layout constants for ClaimGraph.
 *
 * I-p2-058 (#863): rebuilt to a SEMANTIC GRAPH GRAMMAR so the canvas reads as a
 * knowledge-graph PRODUCT, not raw Cytoscape (Codex frontier/lively audit). The
 * design language stays near-neutral + ONE accent: Canada-red `#c8102e` is
 * reserved for the SELECTION state (scarcity). Liveliness comes from MOTION
 * (animated settle), SHAPE (each node type has a distinct silhouette), label
 * halos (readable over edges), directional edges, and dimming non-neighbours of
 * the selected node — NOT from arbitrary colour. The only meaning-colours are
 * the sanctioned ones: verified-green, contradiction-amber, frame-status
 * (pass/partial/fail), all >=3:1 on white.
 *
 * Concrete hex (cytoscape canvas can't read CSS vars); values mirror the tokens.
 */

import type cytoscape from "cytoscape";

const SLATE_SENTENCE = "#475569"; // slate-600 — claims (many, small)
const SLATE_SOURCE = "#334155"; // slate-700 — evidence
const SLATE_SECTION = "#0f172a"; // slate-900 — section anchors
const SLATE_FRAME = "#64748b"; // slate-500 — frame (overridden by status)
const VERIFIED = "#1f7a44"; // --verified (green)
const AMBER = "#a16207"; // --contradiction (amber; NOT red)
const DESTRUCTIVE = "#991b1b"; // --destructive (dark red, frame fail only)
const BRAND = "#c8102e"; // --primary (SELECTION only — scarcity)
const LABEL = "#1e293b"; // slate-800 label text on white
const HALO = "#ffffff";
const HAIRLINE = "#ffffff"; // node rim → separates nodes from edges/each other

export const STYLESHEET: cytoscape.StylesheetStyle[] = [
  // Base: every node gets a white rim + a label halo so labels stay readable
  // over edges (fixes the collision mush), plus a 150ms transition so hover /
  // selection / fade feel alive.
  {
    selector: "node",
    style: {
      label: "data(label)",
      color: LABEL,
      "font-size": 9,
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 5,
      "text-background-color": HALO,
      "text-background-opacity": 0.85,
      "text-background-padding": 2 as unknown as string,
      "text-background-shape": "roundrectangle",
      "text-max-width": "150px",
      "text-wrap": "ellipsis",
      "border-width": 1.5,
      "border-color": HAIRLINE,
      "border-opacity": 0.95,
      "transition-property":
        "opacity, border-width, border-color, width, height",
      "transition-duration": "0.15s" as unknown as number,
    },
  },
  // sentence/claim — small ellipse (the leaves)
  {
    selector: "node[type='sentence']",
    style: {
      shape: "ellipse",
      "background-color": SLATE_SENTENCE,
      width: 16,
      height: 16,
      "font-size": 8,
    },
  },
  // source — rounded pill (evidence)
  {
    selector: "node[type='source']",
    style: {
      shape: "round-rectangle",
      "background-color": SLATE_SOURCE,
      width: 34,
      height: 22,
      "font-size": 9,
    },
  },
  // section — hexagon anchor (the spine of the brief)
  {
    selector: "node[type='section']",
    style: {
      shape: "hexagon",
      "background-color": SLATE_SECTION,
      width: 40,
      height: 40,
      "font-size": 11,
      "font-weight": "bold" as never,
    },
  },
  // frame — diamond, coloured by coverage status (sanctioned meaning colour)
  {
    selector: "node[type='frame']",
    style: {
      shape: "diamond",
      "background-color": SLATE_FRAME,
      width: 28,
      height: 28,
      "font-size": 9,
    },
  },
  {
    selector: "node[frame_status='pass']",
    style: { "background-color": VERIFIED },
  },
  {
    selector: "node[frame_status='partial']",
    style: { "background-color": AMBER },
  },
  {
    selector: "node[frame_status='fail']",
    style: { "background-color": DESTRUCTIVE },
  },
  {
    selector: "node.bibliography_missing",
    style: {
      "background-opacity": 0.4,
      "border-style": "dashed",
      "border-color": "#475569",
      "border-opacity": 1,
    },
  },
  // Dim everything that is NOT a neighbour of the selected node (set from
  // claim_graph on selection) — the focal "spotlight" frontier move.
  { selector: ".faded", style: { opacity: 0.22 } },
  // State borders — ordered search-hit -> snowball -> selected so Canada-red
  // selection always wins cytoscape source-order precedence (scarcity).
  {
    selector: "node.search-hit",
    style: { "border-width": 3, "border-color": AMBER, "border-opacity": 1 },
  },
  {
    selector: "node.snowball-neighbor",
    style: {
      "border-width": 3,
      "border-color": VERIFIED,
      "border-opacity": 1,
      "background-opacity": 0.95,
    },
  },
  {
    selector: "node.selected",
    style: { "border-width": 4, "border-color": BRAND, "border-opacity": 1 },
  },
  // Edges — directional + layered. cites points claim -> source.
  {
    selector: "edge",
    style: {
      "curve-style": "bezier",
      "transition-property": "opacity, line-color, width",
      "transition-duration": "0.15s" as unknown as number,
    },
  },
  {
    selector: "edge[edge_type='cites']",
    style: {
      "line-color": "#94a3b8", // slate-400 (proof relationship, recedes)
      width: 1.5,
      "target-arrow-shape": "triangle",
      "target-arrow-color": "#94a3b8",
      "arrow-scale": 0.7,
    },
  },
  {
    selector: "edge[edge_type='contradicts']",
    style: {
      "line-color": AMBER,
      width: 2.5,
      "target-arrow-shape": "triangle",
      "target-arrow-color": AMBER,
      "arrow-scale": 0.9,
      "curve-style": "bezier",
    },
  },
  {
    selector: "edge[edge_type='section_member']",
    style: {
      "line-color": "#cbd5e1", // slate-300 dashed structural edge (recedes most)
      "line-style": "dashed",
      width: 1,
    },
  },
];

// I-p2-058 (#863): animate the settle (a brief seeded layout reveal) + more
// breathing room so clusters form readable neighbourhoods instead of a cramped
// diagonal string (Codex P1). animate:"end" runs the layout then animates nodes
// to their final spots — a controlled reveal without a chaotic live simulation.
export const LAYOUT_FCOSE = {
  name: "fcose",
  randomize: true,
  quality: "proof",
  animate: true,
  animationDuration: 750,
  animationEasing: "ease-out",
  nodeSeparation: 140,
  idealEdgeLength: 95,
  nodeRepulsion: 7000,
  gravity: 0.25,
  packComponents: true,
  padding: 36,
} as unknown as cytoscape.LayoutOptions;

export const LAYOUT_PRESET: cytoscape.LayoutOptions = { name: "preset" };
