# Codex Brief Review — I-f14-002a (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f14-002a — prerequisite api.ts memory client. Created from Codex iter-1 directive on I-f14-002 PR #304: "split web/lib/api.ts as a 54-LOC prerequisite PR, then keep page+test together at 197 LOC."
- **Scope:** add memory client functions to `web/lib/api.ts` only. No UI, no test (page + test land in I-f14-002 follow-up PR with 197 LOC budget).
- **Backend:** existing `src/polaris_v6/api/memory.py` mounts the routes; this PR adds the JS client.

## Plan

1. Add `MemoryKind` type alias mirroring backend.
2. Add `MemoryEntry` interface mirroring backend schema.
3. Add `_ws(ws)` helper for `/workspaces/{ws}/memory` URL building.
4. Add `listMemory(ws)`, `rememberMemory(ws, payload)`, `forgetMemory(ws, entry_id)` using the existing `asJsonOrThrow` helper.

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
