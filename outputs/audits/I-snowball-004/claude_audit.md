# Claude architect audit — I-snowball-004 (combined 004a+004b)

**Branch:** `bot/I-snowball-004-graph-interaction-a11y`
**Canonical PR diff SHA256:** `430b0447397923694c9574f93fff86c187c183418dff255e88d5bffaec2e253f`

## Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Hover on graph node → tooltip | ✓ | `claim_graph.tsx` custom canvas-anchored tooltip with label/type/tier/source_url |
| Click on graph node → Inspector | ✓ | `cy.on('tap', 'node', ...)` calls `router.push('/inspector/{runId}?focused_node=<id>')` |
| `<AccessibleGraphList>` parallel `<ol>` | ✓ | New component, deterministic ordering (section/sentence/source-by-tier/frame) |
| Keyboard nav (Tab/Arrow/Enter/Esc/`/`) | ✓ | `onKeyDown` on wrapper section + Tab via focusable `<Button>` per row |
| Search input filters list + canvas | ✓ | Shared `nodeMatchesQuery` from `use_graph_state.ts` |
| `useGraphState` single source of truth | ✓ | Hook returns `[state, adjacency, actions]` consumed by both surfaces |

## Codex iter-1 P1 fixes verified

1. **Idempotent event registration** — `useState(cy)` capture + `useEffect` register/off with cleanup. No stacking on rerender.
2. **Canvas-anchored tooltip** — custom div (not Radix EvidenceTooltip); absolutely positioned at `node.renderedPosition()`.
3. **Arrow-key edge traversal** — real adjacency map computed from semantic edges (excludes section_member); ArrowRight=outgoing, ArrowLeft=incoming.

## P2 fixes applied

- LOC split via `graph_styles.ts` (130 LOC) keeps `claim_graph.tsx` under 200.
- Shared search predicate `nodeMatchesQuery` exported from `use_graph_state.ts`.
- `role="region"` on `<section>` wrapper preserves `<ol>` list semantics.
- `<Button onFocus>` syncs selection on Tab focus.
- `URLSearchParams` for `focused_node` query.

## Smoke

- `npm run typecheck` PASS (0 errors)
- `npm run lint` PASS (only 3 pre-existing warnings unrelated)

## Crown jewel invariants

No backend touched. Pure frontend. No LLM/provenance/strict_verify/sovereignty paths modified. Crown jewels intact.

## Verdict

**SHIP.** Combined 004a + 004b scope landed in one PR. All Codex iter-2 acceptance criteria met.
