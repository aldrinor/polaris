# I-cd-002-followup — Claude architect audit

**Issue:** GH#606 (I-cd-002 followup) — make `scripts/redeploy_v6.sh` runnable.
**Why:** the first live run of the I-cd-002 redeploy script failed at Phase 0
preflight (`Permission denied (publickey)`) — the box was untouched (`ARMED=0`,
no rollback path entered; 5 containers verified at prior uptime, site 200).
Two defects in the shipped script, both fixed here.

## Changes

- `scripts/redeploy_v6.sh` (+17/-4): add `--ssh-key` / `$POLARIS_SSH_KEY`
  (default `~/.ssh/polaris_orchestrator_key`) + `-i` / `IdentitiesOnly=yes` on
  `rsh()` and the Phase-2 `scp`; the Phase 0 clean-tree `die` becomes a warning
  scoped to modified TRACKED files (`git diff --quiet HEAD`).
- `docs/deploy_runbook.md` (+4/-1): documents `--ssh-key` + the default.

## Risk surface

Touches only Phase 0 (preflight) + the `rsh`/`scp` definitions. The
Codex-APPROVED Phase 1-6 safety logic (snapshot, quiesce, build, state-aware
rollback) is unchanged. `bash -n` clean. Codex brief APPROVE iter 1.

## Verification

`bash -n scripts/redeploy_v6.sh` clean. Post-merge, the redeploy is re-run from
the working repo (the dirty-tree warning now permits that) — that run is the
I-cd-002 GREEN step (`live=HEAD`, 4 healthchecked containers, https smoke).

## Codex P2 disposition

1 P2 — arg parsing does not validate a missing value before `shift 2` (CLI
hygiene, pre-existing — also affects `--acme-email`). Non-blocking; left as-is.
Fixing pre-existing CLI hygiene is out of scope for a runnability followup.
