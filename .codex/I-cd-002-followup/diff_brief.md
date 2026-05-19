HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-002-followup/codex_diff.patch` (83 lines incl. the
`# canonical-diff-sha256:` trailer). Read ONLY that one file.

# Codex DIFF review — I-cd-002-followup / GH#606: redeploy_v6.sh runnability fix

## §A — What this is

This diff implements the Codex-APPROVED brief `.codex/I-cd-002-followup/brief.md`
(brief APPROVE iter 1, 1 non-blocking P2). The brief embedded this exact diff;
this review confirms the committed `codex_diff.patch` matches.

Canonical diff = 3 files:
- `scripts/redeploy_v6.sh` (+17/-4) — the fix.
- `docs/deploy_runbook.md` (+4/-1) — documents `--ssh-key`.
- `state/polaris_restart/iteration_trajectory.md` (+~10) — the mandatory
  §8.3.5 log (self-referential process metadata).

## §B — The fix (two defects from the first live run)

1. `rsh()` / Phase-2 `scp` invoked `ssh`/`scp` without `-i`, so the box key
   (`~/.ssh/polaris_orchestrator_key`, a non-default name) was never offered →
   `Permission denied (publickey)`. Fix: `--ssh-key` / `$POLARIS_SSH_KEY`
   (default that path) + `[[ -f ]]` validation + `-i "$SSH_KEY" -o
   IdentitiesOnly=yes` on both `ssh` and `scp`.
2. Phase 0's clean-tree `die` required an empty `git status --porcelain`,
   unsatisfiable in the loop working repo. `git archive polaris` deploys the
   committed ref regardless of the working tree → the `die` is now a WARNING
   scoped to modified tracked files (`git diff --quiet HEAD`).

## §C — Red-team focus

1. Does `-i "$SSH_KEY" -o IdentitiesOnly=yes` on both `ssh` and `scp` fully fix
   the publickey failure for a non-default-named key?
2. Is the clean-tree `die`→warning sound — can the working tree affect what
   `git archive polaris` deploys? (It cannot — confirm.)
3. `--ssh-key` arg parsing (with/without `=`); the `[[ -f "$SSH_KEY" ]]` check.
4. Confirm the diff touches ONLY Phase 0 + the `rsh`/`scp` definitions — the
   Codex-APPROVED Phase 1-6 safety logic must be untouched.

## §D — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
