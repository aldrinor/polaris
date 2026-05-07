# Claude architect audit — I-ecg-003

**Issue:** Contract editor UI
**Branch:** bot/I-ecg-003
**Canonical-diff-sha256:** 2d54b7a39a5d9ec5e745f46a7f6a3ef3fd49d76bf715b6b0e3dc087a03a9db82
**Brief verdict:** APPROVE iter 1
**Diff verdict:** APPROVE iter 3 (0/0/0/0; LOC exemption)

## Substrate honesty
- Frontend mirror of `polaris_graph.evidence_contract.schema` (NOT v6 post-run schema).
- Validates 4 backend invariants client-side + min_length/non-empty checks.
- Per-claim jurisdiction multiselect; pruned_claims useMemo prevents stale jurisdictions in serialized output.
- Add/remove rows for entities + claims (length>1 guard).
- Iter cycle: brief APPROVE → diff iter 1 caught CA hard-code + lenient validator → iter 2 fixed validator + Playwright assertion + remove buttons → iter 3 fixed CA in add-claim + pruning + claim_id validation → APPROVE.

## §9.4 N/A (frontend).

## Test integrity
- Lint clean. Playwright spec asserts download fires + filename pattern.

## Out-of-scope follow-ups (named)
- I-ecg-003a: backend max_length / list-cap mirroring + reset saved state on next invalid submit.
- I-ecg-003b: backend `/api/contracts` POST/GET persistence.

## CHARTER §1 LOC cap
- 491 net. Codex granted exemption iter 3.

## Verdict
APPROVE.
