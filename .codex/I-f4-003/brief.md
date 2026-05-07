# Codex Brief Review — I-f4-003 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-003 — Multi-tab independent updates (cancel propagates)
**Phase:** 1 / **Feature:** F4
**LOC budget:** 120 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: open same run in 2 tabs; cancel in one cancels both. Playwright parallel-context test.

## Substrate (HONEST at HEAD)

- I-f4-002 ships `/audit_live` route consuming SSE.
- No existing multi-tab coordination. The standard pattern is `BroadcastChannel` (modern browsers, no deps) — same-origin tabs can post/listen to a named channel.

## Approach

**Part 1 — `web/lib/run_broadcast.ts`** (NEW, ~40 LOC):
- `class RunBroadcast` constructor `(run_id: string, opts?: { onCancel?: () => void })`.
- Wraps `BroadcastChannel(`polaris-run-${run_id}`)` (one channel per run id). Channel constructed lazily on first `subscribe()` call (browser-only API; not available SSR).
- `subscribe()` attaches the message handler.
- `broadcastCancel()` posts `{ type: "cancel" }`; subscribers in other tabs receive and call `onCancel`.
- `close()` closes channel.
- All instantiation in `_panels.tsx` happens inside `useEffect` (client-only) with cleanup calling `close()`.

**Part 2 — `web/app/audit_live/_panels.tsx`** (EDIT, ~25 LOC):
- Add `?run_id=` query param. Instantiate `RunBroadcast(run_id, { onCancel: () => set_cancelled(true) })`.
- `state.cancelled = false` initial. When cancel received from another tab OR clicked locally, close SSEClient + set `cancelled=true` + render `<div data-testid="run-cancelled">Run cancelled.</div>`.
- Add `<button data-testid="run-cancel-btn">` that calls `broadcast.broadcastCancel()` + cancels locally.

**Part 3 — `web/tests/e2e/audit_live_multitab.spec.ts`** (NEW, ~55 LOC):
- Playwright test using ONE BrowserContext with two sibling pages (NOT two contexts; BroadcastChannel does not cross context boundaries).
- `const context = await browser.newContext(); const pageA = await context.newPage(); const pageB = await context.newPage();`
- Both pages navigate to `/audit_live?url=/mock/sse&run_id=test-run-1`.
- Click `run-cancel-btn` in pageA; assert `run-cancelled` testid appears in BOTH pages within 1s.

## Acceptance criteria (binding)

1. `web/lib/run_broadcast.ts` NEW.
2. `web/app/audit_live/_panels.tsx` EDIT — wire RunBroadcast + cancel button + cancelled state.
3. `web/tests/e2e/audit_live_multitab.spec.ts` NEW — Playwright two-pages-same-context test (NOT two contexts).

## Planned diff shape

```
web/lib/run_broadcast.ts                        NEW +40
web/app/audit_live/_panels.tsx                  EDIT +25
web/tests/e2e/audit_live_multitab.spec.ts       NEW +55
```

LOC: +120 net. AT breakdown 120 budget. Under CHARTER §1 200-cap by 80.

## Out of scope

- Server-side cancel (run process actually stopped on backend) → I-f4-003a follow-up; this Issue is UI cancel signal only.
- Cross-browser-window-not-same-origin → not supported by BroadcastChannel; out of scope.

## Risks for Codex Red-Team

1. **`BroadcastChannel` browser support.** Chrome/FF/Safari/Edge all support. Polaris targets modern browsers only.
2. **Same-origin requirement.** Both tabs must be at same origin (Playwright default).
3. **Channel name collision.** `polaris-run-${run_id}` namespaced; no risk of cross-run interference.
4. **Suspense boundary** unchanged.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 120 net. Well under.
7. **No new package dep.**

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
