# Claude Architect Audit — I-f2-004 (DisambiguationModal)

**Branch:** bot/I-f2-004 / **Diff SHA256:** `c25d1f856dc45c9ade30c03eb6d734444b769c51526005f61eaed0380524cb08`
**LOC:** 161 net (under CHARTER §1 200-cap by 39 lines)
**Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/app/intake/components/disambiguation_modal.tsx                    NEW +84
web/app/(test_harness)/disambiguation_modal_preview/page.tsx          NEW +15
web/app/(test_harness)/disambiguation_modal_preview/_client.tsx       NEW +30
web/tests/e2e/disambiguation_modal.spec.ts                            NEW +32
```

## Iter-3 brief P2 advisories — addressed in implementation

- **P2 #1 (harness 404 in production conflicts with `next start` in CI):** Server `page.tsx` does NOT call `notFound()` in production. The harness route remains reachable (so Playwright's `next start` can hit it), with `metadata.robots.index = false` keeping it out of search indexes. The route is unlinked from any nav surface, so it's not user-discoverable in production.
- **P2 #2 (assert exact card count):** Playwright spec uses `await expect(page.locator('[data-testid^="disambiguation-cluster-"]')).toHaveCount(n)` per variant. Catches over-render (e.g. all 5 cards rendered when n=2).
- **P2 #3 (prop name `count={count}`):** `Page` passes `count={count}`; client signature is `({ count }: { count: number })`. Consistent.

## Architecture review

1. **Pattern adherence.** `DisambiguationModal` mirrors `ambiguity_modal.tsx:25-49` Tailwind class strings + DialogPrimitive structure. Future visual refactors touch both files together.

2. **Server/Client split (Codex iter-2 P1 fix).** `page.tsx` is a Server Component exporting `metadata` and awaiting `searchParams: Promise<{n?: string}>` (Next 16 convention). `_client.tsx` carries `"use client"` + state + the modal. Pattern compatible with both `next start` (CI) and `next dev` (local).

3. **Cancel idempotency latch (Codex iter-2 P2 fix).** `is_cancelled_ref = useRef(false)` short-circuits double-invocation when both DialogPrimitive.Close render-prop button onClick AND Root.onOpenChange(false) fire. Reset to `false` via `useEffect` when `open` flips back to true.

4. **Empty-clusters defensive render.** `{clusters.length > 0 && <ul>...}` — Title+Description+Cancel render unconditionally. No runtime error on empty input.

5. **Truncation cap.** `MAX_SAMPLE_LEN = 80` prevents long snippets from breaking layout; constant per CLAUDE.md §4.1 (no magic numbers).

6. **Accessibility.** `<button>` cards are natively focusable; `aria-label="Pick {label}"`; `focus-visible:ring-2` for keyboard users; Esc dismissal via DialogPrimitive default.

7. **Tailwind class drift mitigation.** Class strings copy-pasted from `ambiguity_modal.tsx` for backdrop + popup. Single visual identity for both modals.

8. **No `web/lib/api.ts` import.** Local types; deferred per breakdown to I-f2-005 wiring.

9. **Underscore-prefixed `_client.tsx`.** Co-located file, NOT a route. Next 16 only routes folders containing `page.tsx`/`route.ts`; sibling `_client.tsx` is imported.

10. **No new `package.json` dep.** All primitives + utilities already imported.

## LAW + invariant checks

- **LAW V (file naming):** `disambiguation_modal.tsx` (snake_case file) + `DisambiguationModal` (PascalCase function name — class-naming exception). ✓
- **LAW VI (no hard-coding):** `MAX_SAMPLE_LEN = 80` is a module constant; no inline literals beyond strings. ✓
- **CHARTER §1 (200 LOC cap):** 161. ✓
- **No `unittest.mock` / mocks in `src/`:** UI module + harness fixtures are not in `src/`. Test fixture `FIXTURE_CLUSTERS` is a regular const.
- **§8.4 resource discipline:** No real LLM/network call in tests; harness uses static fixtures.

## Test plan coverage

3 functional Playwright tests (no pixel snapshots) for n=2/3/5:

| Variant | Asserts |
|---|---|
| n=2 | first cluster visible; exactly 2 cluster cards; click cluster_id=1 → last-picked="1"; reopen + Esc → last-picked=""; no horizontal overflow |
| n=3 | same + 3 cards |
| n=5 | same + 5 cards |

## Out of scope (deferred per breakdown)

- `runDisambiguation()` API client → I-f2-005.
- Wiring modal into `web/app/intake/page.tsx` → I-f2-005.
- BPEI 3-cluster real-LLM smoke + latency <500ms requirement → I-f2-005.

## Verdict

APPROVE for Codex diff review.
