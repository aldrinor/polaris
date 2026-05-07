# Codex Diff Review — I-f4-003 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-003 — Multi-tab independent updates (cancel propagates)
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `6bcd13608637785fa8157d1601cf5facdb7146aabf5a7dcca2bdf5dd10f844cf`
**LOC:** 135 net (65 under CHARTER §1 200-cap)
**Tests:** Lint clean.

## Files

```
web/lib/run_broadcast.ts                  NEW +33
web/app/audit_live/_panels.tsx            EDIT +60/-4
web/tests/e2e/audit_live_multitab.spec.ts NEW +46
```

## What changed

**`run_broadcast.ts`:** `RunBroadcast` class wrapping `BroadcastChannel(`polaris-run-${run_id}`)`. SSR-safe (typeof BroadcastChannel guard). `subscribe()` attaches handler; `broadcastCancel()` posts `{type: "cancel"}`; `close()` cleans up.

**`_panels.tsx`:** Added `?run_id=` query param. When present:
- Instantiates `RunBroadcast` in same `useEffect` as SSEClient; subscribes; ref stored for click handler.
- Renders `data-testid="run-cancel-btn"` button (only if `run_id` present per Codex iter-2 P2).
- `on_cancel_click` closes SSE, broadcasts cancel, sets `cancelled=true`.
- Receiving cancel from another tab: `onCancel` closes SSE + sets cancelled.
- Cancelled state renders `data-testid="run-cancelled"` instead of panels.

**`audit_live_multitab.spec.ts`:** Single Playwright test using ONE BrowserContext + 2 sibling pages (per Codex iter-1 P1). Both navigate to `/audit_live?url=/mock/sse&run_id=test-run-mt`. Waits for cancel button visible in BOTH (Codex iter-2 P2 #1). Click in pageA → assert `run-cancelled` visible in BOTH within 1s/2s.

## Risks for Codex Red-Team

1. **One BrowserContext, two pages.** Per Codex iter-1 P1; verified in test setup.
2. **Cancel-button visibility wait** before click; ensures pageB has subscribed via BroadcastChannel before message fires.
3. **`run_id` empty fallback.** If `?run_id=` absent, no broadcast channel created, no cancel button rendered (existing `/audit_live?url=/mock/sse` from I-f4-002 unaffected). Codex iter-2 P2 #2 resolved.
4. **SSR-safe.** `typeof BroadcastChannel === "undefined"` guard for any non-browser execution.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 135 net.
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
