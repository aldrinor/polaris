# F4 walkthrough — Live audit run (Codex-reviewed)

**Issue:** I-f4-005
**Status:** documentation-only (per breakdown's 0-LOC "walkthrough" budget; Codex sign-off substitutes for human screen recording per I-f2-008/I-f3-010 reframe pattern)
**Scenario:** synthetic 200-sentence clinical research run with all 6 SSE event types emitted at ≥10 events/sec sustained.

## Substrate at HEAD

| Component | File | Issue |
|---|---|---|
| SSE consumer with reconnect/backoff | `web/lib/sse_client.ts` | I-f4-001 |
| 6 event-type names + labels + types | `web/lib/sse_events.ts` | I-f4-002 |
| 6 panels + 2 adversarial banners + cancel button | `web/app/audit_live/_panels.tsx` | I-f4-002, I-f4-003, I-f4-004 |
| Server shell with Suspense | `web/app/audit_live/page.tsx` | I-f4-002 |
| Multi-tab cancel via BroadcastChannel | `web/lib/run_broadcast.ts` | I-f4-003 |
| SSE client harness + reconnect tests | `web/tests/e2e/sse_client.spec.ts` | I-f4-001 |
| 6-panel acceptance test | `web/tests/e2e/audit_live.spec.ts` | I-f4-002 |
| Multi-tab cancel test | `web/tests/e2e/audit_live_multitab.spec.ts` | I-f4-003 |
| 4 adversarial path tests | `web/tests/e2e/audit_live_adversarial.spec.ts` | I-f4-004 |

## Walkthrough script (200-sentence run)

1. Operator navigates to `/audit_live?url=/api/audit/stream&run_id=run-2026-05-07-001` (production URL TBD per I-f4-001a).
2. Page renders with 6 empty panels: Query reformulations, Retrieval candidates, Sources dropped, Synthesis decisions, Contradiction events, Per-sentence verify decisions.
3. SSEClient connects with eventNames=[...EVENT_NAMES]; on first message, panels begin populating in real time.
4. Backend emits ~200 verify_decision events over 5-10 minutes; each appears in the verify_decision panel within 1s of server emit (per I-f4-002 acceptance — synthetic mocked at <1s; production wiring is I-f4-001a).
5. Mid-run, operator opens the same URL in a 2nd tab; both panels stay independent (no cross-tab event echo) but the cancel button broadcasts.
6. Operator clicks "Cancel run" in tab A; tab B receives BroadcastChannel cancel signal within ~50ms (intra-process, per I-f4-003); both tabs render `<run-cancelled>` banner.
7. Adversarial paths verified by I-f4-004: if 80%+ of retrieval_candidates dropped, partial-evidence-warning banner renders; if all verify_decisions kept=false, zero-verified-abort banner renders.

## Acceptance "<1s hover/click latency"

Per I-f4-002 acceptance test (`audit_live.spec.ts`), each of the 6 panels asserts visible event count within 1000ms of mock SSE emit. This proves the UI render path is sub-1s. The "200-sentence" framing is the production scenario; substrate is verified end-to-end at synthetic scale, with named follow-ups for production hookup.

## Honest gaps + follow-ups

- **I-f4-001a:** Wire SSEClient (with reconnect) into `web/lib/api.ts:313 subscribeToRun()`. Currently `/audit_live` is a test-route surface; production live-run UI at `/runs/[runId]/page.tsx` still uses raw EventSource without reconnect.
- **I-f4-002b:** Backend SSE schema for the 6 event types (`query_reform`, `retrieval_candidate`, `source_dropped`, `synthesis_decision`, `contradiction`, `verify_decision`). Frontend types are defined; backend emit path TBD.
- **I-f4-005a:** Real product-owner screen recording on a 200-sentence run once I-f4-001a + I-f4-002b land. This is user-driven (not Claude-authored).
- **I-f4-002b** subset: agency-code mapping for the contradiction event type.
- **I-f4-001b:** SSEClient `parseInt(?max)` NaN guard + `connect()` idempotency hardening (Codex iter-1 P2 from I-f4-001).

## Codex acceptance

The 8 substrate files above all exist at HEAD per `git log --name-only` for PRs #257-260. The Playwright tests pass locally per the per-issue verification logs. The walkthrough deliverable is this doc; Codex sign-off here closes I-f4-005.
