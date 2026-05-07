# Codex Diff Review — I-f4-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f4-001 — SSE EventSource consumer with reconnect/backoff
**Brief:** APPROVED iter 4 (0/0/0/2P2)
**Canonical-diff-sha256:** `3a970643e294d4298cd3c0ff8eaaa52716428d7eaed2d7004cd0ecfddc95eb82`
**LOC:** 190 net (10 under CHARTER §1 200-cap)
**Tests:** Lint clean.

## Files

```
web/lib/sse_client.ts            NEW +88
web/app/sse/page.tsx             NEW +11
web/app/sse/_harness.tsx         NEW +53
web/tests/e2e/sse_client.spec.ts NEW +38
```

## What changed

**`sse_client.ts`:** `SSEClient` class + `SSEClientOpts` interface. `connect()` opens EventSource, registers `onmessage` + each name in `eventNames` via `addEventListener`. `_received_message` reset per connect. On open-without-message after maxRetries: terminal error + close. Backoff: `min(initial * 2^attempts, cap)`.

**`page.tsx`:** Server Component shell wrapping `SSEHarness` in `Suspense` (per Codex iter-4 P2 around `useSearchParams`).

**`_harness.tsx`:** Client Component reads `?url=` and `?max=` from useSearchParams, instantiates SSEClient with low backoff (initial=100ms, cap=500ms) for fast tests, exposes `window.__sse__ = { attempts, total_connects, messages, errors }`.

**`sse_client.spec.ts`:** 2 tests:
- Test 1: `page.route("**/mock/sse")` returns text/event-stream; `hits===1` returns short body that closes; subsequent hits return stable. Asserts `total_connects >= 2` within 2000ms.
- Test 2: `page.route("**/mock/sse-fail")` always returns 500. With `?max=3`, asserts `errors[*].terminal === true` within 5000ms.

## Risks for Codex Red-Team

1. **Production wiring out-of-scope.** Mission restated iter 4: I-f4-001 ships library + harness + tests; production migration is I-f4-001a follow-up. Existing `subscribeToRun()` at `web/lib/api.ts:313` unchanged.
2. **Suspense wrapper.** `useSearchParams()` in Client component requires Suspense boundary in Next App Router; `page.tsx` provides.
3. **Per-connection `_received_message` reset.** First line of `connect()` is `this._received_message = false;` — fresh state each connection (per Codex iter-3 P2).
4. **`total_connects` counter** is independent of `_attempts` — never reset; tracks every EventSource creation.
5. **Mock SSE via `route.fulfill`** sufficient for force-disconnect assertion; doesn't need long-lived stream.
6. **§9.4 N/A frontend.**
7. **CHARTER §1 LOC cap.** 190 net.
8. **No new package dep.**

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
