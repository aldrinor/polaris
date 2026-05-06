# Plan amendment — skip ROAD B reset, run cleanup on current `polaris` HEAD

**Date:** 2026-05-05 night
**Status:** Pending Codex review/APPROVE before becoming binding.
**Authority:** advisory until Codex APPROVE.

## What this amendment changes

Plan §7.D LOCKED `ROAD B without cherry-pick` originally said:
> `polaris` branch reset to `365f334` (last commit before slice 002 work) gives bit-exact known-good base

This amendment proposes: **skip the branch reset.** Cleanup-PR-1..PR-8 run on top of current `polaris` HEAD `85f0c38` instead of on top of `365f334`.

All other LOCKED §7.D semantics retained:
- ROAD B "without cherry-pick" — meaning we do NOT cherry-pick old slice-2-5 work into a clean rewrite branch.
- Bug-fix Issues I-BUG-079 / I-BUG-082 / I-BUG-084 (per plan §4.9b) STAY in place. The corresponding bug-fix PRs (#79 / #82 / #84) already shipped under the failed `gh pr merge --admin` pattern; their fixes are LIVE in current `polaris`. Under this amendment they remain live; the I-BUG-* Issues become "verify the live fix is correct under proper Codex audit" rather than "re-discover and re-fix from scratch."

## Why the amendment

Encountered cost-of-A this session that was not surfaced in original §7.D LOCKED decision:

1. **Operational cost is much higher than estimated.** Original framing assumed PR-A/A2/A3/B/B2/G2-prep substrate could be re-applied via 5-commit cherry-pick on top of `365f334`. Tested empirically tonight:
   - 9 NEW files (cage substrate) restore cleanly.
   - 3 deprecation-pointer files (`docs/demo_runbook.md`, `docs/demo_e2e_verification_2026_05_04.md`, `docs/mission_status.md`) don't apply at all — the originals don't exist at `365f334`. Drop the deprecation pointers, but they were part of approved PR-B substrate.
   - 7 modified files (`CLAUDE.md`, `.gitignore`, `.github/CODEOWNERS`, `web/AGENTS.md`, `state/restart_instructions.md`, `tests/polaris_graph/golden/test_slice_001_goldens.py`, `.claude/settings.json`) have base versions at `365f334` that differ substantially from the post-65-commits state PR-B was diffed against. Cherry-pick produces multi-file conflicts requiring per-file reauthor.
   - After re-author: PR-B took 8 Codex iterations to APPROVE originally; re-applied subset would need fresh review.
   - Plus: branch protection requires signed commits → I'd need to sign all re-applied commits with operator's SSH key (same delegated-signing pattern as G2, multiplied across all re-applied commits).
   - Realistic cost: 3-5 hours Claude+Codex work + 2-3 user touch-points (relax branch protection temporarily, rerun reconciliation commands).

2. **Reset hits a deadlock during execution.** Tried locally: `git reset --hard 365f334` succeeded, but the missing hook script + missing pin file then blocked all subsequent file-modifying tools. Required multiple user-side `git checkout` reconciliation commands to recover. Not a bug in the cage; the cage worked exactly as designed (deny on missing pin). But the deadlock during reset was unanticipated by §7.D LOCKED.

3. **The "clean base" property is mostly aesthetic.** The cage installed by PR-D (codex-required.yml + branch protection + signed commits required) enforces ALL FUTURE commits regardless of what's already in history. The 65 pre-restart commits live in `polaris` history forever either way (preserved as `pre_restart_2026_05_05` tag on origin even if reset). Force-pushing destroys them on origin but doesn't unmake them as historical events.

4. **Cleanup-PR-1..PR-8 do not depend on git history surgery.** The cleanup PRs are CONTENT moves (archive/, rename, delete pytest tmpdirs). They produce identical post-state regardless of whether the base is `365f334` or `85f0c38`. The only semantic difference: after Cleanup-PR-8, `polaris` history has 70 extra commits in the past (= the 65 pre-restart commits + 5 PR-A/B/B2 substrate commits) under the amendment, vs only 5 commits under strict §7.D.

## What the amendment preserves (semantic invariants)

- CHARTER §1 role assignment LOCKED. Claude writes briefs+diffs; Codex reviews; user reads `git log`. Unchanged.
- CHARTER §3 200-LOC PR cap. Unchanged.
- CHARTER §4 immutable-tests-via-polaris-controls. Unchanged.
- CHARTER §7 visibility (every Issue is GitHub-visible). Unchanged.
- §10.0 Codex isolation invariant (codex-required.yml runs on the runner, not parses Claude verdict file). Unchanged. Will be installed by PR-D as planned.
- §10.5 TaskCreate addBlockedBy chain. Unchanged.
- §10.6 sequence-violation halt. Unchanged.
- §9.6a session-start hook with SHA pin verification. Unchanged. Currently LIVE in `polaris` working tree at `scripts/hooks/session_start_check.py`.
- §7.G G2 signed commit on polaris-controls. ALREADY DONE this session (commit `7995804` SSH-signed by `id_ed25519`, GitHub-verified after key add).
- §7.A LOCKED A2, §7.B LOCKED B1, §7.C LOCKED C2, §7.E ARCHIVE-not-DELETE, §7.F leapfrog, §7.G G2. All unchanged.

## What the amendment changes (concrete)

- `polaris` branch HEAD at the start of Cleanup-PR-1: `85f0c38` (current; PR-A/A2/A3/B/B2/G2-prep substrate already in place) instead of `365f334`.
- Bug-fix PRs #79 / #82 / #84 fixes STAY LIVE in `polaris`. Plan §4.9b reissued I-BUG-079 / I-BUG-082 / I-BUG-084 reframed: scope becomes "Codex audits the live fix from PR #N for correctness against Issue acceptance criteria" rather than "re-fix from scratch on clean branch."
- The 65 pre-restart slice-002 / slice-003 / slice-004 / slice-005 / demo / bug-fix commits remain in `polaris` git log between `365f334` and `85f0c38`. Their CONTENT will be archived or renamed where applicable by Cleanup-PR-1..PR-8 per existing schedule (most slice-2-5 substrate is already in cleanup_audit.md §3 classification rows as ARCHIVE or RENAME targets).

## Audit trail

- `pre_restart_2026_05_05` tag on origin/polaris-controls and origin/polaris pinning current state for forensic recovery if needed (already pushed earlier this session).
- This amendment file lives at `state/polaris_restart/plan_amendment_skip_road_b_reset.md` per plan §9.5 substrate convention. Becomes part of `polaris` history once committed.

## Specific risks to audit

1. **Does skipping the reset weaken the cage's guarantees going forward?** No: PR-D's codex-required.yml + branch protection + signed-commits-required gate every future commit equally. The reset was for "clean base" not "active enforcement."

2. **Do the 65 pre-restart commits introduce silent landmines that Cleanup-PR-1..PR-8 won't catch?** Possible. The cleanup_audit.md §3 classification was authored against the reset-target (`365f334`) inventory in iter 6 when Codex called for `git ls-tree -r 365f334`. Some content may be present in `85f0c38` but not classified. **Mitigation:** Cleanup-PR-1's manifest emit + zero-hit gates will surface any uncovered files. Cleanup-PR-8 (final consistency check) explicitly verifies `git status` returns no surprises.

3. **Does skipping the reset violate §7.D LOCKED?** Technically yes; this amendment is a deviation. That's why this brief is for Codex review.

4. **Could a bug in PR #79 / #82 / #84 fixes be hidden by accepting them as live?** The bugs were real (async/sync collision, etc.). The fixes are in the code. Under the amendment, I-BUG-* Issues become re-audit-not-re-fix work. If Codex audit finds the live fix is wrong, a follow-up PR fixes it. No worse than re-fixing under strict §7.D.

5. **Operator-attested signed commit on polaris-controls was Method A `--allow-empty -S` per G2 staging — does that still hold value if we skip the reset?** Yes. G2 anchors the SHA pins regardless of `polaris` history. The pins point to `polaris-controls/CHARTER.md` and `PLAN.md` content, not to any specific `polaris` commit.

6. **Plan §2 mandatory pre-execution preconditions — do they still all hold?**
   - #1 §10 mechanical gates LIVE: codex-required.yml is PR-D scope, deferred. Branch protection on `polaris` is LIVE (signed commits required, codeowners review required, no force-push, no admin enforcement off — admin can bypass). gh admin:repo scope is REVOKED. **Partial: codex-required.yml workflow not yet deployed.**
   - #2 §9.6a session-start hook deployed: LIVE (verified via `python scripts/hooks/session_start_check.py < /dev/null; echo $?` = 0 with SHA pins matching).
   - #3 §7.G G2 signed commit on polaris-controls: DONE (commit `7995804` SSH-signed, GitHub-verified after key add).
   - #4 `pre_restart_2026_05_05` tag created on `polaris` branch HEAD: DONE this session.
   - #5 `polaris` branch reset to `365f334`: **AMENDMENT PROPOSES SKIPPING.**
   So 3.5 of 5 preconditions hold; #1 has codex-required.yml deferred to PR-D (consistent with sequence: PR-C cleanup → PR-D gates → PR-E Issues → PR-F first Issue execution). #5 is the amendment subject.

7. **Auditor's question: why didn't the original §7.D analysis surface deadlock cost?** Because §7.D was authored before any cage-substrate PRs existed. The deadlock cost is a function of "cage + force-reset" interaction which only emerged after PR-B landed. Plan v2 (now) has more empirical info than v1 (then).

## Recommended Codex action

If the amendment is REJECTED: state the specific risk that outweighs the operational cost of strict §7.D, AND propose a recovery sequence (e.g., "user must restore polaris-controls/<file> + state/polaris_restart/<file> + scripts/hooks/<file> via individual `git checkout` from backup, then Claude proceeds with cherry-pick + conflict resolution + Codex re-review").

If the amendment is APPROVED: I delete the local `backup/pre-reset-2026-05-05` branch (already done after revert), proceed with Cleanup-PR-1 from `polaris` HEAD `85f0c38`. Cleanup-PR-1 substrate authored per cleanup_audit.md iter 21 schedule; submitted to Codex review; then to user merge per CHARTER §1.

## Output schema

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

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. (HISTORICAL boilerplate; the "no hard cap" rule was REVOKED 2026-05-06 — if this advisory doc is reused, replace this line with the canonical CLAUDE.md §8.3.1 cap directive.) Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
