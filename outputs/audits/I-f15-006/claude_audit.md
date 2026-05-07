# Claude architect audit — I-f15-006

**Issue:** Sovereignty CI: legal-cleared spans only
**Branch:** bot/I-f15-006
**Canonical-diff-sha256:** f086a9c9deb9724b0ae67edde0bb54ac30c07dcfafae22fde8bb21f69509d0fa
**Brief verdict:** APPROVE iter 1 (0/0/0P1, 3 P2)
**Diff verdict:** APPROVE iter 2 (0/0/0/0, accept_remaining)

## Substrate honesty
- Codex iter-1 P1 #1 caught real shipping risk: `evidence_pool.json` serializes full pool, so guard MUST walk all sources, not just cited. Iter-2 fix renamed function and broadened scope.
- Codex iter-1 P1 #2 caught golden-fixture breakage. Iter-2 fix updated 4 Source constructors in test_slice_004_goldens.py.
- Codex iter-1 P2 caught untested HTTP dispatch. Iter-2 added route test asserting 400 + `code: copyrighted_span_in_bundle`.

## Algorithm correctness
- Default-deny: sources without explicit `provenance.legal_cleared = True` → blocked.
- Both `/audit-bundle` and `/audit-bundle/preview` ValueError handlers dispatch correctly: `"copyrighted span"` matches BEFORE `"cited span unreachable"` since both strings differ on first word.

## §9.4 compliance
- No mocks. No magic numbers (LEGAL_CLEARED_KEY constant). No `try: pass`. No TODO/FIXME.

## Sovereignty / external-egress
- Pure additive guard. Zero new external-egress.

## Test integrity
- 103/103 PASS locally on Python 3.13.13.
- Hermetic.
- New route test exercises full HTTP path through TestClient.

## CHARTER §1 LOC cap
- 192 net. Under 200 by 8.

## Out-of-scope follow-ups (named)
- I-f15-006a: UI affordance for marking sources legal_cleared at upload time.
- I-f15-006b: retroactive marking of pools' sources via migration if production runs accumulate.

## Verdict
APPROVE on architect review. Ready to ship.
