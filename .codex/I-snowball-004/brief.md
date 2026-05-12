HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-004 — graph interaction + a11y (hover/click/list/keyboard/search)

Combines original 004a + 004b scope per DECISION.md (CI regex `[0-9]{3}` forces letter-suffix collapse; matches I-snowball-003 precedent).

Builds on I-snowball-003 (merged at sha `a47dcda9`). Branch `bot/I-snowball-004-graph-interaction-a11y`.

## Scope

1. **Hover on graph node** → existing F6 `<EvidenceTooltip>` shows tier + label + source_url
2. **Click on graph node** → opens existing F5 Inspector Sheet at `/inspector/[runId]?focused_node=<id>` (router push, not new component)
3. **`<AccessibleGraphList>`** — `<ol aria-label="Claim graph">` parallel surface mirroring the canvas; one `<li>` per node + "Open Inspector" button; state-synced with canvas via `useGraphState`
4. **Keyboard nav** — `Tab` cycles nodes in deterministic order (section then provenance); `Enter` opens Inspector; `Esc` clears selection; `/` focuses search; arrow keys traverse edges
5. **Search** — `/` focuses input; typing filters `<AccessibleGraphList>` AND highlights matching nodes in canvas via cytoscape `:matches` style toggle
6. **`useGraphState` hook** — single source of truth: `selected_node_id`, `search_query`, `visible_node_ids`

LOC ≤200 per file.

## Files I have ALSO checked and they're clean:

- `web/components/ui/evidence-tooltip.tsx` — existing F6 hover-card; `<EvidenceTooltip>` props: `evidenceId`, `sourceUrl`, `spanText`, `sourceTier ("T1"|"T2"|"T3")`, `publishedDate`. Note tier is only T1-T3 here vs T1-T7 in our graph schema — we'll pass-through T1-T3 and skip T4-T7 in the tooltip (UI gracefully degrades).
- `web/app/inspector/[runId]/page.tsx` — existing F5 Inspector route. Click handler will use Next.js `router.push(\`/inspector/${runId}?focused_node=\${id}\`)`. Inspector page itself may not yet read `focused_node` query param — that's a future enhancement (I-snowball-007), NOT in this PR's scope. v1 just navigates.
- `src/polaris_graph/api/graph_route.py` — `NodeData.id` is kind-prefixed (`sent:`, `src:`, `section:`, `frame:`); cytoscape event payload uses these IDs throughout
- `web/app/runs/[runId]/graph/components/claim_graph.tsx` — existing component from I-snowball-003; extend with `cy.on('tap', ...)`, `cy.on('mouseover', ...)`, `cy.on('mouseout', ...)` handlers via `cy={(cy) => { ... }}` callback prop on `<CytoscapeComponent>`
- `web/lib/api.ts` — `GraphPayload` types already exported (I-snowball-003)

## Proposed file structure

```
web/app/runs/[runId]/graph/components/
  use_graph_state.ts                NEW ~50 LOC  (custom hook)
  accessible_graph_list.tsx         NEW ~120 LOC (a11y parallel `<ol>`)
  claim_graph.tsx                   MODIFIED +60 LOC (cytoscape event handlers, search-highlight)
web/app/runs/[runId]/graph/
  page.tsx                          MODIFIED +30 LOC (mount hook + AccessibleGraphList + search input)
```

Per-file under 200 LOC.

## `useGraphState` hook spec

```ts
export interface GraphState {
  selected_node_id: string | null;
  search_query: string;
  visible_node_ids: Set<string>;     // filtered by search; null query means all visible
}
export interface GraphActions {
  setSelectedNodeId: (id: string | null) => void;
  setSearchQuery: (q: string) => void;
}
export function useGraphState(payload: GraphPayload): [GraphState, GraphActions] {
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    if (!query.trim()) return new Set(payload.elements.nodes.map(n => n.data.id));
    const q = query.toLowerCase();
    return new Set(
      payload.elements.nodes
        .filter(n => n.data.label.toLowerCase().includes(q) || n.data.id.toLowerCase().includes(q))
        .map(n => n.data.id)
    );
  }, [payload, query]);
  return [{ selected_node_id: selected, search_query: query, visible_node_ids: visible }, { setSelectedNodeId: setSelected, setSearchQuery: setQuery }];
}
```

## `<AccessibleGraphList>` spec

- `<ol role="region" aria-label="Claim graph" tabIndex={0}>` — keyboard handler attached here
- One `<li>` per node ordered deterministically: section nodes first, then sentence nodes (grouped by section in section order), then source nodes (sorted by tier T1-T7 then id), then frame nodes
- Each `<li>` has:
  - `<span>` with tier badge (if source) + label + node type icon
  - "Open Inspector" `<Button>` that calls `setSelectedNodeId(n.data.id)` + `router.push`
- Hidden when `visible_node_ids` doesn't include it (filter by search)
- Tab order respects DOM order; current selection has `aria-current="true"`
- Arrow keys handled at `<ol>` level: ArrowDown moves selection to next visible node; ArrowUp prev; Enter opens Inspector; Esc clears

## Cytoscape integration in `claim_graph.tsx`

```ts
const cyRef = useRef<cytoscape.Core | null>(null);
const handleCyInit = useCallback((cy: cytoscape.Core) => {
  cyRef.current = cy;
  cy.on("tap", "node", (evt) => {
    setSelectedNodeId(evt.target.id());
    router.push(`/inspector/${runId}?focused_node=${encodeURIComponent(evt.target.id())}`);
  });
  cy.on("mouseover", "node", (evt) => setHoverNode(evt.target.data()));
  cy.on("mouseout", "node", () => setHoverNode(null));
}, [setSelectedNodeId, router, runId]);

// search highlight
useEffect(() => {
  const cy = cyRef.current; if (!cy) return;
  cy.nodes().removeClass("search-hit");
  if (!searchQuery.trim()) return;
  const q = searchQuery.toLowerCase();
  cy.nodes().filter((n) => n.data("label").toLowerCase().includes(q)).addClass("search-hit");
}, [searchQuery]);
```

Add to stylesheet:
```ts
{ selector: "node.search-hit", style: { "border-width": 3, "border-color": "#facc15" } },
```

The `<EvidenceTooltip>` rendered at the page level reads `hoverNode` from state.

## Direct questions for Codex iter 1

1. `EvidenceTooltip` accepts `sourceTier: "T1"|"T2"|"T3"` but graph nodes carry T1-T7. Two options:
   - (a) Widen `EvidenceTooltip` type to T1-T7 (separate PR)
   - (b) v1: pass tier through only when in T1-T3, else undefined (graceful degrade; no compile error)
   I'd pick (b). Agree?
2. `cy.on('tap', 'node', ...)` plus `router.push` triggers a Next.js client-nav. Is that the right pattern, or should the click be intercepted to prevent multi-tab confusion?
3. Tab order in `<AccessibleGraphList>` — section / sentence / source / frame — is that the canonical deterministic order for a11y, or should it be section-grouped with sources interleaved per-section?
4. Search filter on `label.toLowerCase().includes(q)` — fast enough for 200 sentences × 100 sources? My estimate: O(n) per keystroke, n=~400, <1ms. Acceptable.
5. The `Tab cycles nodes` requirement: in HTML, Tab cycles through focusable elements (the Open-Inspector buttons inside each `<li>`). That's a freebie if the `<li>` contains a `<button>`. Acceptable, or do you want explicit `tabIndex` on each `<li>`?
6. LOC estimate per file: use_graph_state ~50, accessible_graph_list ~120, claim_graph add +60, page add +30. All under 200.
7. Anything else genuinely blocking?

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
