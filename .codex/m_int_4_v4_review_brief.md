# Codex round 4 — M-INT-4 v4

## Round-3 close
v3 was PARTIAL LOW: 0 blockers, 0 mediums, 1 LOW —
malformed confidence shapes preserved verdict='in_scope'.

v4 fix (commit 51cf8a6): track `confidence_malformed` flag.
When set (bool / TypeError / non-finite / out-of-[0,1]),
verdict is coerced to "uncertain" so the parser fails closed.

Legit `confidence=0.0` (low confidence, not malformed) keeps
verdict — explicit regression test pins this.

## Acceptance bar — full re-verify
1. ✅ Imported (substrate + production class)
2. ✅ Invoked (telemetry alongside run_scope_gate)
3. ✅ Run-log evidence
4. ✅ Rollback flag PG_USE_LLM_SCOPE=0 disables (default 0)
5. ✅ Failure does NOT raise (per LAW II)
6. ✅ Adapter contract preserved (M1+M2+M3+M4 closed)
7. ✅ Fail-closed on malformed confidence (round-3 LOW closed)

## Tests
- 21/21 M-INT-4 (6 v1 + 5 v2 + 5 v3 + 5 v4)
- 105/105 across M-INT-0a..4 + M-D5 substrate

Branch: PL-honest-rebuild-phase-1
Commit: 51cf8a6

## Verdict expected
GREEN — round-3 LOW closed, no remaining findings unless new issues found.
