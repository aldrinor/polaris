# Codex Diff Review — I-f15-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-001 — audit bundle schema (verification-only)
**Brief:** APPROVED iter 1 (0/0/2P2)
**Canonical-diff-sha256:** `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty post-exclusion)

## Files (audit-excluded from canonical SHA)

```
outputs/audits/I-f15-001/verification.md     NEW
outputs/audits/I-f15-001/claude_audit.md     NEW
.codex/I-f15-001/{brief, verdict, diff, audit}
```

## What changed

Zero source-code changes. Schema substrate already at HEAD (`src/polaris_graph/audit_bundle/bundle_schema.py`); 17/17 tests PASS.

## Risks for Codex Red-Team

1. **Empty canonical diff.** Audit deliverable.
2. **Test names verified live** — `pytest -v` PASS confirmed.
3. **Shape-constraint deferred** to I-f15-001a (named follow-up).
4. **Brief iter-1 P2 #1 (stale test names in verification.md):** acknowledged hygiene; non-blocking per Codex.
5. **Brief iter-1 P2 #2 (empty files list permitted):** non-blocking; shape-constraint deferred.
6. **CHARTER §1 LOC cap.** 0 source-code LOC.

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


## Diff to review

```diff

```
