# Codex Diff Review — I-f14-002 (page+test, ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f14-002 — Memory page (save+forget UI; pin deferred to I-f14-002b)
**Brief:** APPROVED iter 1 (zero P0/P1)
**Canonical-diff-sha256:** `c2ad55254a519b47c4a56fc5ccc6cd1ae6e7c2c6db585691f7da0f11c0119c4e`
**LOC:** 200 net (at CHARTER §1 200-cap exactly)

## Files

```
web/app/memory/page.tsx                          NEW +117 (save form + list with forget)
web/tests/e2e/memory_page_controls.spec.ts       NEW +83  (save→forget e2e with stateful page.route mock)
```

## What changed

### `web/app/memory/page.tsx`
- "use client" component, fixed workspace `ws_demo` (production workspace context lands when auth wires).
- Banner explicitly notes pin deferred to I-f14-002b.
- `useEffect` initial-load wrapped in `queueMicrotask` per react-hooks/set-state-in-effect lint rule.
- Save form: kind select + content textarea + Save button (disabled if content < 4).
- Forget button per row.
- List sorted by created_at desc.

### `web/tests/e2e/memory_page_controls.spec.ts`
- Stateful `page.route` mock for `/workspaces/ws_demo/memory{,/<id>}` endpoints (Codex prior-iter P2 — must be stateful or optimistic UI breaks).
- One test: visit page → save new entry → assert content rendered → forget the new entry → verify removed.
- Asserts saved content appears in the row (Codex prior-iter P2 coverage — no content/kind blind spot).

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint app/memory/page.tsx tests/e2e/memory_page_controls.spec.ts`: exit 0.
- `npx prettier --check app/memory/page.tsx tests/e2e/memory_page_controls.spec.ts`: exit 0.
- `npx next build`: succeeds; `/memory` static prerender included.
- `npx playwright test memory_page_controls.spec.ts --project chromium`: 1/1 passing in 1.7s.

## Risks for Codex Red-Team

1. **Workspace fixed:** `ws_demo` hard-coded; real workspace context lands when auth wires.
2. **Pin deferral:** explicit follow-up I-f14-002b; banner discloses to user.
3. **Pre-existing api.ts client landed in PR #305:** symbol imports already merged on polaris.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 200 net. AT cap.

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
