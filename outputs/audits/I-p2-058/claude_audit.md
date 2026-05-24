# Claude architect audit — I-p2-058 (#863): Knowledge-graph frontier/lively rebuild

## Goal
Operator directive: drill the UI to 100% at a frontier-competitive + LIVELY bar — "if UI is ugly,
no matter how good we make, no one would look at it." The knowledge graph (/runs/[runId]/graph) is
the highest visual-impact page and had NOT been re-audited under the current bar. Per the directive
to force Codex to review + comment, I ran the visual gate on the CURRENT graph first; Codex's
verdict: "raw Cytoscape output inside a clean admin page, not a knowledge graph product."

## What looking-at-it found (Codex frontier audit iter-1)
Monochrome slate dots, colliding grey labels, thin directionless edges, a cramped diagonal layout,
`animate:false` (nodes pop in, no settle), no focal interaction, a right rail that read like an
admin table of repeated "Inspect" links + a raw `bg-green-100` tier badge.

## What changed (palette-safe — near-neutral + scarce-red selection; life from motion/shape/depth)
- **graph_styles.ts**: a SEMANTIC GRAPH GRAMMAR — node shapes by type (hexagon section / ellipse
  claim / rounded-pill source / diamond frame coloured by status: pass=verified / partial=
  contradiction / fail=destructive); white label halos + ellipsis (kills collision); directional,
  layered edges (cites=thin arrowed slate recede, contradicts=thicker amber arrow, section_member=
  dashed recede); animated fcose settle (750ms) + more separation → readable clusters; `.faded`
  (0.22) for the focal spotlight.
- **claim_graph.tsx**: dot-grid canvas backdrop + card elevation (was flat/document-like); on
  selection, dim everything outside the node's closed neighbourhood; shorter mobile graph viewport.
- **use_graph_state.ts**: lazy useState initializer seeds the first section as the DEFAULT selected
  node so the graph opens on a focal path (the spotlight is the default product moment), not an
  inert all-equal map. No effect → no setState-in-effect.
- **accessible_graph_list.tsx**: the rail became a navigator — each row leads with a canvas-matching
  TYPE GLYPH, "Inspect" text → a single subtle arrow icon (label is the focus), tokenized tier
  badge (was raw bg-green-100), row hover.

## Honest framing
No rainbow / arbitrary colour was added — the only meaning-colours are the sanctioned tokens
(verified / contradiction / destructive / brand-red selection). There is no per-node confidence
field in the graph payload, so the rail surfaces only the HONEST available signals (type, source
tier, frame status). No fabricated SHIPPED data — the render fixture is not committed.

## Dual Codex gate (frontier/lively bar, forced critique)
- Visual `-i`: iter-1 REQUEST_CHANGES ("raw Cytoscape"); iter-2 REQUEST_CHANGES (default lacked a
  focal path; rail = admin table); iter-3 APPROVE (desktop A- / selected A- / mobile B → mobile
  viewport tweak to B+). Code diff APPROVE. Brief APPROVE.
- Residual P2 (accept_remaining): a default-selected node can sit outside the search-filtered list
  until focus moves — edge case, not an execution blocker; Inspect links remain correct via onFocus.

## Preserved
The real getRunGraph fetch, all cytoscape interactions (search, snowball expand, keyboard nav, the
accessible list as the canonical a11y surface), and testids (graph-page, claim-graph,
graph-list-row-*).

## Honest verification state
LIVE-populated verification on polarisresearch.ca is DEFERRED — needs a real run that produced a
graph + the reviewer credential. The grammar/states verified against a route-mocked graph fixture
(visual audit only; never shipped).

canonical-diff-sha256: ecd76d267f04dd155599f7aa6964e02953321b9269bf39c1d2f058b19198ecc6
