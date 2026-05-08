# Codex Brief Review — I-f14-002-api (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f14-002-api — prerequisite api.ts memory client. Created from Codex iter-1 directive on the over-LOC I-f14-002 PR: "split web/lib/api.ts as a 54-LOC prerequisite PR, then keep page+test together at 197 LOC."
- **Branch name note:** branch named `bot/I-f14-002-api` (issue ID + suffix per CI regex `I-[a-z0-9]{2,8}-[0-9]{3}[-<NAME>]`); prior `bot/I-f14-002a-api-client` rejected because `002a` is not three digits.
- **Scope:** add memory client functions to `web/lib/api.ts` only. No UI, no test (page + test land in I-f14-002 follow-up PR with 197 LOC budget).

## Plan

1. Add `MemoryKind` type alias mirroring backend (5 values).
2. Add `MemoryEntry` interface mirroring `src/polaris_v6/memory/schema.py:MemoryEntry` (omits `embedding_vector` — UI-scope).
3. Add `_ws(ws)` helper for `/workspaces/{ws}/memory` URLs.
4. Add `listMemory(ws)`, `rememberMemory(ws, payload)`, `forgetMemory(ws, entry_id)` using existing `asJsonOrThrow` helper. `forgetMemory` treats 404 as success (idempotent).

## Acceptance criteria

1. New types/functions exported from `web/lib/api.ts`.
2. CHARTER §1 LOC cap respected (54 net, well under 200).
3. tsc + eslint + prettier clean.

**Forced enumeration:** before verdict, write one line per criterion 1-3.
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
