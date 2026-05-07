# Codex Diff Review — I-f4-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-002 — Event-type UI affordances
**Brief:** APPROVED iter 3
**Canonical-diff-sha256:** `f83b83188435c8cf862ad39806d050fdf602783196c016825cf8a9a65f2d94ba`
**LOC:** 151 net (49 under CHARTER §1 200-cap)
**Tests:** Lint clean.

## Files

```
web/lib/sse_events.ts            NEW +27
web/app/audit_live/page.tsx      NEW +11
web/app/audit_live/_panels.tsx   NEW +84
web/tests/e2e/audit_live.spec.ts NEW +29
```

## What changed

**`sse_events.ts`:** `EVENT_NAMES = [...] as const`, `SSEEventName = (typeof EVENT_NAMES)[number]`, `EVENT_LABELS` map, `LoggedEvent` interface.

**`page.tsx`:** Server shell + Suspense wrapper.

**`_panels.tsx`:** Client component, uses SSEClient with `eventNames: [...EVENT_NAMES]` (mutable array per Codex iter-2 P1 fix). Renders 6 panels with `data-testid="panel-{name}"` + `panel-{name}-count`. Last 50 events per panel (memory cap).

**`audit_live.spec.ts`:** Single Playwright test stubs `/mock/sse` with text/event-stream containing all 6 named events; navigates to `/audit_live?url=/mock/sse`; asserts each panel-count contains `[1-9]\d* events` within 1000ms (per "<1s" acceptance).

## Risks for Codex Red-Team

1. **Mock SSE single-body trick.** EventSource parses multiple `event: name\ndata: ...\n\n` blocks correctly per WHATWG Server-Sent Events spec.
2. **`MAX_EVENTS = 50` truncation.** Memory cap; current event-pump scope is well under in tests.
3. **Suspense boundary** for `useSearchParams`.
4. **Production wiring** out-of-scope — `/audit_live` is a test-route surface; production live-run UI is I-f4-002a.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 151 net.
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
