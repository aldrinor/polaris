HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-004 — DIFF REVIEW iter 1

Branch `bot/I-snowball-004-graph-interaction-a11y`. Diff implements brief APPROVE'd iter 2.

## Commit summary

```
5 files changed
- graph_styles.ts                   NEW 130 LOC (extracted from claim_graph)
- use_graph_state.ts                NEW 85 LOC (hook + shared predicate)
- accessible_graph_list.tsx         NEW 165 LOC (parallel <ol> + keyboard handler)
- claim_graph.tsx                   MODIFIED ~180 LOC (event handlers + hover card + selection sync)
- page.tsx                          MODIFIED ~135 LOC (mount hook + search input + grid layout)
```

## Brief iter 2 → execution mapping

| Brief stage | Implementation |
|---|---|
| Idempotent cy event binding via useState(cy) + useEffect cleanup | `claim_graph.tsx:81-113` |
| Custom canvas-anchored tooltip (NOT EvidenceTooltip) | `claim_graph.tsx:154-171` |
| Arrow-key real edge adjacency on semantic edges (no section_member) | `use_graph_state.ts:63-77` + `accessible_graph_list.tsx:91-110` |
| Shared `nodeMatchesQuery` predicate | `use_graph_state.ts:32` exported, used at `accessible_graph_list.tsx` filter + `claim_graph.tsx:121-125` highlight |
| `role="region"` on `<section>` wrapper, NOT on `<ol>` | `accessible_graph_list.tsx:122` |
| onFocus syncs selection | `accessible_graph_list.tsx:164` Button onFocus |
| URLSearchParams for focused_node | `claim_graph.tsx:87`, `accessible_graph_list.tsx:81` |
| Preventdefault on handled keys | `accessible_graph_list.tsx:75-110` |
| React.KeyboardEvent type | `accessible_graph_list.tsx:14` import + handler signature |

## Smoke

- `npm run typecheck` PASS
- `npm run lint` PASS (only pre-existing warnings)

## Direct questions for Codex iter 1

1. Diff matches brief iter-2 APPROVE'd scope? Any P0/P1?
2. Hover card position: I use `node.renderedPosition()` which returns coords relative to the cytoscape canvas, and I position the absolute div with `left: x+12, top: y+12` inside the relative-positioned `<div className="relative h-[600px] w-full">` wrapper. Is the coordinate plane correct, or do I need to account for `cy.pan()` / `cy.zoom()` deltas?
3. `<CytoscapeComponent cy={(cy) => setCyInstance(cy)}>` — the prop fires once per mount per react-cytoscapejs implementation, and setCyInstance is stable from useState. Acceptable, or do you want a stable callback?
4. `<Button onFocus>` syncs selection on Tab. Acceptable as a roving-tabindex substitute, or should I add explicit `tabIndex` management?
5. Anything blocking?

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
