# Codex Diff Review — I-f3-010 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-010 — F3 sovereignty walkthrough (Codex-reviewed)
**Brief:** APPROVED iter 3 (iter1 REQ_CH artifact-not-at-HEAD → iter2 REQ_CH file:line refs → iter3 APPROVE 0/0/0)
**Canonical-diff-sha256:** `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty post-exclusion)

## Files (all audit-excluded from canonical SHA)

```
outputs/audits/I-f3-010/sovereignty_walkthrough.md   NEW (40 LOC) — durable Codex deliverable
outputs/audits/I-f3-010/claude_audit.md              NEW
.codex/I-f3-010/{brief, codex_brief_verdict, codex_diff, codex_diff_audit, diff_review_brief}.{md,txt,patch}
```

## What changed

**Zero source-code changes.** Walkthrough deliverable only. Cross-references existing sovereignty substrate (I-f3-002, I-f3-003, I-f3-004) by exact file:line.

## Risks for Codex Red-Team

1. **Empty canonical diff.** SHA stamps the empty post-exclusion diff. Deliverable IS the audit doc.
2. **All file:line refs verified at HEAD.** Iter-2 fixes applied: classification.py:25-32, router.py:43+71, upload.py:43+56, test_red_team.py:25/31/37, test_router.py:49.
3. **CI gating qualified as INACTIVE.** Per iter-2 P2 — sovereignty workflow is `.yml.pending_workflow_scope` until user rename.
4. **No new package.json / requirements.txt dep.**
5. **CHARTER §1 LOC cap.** 0 source-code LOC.

## Out of scope

- Real human screen recording (user-driven).
- I-f3-008b classification badge in UI (named follow-up).
- I-f3-008c integration test for caller-side gate invocation (named follow-up).

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


## Diff to review (empty post-exclusion; deliverable in audit-excluded paths)

```diff

```
