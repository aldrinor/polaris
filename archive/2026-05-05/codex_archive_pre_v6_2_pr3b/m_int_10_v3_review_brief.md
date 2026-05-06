# Codex round 3 — M-INT-10 v3

## Round-2 close
v2 had 1 LOW (workspace_id normalization mismatch).

v3 fix (commit cee30f9):
- GET endpoint now strips workspace_id before substrate call
- Padded GET (`%20%20ws_pad%20%20`) finds padded POST (`'  ws_pad  '`)
- Empty/whitespace still returns 400

1 regression test added (12 total).

## Round summary
- R1: 1 MEDIUM (Drive-only unenforced) + 1 LOW (empty workspace_id)
- R2: 1 LOW (workspace_id normalization mismatch)
- R3: GREEN expected

## Acceptance bar
1. ✅ Imported (substrates)
2. ✅ Invoked (3 endpoints)
3. ✅ Run-log evidence
4. ✅ Rollback flag (404 anon AND auth)
5. ✅ M-15b authn + role gate
6. ✅ Org-scoping (cross-org → 404)
7. ✅ NARROW: Drive-only at TWO layers (extra='forbid' + folder-ID regex)
8. ✅ workspace_id normalization consistent across POST/GET

## Tests
- 12/12 M-INT-10
- 101/101 substrate

Branch: PL-honest-rebuild-phase-1
Commit: cee30f9

## Verdict expected
GREEN — workspace_id normalization fixed.
