HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-004 — brief iter 2 (3 P1 fixes)

## P1-1.1 fix — idempotent cytoscape event registration

Use `useEffect` keyed on `cy` ref + cleanup via `cy.off()`. The `cy={...}` callback fires once per mount; we capture the instance, then bind handlers in a separate effect that owns its cleanup:

```ts
const [cyInstance, setCyInstance] = useState<cytoscape.Core | null>(null);

useEffect(() => {
  if (!cyInstance) return;
  const onTap = (evt: cytoscape.EventObject) => { ... };
  const onMouseover = (evt: cytoscape.EventObject) => { ... };
  const onMouseout = (evt: cytoscape.EventObject) => { ... };
  cyInstance.on("tap", "node", onTap);
  cyInstance.on("mouseover", "node", onMouseover);
  cyInstance.on("mouseout", "node", onMouseout);
  return () => {
    cyInstance.off("tap", "node", onTap);
    cyInstance.off("mouseover", "node", onMouseover);
    cyInstance.off("mouseout", "node", onMouseout);
  };
}, [cyInstance, runId, setSelectedNodeId, setHoverNode]);
```

Pass `cy={setCyInstance}` to `<CytoscapeComponent>` — fires once per mount; no per-render stacking.

## P1-1.2 fix — custom canvas-anchored tooltip (NOT EvidenceTooltip Radix wrapper)

Radix `Tooltip.Trigger` requires a real DOM element; canvas nodes have no DOM analog. v1 ships a thin custom hover-card:

```tsx
// claim_graph.tsx adds local state
const [hover, setHover] = useState<{ node: cytoscape.NodeDataDefinition; x: number; y: number } | null>(null);

// in useEffect handlers:
onMouseover = (evt) => {
  const rendered = evt.target.renderedPosition();
  setHover({ node: evt.target.data(), x: rendered.x, y: rendered.y });
};
onMouseout = () => setHover(null);

// render: absolute-positioned card inside the graph wrapper
{hover && (
  <div
    role="tooltip"
    className="absolute z-50 max-w-xs rounded-md border bg-popover px-3 py-2 text-xs shadow-md"
    style={{ left: hover.x + 12, top: hover.y + 12, pointerEvents: "none" }}
  >
    <div className="font-medium">{hover.node.label}</div>
    {hover.node.tier && <div className="text-muted-foreground">{hover.node.tier}</div>}
    {hover.node.source_url && <div className="text-muted-foreground truncate">{hover.node.source_url}</div>}
  </div>
)}
```

This intentionally does NOT use `<EvidenceTooltip>`. The existing F6 EvidenceTooltip is for prose sentences in the report; the graph node hover is a different surface that deserves its own thin component. Avoids the virtual-anchor problem entirely. ~30 LOC.

If a future PR wants Radix-style consistency, that's I-snowball-004b-follow-up (out of scope here).

## P1-1.3 fix — arrow-key edge adjacency traversal

`AccessibleGraphList` builds a `adjacency` map at mount and arrow keys traverse the graph:

```ts
const adjacency = useMemo(() => {
  const map = new Map<string, { in: string[]; out: string[]; siblings: string[] }>();
  for (const n of payload.elements.nodes) {
    map.set(n.data.id, { in: [], out: [], siblings: [] });
  }
  for (const e of payload.elements.edges) {
    // skip section_member edges for traversal (they're styling-only per I-snowball-002 brief)
    if (e.data.edge_type === "section_member") continue;
    map.get(e.data.source)?.out.push(e.data.target);
    map.get(e.data.target)?.in.push(e.data.source);
  }
  return map;
}, [payload]);

const onKey = (e: KeyboardEvent) => {
  if (!selected_node_id) return;
  const adj = adjacency.get(selected_node_id);
  if (!adj) return;
  if (e.key === "ArrowRight") setSelectedNodeId(adj.out[0] ?? selected_node_id);
  if (e.key === "ArrowLeft") setSelectedNodeId(adj.in[0] ?? selected_node_id);
  if (e.key === "ArrowDown") { /* next visible in list order */ }
  if (e.key === "ArrowUp") { /* prev visible in list order */ }
  if (e.key === "Enter") router.push(`/inspector/${runId}?${new URLSearchParams({ focused_node: selected_node_id }).toString()}`);
  if (e.key === "Escape") setSelectedNodeId(null);
  if (e.key === "/") { e.preventDefault(); searchInputRef.current?.focus(); }
};
```

Semantics:
- **ArrowRight** = follow outgoing semantic edge (sentence → source first; source → contradicting source first)
- **ArrowLeft** = follow incoming
- **ArrowUp/Down** = previous/next in visible list display order
- **Enter** = open Inspector
- **Esc** = clear selection
- **`/`** = focus search input

## P2 fixes applied

- **P2-1.4 split LOC**: extract stylesheet + layout constants into `graph_styles.ts` (~70 LOC); `claim_graph.tsx` stays under 200 LOC after adding event handlers.
- **P2-1.5 shared search predicate**: extract `nodeMatchesQuery(node, query)` helper in `use_graph_state.ts`; both list filter AND canvas highlight import it.
- **P2-1.6 `role="region"` on wrapper**: wrap `<ol>` in `<section role="region" aria-label="Claim graph">` so list semantics stay intact.
- **P2-1.7 onFocus syncs state**: each `<li>` button has `onFocus={() => setSelectedNodeId(node.id)}` so tab-through keeps canvas + list selection in sync.
- **P2-1.8 URLSearchParams**: use `new URLSearchParams({focused_node: id}).toString()` consistently (router.push + handler).
- **P2-1.1 EvidenceTooltip tier widening**: not needed; custom canvas tooltip in P1-1.2 fix carries tier as a string (graceful pass-through).

## Revised file plan

```
web/app/runs/[runId]/graph/components/
  graph_styles.ts                   NEW ~80 LOC  (STYLESHEET + LAYOUT_FCOSE + LAYOUT_PRESET)
  use_graph_state.ts                NEW ~70 LOC  (hook + nodeMatchesQuery helper)
  accessible_graph_list.tsx         NEW ~140 LOC (list + roving keyboard)
  claim_graph.tsx                   MODIFIED net +30 (extract styles -50, add event handlers +50, add hover card +30)
web/app/runs/[runId]/graph/
  page.tsx                          MODIFIED +40 (mount hook + AccessibleGraphList + search input)
```

LOC per file:
- graph_styles.ts ≈ 80
- use_graph_state.ts ≈ 70
- accessible_graph_list.tsx ≈ 140
- claim_graph.tsx ≈ 180 (after split)
- page.tsx ≈ 130

All under 200.

## Direct questions for Codex iter 2

1. P1 fixes correct?
2. Custom canvas tooltip approach (not EvidenceTooltip Radix) — accept v1, or insist on a Radix-virtual-anchor solution this PR?
3. Arrow-key semantics: ArrowRight=outgoing, ArrowLeft=incoming, ArrowUp/Down=list-order. Acceptable, or do you prefer ArrowUp/Down=adjacency / ArrowLeft/Right=list?
4. Anything else blocking?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
