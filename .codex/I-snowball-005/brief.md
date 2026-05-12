HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-005 — snowball BFS + expand-snowball UI

Branch `bot/I-snowball-005-bfs-expand-snowball`. Depends on I-snowball-004 (merged at sha `108d62f5`).

## Scope (narrowed for v1)

The full DECISION.md scope (BFS + evidence_deepener API + expand-collapse + F13 diff overlay) would exceed 200 LOC per file. v1 ships the **client-side frontier walk + highlight UI**:

1. NEW `web/app/runs/[runId]/graph/components/snowball.ts` — `snowballNeighbors(payload, target, maxHops, includeCoCites)` pure function that walks the semantic edges (cites + contradicts, optionally co_cites_default_off) of the already-loaded GraphPayload, BFS-style with maxHops bound; returns a `Set<string>` of node ids in the snowball.
2. MODIFY `web/app/runs/[runId]/graph/components/claim_graph.tsx` — add `snowball-neighbor` cytoscape class + style (subtle blue halo). When `snowballHighlightIds` prop is non-null, apply the class to matching nodes.
3. MODIFY `web/app/runs/[runId]/graph/page.tsx` — add "Expand snowball" button to the toolbar. Click computes `snowballNeighbors(payload, selected_node_id, 2)` and passes the resulting set as `snowballHighlightIds` to ClaimGraph. "Clear snowball" button clears it.
4. MODIFY `web/app/runs/[runId]/graph/components/use_graph_state.ts` — add `snowball_highlight_ids: Set<string> | null` to GraphState + `setSnowballHighlight(ids: Set<string>|null)` action.

**DEFERRED to follow-up issues** (not in v1 scope):
- Backend `/api/runs/{id}/graph/snowball` endpoint (client can compute locally on the loaded payload; backend BFS is only needed for graphs too large to fit client-side, which isn't our scale)
- `cytoscape-expand-collapse` integration (collapse sections to single super-nodes) — visual nicety, not core to snowball semantic
- F13 pin-replay diff overlay (depends on F13 infrastructure which is its own surface)

These belong in I-snowball-005-follow-up if needed.

## Files I have ALSO checked and they're clean:

- `web/app/runs/[runId]/graph/components/use_graph_state.ts` — already has `GraphState` + `GraphAdjacency` + `GraphActions`; will extend with `snowball_highlight_ids`
- `web/app/runs/[runId]/graph/components/claim_graph.tsx` — already has cytoscape class-toggle effect pattern (search-hit, selected); add same pattern for snowball-neighbor
- `web/app/runs/[runId]/graph/components/graph_styles.ts` — already has class-based selectors; add `node.snowball-neighbor`
- `web/lib/api.ts` — `GraphPayload`/`GraphNode`/`GraphEdge` types exist; no API change in v1

## Algorithm spec

```ts
export function snowballNeighbors(
  payload: GraphPayload,
  targetId: string,
  maxHops: number,
  includeCoCites: boolean,
): Set<string> {
  const semanticEdgeTypes = includeCoCites
    ? new Set(["cites", "co_cites_default_off", "contradicts"])
    : new Set(["cites", "contradicts"]);
  // Adjacency on undirected semantic edges (drop section_member).
  const adj = new Map<string, Set<string>>();
  for (const n of payload.elements.nodes) adj.set(n.data.id, new Set());
  for (const e of payload.elements.edges) {
    if (!semanticEdgeTypes.has(e.data.edge_type)) continue;
    adj.get(e.data.source)?.add(e.data.target);
    adj.get(e.data.target)?.add(e.data.source);
  }
  // BFS frontier walk
  const visited = new Set<string>([targetId]);
  let frontier: Set<string> = new Set([targetId]);
  for (let hop = 0; hop < maxHops; hop++) {
    const next = new Set<string>();
    for (const id of frontier) {
      for (const neighbor of adj.get(id) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          next.add(neighbor);
        }
      }
    }
    if (next.size === 0) break;
    frontier = next;
  }
  return visited;
}
```

Note: undirected traversal (matches `cy.elements().bfs()` default); excludes `section_member` and `frame_member` (styling-only edges).

## Toolbar UI

```tsx
<div className="flex items-center gap-2">
  {/* existing search input */}
  <Button
    variant="outline"
    size="sm"
    disabled={!state.selected_node_id}
    onClick={() => {
      if (!state.selected_node_id) return;
      actions.setSnowballHighlight(
        snowballNeighbors(payload, state.selected_node_id, 2, false),
      );
    }}
  >
    Expand snowball (2 hops)
  </Button>
  {state.snowball_highlight_ids && (
    <Button variant="ghost" size="sm" onClick={() => actions.setSnowballHighlight(null)}>
      Clear ({state.snowball_highlight_ids.size} nodes)
    </Button>
  )}
</div>
```

## Stylesheet addition

```ts
{
  selector: "node.snowball-neighbor",
  style: {
    "border-width": 3,
    "border-color": "#3b82f6",
    "background-opacity": 0.95,
  },
}
```

## Direct questions for Codex iter 1

1. Narrowed v1 scope (client-side BFS only, no backend endpoint / no expand-collapse / no F13 overlay) — acceptable, or do you want one of the deferred items moved back into 005?
2. Undirected semantic BFS — correct semantics, or should it be directed (e.g. ArrowRight = only outgoing cites)?
3. The DECISION.md iter-3 BFS reference implementation built a `cy.collection()` and called `.bfs()` natively; I'm using a JS-only Map+Set frontier walk instead because we already have the payload in memory and don't need cytoscape's bfs API. Acceptable, or insist on `cy.elements().bfs()`?
4. UI: "Expand snowball (2 hops)" button + Clear button. Acceptable; add a "1 hop / 3 hops" toggle (P3)?
5. LOC estimate: snowball.ts ~50, use_graph_state.ts +15, claim_graph.tsx +25, page.tsx +25, graph_styles.ts +10. All under 200.

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
