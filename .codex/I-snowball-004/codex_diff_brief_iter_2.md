HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-004 — DIFF REVIEW iter 2 (P1 + P2 fixes)

Iter 1: 1 P1 (Enter uses focused-link not selected node) + 1 P2 (nodeMatchesQuery not shared). Both fixed in commit `e0aa951b`.

## P1 fix — Enter uses `state.selected_node_id`

`accessible_graph_list.tsx` onKeyDown handler now intercepts Enter BEFORE the focused link's default action:

```ts
if (e.key === "Enter" && state.selected_node_id) {
  e.preventDefault();
  router.push(inspectorHref(state.selected_node_id));
  return;
}
```

Imports added: `useRouter` from `next/navigation`.

## P2 fix — share `nodeMatchesQuery`

`claim_graph.tsx` search-highlight effect now imports and uses `nodeMatchesQuery` from `use_graph_state.ts` (the same predicate the list filter uses). Wraps cytoscape node into a `{ data: ... }` shape matching the helper's input.

## Smoke

`npm run typecheck` PASS after fixes.

## Direct question for Codex iter 2

Anything genuinely blocking? P3 cosmetic notes from iter 1 are acknowledged but not blocking.

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
