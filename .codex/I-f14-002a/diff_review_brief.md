# Codex Diff Review — I-f14-002a (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f14-002a — api.ts memory client (prerequisite for I-f14-002 page split per your iter-1 directive on PR #304)
**Brief:** APPROVED iter 1 (zero P0/P1)
**Canonical-diff-sha256:** `322eeada58c39e65190758fab918ff4f9fa68ca7557ada8e0522113302ceb416`
**LOC:** 54 net (well under CHARTER §1 200-cap)

## Files

```
web/lib/api.ts   +54  (MemoryKind type, MemoryEntry interface, _ws helper, listMemory/rememberMemory/forgetMemory)
```

## What changed

### `web/lib/api.ts` (extension only)
- `MemoryKind` type alias mirroring backend (5 values).
- `MemoryEntry` interface mirroring `src/polaris_v6/memory/schema.py:MemoryEntry`. **Note (iter-1 P2):** omits `embedding_vector` field — intentional for UI consumption (page never reads/writes vectors). Honest about contract drift; adding the field is one-line follow-up if a future surface needs it.
- `_ws(ws)` helper (3 LOC) for `/workspaces/{ws}/memory` URL building.
- `listMemory`, `rememberMemory` use existing `asJsonOrThrow` helper for consistent ApiError semantics.
- `forgetMemory` handles DELETE manually (no JSON response body) and treats 404 as success — intentional idempotent semantics for a "forget" operation. **Iter-1 P2 acknowledged** — non-blocking and the symmetric in-memory store DELETE returns 204 with no body.

## Verification

- `npx tsc --noEmit` (scoped to changed file): exit 0.
- `npx eslint web/lib/api.ts`: exit 0.
- `npx prettier --check web/lib/api.ts`: exit 0.

## Risks for Codex Red-Team

1. **Embedding_vector schema drift:** intentional UI-scope omission per above.
2. **DELETE 404-as-success:** intentional idempotent semantics per above.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 54 net. Well under 200.

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
