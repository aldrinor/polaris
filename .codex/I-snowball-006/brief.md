HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-006 — graph PNG + JSON export + Playwright smoke

Combined original 006a + 006b scope per DECISION.md, narrowed for v1.

## v1 scope

1. NEW `web/app/runs/[runId]/graph/components/graph_export.ts` — `exportPNG(cy)` returning a `Blob` via `cy.png({full: true, scale: 4, output: 'blob-promise'})`; `exportJSON(payload)` returning a JSON-serialized blob of the canonical elements (positions stripped, sorted by id, identical to backend `elements_hash` input).
2. NEW Export buttons in `page.tsx` toolbar — "Download PNG" + "Download JSON" triggering browser-side downloads.
3. NEW `web/tests/e2e/graph_page_smoke.spec.ts` — Playwright e2e on `/runs/<fixture>/graph`:
   - Page loads without error
   - Canvas renders (cytoscape instance present)
   - Search input filters list
   - Click node selects (no immediate navigation per I-snowball-005 P1 fix)
   - Click "Expand snowball" → snowball halo appears on neighbors
   - Click "Open Inspector" → router pushes `/inspector/<runId>?focused_node=...`
   - PNG and JSON export buttons trigger downloads (mocked via Playwright `expect(download).toHaveSuffix(".png" | ".json")`)
4. Audit bundle schema: NOT modified in this PR; the bundle integration (server-side audit_bundle picks up exported PNG/JSON) is **DEFERRED** to a follow-up issue (requires backend changes outside the 200-LOC cap).

## DEFERRED (follow-up issues)

- Audit bundle backend integration (server-side picks up PNG/JSON from a posted snapshot endpoint)
- axe-core WCAG-AA test (requires `@axe-core/playwright` config + dedicated test file with detailed rules)
- Perf gate via Lighthouse (Core Web Vitals; needs CI config changes)

These are all valuable but each is its own follow-up issue to keep this PR tractable.

## Files I have ALSO checked and they're clean:

- `web/app/runs/[runId]/graph/components/claim_graph.tsx` — has access to `cyInstance`; will lift it to `cyRef` via callback prop so page.tsx can call `cy.png()` from the toolbar
- `web/tests/e2e/` — existing Playwright tests follow pattern `*.spec.ts`
- `web/package.json` — `@playwright/test` + `@axe-core/playwright` already installed

## Plan

```
graph_export.ts                                    NEW ~80 LOC
graph_page.tsx                                     +30 LOC (export buttons + cyInstance lifting)
claim_graph.tsx                                    +10 LOC (expose cyInstance via callback prop)
web/tests/e2e/graph_page_smoke.spec.ts             NEW ~150 LOC (5-7 test cases)
```

All per-file ≤200 LOC.

## Direct questions for Codex iter 1

1. v1 scope narrowing: defer audit-bundle integration + axe-core + perf gate to follow-ups. Acceptable?
2. `cy.png({full: true, scale: 4, output: 'blob-promise'})` returns a Promise<Blob> per Cytoscape docs; export function awaits + triggers browser download via `URL.createObjectURL` + temp `<a download>` click. Acceptable pattern?
3. Lifting `cyInstance` via a callback prop `onCyReady` from ClaimGraph to page.tsx — acceptable, or do I refactor `useGraphState` to own the cy instance?
4. Playwright tests against backend fixture run — should I use the live backend or mock fetch responses for these tests? Existing e2e patterns likely answer this.
5. LOC estimate acceptable?

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
