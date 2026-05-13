HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001c DIFF REVIEW iter 1

Brief APPROVE iter 1 (zero P0/P1). Tiny scope.
Canonical diff SHA256: `e26d0451025cbdf05efd50d773a22c12f22e66d09b327b1b9a9dd04a7cb254b3`.

## Files

```
src/polaris_v6/queue/actors.py                            MOD  +14 / -7  (mapping refinement + doc comment)
tests/polaris_v6/queue/test_template_to_scope_domain.py   NEW  60 LOC (4 tests)

2 files changed, 73 insertions(+), 7 deletions(-)
```

## Brief APPROVE'd criteria → implementation

| Criterion | Implementation |
|---|---|
| Promote ai_sovereignty/canada_us/workforce to identity | `actors.py:34-43` |
| clinical → clinical (unchanged) | `actors.py:38` |
| housing/trade/defense/climate → policy (Phase 2 deferred) | `actors.py:39-42` with doc comment |
| Test: every v6 template_id has a mapping (registry-driven) | `test_every_v6_template_has_a_mapping` |
| Test: every value ∈ SUPPORTED_DOMAINS | `test_every_mapping_value_is_a_supported_scope_domain` |
| Test: promoted templates use identity | `test_promoted_templates_use_identity_mapping` |
| Test: Phase 2 deferred → "policy" | `test_phase2_deferred_templates_fall_back_to_policy` |

## Smoke

`pytest tests/polaris_v6/queue/test_template_to_scope_domain.py`: **4/4 pass in 0.82s**.

## Direct questions

1. Diff matches APPROVED brief?
2. Test pattern (registry-driven, not hardcoded list) catches the regression Codex iter-1 P3 flagged?
3. Any P0/P1?

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
