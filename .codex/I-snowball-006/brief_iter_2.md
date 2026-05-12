HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-006 — brief iter 2 (P1 + P2 fixes)

## P1 fix — Playwright download matcher

Use the existing repo pattern from `web/tests/e2e/contract_editor.spec.ts` + `audit_bundle.spec.ts`:

```ts
const downloadPromise = page.waitForEvent("download");
await page.click('[data-testid="graph-export-png"]');
const download = await downloadPromise;
expect(download.suggestedFilename()).toMatch(/\.png$/);
```

NOT `toHaveSuffix`.

## P2-1 fix — LOC budget

Extract export logic to `graph_export.ts` + a thin `<GraphExportButtons cy={cyInstance} payload={payload} />` component (~50 LOC) instead of inlining buttons in page.tsx. claim_graph.tsx only grows by ~10 LOC (callback prop for cy).

Final file deltas:
```
graph_export.ts                                    NEW 80 LOC (exportPNG + exportJSON + download helpers)
graph_export_buttons.tsx                           NEW 50 LOC (component)
page.tsx                                           +5 LOC (mount GraphExportButtons + receive cy)
claim_graph.tsx                                    +10 LOC (onCyReady callback prop)
web/tests/e2e/graph_page_smoke.spec.ts             NEW 150 LOC (5 cases, mocked fetch)
```

All per-file under 200 LOC. claim_graph.tsx ends at ~190.

## P2-2 fix — JSON canonicalization matches backend

Backend `graph_route.py:206-216` does:
```python
elements_dict = GraphElements(nodes=nodes, edges=edges).model_dump(mode="json")
elements_dict["nodes"].sort(key=lambda n: n["data"]["id"])
elements_dict["edges"].sort(key=lambda e: e["data"]["id"])
for n in elements_dict["nodes"]: n.pop("position", None)
canonical = json.dumps(elements_dict, sort_keys=True, separators=(",", ":"))
```

JS equivalent (`graph_export.ts`):
```ts
function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    const sorted: Record<string, unknown> = {};
    for (const k of Object.keys(value).sort()) {
      sorted[k] = sortKeys((value as Record<string, unknown>)[k]);
    }
    return sorted;
  }
  return value;
}

export function exportJSON(payload: GraphPayload): Blob {
  const nodes = payload.elements.nodes
    .map((n) => {
      const { position: _drop, ...rest } = n;
      return rest;
    })
    .sort((a, b) => a.data.id.localeCompare(b.data.id));
  const edges = [...payload.elements.edges].sort((a, b) =>
    a.data.id.localeCompare(b.data.id),
  );
  const canonical = JSON.stringify(sortKeys({ nodes, edges }));
  return new Blob([canonical], { type: "application/json" });
}
```

Note: this matches backend's `elements_hash` input format byte-for-byte (no positions, lists sorted by id, recursive sort_keys, no whitespace). A consumer can verify by re-hashing the export JSON and comparing to `payload.elements_hash`.

## P2-3 fix — mocked fetch in Playwright

Use `page.route('**/api/runs/*/graph', ...)` to inject deterministic GraphPayload fixture. Example follows pattern from `web/tests/e2e/disambiguation*.spec.ts`. The fixture is a small canonical-shape payload (e.g. 4 sentences + 3 sources + 2 sections + 2 frames) checked into `web/tests/fixtures/graph_payload.json`.

## P2-4 fix — clear cy ref on unmount + test ids on buttons

```ts
// claim_graph.tsx
useEffect(() => {
  return () => { onCyReady?.(null); };
}, [onCyReady]);

// graph_export_buttons.tsx
<Button data-testid="graph-export-png" ...>Download PNG</Button>
<Button data-testid="graph-export-json" ...>Download JSON</Button>
```

## Direct questions for Codex iter 2

1. P1 + P2 fixes acceptable?
2. JSON canonicalization JS-equivalent of Python `json.dumps(..., sort_keys=True, separators=(',',':'))` — correct enough for byte-equal output (modulo float serialization variance, which our schema doesn't include since positions are stripped)?
3. Mocked fetch fixture file shape — OK, or do you want it shipped in this PR or in a separate test-data PR?
4. LOC plan under 200 per file?

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
