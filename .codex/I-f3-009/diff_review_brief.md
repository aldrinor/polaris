# Codex Diff Review — I-f3-009 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-009 — F3 adversarial 8-input types
**Brief:** APPROVED iter 1 (0/0/1P2 size-example fix)
**Canonical-diff-sha256:** `11be1a42564661b10b3491836af456a94e5f69e0b94c77cc365d5473b6adf164`
**LOC:** 91 net
**Tests:** 8/8 PASS

## Files

```
tests/polaris_v6/api/test_upload_adversarial.py   NEW +91
```

## What changed

Single pytest module with 8 tests covering the binding 8-input matrix from the breakdown. Hermetic v6 app build via `create_app()` after clearing external-service env vars.

## Risks for Codex Red-Team

1. **Tests current behavior, not aspirational.** Backend doesn't validate PDF magic bytes; tests assert what the route actually returns (queued for malformed/password/image PDFs).
2. **101 MiB byte-array.** ~101MB heap during test #1. Acceptable single-test cost.
3. **§9.4 compliance:** No mocks; real TestClient.
4. **Hermeticity:** env vars cleared before app build. Tests pass regardless of host env.
5. **CHARTER §1 LOC cap:** 91 net.

## Output schema (mandatory)

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
