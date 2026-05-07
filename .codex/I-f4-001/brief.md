# Codex Brief Review — I-f4-001 (ITER 4 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f4-001 — SSE EventSource consumer with reconnect/backoff
**Phase:** 1 / **Feature:** F4 (Live audit run)
**LOC budget:** 150 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-3 verdict consumed

- P1 (existing production caller `subscribeToRun()` not wired): MISSION RESTATED iter 4 — this Issue's mission is restated to: ship the SSEClient library + harness + Playwright tests. Production wiring of `web/lib/api.ts:313 subscribeToRun` is EXPLICITLY OUT-OF-SCOPE and tracked as I-f4-001a follow-up. The breakdown's "reconnect within 2s" acceptance is verified via the harness; production migration of the existing F4 surface to use SSEClient is a separate, sequential Issue.
- P1 (`(test_harness)/sse` paths still appearing): RESOLVED iter 4 — all paths in Parts 2-4 + Planned diff updated to `web/app/sse/...` (URL `/sse`). Search-and-replace across brief.
- P2 (stale `attempts >= 2` wording): RESOLVED iter 4 — Part 4 Test 1 explicitly uses `window.__sse__.total_connects >= 2`.
- P2 (per-connection `_received_message` reset): RESOLVED iter 4 — `_received_message` is reset to false at the start of each `connect()` call (before the new EventSource is created).

## Iter-2 verdict consumed

- P1 (`(test_harness)/sse` not routable in Next App Router): RESOLVED iter 3 — moved to route group `web/app/sse/page.tsx` (URL: `/sse`). Route groups don't appear in URL path; harness IS reachable.
- P2 #1 (attempts counter resets after first message): RESOLVED iter 3 — harness exposes BOTH `attempts` (current run) AND `total_connects` (cumulative connect events) on `window.__sse__`. Test asserts `total_connects >= 2`.
- P2 #2 (Part 3 missing maxRetries parsing): RESOLVED iter 3 — harness reads `?url=` AND `?max=` (default 10).
- P2 #3 (page.route can't model long-lived SSE): RESOLVED iter 3 — first test asserts `total_connects >= 2` after force-disconnect; doesn't require persistent stream. Second test: route always 500; assert `terminal_error` flag.

## Iter-1 verdict consumed

- P1 #1 (named events): RESOLVED iter 2 — `SSEClient` constructor now accepts `eventNames?: string[]` opt; for each name calls `_es.addEventListener(name, handler)` in addition to default `onmessage`. `onEvent(name: string, handler)` API exposed.
- P1 #2 (production wiring not done): SCOPED iter 2 — this Issue ships TESTED LIBRARY ONLY. Wiring into `subscribeToRun()` is named follow-up I-f4-001a (separate Issue). Brief explicitly states "no production callers yet."
- P1 #3 (Playwright harness): RESOLVED iter 2 — adds `web/app/sse/page.tsx` Server Component shell + `web/app/sse/_harness.tsx` Client harness that mounts SSEClient pointing at a configurable URL (`?url=` query param). Harness exposes `window.__sse__ = { attempts, messages, onError }` for Playwright assertion. Playwright test (a) starts a controlled mock SSE server via `page.route()` returning text/event-stream, (b) navigates to `/sse?url=/mock/sse`, (c) drops the connection mid-stream, (d) asserts `window.__sse__.attempts >= 2 within 2s`.
- P2 #1 (attempts reset on every open defeats maxRetries): RESOLVED iter 2 — `_attempts` reset to 0 only after first successful onmessage event (not just open). Tracks consecutive-open-without-message as failure.
- P2 #2 (2000ms cap doesn't strictly guarantee <2s reconnect): NOTED iter 2 — cap lowered to 1000ms (initial 200ms, max 1000ms). Acceptance test asserts reconnect within 2000ms wall-clock which gives safety margin for timer + connect overhead.

## Mission

Per breakdown: `web/lib/sse_client.ts` — reconnect on drop with exponential backoff. Playwright force-disconnect → reconnects within 2s.

## Substrate (HONEST at HEAD)

- No existing `web/lib/sse_client.ts`.
- Browser native `EventSource` does NOT have configurable reconnect-backoff; it auto-reconnects with a 3s default. Custom wrapper needed for exponential backoff + max-retries + circuit-break.
- F4 (live audit run) needs to surface generation progress as SSE events. This Issue ships the CLIENT consumer; backend SSE route is out-of-scope (named follow-up).

## Approach

**Part 1 — `web/lib/sse_client.ts`** (NEW, ~80 LOC):
- `class SSEClient` with constructor `(url: string, opts?: { initialBackoffMs?: number; maxBackoffMs?: number; maxRetries?: number; eventNames?: string[]; onMessage?, onEvent?, onOpen?, onError?, onReconnect? })`.
- Defaults: initialBackoff=200ms, maxBackoff=1000ms, maxRetries=10.
- Internal state: `_es: EventSource | null`, `_attempts: number`, `_closed: boolean`, `_reconnect_timer: number | null`, `_received_message: boolean`.
- `connect()` opens EventSource; subscribes default `onmessage` + each name in `eventNames` via `addEventListener`. Sets `_received_message=true` on first event; resets `_attempts=0` only when `_received_message`. On `onerror` schedules reconnect with backoff `min(initialBackoff * 2^attempts, maxBackoff)`. After `maxRetries` consecutive open-without-message failures, calls `onError` with terminal flag and stops.
- `close()` sets `_closed=true`, clears timer, closes EventSource.
- `getAttempts() / getReadyState()` for tests.

**Part 2 — `web/app/sse/page.tsx`** (NEW, ~10 LOC): Server Component shell loading `_harness`. NOT linked from main nav; test-only.

**Part 3 — `web/app/sse/_harness.tsx`** (NEW, ~30 LOC): Client component reading `?url=` query param, instantiating SSEClient, exposing `window.__sse__ = { attempts, messages, errors }` for Playwright assertion.

**Part 4 — `web/tests/e2e/sse_client.spec.ts`** (NEW, ~40 LOC):
- Test 1 (`reconnects within 2s`): `page.route("**/mock/sse", ...)` returns text/event-stream that closes after one event on first attempt; on second attempt returns a stable stream. Navigate to `/sse?url=/mock/sse`, assert `window.__sse__.total_connects >= 2` within 2000ms.
- Test 2 (`stops after maxRetries`): route always returns 500; assert `window.__sse__.errors[0].terminal === true` after maxRetries attempts (with maxRetries lowered to 3 in URL `?max=3` for fast test).

## Acceptance criteria (binding)

1. `web/lib/sse_client.ts` NEW with class + opts + reconnect/backoff.
2. `web/tests/e2e/sse_client.spec.ts` NEW with 2 Playwright tests.

## Planned diff shape

```
web/lib/sse_client.ts                    NEW +80
web/app/sse/page.tsx               NEW +10
web/app/sse/_harness.tsx           NEW +30
web/tests/e2e/sse_client.spec.ts         NEW +40
```

LOC: +160 net. Over breakdown 150 budget by 10; under CHARTER §1 200-cap by 40.

## Out of scope

- Backend SSE route (`/api/audit/stream`) → I-f4-001a.
- React hook `useSSE()` wrapper → I-f4-002 (event-type UI affordances).
- Multi-tab broadcast/coordination → I-f4-003.

## Risks for Codex Red-Team

1. **Browser EventSource has built-in reconnect.** This wrapper REPLACES that by setting `withCredentials: false` (default) and explicitly closing+reopening on error. Brief author commits to verifying that closing the underlying EventSource cancels the browser's built-in retry, then opens a fresh one with our backoff timer.
2. **Playwright fake SSE.** Use `page.route()` with `route.fulfill()` returning `Content-Type: text/event-stream` and a body that closes after one event. Some Playwright versions need `route.continue()` for SSE — brief author commits to verifying this works. Fallback: stub a tiny test server in the test setup.
3. **Backoff calculation.** Cap at `maxBackoffMs`; first reconnect attempt is `initialBackoffMs` (not 0). 2000ms cap meets "<2s" acceptance.
4. **`onMessage(data: string)` signature** — JSON parsing is caller's responsibility.
5. **No new package dep.**
6. **§9.4 N/A frontend.**
7. **CHARTER §1 LOC cap.** 160 net. Under 200.

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
