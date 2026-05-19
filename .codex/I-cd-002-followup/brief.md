HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is embedded
verbatim below (§C). Review ONLY that diff.

# Codex brief review — I-cd-002-followup / GH#606: redeploy_v6.sh runnability fix

## §A — Why this followup exists

I-cd-002 merged `scripts/redeploy_v6.sh` (PR #656, Codex brief APPROVE iter 2,
diff APPROVE iter 4). On its **first live run** it failed at Phase 0 preflight:

```
[redeploy ...] Phase 0: preflight
ubuntu@51.79.90.35: Permission denied (publickey).
[redeploy] FATAL: docker missing on box
```

The failure was BEFORE any box mutation (`ARMED=0`, no rollback path entered) —
the live box was verified untouched (5 containers at prior uptime, site 200).
The script's fail-loud-before-mutation design held. But two real defects in the
shipped script kept it from running at all; this followup fixes both.

**Defect 1 — `rsh()`/`scp` omit `-i`.** `rsh() { ssh -o ConnectTimeout=20 ... }`
and the Phase-2 `scp` rely on default SSH key resolution. The box key
(`~/.ssh/polaris_orchestrator_key`) has a non-default name, so ssh never offers
it → `Permission denied (publickey)`. The `rsh 'command -v docker'` check then
mis-reports "docker missing on box".

**Defect 2 — Phase 0 clean-tree guard too strict.** `[[ -z "$(git status
--porcelain)" ]] || die` requires a fully clean tree including no untracked
files. The autonomous-loop working repo always has untracked scratch
(`.codex/...`, pytest temp dirs, some ACL-locked) — `git status --porcelain` is
never empty there, so the script could not run from the working repo at all.
Phase 2 uses `git archive polaris`, which deploys the committed `polaris` ref
regardless of the working tree — untracked files and modified tracked files are
NEVER in the archive — so a dirty tree has zero effect on what is deployed.

## §B — The fix

**Defect 1:** add `--ssh-key <path>` / `$POLARIS_SSH_KEY` (default
`~/.ssh/polaris_orchestrator_key` — the documented project key); validate the
key file exists at parse time (`die` if not); `rsh()` and the Phase-2 `scp`
both pass `-i "$SSH_KEY" -o IdentitiesOnly=yes` so the named key is the ONLY
identity offered.

**Defect 2:** replace the hard `die` with a non-fatal WARNING scoped to
modified TRACKED files (`git diff --quiet HEAD`); the branch-is-`polaris` `die`
is kept. Rationale: `git archive polaris` is deterministic w.r.t. the committed
ref; the guard's only value is a heads-up, and a `die` made the script
unrunnable from a working repo for zero correctness benefit.

`docs/deploy_runbook.md`: one sentence documenting `--ssh-key` + the default.

Verified: `bash -n scripts/redeploy_v6.sh` clean. The fix touches only Phase 0
(preflight) + the `rsh`/`scp` definitions — no change to the Codex-APPROVED
Phase 1-6 safety logic (snapshot, build, rollback).

## §C — The complete diff under review

```diff
diff --git a/docs/deploy_runbook.md b/docs/deploy_runbook.md
index 13f97de9..87051a2b 100644
--- a/docs/deploy_runbook.md
+++ b/docs/deploy_runbook.md
@@ -102,7 +102,9 @@ POLARIS_ACME_EMAIL=orchunyin@gmail.com scripts/redeploy_v6.sh ubuntu@51.79.90.35
 `POLARIS_ACME_EMAIL` (or `--acme-email <addr>`) is **required** — HEAD's
 `Caddyfile` reads the Let's Encrypt account email from `.env`, and the script
 fails loudly rather than guessing; `orchunyin@gmail.com` above is the example
-contact for this VM.
+contact for this VM. The box SSH key defaults to
+`~/.ssh/polaris_orchestrator_key`; pass `--ssh-key <path>` (or `$POLARIS_SSH_KEY`)
+if it lives elsewhere.
 
 The script snapshots volumes + images to `/home/ubuntu/polaris-rollback-<utc>/`,
 `git archive`+`rsync --delete`s HEAD onto the box (leaving `.env` and the
diff --git a/scripts/redeploy_v6.sh b/scripts/redeploy_v6.sh
index b1c618a6..eb599952 100644
--- a/scripts/redeploy_v6.sh
+++ b/scripts/redeploy_v6.sh
@@ -18,18 +18,24 @@ die() { echo "[redeploy] FATAL: $*" >&2; exit 1; }
 
 # --- args -------------------------------------------------------------------
 ACME_EMAIL="${POLARIS_ACME_EMAIL:-}"
+SSH_KEY="${POLARIS_SSH_KEY:-$HOME/.ssh/polaris_orchestrator_key}"
 TARGET=""
 while [[ $# -gt 0 ]]; do
   case "$1" in
     --acme-email)   ACME_EMAIL="${2:-}"; shift 2 ;;
     --acme-email=*) ACME_EMAIL="${1#*=}"; shift ;;
+    --ssh-key)      SSH_KEY="${2:-}"; shift 2 ;;
+    --ssh-key=*)    SSH_KEY="${1#*=}"; shift ;;
     -*) die "unknown flag: $1" ;;
     *)  TARGET="$1"; shift ;;
   esac
 done
 TARGET="${TARGET:-ubuntu@51.79.90.35}"
 [[ -n "$ACME_EMAIL" ]] || die "ACME email required: pass --acme-email <addr> or set \$POLARIS_ACME_EMAIL (runbook example: orchunyin@gmail.com)"
-rsh() { ssh -o ConnectTimeout=20 "$TARGET" "$@"; }
+[[ -f "$SSH_KEY" ]] || die "SSH key not found: $SSH_KEY (pass --ssh-key <path> or set \$POLARIS_SSH_KEY)"
+# -i + IdentitiesOnly: the box key has a non-default name, so it must be named
+# explicitly and be the ONLY identity offered (else ssh fails publickey auth).
+rsh() { ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o ConnectTimeout=20 "$TARGET" "$@"; }
 
 # --- rollback (state-aware; armed only after Phase 2) -----------------------
 ARMED=0
@@ -63,7 +69,12 @@ trap on_exit EXIT
 # --- Phase 0: preflight -----------------------------------------------------
 log "Phase 0: preflight"
 [[ "$(git rev-parse --abbrev-ref HEAD)" == "polaris" ]] || die "not on local 'polaris' branch"
-[[ -z "$(git status --porcelain)" ]] || die "local tree dirty — commit/stash first"
+# Phase 2's `git archive polaris` deploys the committed `polaris` ref — untracked
+# files are never in the archive, and modified tracked files are not either, so a
+# dirty working tree is a heads-up, not a blocker. Warn; do not abort.
+if ! git diff --quiet HEAD; then
+  log "WARNING: $(git diff --name-only HEAD | wc -l | tr -d ' ') modified tracked file(s) are NOT in the deploy — it uses the committed 'polaris' ref"
+fi
 HEAD_SHA="$(git rev-parse HEAD)"
 rsh 'command -v docker >/dev/null' || die "docker missing on box"
 rsh "test -f ${DEPLOY_DIR}/.env" || die "${DEPLOY_DIR}/.env missing on box"
@@ -114,7 +125,7 @@ log "Phase 2: sync tracked tree to box"
 SHORT="${HEAD_SHA:0:12}"
 ARCHIVE="/tmp/polaris-head-${SHORT}.tgz"
 git archive --format=tar polaris | gzip > "$ARCHIVE"
-scp -q "$ARCHIVE" "${TARGET}:/tmp/"
+scp -i "$SSH_KEY" -o IdentitiesOnly=yes -q "$ARCHIVE" "${TARGET}:/tmp/"
 rm -f "$ARCHIVE"
 rsh "SHORT='${SHORT}' DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R2'
 set -euo pipefail
```

## §D — Red-team focus

1. Does `-i "$SSH_KEY" -o IdentitiesOnly=yes` correctly + completely fix the
   publickey failure for a non-default-named key on both `ssh` and `scp`?
2. `SSH_KEY` default `$HOME/.ssh/polaris_orchestrator_key` + `[[ -f ]]` check —
   acceptable, or should it have no default (consistency with `--acme-email`)?
   Note: unlike the ACME email (live TLS account metadata), an SSH key path is
   connection auth — defaulting to the known project key is convenience, and
   the `[[ -f ]]` check still fails loudly if it is wrong/absent.
3. Is downgrading the clean-tree `die` to a `git diff --quiet HEAD` warning
   sound? `git archive polaris` deploys the committed ref — confirm the working
   tree genuinely cannot affect the deployed content.
4. Anything in the arg parsing (`--ssh-key` with/without `=`) that breaks?
5. Any interaction with the untouched Phase 1-6 safety logic?

## §E — Files I have ALSO checked and they are clean

- Phase 1-6 of `redeploy_v6.sh` (snapshot/build/rollback) — unchanged; the
  followup touches only Phase 0 + the `rsh`/`scp` definitions.
- `.codex/I-cd-002/` artifacts — the prior issue's record, untouched.

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
