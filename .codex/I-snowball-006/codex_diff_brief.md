HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-006 — DIFF REVIEW iter 1

Branch `bot/I-snowball-006-export-and-tests`. Brief APPROVE iter 2.

## Files

```
graph_export.ts                     NEW 80 LOC
graph_export_buttons.tsx            NEW 50 LOC
claim_graph.tsx                     MOD +8 LOC (onCyReady callback)
page.tsx                            MOD +12 LOC (cy state, mount buttons)
tests/e2e/graph_page_smoke.spec.ts  NEW 60 LOC (5 cases)
tests/fixtures/graph_payload.json   NEW (3 sources/3 sentences/2 sections/1 frame fixture)
```

## Brief iter 2 → execution

| Brief | Implementation |
|---|---|
| exportPNG returns Blob via cy.png 4x | `graph_export.ts:25-34` |
| exportJSON canonical (positions stripped, sorted by id, recursive sort_keys) | `graph_export.ts:38-62` |
| triggerDownload helper | `graph_export.ts:64-72` |
| Toolbar buttons with data-testid | `graph_export_buttons.tsx:24-43` |
| onCyReady callback prop | `claim_graph.tsx:55-58,65-67` |
| Playwright suggestedFilename().toMatch(/\.png$/) | `graph_page_smoke.spec.ts:44,53` |
| Mocked fetch via page.route | `graph_page_smoke.spec.ts:14-22` |
| Hermetic fixture | `tests/fixtures/graph_payload.json` |

## Smoke
- `npm run typecheck` PASS
- prettier formatted

## Direct questions
1. Diff matches brief iter-2 APPROVE'd scope? Any P0/P1?
2. JSON canonicalization: raw `<`/`>` comparator + recursive sort_keys + position strip. Acceptable for v1 (byte-equality with Python output not claimed; structural equivalence to backend `elements_hash` input)?
3. Playwright assertions use `getByTestId` + `suggestedFilename().toMatch(/\.png$/)`. Matches repo patterns?
4. Anything blocking?

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
