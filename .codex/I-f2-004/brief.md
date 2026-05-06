# Codex Brief Review — I-f2-004 (ITER 3 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-004 — Frontend: disambiguation modal (2/3/5 candidate variants)
**LOC budget:** 160 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-2 verdict resolution (REQUEST_CHANGES → addressed in this iter 3)

**P1 (Server vs Client constraint + Suspense rule):** ADDRESSED. Harness is split into:
- `web/app/(test_harness)/disambiguation_modal_preview/page.tsx` — **Server Component** that exports `metadata`, calls `notFound()` early when `process.env.NODE_ENV === "production"`, awaits `searchParams` (Next 16 Promise-shaped), and renders `<DisambiguationModalHarnessClient n={n} />`.
- `web/app/(test_harness)/disambiguation_modal_preview/_client.tsx` — Client Component (`"use client";`) that owns local state and the modal. Receives `n` as a plain numeric prop. **Does NOT call `useSearchParams`** → no Suspense wrapping needed.

**P2 #1 (config file is `.ts` not `.mjs`):** ADDRESSED. The Server Component handles 404 via `notFound()` directly. No edits to `web/next.config.*` (TS or otherwise).

**P2 #2 (`redirects()` returns 307/308 not 404):** ADDRESSED. We use `notFound()` from `next/navigation` — emits 404 status from the Server Component without invoking the redirects pipeline.

## Mission

Add `web/app/intake/components/disambiguation_modal.tsx` — the React component that renders the F2 disambiguation UI. Given clusters from `/api/disambiguation` (I-f2-003), the modal shows one card per cluster with label + sample snippets preview, and the user clicks a card to pick a meaning. Add a route-group test harness page (Server Component metadata + Client child) + 3 functional Playwright tests.

## Substrate (HONEST)

- I-f2-003 just merged: `POST /api/disambiguation` returns `{is_ambiguous, num_clusters, clusters: ClusterPayload[]}`.
- `web/app/intake/components/ambiguity_modal.tsx` is the canonical modal pattern.
- Project: Next.js 16.2.4, React 19.2.4, `@base-ui/react`, Tailwind. `web/next.config.ts` is the config file; do NOT touch it.
- `searchParams` in App Router pages is `Promise<{...}>` per Next 16 docs (`web/node_modules/next/dist/docs/01-app/04-api-reference/02-file-conventions/page.md`). Server Component awaits it.

## Acceptance criteria (binding)

1. **`web/app/intake/components/disambiguation_modal.tsx`** (NEW): exports `DisambiguationModal` (PascalCase function — class-naming exception per CLAUDE.md §4.1).
   - `"use client"` directive at top.
   - Local props (no `web/lib/api.ts` edit; deferred to I-f2-005):
     ```ts
     export type DisambiguationCluster = {
       cluster_id: number;
       label: string;
       sample_snippets: string[];
     };
     export type DisambiguationModalProps = {
       open: boolean;
       clusters: DisambiguationCluster[];
       onSelectCluster: (cluster_id: number) => void;
       onCancel: () => void;
     };
     ```
   - Renders DialogPrimitive Root + Portal + Backdrop + Popup (mirrors `ambiguity_modal.tsx:25-49` class strings).
   - Title "Did you mean…" + Description "We found multiple meanings. Pick one to focus the search."
   - `<ul>` of cluster cards. Each is a `<button>` with `data-testid="disambiguation-cluster-${cluster_id}"`, `aria-label={`Pick ${label}`}`, focusable + visible focus ring (`focus-visible:ring-2`). Card body: bold `<span>` label + first 2 sample_snippets joined with " · " (truncated to `MAX_SAMPLE_LEN = 80` chars).
   - Footer: single Cancel button (DialogPrimitive.Close render-prop).
   - Click on card → `onSelectCluster(cluster_id)`.
   - Cancel-idempotency latch: `is_cancelled_ref = useRef(false)`. `handleCancel = () => { if (is_cancelled_ref.current) return; is_cancelled_ref.current = true; onCancel(); }`. Reset to `false` via `useEffect([open], () => { if (open) is_cancelled_ref.current = false; })`.
   - Empty `clusters=[]`: renders Title+Description+Cancel only, no `<ul>`.
   - LOC: ~110.

2. **`web/app/(test_harness)/disambiguation_modal_preview/page.tsx`** (NEW, Server Component):
   - `import { notFound } from "next/navigation";`
   - `export const metadata = { robots: { index: false, follow: false } };`
   - `export default async function Page({ searchParams }: { searchParams: Promise<{ n?: string }> })`:
     - If `process.env.NODE_ENV === "production"` → `notFound()` (returns 404, NOT a redirect).
     - `const { n } = await searchParams;`
     - `const count = n === "5" ? 5 : n === "3" ? 3 : 2;` (defaults to 2)
     - Render `<DisambiguationModalHarnessClient count={count} />`.
   - LOC: ~15.

3. **`web/app/(test_harness)/disambiguation_modal_preview/_client.tsx`** (NEW, Client Component):
   - `"use client";`
   - Imports `<DisambiguationModal>` from `@/app/intake/components/disambiguation_modal`.
   - Constant fixture: `FIXTURE_CLUSTERS = [{cluster_id: 0, label: "syndrome", sample_snippets: ["sample syndrome snippet"]}, {cluster_id: 1, label: "institute", sample_snippets: ["sample institute snippet"]}, {cluster_id: 2, label: "chemical", sample_snippets: ["sample chemical snippet"]}, {cluster_id: 3, label: "company", sample_snippets: ["sample company snippet"]}, {cluster_id: 4, label: "course", sample_snippets: ["sample course snippet"]}]` — 5 entries; component slices `[0, count)`.
   - Local state: `[open, setOpen] = useState(true)`, `[lastPicked, setLastPicked] = useState<number | null>(null)`.
   - `handleSelect = (cid) => { setLastPicked(cid); setOpen(false); }`. `handleCancel = () => setOpen(false);`.
   - Renders the modal + a `<output data-testid="last-picked">{lastPicked === null ? "" : String(lastPicked)}</output>` for Playwright assertions + a `<button data-testid="reopen" onClick={() => { setLastPicked(null); setOpen(true); }}>Reopen</button>` for re-running tests after backdrop dismiss.
   - LOC: ~30.

4. **`web/tests/e2e/disambiguation_modal.spec.ts`** (NEW): 3 functional tests.
   - For each `n in [2, 3, 5]`:
     - `await page.goto(`/disambiguation_modal_preview?n=${n}`)`.
     - `await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();`
     - For `i in [0, n)` assert `disambiguation-cluster-${i}` is visible.
     - Click `disambiguation-cluster-1`; assert `last-picked` text equals `"1"`.
     - Click `reopen`; press Esc; assert `last-picked` text equals `""` (cancel path didn't write).
     - Lightweight overflow sanity: `expect(await page.evaluate(() => document.documentElement.scrollWidth <= 1280)).toBe(true);`
   - LOC: ~50.

## Planned diff shape

```
web/app/intake/components/disambiguation_modal.tsx                    NEW +110
web/app/(test_harness)/disambiguation_modal_preview/page.tsx          NEW +15
web/app/(test_harness)/disambiguation_modal_preview/_client.tsx       NEW +30
web/tests/e2e/disambiguation_modal.spec.ts                            NEW +50
```

LOC: +205 net. **OVER CHARTER §1 200-cap by 5 lines.** Brief author commits to docstring/blank-line trim during implementation to land at ≤ 200 net before Codex diff review.

## Out of scope (deferred per breakdown)

- `runDisambiguation()` API client → I-f2-005.
- Wiring modal into `web/app/intake/page.tsx` flow → I-f2-005.
- BPEI 3-cluster real-LLM smoke → I-f2-005.
- Latency tooltip-to-modal <500ms → I-f2-005.
- Fixing `ambiguity_modal.tsx`'s pre-existing potential double-cancel → follow-up Issue.

## Risks for Codex Red-Team

1. **Server/Client split.** Codex iter-2 P1 fix. Server `page.tsx` exports metadata + handles 404 + awaits searchParams; Client `_client.tsx` owns state. No `"use client"` + `metadata` collision. No `useSearchParams` + Suspense ambiguity.

2. **`notFound()` for 404.** Codex iter-2 P2 #2 fix. `notFound()` from `next/navigation` halts rendering and serves the route's `not-found.tsx` (or default 404). True 404 status, not a 307/308 redirect.

3. **No `next.config.ts` edits.** Codex iter-2 P2 #1 fix. The Server Component handles production gating; no Next config touched.

4. **`_client.tsx` underscore prefix.** This is a co-located file, NOT a route. Next 16 App Router only routes folders containing a `page.tsx`/`route.ts`; sibling files like `_client.tsx` are imported, not routed. Underscore prefix is convention for "private file" + signals "not exported as route." Verified via `web/node_modules/next/dist/docs/01-app/01-getting-started/04-project-structure.md`.

5. **`searchParams` Promise.** Per Next 16 docs, Server Component pages receive `searchParams` as `Promise<{...}>`. We `await` and pass resolved props to the client. Test reads URL via `page.goto(...?n=N)`; the server resolves the param and renders accordingly.

6. **No pixel snapshots.** Tests are functional DOM assertions only. Removes baseline + platform concerns.

7. **Cancel idempotency latch.** Prevents double-invocation of `onCancel` when both DialogPrimitive.Close render-prop button onClick AND Root.onOpenChange(false) fire. Reset on `open` flipping back to true.

8. **Empty clusters defensive render.** Component renders Title+Description+Cancel only when `clusters=[]`. No runtime error.

9. **Tailwind class drift.** Reuses exact class strings from `ambiguity_modal.tsx`.

10. **No new package.json dep.**

11. **CHARTER §1 LOC cap risk.** Currently estimated 205 net (5 over). Brief author commits to landing at ≤200 via:
    - Trimming `disambiguation_modal.tsx` blank lines + comments.
    - Combining adjacent test assertions.
    - Inlining trivial fixtures.

12. **Next 16 route-group convention.** `(test_harness)` parens are stripped from the URL path. Route resolves at `/disambiguation_modal_preview`. Verified via `web/node_modules/next/dist/docs/01-app/03-building-your-application/01-routing/02-route-groups.md`.

13. **Snake_case file naming vs. breakdown.** Breakdown wrote `DisambiguationModal.tsx`; project convention is `disambiguation_modal.tsx`. CLAUDE.md §4.1 binds.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
