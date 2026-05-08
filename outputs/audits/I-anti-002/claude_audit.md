# Claude architect audit — I-anti-002

## Issue scope
Stance-delta computation. Acceptance: unit tests on fixture corpus.

## What landed
- src/polaris_graph/anti_sycophancy/stance_delta.py: classify_stance (5-label keyword classifier) + compute_stance_delta (framing-set validated, pairwise-shift score).
- tests/polaris_graph/anti_sycophancy/test_stance_delta.py: 9 tests including corpus loop over all 20 I-anti-001 entries.

## Architectural alignment
- Plan §4.9 anti-sycophancy. Complements polaris_v6.sycophancy.scorer drift_score (lexical) with semantic-position drift signal.
- Unblocks I-anti-003 (CI gate that enforces stance_delta_score threshold).
- §9.4 hygiene clean. CHARTER §3 LOC: 174 net.

## Iteration history
- Brief 2 iters: P1 framing-set validation + parametrized rejection test.
- Diff APPROVE iter 1.

## Verdict
Ready to merge. 9/9 pass; corpus loop validates against all 20 I-anti-001 entries. Codex brief APPROVE iter 2; Codex diff APPROVE iter 1.
