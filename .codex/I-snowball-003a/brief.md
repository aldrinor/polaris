HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-003a — `<ClaimGraph>` component + preset-or-fcose rendering

GH#449. Branch `bot/I-snowball-003a-claim-graph-component`. Second issue in F-snowball workstream; depends on I-snowball-002 (now merged at sha 2d4653a9).

## Scope

- NEW route page: `web/app/runs/[runId]/graph/page.tsx` (`'use client'`).
- NEW component: `web/app/runs/[runId]/graph/components/claim_graph.tsx`.
- NEW API client: extend `web/lib/api.ts` with `getRunGraph(runId)` + TypeScript types matching the Pydantic schema in `src/polaris_graph/api/graph_route.py`.
- Renders `GraphPayload` via `react-cytoscapejs`. v1 server returns `position: null` so render uses `layout: { name: "fcose" }` (auto-layout on mount) with a loading spinner; future I-snowball-002b will add server-side positions and switch to `preset`.
- Loading state + error state (404/422/network).
- LOC ≤200 per file.

## Decision-doc reaffirmation

Per `.codex/I-snowball-001/DECISION.md` Codex APPROVE iter 4:
- Library: `cytoscape@3.30.4` + `react-cytoscapejs@2.0.0` + `cytoscape-fcose@2.2.0` (installed in `web/package.json` on this branch — verified).
- SSR-unsafe; use `'use client'` + dynamic-import `CytoscapeComponent` with `ssr: false`.
- Layout: when `position` is present (future), use `preset`; when `position` is null (v1), use `fcose` with `randomize: false, quality: 'proof', animate: false`.

## Compat spike (P1 candidate for Codex)

`react-cytoscapejs@2.0.0` was last updated 2024. React 19 + Next 16 may not be officially supported. **Spike plan:**
- Render `<CytoscapeComponent elements={[]} />` in an isolated test page; if it throws or renders blank, fall back to a thin 30-LOC wrapper that calls `cytoscape({...})` inside `useEffect` directly.
- Document outcome in `.codex/I-snowball-003a/spike_react_cytoscapejs.md`.
- If fallback is required, swap the import in `claim_graph.tsx` to the direct-mount wrapper.

## Files I have ALSO checked and they're clean:

- `web/package.json` — cytoscape@^3.30.4 + react-cytoscapejs@^2.0.0 + cytoscape-fcose@^2.2.0 now in dependencies
- `web/app/inspector/[runId]/page.tsx` — `'use client'` + `use(params)` pattern reference
- `web/lib/api.ts` — `BACKEND_URL`, `TemplateId`, `RunStatus`, type-export pattern reference
- `src/polaris_graph/api/graph_route.py` — Pydantic models for `GraphPayload`/`NodeData`/`EdgeData`/`GraphDiagnostics` (source of truth for TS types)
- `src/polaris_v6/api/app.py:165` — route mounted at `/api/runs/{run_id}/graph`

## Proposed implementation

### 1. `web/lib/api.ts` — extend (NOT replace) with graph types + client

```ts
export type GraphNodeType = "sentence" | "source" | "section" | "frame";
export type GraphEdgeType = "cites" | "contradicts" | "section_member";
export type Tier = "T1" | "T2" | "T3" | "T4" | "T5" | "T6" | "T7";
export type FrameStatus = "pass" | "partial" | "fail";

export interface GraphNodeData {
  id: string;
  type: GraphNodeType;
  label: string;
  tier?: Tier;
  sentence_text?: string;
  source_url?: string;
  section_title?: string;
  frame_status?: FrameStatus;
  classes?: string;
}

export interface GraphPosition { x: number; y: number; }
export interface GraphNode { data: GraphNodeData; position?: GraphPosition | null; }
export interface GraphEdgeData { id: string; source: string; target: string; edge_type: GraphEdgeType; }
export interface GraphEdge { data: GraphEdgeData; }
export interface GraphDiagnostics {
  bibliography_count: number;
  fallback_source_count: number;
  missing_reference_occurrence_count: number;
  referenced_unknown_evidence_ids: string[];
}
export interface GraphPayload {
  elements: { nodes: GraphNode[]; edges: GraphEdge[]; };
  run_id: string;
  elements_hash: string;
  diagnostics: GraphDiagnostics;
  schema_version: "1.0";
}

export async function getRunGraph(runId: string): Promise<GraphPayload> {
  const res = await fetch(`${BACKEND_URL}/api/runs/${runId}/graph`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`getRunGraph(${runId}) ${res.status}: ${body}`);
  }
  return res.json() as Promise<GraphPayload>;
}
```

### 2. `web/app/runs/[runId]/graph/page.tsx`

```tsx
"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { getRunGraph, type GraphPayload } from "@/lib/api";
import { ClaimGraph } from "./components/claim_graph";

interface Props { params: Promise<{ runId: string }>; }

export default function GraphPage({ params }: Props) {
  const { runId } = use(params);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRunGraph(runId).then(setPayload).catch((e: Error) => setError(e.message));
  }, [runId]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS — F-snowball
            </span>
            <span className="text-foreground text-base font-semibold">
              Claim graph: {runId}
            </span>
          </div>
          <Button variant="outline" nativeButton={false} render={<Link href={`/inspector/${runId}`} />}>
            Back to Inspector
          </Button>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 px-6 py-6">
        {error && <div role="alert" className="rounded border border-destructive p-4 text-destructive">{error}</div>}
        {!payload && !error && <div role="status">Loading graph for run {runId}…</div>}
        {payload && <ClaimGraph payload={payload} />}
      </main>
    </div>
  );
}
```

### 3. `web/app/runs/[runId]/graph/components/claim_graph.tsx`

```tsx
"use client";
import { useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import type { GraphPayload } from "@/lib/api";

// SSR-unsafe; dynamic-import client-only.
const CytoscapeComponent = dynamic(() => import("react-cytoscapejs"), { ssr: false });

interface Props { payload: GraphPayload; }

const STYLESHEET = [
  { selector: "node[type='sentence']", style: { "background-color": "#3b82f6", width: 18, height: 18, label: "data(label)", "font-size": 8 } },
  { selector: "node[type='source']", style: { "background-color": "#22c55e", width: 26, height: 26, label: "data(label)", "font-size": 9 } },
  { selector: "node[type='section']", style: { "background-color": "#a3a3a3", width: 30, height: 30, label: "data(label)", "font-weight": "bold" } },
  { selector: "node[type='frame']", style: { "background-color": "#f59e0b", width: 22, height: 22, label: "data(label)" } },
  { selector: "node.bibliography_missing", style: { "background-color": "#9ca3af", "border-style": "dashed", "border-width": 1 } },
  { selector: "edge[edge_type='cites']", style: { "line-color": "#60a5fa", width: 1, "curve-style": "bezier" } },
  { selector: "edge[edge_type='contradicts']", style: { "line-color": "#ef4444", width: 2, "curve-style": "bezier", "line-style": "solid" } },
  { selector: "edge[edge_type='section_member']", style: { "line-color": "#d4d4d4", "line-style": "dashed", width: 1, opacity: 0.5 } },
];

export function ClaimGraph({ payload }: Props) {
  // react-cytoscapejs accepts the element list flattened (nodes + edges).
  // Use fcose layout when no positions present (v1 server returns position: null).
  // Determine once on mount.
  const hasPositions = payload.elements.nodes.some((n) => n.position != null);
  const elements = [
    ...payload.elements.nodes.map((n) => ({
      data: n.data, position: n.position ?? undefined,
      classes: n.data.classes ?? undefined,
    })),
    ...payload.elements.edges.map((e) => ({ data: e.data })),
  ];
  return (
    <section aria-label="Claim graph" className="border-border h-[600px] w-full overflow-hidden rounded-md border">
      <CytoscapeComponent
        elements={elements as never}
        style={{ width: "100%", height: "100%" }}
        layout={
          hasPositions
            ? { name: "preset" }
            : { name: "fcose", randomize: false, quality: "proof", animate: false } as never
        }
        stylesheet={STYLESHEET as never}
      />
      <p className="text-muted-foreground p-2 text-xs">
        {payload.elements.nodes.length} nodes · {payload.elements.edges.length} edges · hash {payload.elements_hash.slice(0, 12)}…
      </p>
    </section>
  );
}
```

### 4. fcose registration

`cytoscape-fcose` needs `cytoscape.use(fcose)` once at module load. Add to `claim_graph.tsx`:
```ts
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
if (!(cytoscape as never as { _fcoseRegistered?: boolean })._fcoseRegistered) {
  cytoscape.use(fcose);
  (cytoscape as never as { _fcoseRegistered?: boolean })._fcoseRegistered = true;
}
```
(Idempotent guard against double-registration on HMR / dynamic re-mount.)

## Test plan (Playwright deferred to I-snowball-006b; this PR is unit-only)

- `web/tests/e2e/graph_page_smoke.spec.ts` — minimal smoke: navigate to `/runs/<fixture_run_id>/graph`, expect canvas to render (count > 0 nodes after layout). Uses MSW-style mock for `/api/runs/...` OR backend dev server. **DEFERRED to 006b** per DECISION.md decomposition.
- For this PR: TypeScript typecheck + lint must pass; manual `npm run dev` smoke recorded in PR body.

## Direct questions for Codex iter 1

1. react-cytoscapejs@2.0 + React 19.2 + Next 16.2 — known compatible, or do you require the spike test BEFORE shipping? My plan: ship the `<CytoscapeComponent>` path; if it errors on dev-server smoke, switch to direct-mount wrapper in iter 2.
2. SSR strategy — `dynamic(..., { ssr: false })` correct, or do you want `useEffect`-based imperative mount?
3. Stylesheet typing — `as never` cast: acceptable, or write proper `cytoscape.Stylesheet[]` types?
4. fcose registration with HMR guard — idempotent pattern OK, or use a different mechanism?
5. LOC: claim_graph.tsx ~120 LOC, page.tsx ~50 LOC, api.ts additions ~40 LOC. All under 200.
6. Anything else genuinely blocking?

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
