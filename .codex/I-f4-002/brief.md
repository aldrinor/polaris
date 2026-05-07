# Codex Brief Review — I-f4-002 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f4-002 — Event-type UI affordances
**Phase:** 1 / **Feature:** F4 (Live audit run)
**LOC budget:** 200 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict consumed

- P1 (`EVENT_NAMES as const` readonly vs `string[]` mutable): RESOLVED iter 2 — `_panels.tsx` passes `eventNames: [...EVENT_NAMES]` (spreads to mutable array). No SSEClient API change.
- P2 #1 (`useSSEEvents` hook claim mismatch): RESOLVED iter 2 — hook removed from scope; subscription state lives in `_panels.tsx`. Brief no longer mentions `useSSEEvents`.
- P2 #2 (single-body mock doesn't truly test <1s): NOTED iter 2 — synthetic coverage only; production timing measurement is I-f4-002a follow-up. Brief explicit about this.

## Mission

Per breakdown: 6 event types render as dedicated UI panels: query reformulations, retrieval candidates, sources dropped, synthesis decisions, contradiction events, per-sentence verify decisions. Playwright full-run recording 5-10min — every event appears within 1s of server emit.

## Substrate (HONEST at HEAD)

- I-f4-001 ships `SSEClient` library + `/sse` test harness; production wiring is I-f4-001a follow-up.
- This Issue ships UI components consuming SSE events — driven via a new dedicated route at `/audit_live`. Since production wiring is deferred, this Issue scopes to: 6 event-type panels + tests via mock event streams (no `useSSEEvents` hook in this Issue; subscription state lives inline in `_panels.tsx`).

## Approach

**Part 1 — `web/lib/sse_events.ts`** (NEW, ~30 LOC):
- Define 6 event TypeScript interfaces: `QueryReformulation`, `RetrievalCandidate`, `SourceDropped`, `SynthesisDecision`, `ContradictionEvent`, `VerifyDecision`. Minimal fields (timestamp, label, payload).
- `EVENT_NAMES = ["query_reform", "retrieval_candidate", "source_dropped", "synthesis_decision", "contradiction", "verify_decision"] as const`.

**Part 2 — `web/app/(audit_live)/audit_live/page.tsx`** (NEW, ~10 LOC): Server Component shell for the 6-panel live view at `/audit_live`. (Route group keeps name flat.)

Wait — Next route group syntax is `(group_name)`. Will use `web/app/audit_live/page.tsx` for simplicity (URL `/audit_live`).

**Part 3 — `web/app/audit_live/_panels.tsx`** (NEW, ~120 LOC): Client component with 6 stacked panels, each:
- `<section data-testid="panel-{event_name}">` header + scrollable list of last 50 events.
- Each event row: timestamp + label + JSON.stringify(payload, null, 2).
- Subscribes via `SSEClient(?url=)` with `eventNames: [...EVENT_NAMES]` (spread to mutable array; matches SSEClientOpts.eventNames: string[]); `onEvent(name, data)` parses + appends.
- `data-testid="panel-{name}-count"` for assertion.

**Part 4 — `web/tests/e2e/audit_live.spec.ts`** (NEW, ~40 LOC):
- Playwright test stubs `/mock/sse` returning a single text/event-stream body that emits one `event:` of each type in sequence (synthetic 6-event stream); navigates to `/audit_live?url=/mock/sse`; asserts each `panel-{name}-count >= 1` within 1000ms (per "<1s" acceptance).

## Acceptance criteria (binding)

1. `web/lib/sse_events.ts` NEW — types + EVENT_NAMES.
2. `web/app/audit_live/page.tsx` NEW — Server shell.
3. `web/app/audit_live/_panels.tsx` NEW — 6 panels Client component.
4. `web/tests/e2e/audit_live.spec.ts` NEW — Playwright per-event-type assertion.

## Planned diff shape

```
web/lib/sse_events.ts                    NEW +30
web/app/audit_live/page.tsx              NEW +10
web/app/audit_live/_panels.tsx           NEW +120
web/tests/e2e/audit_live.spec.ts         NEW +40
```

LOC: +200 net. AT CHARTER §1 200-cap. Brief author commits to inline minification post-Prettier.

## Out of scope

- Production wiring of `/audit_live` to the live `/api/audit/stream` SSE → I-f4-002a follow-up.
- Real backend SSE event emission for these 6 types → I-f4-002b backend SSE schema.
- Multi-tab broadcast → I-f4-003.
- Adversarial paths → I-f4-004.

## Risks for Codex Red-Team

1. **Mock SSE single-body trick.** `route.fulfill()` with a body containing multiple `event:` lines emits the event stream as one chunk. EventSource parses each event correctly. Brief author commits to verifying the multi-event single-body works in browser EventSource.
2. **`<1s` timing.** Tests use `waitForFunction(..., { timeout: 1000 })` per panel.
3. **Panel state truncation.** Last 50 events only (memory cap).
4. **Suspense for `useSearchParams()` in Client component** — `page.tsx` wraps `_panels` in Suspense (same pattern as I-f4-001).
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 200 net AT cap; trim aggressively.
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
