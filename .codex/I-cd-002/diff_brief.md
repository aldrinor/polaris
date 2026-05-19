HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is embedded verbatim
below (§D). Review ONLY that diff. The plan it implements was APPROVED by you at
brief iter 2 (`.codex/I-cd-002/brief.md`).

# Codex DIFF review — I-cd-002 / GH#606: scripts/redeploy_v6.sh

## §A — What this is

This diff implements the Codex-APPROVED brief `.codex/I-cd-002/brief.md` (brief
iter 1 REQUEST_CHANGES → iter 2 APPROVE). It adds a six-phase, workstation-driven
redeploy script for the live OVH demo VM, plus a runbook section and the
mandatory §8.3.5 iteration-trajectory log entry.

Canonical diff = 3 files:
- `scripts/redeploy_v6.sh` — NEW, 169 lines. The reviewable code surface.
- `docs/deploy_runbook.md` — +26 lines, a "Redeploying over a running stack"
  section (required by the brief deliverable).
- `state/polaris_restart/iteration_trajectory.md` — +26 lines, the mandatory
  CLAUDE.md §8.3.5 brief-review log (also catches up two pending earlier
  session entries — plan v6, issue breakdown — that were sitting uncommitted).

**LOC note:** the canonical diff totals ~221 added lines, over the 200 soft cap.
The code is a single cohesive 169-line deploy script — not meaningfully
splittable; the overage is entirely the mandatory runbook doc + trajectory log.
Flagging transparently — if you consider this a blocker, say so; otherwise it is
a documented exemption (code surface 169 LOC, well within reviewer-fatigue
limits).

## §B — How the brief's 2 prior P1 + 4 P2 are encoded (verify against the diff)

- **P1-1 (redis snapshot consistency)** — Phase 1 stops `worker api redis` (all
  volume writers) before the `tar`, then `start`s them again. See diff lines for
  the R1 heredoc.
- **P1-2 (state-aware rollback, no forward `down`)** — `rollback()` restores OLD
  compose files in place, retags `:rollback-<utc>` images to `:latest`, and runs
  `up -d --force-recreate` from the OLD compose set. No forward `down`. Armed via
  the `ARMED` flag + `on_exit` EXIT trap, set `ARMED=1` only after Phase 2.
- **P2-1 (ACME email)** — required via `--acme-email` / `$POLARIS_ACME_EMAIL`;
  `die` if absent. No silent default.
- **P2-2/3/4** — `git archive`+`rsync` sync; ~1-2 min recreate downtime;
  in-container `curl` (Dockerfile.v6 installs curl).

## §C — Red-team focus (this is a script that touches the LIVE demo box)

1. Does the script faithfully implement the 6 phases of the APPROVED brief?
2. Rollback correctness: the `ARMED` flag + `on_exit` EXIT trap — does rollback
   fire on (and only on) a post-Phase-2 failure? Is `up -d --force-recreate`
   from the restored OLD files sufficient with no forward `down`?
3. Data-loss paths: is there ANY `down -v`? Are the `rsync --delete` excludes
   (`.env outputs/ logs/ data/ state/`) correct and complete so runtime data is
   never pruned? Volumes are Docker-named — never removed by the forward path?
4. `-p polaris` — is it on EVERY `docker compose` invocation (forward AND
   rollback)? A missing `-p polaris` would switch the volume namespace.
5. SSH heredoc safety: the `rsh "VAR='x' bash -se" <<'TAG'` pattern — quoted
   heredocs (no local expansion), vars passed as remote env. Any quoting,
   escaping, or word-splitting bug? Any value that could break out?
6. `set -euo pipefail` interactions: the `|| true`, `|| echo ...`,
   `[[ ... ]] && ... || ...`, and the Phase-5 `ok` health-poll loop — any place
   where a real failure is masked, or a benign non-zero aborts the script?
7. `.env` reconcile (R3) idempotency: `grep -q` guards + the `sed -i` for
   `POLARIS_GIT_COMMIT` — correct? Safe if a key is absent?
8. `git archive --format=tar polaris` archives the LOCAL `polaris` branch —
   correct intent (post-merge, that is the merged HEAD incl. this issue)?
9. Anything that risks `.env`, the GPG mount, `/etc/polaris`, the
   `polaris_caddy_data` Let's Encrypt cert, or `shared_state`/`redis_data`?

## §D — The complete diff under review

```diff
diff --git a/docs/deploy_runbook.md b/docs/deploy_runbook.md
index 84ac662b..13f97de9 100644
--- a/docs/deploy_runbook.md
+++ b/docs/deploy_runbook.md
@@ -87,6 +87,32 @@ For a clean wipe (drops Redis AOF + sqlite v6_runs.sqlite — DATA LOSS):
 docker compose -f docker-compose.v6.yml down -v
 ```
 
+## Redeploying over a running stack (`scripts/redeploy_v6.sh`)
+
+Steps 1-4 bootstrap a *fresh* host. To push a new `polaris` HEAD to an
+already-running box (the live OVH demo VM), use `scripts/redeploy_v6.sh` — it
+snapshots first, builds while the old stack still serves, and auto-rolls-back
+on any failure. Run it from a workstation with this repo at `polaris` HEAD and
+the box SSH key:
+
+```
+POLARIS_ACME_EMAIL=orchunyin@gmail.com scripts/redeploy_v6.sh ubuntu@51.79.90.35
+```
+
+`POLARIS_ACME_EMAIL` (or `--acme-email <addr>`) is **required** — HEAD's
+`Caddyfile` reads the Let's Encrypt account email from `.env`, and the script
+fails loudly rather than guessing; `orchunyin@gmail.com` above is the example
+contact for this VM.
+
+The script snapshots volumes + images to `/home/ubuntu/polaris-rollback-<utc>/`,
+`git archive`+`rsync --delete`s HEAD onto the box (leaving `.env` and the
+`outputs/ logs/ data/ state/` runtime dirs untouched), reconciles `.env`, then
+builds and `up -d`s from `docker-compose.v6.yml` only — Caddy is native there,
+so the old box-local `docker-compose.caddy.yml` is retired. On any build or
+verify failure it restores the previous compose files + images and
+`up -d --force-recreate`s the old stack — never a forward `down`, never
+`down -v`. See `.codex/I-cd-002/brief.md` for the full vetted plan.
+
 ## Troubleshooting
 
 | Symptom | Likely cause | Fix |
diff --git a/scripts/redeploy_v6.sh b/scripts/redeploy_v6.sh
new file mode 100644
index 00000000..4878ca08
--- /dev/null
+++ b/scripts/redeploy_v6.sh
@@ -0,0 +1,169 @@
+#!/usr/bin/env bash
+# scripts/redeploy_v6.sh — I-cd-002 / GH#606
+# Redeploy current `polaris` HEAD to the live OVH demo VM (polarisresearch.ca).
+# Run from a workstation with this repo at `polaris` HEAD + the box SSH key:
+#   POLARIS_ACME_EMAIL=you@example.com  scripts/redeploy_v6.sh  [ssh_target]
+# ssh_target defaults to ubuntu@51.79.90.35. Full vetted plan + safety model:
+# .codex/I-cd-002/brief.md — snapshot first; build while the old stack serves;
+# state-aware rollback on failure; never `down`/`down -v` on the forward path.
+set -euo pipefail
+
+DEPLOY_DIR=/home/ubuntu/polaris
+DOMAIN=polarisresearch.ca
+UTC="$(date -u +%Y%m%dT%H%M%SZ)"
+BACKUP="/home/ubuntu/polaris-rollback-${UTC}"
+
+log() { echo "[redeploy ${UTC}] $*"; }
+die() { echo "[redeploy] FATAL: $*" >&2; exit 1; }
+
+# --- args -------------------------------------------------------------------
+ACME_EMAIL="${POLARIS_ACME_EMAIL:-}"
+TARGET=""
+while [[ $# -gt 0 ]]; do
+  case "$1" in
+    --acme-email)   ACME_EMAIL="${2:-}"; shift 2 ;;
+    --acme-email=*) ACME_EMAIL="${1#*=}"; shift ;;
+    -*) die "unknown flag: $1" ;;
+    *)  TARGET="$1"; shift ;;
+  esac
+done
+TARGET="${TARGET:-ubuntu@51.79.90.35}"
+[[ -n "$ACME_EMAIL" ]] || die "ACME email required: pass --acme-email <addr> or set \$POLARIS_ACME_EMAIL (runbook example: orchunyin@gmail.com)"
+rsh() { ssh -o ConnectTimeout=20 "$TARGET" "$@"; }
+
+# --- rollback (state-aware; armed only after Phase 2) -----------------------
+ARMED=0
+rollback() {
+  log "ROLLBACK: restoring the previous stack in place"
+  rsh "BACKUP='${BACKUP}' DEPLOY_DIR='${DEPLOY_DIR}' UTC='${UTC}' bash -se" <<'RB' || true
+set -uo pipefail
+cd "$DEPLOY_DIR"
+for f in docker-compose.v6.yml docker-compose.caddy.yml docker-compose.v6.yml.bak Caddyfile; do
+  [[ -e "$BACKUP/$f" ]] && cp -a "$BACKUP/$f" "./$f"
+done
+for s in api worker webui caddy; do
+  docker image inspect "polaris-${s}:rollback-${UTC}" >/dev/null 2>&1 \
+    && docker tag "polaris-${s}:rollback-${UTC}" "polaris-${s}:latest" || true
+done
+docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml up -d --force-recreate
+RB
+  log "ROLLBACK done — volume tarballs kept in ${BACKUP} (manual restore only)"
+}
+on_exit() { local rc=$?; [[ $rc -ne 0 && $ARMED -eq 1 ]] && rollback; exit $rc; }
+trap on_exit EXIT
+
+# --- Phase 0: preflight -----------------------------------------------------
+log "Phase 0: preflight"
+[[ "$(git rev-parse --abbrev-ref HEAD)" == "polaris" ]] || die "not on local 'polaris' branch"
+[[ -z "$(git status --porcelain)" ]] || die "local tree dirty — commit/stash first"
+HEAD_SHA="$(git rev-parse HEAD)"
+rsh 'command -v docker >/dev/null' || die "docker missing on box"
+rsh "test -f ${DEPLOY_DIR}/.env" || die "${DEPLOY_DIR}/.env missing on box"
+FREE_G="$(rsh "df -BG --output=avail / | tail -1 | tr -dc 0-9" || echo 0)"
+[[ "${FREE_G:-0}" -ge 15 ]] || die "box disk free ${FREE_G}G < 15G needed"
+log "preflight OK — HEAD ${HEAD_SHA}, box disk ${FREE_G}G free"
+
+# --- Phase 1: snapshot + backup ---------------------------------------------
+log "Phase 1: snapshot volumes + images -> ${BACKUP}"
+rsh "UTC='${UTC}' BACKUP='${BACKUP}' DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R1'
+set -euo pipefail
+cd "$DEPLOY_DIR"
+mkdir -p "$BACKUP"
+for s in api worker webui caddy; do
+  img="$(docker inspect --format '{{.Config.Image}}' "polaris-${s}-1" 2>/dev/null || true)"
+  [[ -n "$img" ]] && docker tag "$img" "polaris-${s}:rollback-${UTC}" || true
+done
+for f in docker-compose.v6.yml docker-compose.caddy.yml docker-compose.v6.yml.bak Caddyfile .env; do
+  [[ -e "$f" ]] && cp -a "$f" "$BACKUP/" || true
+done
+docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml ps \
+  > "$BACKUP/pre_state.txt" 2>&1 || true
+# Quiesce ALL volume writers before the tar — a live redis keeps rewriting AOF/RDB.
+docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml stop worker api redis
+for v in shared_state redis_data caddy_data; do
+  docker run --rm -v "polaris_${v}:/v:ro" -v "$BACKUP:/b" alpine \
+    tar czf "/b/${v}.tgz" -C /v . || echo "WARN: ${v} snapshot best-effort (caddy may keep /data open)"
+done
+# Restart the old stack so it serves during the long Phase 4 build.
+docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml start worker api redis
+R1
+log "Phase 1 done — volumes snapshotted, old stack serving"
+
+# --- Phase 2: sync HEAD tracked tree (local -> box, in place) ---------------
+log "Phase 2: sync tracked tree to box"
+SHORT="${HEAD_SHA:0:12}"
+ARCHIVE="/tmp/polaris-head-${SHORT}.tgz"
+git archive --format=tar polaris | gzip > "$ARCHIVE"
+scp -q "$ARCHIVE" "${TARGET}:/tmp/"
+rm -f "$ARCHIVE"
+rsh "SHORT='${SHORT}' DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R2'
+set -euo pipefail
+work="/tmp/polaris-head-${SHORT}"
+rm -rf "$work" && mkdir -p "$work"
+tar xzf "/tmp/polaris-head-${SHORT}.tgz" -C "$work"
+# --delete prunes stale tracked files; excludes protect runtime/gitignored dirs.
+rsync -a --delete \
+  --exclude='.env' --exclude='outputs/' --exclude='logs/' --exclude='data/' \
+  --exclude='state/' --exclude='docker-compose.caddy.yml' \
+  --exclude='docker-compose.v6.yml.bak' \
+  "$work/" "$DEPLOY_DIR/"
+rm -rf "$work" "/tmp/polaris-head-${SHORT}.tgz"
+R2
+ARMED=1   # forward changes on the box now exist — failures past here roll back
+log "Phase 2 done — box tracked tree at ${HEAD_SHA}"
+
+# --- Phase 3: reconcile box .env --------------------------------------------
+log "Phase 3: reconcile .env (POLARIS_DOMAIN / POLARIS_ACME_EMAIL / POLARIS_GIT_COMMIT)"
+rsh "DEPLOY_DIR='${DEPLOY_DIR}' DOMAIN='${DOMAIN}' ACME_EMAIL='${ACME_EMAIL}' HEAD_SHA='${HEAD_SHA}' bash -se" <<'R3'
+set -euo pipefail
+cd "$DEPLOY_DIR"
+grep -q '^POLARIS_DOMAIN='     .env || echo "POLARIS_DOMAIN=${DOMAIN}"          >> .env
+grep -q '^POLARIS_ACME_EMAIL=' .env || echo "POLARIS_ACME_EMAIL=${ACME_EMAIL}" >> .env
+if grep -q '^POLARIS_GIT_COMMIT=' .env; then
+  sed -i "s|^POLARIS_GIT_COMMIT=.*|POLARIS_GIT_COMMIT=${HEAD_SHA}|" .env
+else
+  echo "POLARIS_GIT_COMMIT=${HEAD_SHA}" >> .env
+fi
+R3
+log "Phase 3 done"
+
+# --- Phase 4: validate + build + up -----------------------------------------
+log "Phase 4: config validate + build + up  (build ~10-15 min; old stack serves until 'up')"
+rsh "DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R4'
+set -euo pipefail
+cd "$DEPLOY_DIR"
+docker compose -p polaris -f docker-compose.v6.yml config >/dev/null
+docker compose -p polaris -f docker-compose.v6.yml build
+docker compose -p polaris -f docker-compose.v6.yml up -d
+R4
+log "Phase 4 done — new stack recreated"
+
+# --- Phase 5: verify --------------------------------------------------------
+log "Phase 5: verify health + smoke"
+rsh "DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R5'
+set -euo pipefail
+cd "$DEPLOY_DIR"
+ok=0
+for _ in $(seq 1 36); do
+  ok=1
+  for c in polaris-redis-1 polaris-api-1 polaris-worker-1 polaris-webui-1; do
+    h="$(docker inspect --format '{{.State.Health.Status}}' "$c" 2>/dev/null || echo missing)"
+    [[ "$h" == healthy ]] || ok=0
+  done
+  cs="$(docker inspect --format '{{.State.Status}}' polaris-caddy-1 2>/dev/null || echo missing)"
+  [[ "$cs" == running ]] || ok=0
+  [[ $ok -eq 1 ]] && break
+  sleep 5
+done
+[[ $ok -eq 1 ]] || { docker compose -p polaris -f docker-compose.v6.yml ps; exit 1; }
+docker exec polaris-api-1 curl -fsS http://localhost:8000/health >/dev/null
+echo "box OK: redis+api+worker+webui healthy, caddy running, api /health 200"
+R5
+CODE="$(curl -fsS -o /dev/null -w '%{http_code}' "https://${DOMAIN}/" --max-time 25 || echo 000)"
+[[ "$CODE" == "200" ]] || die "external https://${DOMAIN}/ returned ${CODE}"
+log "Phase 5 done — https://${DOMAIN}/ -> 200"
+
+# --- success ----------------------------------------------------------------
+rsh "rm -f ${DEPLOY_DIR}/docker-compose.caddy.yml ${DEPLOY_DIR}/docker-compose.v6.yml.bak" || true
+ARMED=0
+log "REDEPLOY OK — live = ${HEAD_SHA}; rollback artifacts retained in ${BACKUP}"
diff --git a/state/polaris_restart/iteration_trajectory.md b/state/polaris_restart/iteration_trajectory.md
index 9ea6c334..29b77c31 100644
--- a/state/polaris_restart/iteration_trajectory.md
+++ b/state/polaris_restart/iteration_trajectory.md
@@ -518,3 +518,29 @@
 (mandatory CLAUDE.md §8.3.5 iteration-trajectory log: appends the plan-v6,
  issue-breakdown, I-cd-001 and I-cd-002 brief-review entries — process log
  text only, no executable content)
```

## §E — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
