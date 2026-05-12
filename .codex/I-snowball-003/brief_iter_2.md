HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-003a — brief iter 2 (P1 typecheck fix)

Iter 1 P1: missing TypeScript declarations for cytoscape ecosystem. Resolution applied below. P2/P3 also folded.

## P1-1.1 fix — TypeScript declarations

Install order (additions to `web/package.json` devDependencies):

```bash
npm i -D @types/cytoscape @types/react-cytoscapejs
```

For `cytoscape-fcose` (no public `@types/cytoscape-fcose` on npm), add local ambient declaration:

```ts
// web/types/cytoscape-fcose.d.ts (NEW ~15 LOC)
declare module "cytoscape-fcose" {
  import type { Ext } from "cytoscape";
  const fcose: Ext;
  export default fcose;
}
```

Reference from `web/tsconfig.json` if it doesn't already auto-include `types/**/*.d.ts` (verify in iter 2; most likely already covered by `"include": ["**/*.ts","**/*.tsx"]`).

With declarations in place, drop the `as never` casts and use proper types:

```ts
import type cytoscape from "cytoscape";
const STYLESHEET: cytoscape.Stylesheet[] = [
  { selector: "node[type='sentence']", style: { /*...*/ } as cytoscape.Css.Node },
  // ...
];

const LAYOUT_FCOSE: cytoscape.LayoutOptions = {
  name: "fcose", randomize: false, quality: "proof", animate: false,
} as cytoscape.LayoutOptions;  // fcose options aren't in @types/cytoscape base; cast OK
```

## P2 fixes (folded into spec)

### P2-1.2 `every` over `some` for hasPositions

Mixed-position payload silently falling into preset path is a future-bug. Use `every`:

```ts
const hasPositions =
  payload.elements.nodes.length > 0 &&
  payload.elements.nodes.every((n) => n.position != null);
```

If empty nodes, default to fcose layout (gives empty graph cleanly).

### P2-1.3 Layout-typing leak

`STYLESHEET` and `layout` now properly typed against `@types/cytoscape`. No `as never`.

### P2-1.4 Dev-server smoke before final PR

Acceptance criterion added: before opening PR, run `cd web && npm run typecheck && npm run lint && npm run build`; record output in `outputs/audits/I-snowball-003a/claude_audit.md` under "smoke evidence". If build passes, the PR is shippable; if `<CytoscapeComponent>` fails at runtime, fall back to direct-mount wrapper in iter 3.

## P3 cosmetics (applied)

### P3-1.5 Real spinner for loading state

Use shadcn-style:

```tsx
{!payload && !error && (
  <div role="status" className="flex items-center gap-2 text-muted-foreground">
    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
    Loading graph for run {runId}…
  </div>
)}
```

### P3-1.6 Metadata line not clipped

Change `<section>` from fixed-height to flex-column:

```tsx
<section aria-label="Claim graph" className="border-border flex w-full flex-col overflow-hidden rounded-md border">
  <div className="h-[600px] w-full"><CytoscapeComponent ... /></div>
  <p className="text-muted-foreground border-t border-border p-2 text-xs">{counts}</p>
</section>
```

## Revised file plan (final for iter 2)

```
web/types/cytoscape-fcose.d.ts                                # NEW ~15 LOC (ambient)
web/lib/api.ts                                                # MODIFIED +60 LOC (graph types + getRunGraph)
web/app/runs/[runId]/graph/page.tsx                           # NEW ~70 LOC
web/app/runs/[runId]/graph/components/claim_graph.tsx         # NEW ~140 LOC
web/package.json                                              # MODIFIED (@types/* devDependencies)
```

LOC per file all under 200.

## Direct questions for Codex iter 2

1. TS declaration approach acceptable (install `@types/cytoscape` + `@types/react-cytoscapejs` + local `cytoscape-fcose.d.ts` ambient)?
2. `cytoscape.LayoutOptions` cast for fcose options — better way?
3. Dev-server smoke as acceptance criterion (recorded in claude_audit.md) — sufficient, or do you want an automated test in this PR?
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
