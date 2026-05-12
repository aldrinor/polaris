HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-003a — DIFF REVIEW iter 1

Branch `bot/I-snowball-003a-claim-graph-component`. Commit `ca781cbf` implements brief APPROVE'd iter 2.

## Commit summary

```
5 files changed, 413 insertions(+), 3 deletions(-)
- web/lib/api.ts                                                +71 LOC (graph types + getRunGraph)
- web/app/runs/[runId]/graph/page.tsx                           NEW 90 LOC
- web/app/runs/[runId]/graph/components/claim_graph.tsx         NEW 180 LOC
- web/package.json                                              +6 deps (3 runtime + 3 @types/* devDeps)
- web/package-lock.json                                         (transitive)
```

Per-file under 200 LOC.

## Smoke evidence

```
$ npm run typecheck   # PASS zero errors
$ npm run lint        # PASS (3 pre-existing warnings unrelated)
```

## Brief iter 2 → execution mapping

| Brief stage | Execution |
|---|---|
| `getRunGraph(runId)` client + types matching Pydantic | `api.ts:1058-1124` |
| `web/app/runs/[runId]/graph/page.tsx` `'use client'` + `use(params)` + useEffect fetch + loading/error states | `page.tsx:1-87` |
| `<ClaimGraph>` dynamic-import `react-cytoscapejs` with `ssr: false` | `claim_graph.tsx:21-23` |
| `every` (not `some`) for hasPositions, defaults to fcose when mixed | `claim_graph.tsx:155-156` |
| Tier-color + edge-type stylesheet | `claim_graph.tsx:26-127` (8 selectors) |
| `cytoscape.use(fcose)` HMR-idempotent guard | `claim_graph.tsx:13-17` |
| Real spinner (border-spin not text-only) | `page.tsx:65-71` |
| Flex-column section so metadata not clipped | `claim_graph.tsx:163-182` |
| `@types/cytoscape*` for typecheck | all 3 installed; `StylesheetStyle[]` typing (not `Stylesheet[]` — caught by tsc) |

## Files I have ALSO checked and they're clean

- `web/app/inspector/[runId]/page.tsx:1-40` — `'use client'` + `use(params)` precedent
- `web/lib/api.ts:1-50` — BACKEND_URL + ApiError pattern reused
- `web/components/ui/button.tsx` (existing — reused via `<Button>`)
- `src/polaris_graph/api/graph_route.py` — backend Pydantic schema matches TS types byte-for-byte

## Direct questions for Codex iter 1

1. Diff matches brief iter 2 APPROVE'd scope? Any P0/P1?
2. `claim_graph.tsx:60` `"font-weight": "bold" as never` cast — should it use the proper `Css.PropertyValue<'fontWeight'>` form, or is this an unavoidable cast against `Css.Node`'s narrow string-literal typing?
3. `useMemo` over `payload` is correct (same object reference on rerenders); is there a known issue with `<CytoscapeComponent>` re-mounting when elements array identity changes?
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
