# Codex Brief Review — I-f14-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f14-002 — Memory page with explicit controls (save+forget UI; pin deferred to follow-up I-f14-002b per CHARTER §1 LOC cap split).
- **API client:** already merged in PR #305 (I-f14-002-api), provides `listMemory`/`rememberMemory`/`forgetMemory` thin fetchers.
- **Backend:** existing `/workspaces/{ws}/memory` FastAPI routes (in-memory store today; Chroma swap is I-f14-001b).
- **Honest framing:** workspace fixed to `ws_demo` (real workspace context lands when auth wires); pin deferred (follow-up I-f14-002b); explicit banner.

## Plan

### `web/app/memory/page.tsx` (NEW, "use client")

1. State: entries (MemoryEntry[]), content/kind for save form. No error/pin state (deferred).
2. `useEffect` initial-load wrapped in `queueMicrotask` per react-hooks/set-state-in-effect lint rule.
3. Save form: kind select + content textarea + Save button (disabled if content < 4).
4. Forget button per row.
5. List sorted by created_at desc.

### Playwright `web/tests/e2e/memory_page_controls.spec.ts` (NEW)

6. Mock `/workspaces/ws_demo/memory{,/<id>}` via stateful `page.route` (Codex prior-iter P2: must be stateful or optimistic UI breaks).
7. One test: visit page → save new entry → assert content rendered → forget the new entry → verify removed.

## Acceptance criteria

1. `/memory` page renders save form + list with forget buttons.
2. Honest banner noting pin deferral to I-f14-002b.
3. Playwright spec verifies save→forget flow with stateful mock.
4. CHARTER §1 LOC cap respected (≤200 net; estimated 200 exactly: page 117, test 83).
5. tsc + eslint + prettier clean.

**Forced enumeration:** before verdict, write one line per criterion 1-5.
**Completeness check:** list files actually read.

## Output schema

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
