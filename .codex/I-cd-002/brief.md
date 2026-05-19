HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. Everything you need to review is embedded in this brief. The
prior I-A-01 review (iter 1) crashed after exploring 7,500+ lines — this brief is fully
self-contained. Review ONLY the plan below.

# Codex brief review — I-cd-002 / GH#606: Redeploy current `polaris` HEAD to the live VM

Seq 2 of the Codex-APPROVED Carney-demo breakdown. This touches the **LIVE demo box**, so
the plan is vetted before any execution. This is a re-review: I-A-01 (the prior id for this
same issue) returned **REQUEST_CHANGES** with 5 P1 on iter 1. This brief is the materially
revised plan; §B below maps every prior P1 to its resolution — please VERIFY each.

## §0 — Iter-2 revisions (responding to iter-1 REQUEST_CHANGES)

Iter 1 returned REQUEST_CHANGES with 2 P1; both are fixed in this revision:
- **P1-1 (redis snapshot consistency)** — Phase 1 now stops `redis` (not just `worker` +
  `api`) before the volume tar, then restarts the old stack for the build window. The
  snapshot is taken with every volume writer quiesced → consistent rollback artifact.
- **P1-2 (rollback unconditional `down`)** — Phase 6 is rewritten state-aware: it restores
  the OLD compose files in-place and runs `up -d --force-recreate` from them, with NO
  forward-compose `down`, so a failure while the old stack is still serving does not tear
  down still-healthy containers.
- **P2-1 (ACME email)** — the script no longer silently defaults the email; it requires
  `--acme-email` / `$POLARIS_ACME_EMAIL` and fails loudly if absent.
P2-2 (`git archive | rsync` mechanism) and P2-3 (1-2 min downtime) were confirmations — no
change needed.

## §A — Context (grounded, verified this session via SSH + git)

- Live VM: OVH `polaris-orchestrator`, BHS5 Québec, `51.79.90.35`, deploy dir
  `/home/ubuntu/polaris/`. Live at `https://polarisresearch.ca/` → HTTP **200** right now.
- Running stack (`docker ps`): 5 containers, project name **`polaris`** —
  `polaris-caddy-1` (up 11h, `caddy:2-alpine`), `polaris-webui-1` / `polaris-worker-1` /
  `polaris-api-1` / `polaris-redis-1` (all up 4 days, **healthy**).
- The box runs via `docker compose -f docker-compose.v6.yml -f docker-compose.caddy.yml`
  — the box's `docker-compose.v6.yml` is a ~May-14 divergent hand-edited build (4 services),
  and `docker-compose.caddy.yml` is an **additive box-local override** that bolts on the
  `caddy` service. Box also has `docker-compose.v6.yml.bak`, an untracked hand-written
  `Caddyfile`, and the legacy `docker-compose.yml`.
- The box deploy dir has **no `.git`** — it is a snapshot.
- Box named volumes (verified `docker volume ls`): `polaris_shared_state`,
  `polaris_redis_data`, `polaris_caddy_data`, `polaris_caddy_config`.
- Box `.env` (13 keys, generated 2026-05-15, sovereign mode — NO `OPENROUTER_API_KEY`):
  `POLARIS_JWT_SECRET`, `POLARIS_STATIC_ACCOUNTS_PATH`, `POLARIS_ETC_DIR`,
  `POLARIS_GPG_HOMEDIR`, `POLARIS_GPG_KEY_ID`, `POLARIS_V6_CORS_ORIGINS`, `SERPER_API_KEY`,
  `SEMANTIC_SCHOLAR_API_KEY`, `PG_LOG_LEVEL`, `POLARIS_PROVIDER`, `POLARIS_REGION`,
  `POLARIS_GIT_COMMIT`. **There is NO `POLARIS_DOMAIN` and NO `POLARIS_ACME_EMAIL`.**
- Target: local `polaris` HEAD — includes I-cd-001 (clean Docker build, merged squash
  `6eb79da0` ~1h ago). HEAD's `docker-compose.v6.yml` (4600 B) has **all 5 services
  including `caddy` native**, `caddy_data`/`caddy_config` volumes, and the worker
  healthcheck override. HEAD's `Caddyfile` is tracked and **env-parameterized**:
  global `email {$POLARIS_ACME_EMAIL:internal@localhost}`, site block `{$POLARIS_DOMAIN} {`.
- Disk on box: 53 G free of 96 G. Build needs ~15 G; ample.

## §B — Prior I-A-01 review: the 5 P1, each mapped to its resolution (VERIFY each)

**P1-1 (build fixes dropped — pydantic-settings / bcrypt / requirements.lock).**
RESOLVED by **I-cd-001**, merged (squash `6eb79da0`). HEAD now has
`pydantic-settings>=2.10.1,<3.0.0`, `bcrypt==4.0.1`, a 284-pkg `requirements.lock`, and
`Dockerfile.v6` installs via `pip install -r requirements.lock`. **Empirically verified:** a
full `docker compose -f docker-compose.v6.yml build` was run on this exact box during
I-cd-001 and exited 0 (`BUILD_EXIT=0`). HEAD builds cleanly on the VM.

**P1-2 (healthcheck fixes dropped — worker `:8000`, webui `localhost`).**
RESOLVED by **I-cd-001**. HEAD's `docker-compose.v6.yml` worker service has a
healthcheck override (`CMD-SHELL` redis-reachability socket check, lines 107-112).
HEAD's `web/Dockerfile` has `ENV HOSTNAME=0.0.0.0` and a `127.0.0.1` healthcheck.
All 5 containers can become healthy as written.

**P1-3 (Caddy/TLS inconsistent — tracked Caddyfile, stale `docker-compose.caddy.yml`).**
ADDRESSED in this plan. The redeploy uses **ONLY** HEAD's `docker-compose.v6.yml`
(`caddy` is native there) and **drops `docker-compose.caddy.yml`** (its sole purpose —
bolting caddy onto a caddy-less box compose — is obsolete). HEAD's tracked
env-parameterized `Caddyfile` becomes canonical and replaces the box's hand-written one.
**See §C — this surfaces a NEW critical finding the prior brief missed.**

**P1-4 (rollback project-name/volume drift).**
ADDRESSED. Every `docker compose` invocation in the script pins **`-p polaris`**, and the
deploy dir stays **`/home/ubuntu/polaris`** (rsync-in-place, never a renamed dir). So
volumes always resolve to `polaris_shared_state` / `polaris_redis_data` /
`polaris_caddy_data` / `polaris_caddy_config` — the exact existing volumes. Rollback
restores compose files in-place into the same dir with the same `-p polaris`.

**P1-5 (rollback image-only — `shared_state`/`redis_data` not snapshotted/quiesced).**
ADDRESSED. Phase 1 quiesces (`compose stop worker api` — the SQLite + queue writers) then
tar-snapshots `polaris_shared_state`, `polaris_redis_data`, and `polaris_caddy_data` into a
timestamped backup dir before any new container starts. Rollback restores those tarballs.

**Prior P2s** also folded in: exact-ref handling (§D phase 2 uses `git archive` of the
exact `polaris` ref — no ambiguous on-box fetch); `docker compose config` validation before
build (§D phase 4); `POLARIS_GIT_COMMIT` provenance refresh (§D phase 3).

## §C — NEW critical finding (the prior brief missed this)

HEAD's tracked `Caddyfile` resolves the site address from `{$POLARIS_DOMAIN}` and the ACME
account email from `{$POLARIS_ACME_EMAIL:internal@localhost}`, both via compose
`env_file: .env`. **The box `.env` contains neither key** (§A). The box's caddy works today
only because the box's *untracked* `Caddyfile` hard-codes `polarisresearch.ca`.

If HEAD's `Caddyfile` is deployed without first adding those keys, Caddy renders a site
block addressed `{$POLARIS_DOMAIN}` (empty/literal) → no valid site → **the live HTTPS
site goes down**. This is a redeploy-breaking defect, not cosmetic.

**Mitigation (Phase 3):** before `up -d`, append to the box `.env` (idempotently, only if
absent): `POLARIS_DOMAIN=polarisresearch.ca` and `POLARIS_ACME_EMAIL=<value>`. Per iter-1
P2-1, the ACME email is NOT silently defaulted — the script requires it via `--acme-email
<addr>` (or `$POLARIS_ACME_EMAIL` in the invoking shell) and **fails loudly** if absent
(LAW II — no silent default); `docs/deploy_runbook.md` documents `orchunyin@gmail.com` as
the example value. The existing Let's Encrypt cert + ACME account live in
`polaris_caddy_data` (preserved — same volume), so Caddy reuses the cert on restart; the
email key mainly governs any future re-registration.

## §D — The deliverable + the redeploy plan to review

**Deliverable:** `scripts/redeploy_v6.sh` — an idempotent redeploy script run from a
workstation that has the repo at `polaris` HEAD + the box SSH key; arg = ssh target
(default `ubuntu@51.79.90.35`). Plus a "Redeploy over a running stack" section appended to
`docs/deploy_runbook.md`. The script encodes the 6 phases below. I-cd-002 GREEN =
`scripts/redeploy_v6.sh` Codex-APPROVED + executed on the box + evidence captured in
`outputs/audits/I-cd-002/` (`live=HEAD`, 4 healthchecked containers healthy + caddy up,
smoke OK).

**Phase 0 — preflight.** Local: on `polaris` branch, clean tree, capture HEAD sha. Box
(SSH): docker present, ≥15 G free, `/home/ubuntu/polaris/.env` exists.

**Phase 1 — snapshot/backup (box).** `BACKUP=/home/ubuntu/polaris-rollback-<utc>`.
`docker tag` each running image → `:rollback-<utc>` (api, worker, webui, caddy). Copy the
box's `docker-compose.v6.yml`, `.bak`, `docker-compose.caddy.yml`, `Caddyfile`, `.env` into
`BACKUP`. **Quiesce ALL volume writers** (iter-1 P1-1 — a live `redis` keeps rewriting
AOF/RDB, so a tar of a running `redis` volume is not a consistent rollback artifact):
`docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml stop worker
api redis`. Snapshot volumes (all writers stopped → consistent):
`docker run --rm -v polaris_shared_state:/v:ro -v BACKUP:/b alpine tar czf /b/shared_state.tgz -C /v .`
(same for `polaris_redis_data`, `polaris_caddy_data`). Then **restart the old stack** —
`docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml start
worker api redis` — so it is fully serving during the ~10-15 min Phase 4 build (snapshot
window downtime ≈ 1 min, not 15). The snapshot is point-in-time; build-window writes are
not captured — acceptable, as the box's generation backend returns
`400 completion_backend_unavailable` (no GPU yet) so there is no run/queue write traffic.
Write `docker compose ... ps` + image digests to `BACKUP/pre_state.txt`.

**Phase 2 — sync HEAD tracked tree (local→box).** Local:
`git archive --format=tar polaris | gzip > /tmp/polaris-head-<sha>.tgz`; `scp` to box;
box extracts to `/tmp/polaris-head-<sha>/`. Then on box:
`rsync -a --delete --exclude .env --exclude 'outputs/' --exclude 'logs/' --exclude 'data/'
--exclude 'state/' --exclude docker-compose.caddy.yml --exclude docker-compose.v6.yml.bak
/tmp/polaris-head-<sha>/ /home/ubuntu/polaris/`. Effect: every tracked file → HEAD,
**stale tracked files deleted** (`--delete`), runtime/gitignored dirs + `.env` untouched,
dir stays `/home/ubuntu/polaris`. `git archive` carries only tracked content (no `.git`,
no gitignored files). The box's now-obsolete `docker-compose.caddy.yml` + `.bak` are
excluded from the rsync so they survive as inert leftovers (the script `rm`s them at the
end, post-verify, to avoid confusion — not load-bearing).

**Phase 3 — `.env` reconcile (box).** Append-if-absent `POLARIS_DOMAIN=polarisresearch.ca`
and `POLARIS_ACME_EMAIL=orchunyin@gmail.com`; set `POLARIS_GIT_COMMIT=<HEAD sha>`. Every
other key preserved byte-for-byte. (`.env` is never rsync'd — Phase 2 excludes it.)

**Phase 4 — validate + build + up (box).** `cd /home/ubuntu/polaris`.
`docker compose -p polaris -f docker-compose.v6.yml config` → must exit 0.
`docker compose -p polaris -f docker-compose.v6.yml build` (old stack still serving — zero
downtime during the ~10-15 min build). Then `... up -d` (recreates the 5 services; caddy
native; brief ~1-2 min recreate downtime). **NEVER `down`, NEVER `down -v`** on the
forward path.

**Phase 5 — verify.** Poll ≤180 s: the 4 healthchecked services (`redis`, `api`, `worker`,
`webui`) report `healthy` AND `caddy` reports `running`. `docker exec polaris-api-1 curl
-fsS http://localhost:8000/health` → 200. External `curl -fsS https://polarisresearch.ca/`
→ 200. TLS: `curl -vI` shows a valid non-self-signed cert (the preserved LE cert). Note:
Caddy reverse-proxies the `webui` service, so the external smoke is the homepage `/`; the
API `/health` is checked in-container (there is no public `/health` route through Caddy —
flagged honestly rather than promising an external `/health`).

**Phase 6 — rollback (auto, on ANY Phase 4/5 failure) — state-aware, no unconditional
`down` (iter-1 P1-2).** The forward path never `down`s the old stack — `up -d` recreates
in place — so on a failure before a successful Phase 5 the old containers may still be
serving. Rollback therefore does NOT issue a forward-compose `down`. Instead:
(1) restore `BACKUP`'s `docker-compose.v6.yml`, `docker-compose.caddy.yml`, `Caddyfile`
into `/home/ubuntu/polaris` (overwriting HEAD's that Phase 2 rsync'd in);
(2) retag the `:rollback-<utc>` images back to `:latest`;
(3) `docker compose -p polaris -f docker-compose.v6.yml -f docker-compose.caddy.yml up -d
--force-recreate` from the restored OLD files — `--force-recreate` brings every service to
the OLD spec whether it is currently the new partial stack or the still-running old stack,
with no teardown gap;
(4) verify the OLD stack healthy + `https://polarisresearch.ca/` 200.
The 3 volume tarballs stay in `BACKUP` but are **NOT auto-restored** — the forward path
never runs `down -v`, so the `polaris_*` volumes are intact; a volume restore is a
separate, operator-confirmed procedure (documented in the runbook) used only if a volume is
ever found corrupted, because restoring a volume itself requires disruptive teardown. Exit
non-zero with the failure reason.

## §E — Files I have ALSO checked and they are clean / accounted for

- `Dockerfile.v6`, `web/Dockerfile`, `docker-compose.v6.yml` (HEAD) — read in full this
  session; carry every I-cd-001 fix; `caddy` is native in the compose. No change needed.
- `Caddyfile` (HEAD) — env-parameterized; correct *given* §C's `.env` fix. No change.
- `scripts/deploy.sh` — the legacy native/venv + `docker-compose.yml` (pipeline-B)
  deployer. NOT used by the v6 stack and NOT touched by I-cd-002.
- `docs/deploy_runbook.md` — covers a *fresh* v6 bring-up only; I-cd-002 appends a
  "Redeploy over a running stack" section. Other runbooks (`carney_demo_runbook.md`,
  `runbook.md`) are out of scope (I-cd-035 owns runbook consolidation).
- `docker-compose.yml` (legacy pipeline-B) — untouched.
- Box `outputs/`, `logs/`, `data/`, `state/`, `~/.gnupg-polaris`, `/etc/polaris` mounts —
  preserved (Phase 2 rsync excludes them; named volumes preserved via `-p polaris`).

## §F — Open questions (resolved by the iter-1 review)

1. ACME email — RESOLVED (iter-1 P2-1): the script requires `--acme-email` /
   `$POLARIS_ACME_EMAIL` and fails loudly if absent; no silent default. §C + Phase 3
   updated accordingly.
2. `git archive | rsync --delete` HEAD-sync mechanism — CONFIRMED correct (iter-1 P2-2;
   avoids putting a private-repo credential on the VM).
3. ~1-2 min `up -d` recreate downtime — CONFIRMED acceptable for a pre-Carney box; no
   blue/green required (iter-1 P2-3).
4. Phase-1-6 risk to `.env` / GPG mount / `/etc/polaris` / `polaris_caddy_data` cert /
   `shared_state` / `redis_data` — iter 1 found two real risks (P1-1 redis snapshot
   consistency, P1-2 rollback `down`); both are fixed in §0 / Phase 1 / Phase 6 above.
   Please confirm no residual risk.

## §G — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
