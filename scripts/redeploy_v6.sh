#!/usr/bin/env bash
# scripts/redeploy_v6.sh — I-cd-002 / GH#606
# Redeploy current `polaris` HEAD to the live OVH demo VM (polarisresearch.ca).
# Run from a workstation with this repo at `polaris` HEAD + the box SSH key:
#   POLARIS_ACME_EMAIL=you@example.com  scripts/redeploy_v6.sh  [ssh_target]
# ssh_target defaults to ubuntu@51.79.90.35. Full vetted plan + safety model:
# .codex/I-cd-002/brief.md — snapshot first; build while the old stack serves;
# state-aware rollback on failure; never `down`/`down -v` on the forward path.
set -euo pipefail

DEPLOY_DIR=/home/ubuntu/polaris
DOMAIN=polarisresearch.ca
UTC="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/home/ubuntu/polaris-rollback-${UTC}"

log() { echo "[redeploy ${UTC}] $*"; }
die() { echo "[redeploy] FATAL: $*" >&2; exit 1; }

# --- args -------------------------------------------------------------------
ACME_EMAIL="${POLARIS_ACME_EMAIL:-}"
TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --acme-email)   ACME_EMAIL="${2:-}"; shift 2 ;;
    --acme-email=*) ACME_EMAIL="${1#*=}"; shift ;;
    -*) die "unknown flag: $1" ;;
    *)  TARGET="$1"; shift ;;
  esac
done
TARGET="${TARGET:-ubuntu@51.79.90.35}"
[[ -n "$ACME_EMAIL" ]] || die "ACME email required: pass --acme-email <addr> or set \$POLARIS_ACME_EMAIL (runbook example: orchunyin@gmail.com)"
rsh() { ssh -o ConnectTimeout=20 "$TARGET" "$@"; }

# --- rollback (state-aware; armed only after Phase 2) -----------------------
ARMED=0
rollback() {
  log "ROLLBACK: restoring the previous stack in place"
  rsh "BACKUP='${BACKUP}' DEPLOY_DIR='${DEPLOY_DIR}' UTC='${UTC}' bash -se" <<'RB' || true
# fail-fast internally: a failed restore step must abort before `up`, not be
# masked. The outer `|| true` still treats the whole rollback as best-effort.
set -euo pipefail
cd "$DEPLOY_DIR"
# Restore the OLD compose files, Caddyfile, AND .env — Phase 3 mutated .env, so
# leaving it would keep stale POLARIS_GIT_COMMIT / domain / ACME values.
for f in docker-compose.v6.yml docker-compose.caddy.yml docker-compose.v6.yml.bak Caddyfile .env; do
  [[ -e "$BACKUP/$f" ]] && cp -a "$BACKUP/$f" "./$f"
done
for s in api worker webui caddy; do
  docker image inspect "polaris-${s}:rollback-${UTC}" >/dev/null 2>&1 \
    && docker tag "polaris-${s}:rollback-${UTC}" "polaris-${s}:latest" || true
done
# Only -f compose files that the restore actually produced (the box's old
# stack may or may not have carried docker-compose.caddy.yml).
cf="-f docker-compose.v6.yml"
[[ -e docker-compose.caddy.yml ]] && cf="$cf -f docker-compose.caddy.yml"
docker compose -p polaris $cf up -d --force-recreate
RB
  log "ROLLBACK done — volume tarballs kept in ${BACKUP} (manual restore only)"
}
on_exit() { local rc=$?; [[ $rc -ne 0 && $ARMED -eq 1 ]] && rollback; exit $rc; }
trap on_exit EXIT

# --- Phase 0: preflight -----------------------------------------------------
log "Phase 0: preflight"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "polaris" ]] || die "not on local 'polaris' branch"
[[ -z "$(git status --porcelain)" ]] || die "local tree dirty — commit/stash first"
HEAD_SHA="$(git rev-parse HEAD)"
rsh 'command -v docker >/dev/null' || die "docker missing on box"
rsh "test -f ${DEPLOY_DIR}/.env" || die "${DEPLOY_DIR}/.env missing on box"
FREE_G="$(rsh "df -BG --output=avail / | tail -1 | tr -dc 0-9" || echo 0)"
[[ "${FREE_G:-0}" -ge 15 ]] || die "box disk free ${FREE_G}G < 15G needed"
log "preflight OK — HEAD ${HEAD_SHA}, box disk ${FREE_G}G free"

# --- Phase 1: snapshot + backup ---------------------------------------------
log "Phase 1: snapshot volumes + images -> ${BACKUP}"
rsh "UTC='${UTC}' BACKUP='${BACKUP}' DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R1'
set -euo pipefail
cd "$DEPLOY_DIR"
mkdir -p "$BACKUP"
# Compose file set — docker-compose.caddy.yml is optional (it is removed after a
# successful native-Caddy redeploy), so the script stays repeatable.
CF="-f docker-compose.v6.yml"
[[ -e docker-compose.caddy.yml ]] && CF="$CF -f docker-compose.caddy.yml"
# Arm the restart trap BEFORE the stop — if `stop` itself fails or is interrupted
# mid-way the trap still restarts the stack. `start` on already-running services
# (a pre-stop failure) is a harmless no-op. The outer rollback is not armed
# during Phase 1, so this trap is the box's only safety here.
trap 'docker compose -p polaris $CF start worker api redis || true' EXIT
for s in api worker webui caddy; do
  img="$(docker inspect --format '{{.Config.Image}}' "polaris-${s}-1" 2>/dev/null || true)"
  [[ -n "$img" ]] && docker tag "$img" "polaris-${s}:rollback-${UTC}" || true
done
for f in docker-compose.v6.yml docker-compose.caddy.yml docker-compose.v6.yml.bak Caddyfile .env; do
  [[ -e "$f" ]] && cp -a "$f" "$BACKUP/" || true
done
docker compose -p polaris $CF ps > "$BACKUP/pre_state.txt" 2>&1 || true
# Quiesce ALL volume writers before the tar — a live redis keeps rewriting AOF/RDB.
docker compose -p polaris $CF stop worker api redis
# shared_state + redis_data are the rollback DATA artifacts — their snapshot
# MUST succeed; only caddy_data is best-effort (caddy keeps /data open).
for v in shared_state redis_data; do
  docker run --rm -v "polaris_${v}:/v:ro" -v "$BACKUP:/b" alpine tar czf "/b/${v}.tgz" -C /v .
done
docker run --rm -v "polaris_caddy_data:/v:ro" -v "$BACKUP:/b" alpine \
  tar czf "/b/caddy_data.tgz" -C /v . || echo "WARN: caddy_data snapshot best-effort"
# Restart the old stack so it serves during the long Phase 4 build.
docker compose -p polaris $CF start worker api redis
trap - EXIT
R1
log "Phase 1 done — volumes snapshotted, old stack serving"

# --- Phase 2: sync HEAD tracked tree (local -> box, in place) ---------------
log "Phase 2: sync tracked tree to box"
SHORT="${HEAD_SHA:0:12}"
ARCHIVE="/tmp/polaris-head-${SHORT}.tgz"
git archive --format=tar polaris | gzip > "$ARCHIVE"
scp -q "$ARCHIVE" "${TARGET}:/tmp/"
rm -f "$ARCHIVE"
rsh "SHORT='${SHORT}' DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R2'
set -euo pipefail
work="/tmp/polaris-head-${SHORT}"
rm -rf "$work" && mkdir -p "$work"
tar xzf "/tmp/polaris-head-${SHORT}.tgz" -C "$work"
# --delete prunes stale tracked files; excludes protect runtime/gitignored dirs.
rsync -a --delete \
  --exclude='.env' --exclude='outputs/' --exclude='logs/' --exclude='data/' \
  --exclude='state/' --exclude='docker-compose.caddy.yml' \
  --exclude='docker-compose.v6.yml.bak' \
  "$work/" "$DEPLOY_DIR/"
rm -rf "$work" "/tmp/polaris-head-${SHORT}.tgz"
R2
ARMED=1   # forward changes on the box now exist — failures past here roll back
log "Phase 2 done — box tracked tree at ${HEAD_SHA}"

# --- Phase 3: reconcile box .env --------------------------------------------
log "Phase 3: reconcile .env (POLARIS_DOMAIN / POLARIS_ACME_EMAIL / POLARIS_GIT_COMMIT)"
# ACME_EMAIL is operator-supplied — base64 it so a value containing shell-special
# characters cannot break or inject into the remote command. DOMAIN/HEAD_SHA are
# repo constants / hex and safe to interpolate directly.
ACME_B64="$(printf %s "$ACME_EMAIL" | base64 | tr -d '\n')"
rsh "DEPLOY_DIR='${DEPLOY_DIR}' DOMAIN='${DOMAIN}' ACME_B64='${ACME_B64}' HEAD_SHA='${HEAD_SHA}' bash -se" <<'R3'
set -euo pipefail
cd "$DEPLOY_DIR"
acme_email="$(printf %s "$ACME_B64" | base64 -d)"
# upsert: set-or-update — an existing stale value is corrected, not left in place.
set_env() {
  grep -v "^${1}=" .env > .env.redeploy_tmp || true
  printf '%s=%s\n' "$1" "$2" >> .env.redeploy_tmp
  chmod --reference=.env .env.redeploy_tmp   # preserve .env's mode (it holds secrets)
  mv .env.redeploy_tmp .env
}
set_env POLARIS_DOMAIN     "$DOMAIN"
set_env POLARIS_ACME_EMAIL "$acme_email"
set_env POLARIS_GIT_COMMIT "$HEAD_SHA"
R3
log "Phase 3 done"

# --- Phase 4: validate + build + up -----------------------------------------
log "Phase 4: config validate + build + up  (build ~10-15 min; old stack serves until 'up')"
rsh "DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R4'
set -euo pipefail
cd "$DEPLOY_DIR"
docker compose -p polaris -f docker-compose.v6.yml config >/dev/null
docker compose -p polaris -f docker-compose.v6.yml build
docker compose -p polaris -f docker-compose.v6.yml up -d
R4
log "Phase 4 done — new stack recreated"

# --- Phase 5: verify --------------------------------------------------------
log "Phase 5: verify health + smoke"
rsh "DEPLOY_DIR='${DEPLOY_DIR}' bash -se" <<'R5'
set -euo pipefail
cd "$DEPLOY_DIR"
ok=0
for _ in $(seq 1 36); do
  ok=1
  for c in polaris-redis-1 polaris-api-1 polaris-worker-1 polaris-webui-1; do
    h="$(docker inspect --format '{{.State.Health.Status}}' "$c" 2>/dev/null || echo missing)"
    [[ "$h" == healthy ]] || ok=0
  done
  cs="$(docker inspect --format '{{.State.Status}}' polaris-caddy-1 2>/dev/null || echo missing)"
  [[ "$cs" == running ]] || ok=0
  [[ $ok -eq 1 ]] && break
  sleep 5
done
[[ $ok -eq 1 ]] || { docker compose -p polaris -f docker-compose.v6.yml ps; exit 1; }
docker exec polaris-api-1 curl -fsS http://localhost:8000/health >/dev/null
echo "box OK: redis+api+worker+webui healthy, caddy running, api /health 200"
R5
CODE="$(curl -fsS -o /dev/null -w '%{http_code}' "https://${DOMAIN}/" --max-time 25 || echo 000)"
[[ "$CODE" == "200" ]] || die "external https://${DOMAIN}/ returned ${CODE}"
log "Phase 5 done — https://${DOMAIN}/ -> 200"

# --- success ----------------------------------------------------------------
rsh "rm -f ${DEPLOY_DIR}/docker-compose.caddy.yml ${DEPLOY_DIR}/docker-compose.v6.yml.bak" || true
ARMED=0
log "REDEPLOY OK — live = ${HEAD_SHA}; rollback artifacts retained in ${BACKUP}"
