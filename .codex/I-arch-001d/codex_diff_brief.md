HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d DIFF REVIEW iter 1

Brief APPROVE iter 4 (zero P0/P1). Canonical diff SHA: `3b38af52187d5bc64f2c6f5343eba3c6a2940caf9017ad6c081cff18ddfaeabe`.

## Files

```
src/polaris_v6/api/artifact_to_slice_chain.py        NEW  364 LOC
src/polaris_v6/api/bundle.py                          MOD  +109 / -3
tests/polaris_v6/api/test_artifact_to_slice_chain.py NEW  271 LOC (22 tests)

3 files changed, 740 insertions(+), 3 deletions(-)
```

## Brief APPROVE'd criteria → implementation

| Criterion | Implementation |
|---|---|
| build_slice_chain(artifact_dir) → 3 Pydantic models | `artifact_to_slice_chain.py:202-329` |
| AuditIR load + raw manifest.json read for fields loader doesn't expose | line 211-213 |
| Sovereignty cascade (drop + recompute) | lines 281-303 |
| Sentences rebuilt via constructor (validators), NOT model_copy | `_redact_sentence` lines 117-125 |
| evaluator_agrees=False when verifier_pass=False | line 124 |
| section_status="dropped" when no passing sentences | line 297 |
| SovereigntyFilterEmptiedReportError → 422 | lines 305-309 + bundle.py:101 |
| SourceTier normalization (T4+/UNKNOWN → T3 + raw_tier) | `_normalize_tier` lines 102-107 |
| DropReason normalization | `_normalize_drop_reason` + `_DROP_REASON_MAP` lines 80-96 |
| Canonical PROVENANCE_TOKEN_RE import (with fallback) | lines 51-60 |
| AuditIR token → string serialization | `_tokens_to_strings` lines 143-144 |
| GET /runs/{run_id}/bundle.tar.gz endpoint | `bundle.py:62-128` |
| Explicit Depends(get_sign_fn) | bundle.py:65-72 (lazy lambda for import order) |
| 404/422/503 status codes | bundle.py:78-118 |

## Smoke

- 22 new tests pass (7 tier params + 10 drop_reason params + 5 integration tests)
- 448 pre-existing tests pass (tests/polaris_v6 + tests/v6), zero regressions

## Direct questions

1. Diff matches APPROVED brief iter-4?
2. Sovereignty cascade implementation (constructor rebuild + section_status recomputation + SovereigntyFilterEmptiedReportError) — APPROVE'd?
3. FastAPI endpoint shape (`Depends(get_sign_fn)` via lazy lambda; HTTPException detail nested dict) — APPROVE'd?
4. Any P0/P1?

## LOC discussion

740 insertions: bridge 364 LOC + tests 271 LOC + endpoint 109 LOC additions. Above brief budget ~370 because bridge logic itself is denser than estimated (8 helper functions for tier/drop_reason/url-domain/slugify/sentence-redaction/evidence-id-extraction/token-serialization). Each helper is small and pure; collectively they make the bridge testable in isolation.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
