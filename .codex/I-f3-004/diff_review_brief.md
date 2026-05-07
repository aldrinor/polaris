# Codex Diff Review — I-f3-004 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-004 — sovereignty CI test
**Brief:** APPROVED iter 2 (iter1 REQ_CH artifacts not at HEAD → iter2 APPROVE 0/0/0)
**Canonical-diff-sha256:** `f1609fb0743b9486e75768ddef4e064de6eac468c180f1eccd9ba8be678e1e8b` (post-rename to .pending_workflow_scope per project convention; bot account lacks GitHub `workflow` OAuth scope)
**LOC:** 64 net
**Tests:** 19/19 PASS

## Files

```
.github/workflows/sovereignty.yml.pending_workflow_scope    NEW +24
tests/polaris_graph/sovereignty/test_red_team.py     NEW +40
```

## What changed

- `sovereignty.yml`: GitHub Actions workflow on `pull_request` + `push: branches: [polaris, main]`. Job runs `PYTHONPATH=src python -m pytest tests/polaris_graph/sovereignty/ -v` with Python 3.11. Fails CI if any sovereignty test fails.
- `test_red_team.py`: 3 tests asserting `assert_safe_for_external` raises `SovereigntyViolationError` with classification-specific message for CLIENT, CAN_REAL, and missing-classification (UNKNOWN default-deny).

## Risks for Codex Red-Team

1. **Workflow triggers.** PR-gated + push-defense.
2. **Red-team test classification-specific assertions.** If anyone weakens EXTERNAL_LEAK_FORBIDDEN to e.g. remove CAN_REAL, `test_red_team_can_real_blocked` fails because no `CAN_REAL` in the (non-raised) error.
3. **`PYTHONPATH=src`** as env var on the workflow step.
4. **`pip install pytest`** is sufficient — sovereignty modules use only stdlib.
5. **No new package.json / requirements.txt dep.**
6. **CHARTER §1 LOC cap.** 64 net.
7. **Test name `test_red_team_*`** distinct from happy-path tests in `test_router.py`.
8. **All 3 red-team tests PASS locally.** Confirms gate is currently working.

## Out of scope

- Frontend drag-drop upload zone → I-f3-005.

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
