HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-005 — DIFF REVIEW iter 1

Branch `bot/I-snowball-005-bfs-expand-snowball`. Implements brief APPROVE'd iter 2.

## Commit summary

```
5 files changed, 128 insertions(+), 14 deletions(-)
- snowball.ts                   NEW 60 LOC (BFS pure function)
- use_graph_state.ts            +6 (snowball_highlight_ids state)
- claim_graph.tsx               -2 +18 (drop router import from tap; add snowball-neighbor class effect)
- graph_styles.ts               +8 (node.snowball-neighbor style)
- page.tsx                      +35 (Open Inspector + Expand snowball + Clear buttons; useRouter)
```

## Brief iter 2 → execution mapping

| Brief stage | Implementation |
|---|---|
| `snowballNeighbors(payload, target, maxHops)` pure BFS | `snowball.ts:23-58` |
| Drop `includeCoCites` per iter-2 P2 (schema doesn't include co_cites_default_off) | `snowball.ts:17` SEMANTIC_EDGE_TYPES = {cites, contradicts} only |
| Selection-only tap; Open Inspector via button | `claim_graph.tsx:82-87` (no router.push); `page.tsx:113-119` Open Inspector button |
| node.snowball-neighbor class effect | `claim_graph.tsx:124-131` |
| useGraphState exposes snowball_highlight_ids + setSnowballHighlight | `use_graph_state.ts:14,30,72-78` |
| Toolbar: "Expand snowball (2 hops)" + Clear | `page.tsx:121-134` |

## Smoke

- `npm run typecheck` PASS
- prettier formatted

## Direct questions for Codex iter 1

1. Diff matches brief iter-2? Any P0/P1?
2. The "Open Inspector" button uses `state.selected_node_id`; matches the iter-1 P1 fix?
3. Anything blocking?

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
