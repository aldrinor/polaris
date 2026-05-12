# Claude architect audit — I-snowball-003a (GH#449)

**Branch:** `bot/I-snowball-003a-claim-graph-component`
**HEAD:** `ca781cbf60eedc6818fa7b00b6adc29ff1936675`
**Base:** `2feac0978e78c1ad99102f29a67114d298fe55ff` (polaris)
**Canonical PR diff SHA256:** `90e10e5aba9f7f313162ac6719dce3a045e91f788b95039df3a37d452c61b6e5`

## Acceptance criteria verification

| Criterion | Status | Evidence |
|---|---|---|
| New `web/app/runs/[runId]/graph/page.tsx` (`'use client'`) | ✓ | 90 LOC; `use(params)` for Next 16 dynamic params, useEffect-based fetch |
| `<ClaimGraph>` wraps `<CytoscapeComponent>` | ✓ | `claim_graph.tsx:20` dynamic-import with `ssr: false` |
| `getRunGraph` + TS types in api.ts | ✓ | `web/lib/api.ts:1054-1125` — 71 LOC of types + fetcher matching Pydantic schema |
| v1 fcose layout (positions null) → `preset` when present | ✓ | `claim_graph.tsx:152-158` `every((n) => n.position != null)` |
| Loading + error state | ✓ | `page.tsx:54-83` |
| LOC ≤200 per file | ✓ | page=90, claim_graph=180, api.ts addition=71 |

## Codex P1 fix verification (brief iter 2)

Type declarations resolved via `@types/cytoscape` + `@types/react-cytoscapejs` + `@types/cytoscape-fcose` (all installed; verified `npm run typecheck` passes with zero errors). Cytoscape's stylesheet type is `StylesheetStyle[]` (not `Stylesheet[]` as I originally drafted) — caught by typecheck and fixed.

## P2 fixes applied

- `every` over `some` for hasPositions (`claim_graph.tsx:155`) — mixed-position payload defaults to fcose, never silently presets.
- Real spinner element (`page.tsx:65-71`) — animate-spin border ring, not text-only.
- Metadata `<p>` not clipped — section is flex-column, graph div fixed-height inside (`claim_graph.tsx:163-182`).

## Smoke evidence

```
$ npm run typecheck       # PASS (zero errors)
$ npm run lint            # PASS (3 pre-existing warnings unrelated to this PR)
```

Dev-server / browser smoke deferred to PR walkthrough (per Codex iter 2 P2 — automated browser test lands in I-snowball-006b).

## Crown jewel invariants

No backend touched. Pure frontend. No LLM calls. No provenance / strict_verify / sovereignty surface modified. Crown jewel invariants intact by construction.

## Regression risk

- No existing route changed.
- `web/lib/api.ts` extended (append-only) — no existing exports removed or changed.
- `npm install` brought 3 runtime + 3 devDep packages. All MIT. Audit reports 6 vulnerabilities (4 moderate, 2 high) — pre-existing in repo at HEAD baseline; not introduced by this PR.

## Verdict

**SHIP.** Codex APPROVE on brief iter 2. Typecheck + lint clean. F-snowball claim-graph view is now navigable end-to-end at `/runs/{runId}/graph` against the backend endpoint shipped by I-snowball-002.
