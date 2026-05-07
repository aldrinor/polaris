# Claude architect audit — I-ecg-001

**Issue:** Evidence Contract schema
**Branch:** bot/I-ecg-001
**Canonical-diff-sha256:** c221bff21eba8158182b123ff277bb96ff58c181e771e415a7851fbb263a3322
**Brief verdict:** APPROVE iter 2 (0/0/0P1, 2 P2 bookkeeping)
**Diff verdict:** APPROVE iter 1 (0/0/0P1, 1 P2 hardening; accept_remaining; LOC exemption)

## Substrate honesty
- New module `polaris_graph.evidence_contract`. Module docstring distinguishes from `polaris_v6.schemas.evidence_contract` (post-run artifact) — different concepts, same class name OK.
- `_internal_consistency` covers all 4 invariants per Codex iter-2 P1: unique entity names, unique claim_ids, claim entity refs, claim jurisdiction subset.
- Jurisdiction enum is geographic (CA/US/EU/UK/GLOBAL); agency-code mapping (FDA/EMA/NICE/HC/MHRA) owned by I-ecg-002.

## §9.4 compliance
- No mocks. No magic numbers. No `try: pass`. No TODO/FIXME.

## Test integrity
- 11/11 PASS locally on Python 3.13.13.
- Hermetic.

## Out-of-scope follow-ups (named)
- I-ecg-001a: whitespace-only string rejection (Codex diff iter-1 P2 hardening).
- I-ecg-002: gate enforcement + agency-code-to-jurisdiction mapping.

## CHARTER §1 LOC cap
- 246 net. Codex granted exemption iter 1 (accept_remaining; binding cross-validation coverage artifact-inseparable).

## Verdict
APPROVE.
