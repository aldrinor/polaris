HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-005 — brief iter 2 (1 P1 + 1 P2 fix)

## P1 fix — selection without navigation

Change cytoscape tap handler in `claim_graph.tsx` to **select-only** (not navigate). Open Inspector via:
- "Open Inspector" button in page toolbar (uses `state.selected_node_id`)
- "Inspect" button per row in `AccessibleGraphList` (already present from I-snowball-004)
- Double-click on canvas node (`cy.on('dblclick')`) optional — defer to follow-up

Updated tap handler:
```ts
const onTap = (evt: cytoscape.EventObject) => {
  setSelectedNodeId(evt.target.id());
  // No router.push; explicit Inspector navigation is now the button's job.
};
```

Removes `useRouter` import + `runId` dep from `claim_graph.tsx`'s effect (cleaner; router push moves to page.tsx).

New page toolbar:
```tsx
<Button
  variant="outline" size="sm"
  disabled={!state.selected_node_id}
  onClick={() => state.selected_node_id && router.push(inspectorHref(state.selected_node_id))}
>
  Open Inspector
</Button>
<Button
  variant="outline" size="sm"
  disabled={!state.selected_node_id}
  onClick={() => state.selected_node_id && actions.setSnowballHighlight(
    snowballNeighbors(payload, state.selected_node_id, 2),
  )}
>
  Expand snowball (2 hops)
</Button>
```

## P2 fix — drop `co_cites_default_off` from v1 helper

That edge_type isn't in the current schema (`cites | contradicts | section_member` only). Drop `includeCoCites` parameter for v1; helper walks `cites + contradicts` only. If/when co-citation edges are added in a future PR, reintroduce the parameter.

```ts
export function snowballNeighbors(
  payload: GraphPayload,
  targetId: string,
  maxHops: number,
): Set<string> {
  const SEMANTIC = new Set<GraphEdgeType>(["cites", "contradicts"]);
  // ... rest unchanged
}
```

## P2 deferral — unit test for snowballNeighbors

`web/` has no jest/vitest setup (`tests/e2e` only). Adding a unit test runner is out of scope for this PR. Behavior is covered indirectly via Playwright in I-snowball-006 (e2e on the "Expand snowball" button). Documented as a follow-up.

## Direct questions for Codex iter 2

1. Selection-only tap + explicit "Open Inspector" button — acceptable? Or do you require a double-click route to Inspector?
2. Dropping `includeCoCites` for v1 — acceptable, or block?
3. Anything else genuinely blocking?

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
