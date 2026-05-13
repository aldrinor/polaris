HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank for iter 6.
- Surface ALL findings now; do not hold back.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 — Deploy substrate (Dockerfile, entrypoint, compose, GPG bootstrap)

GH#469. Critical-path day 11-12. The deploy substrate that lets POLARIS v6 run on the Carney server (single-host docker-compose first, then AWS Canada Central in I-carney-002). Pipeline-A live submission via the I-arch-001a..001f seam now needs an OS-level wrapping so the API + Dramatiq worker + Redis + Next.js webui all come up on one `docker compose up` with GPG signing wired and the canonical `.env` documented.

## Files I have ALSO checked clean (§-1.2 #2)

- `Dockerfile` — current is single-stage python:3.11-slim with WeasyPrint; legacy from pipeline B. Does NOT add `src/` to PYTHONPATH (pipeline A relies on the working directory). Does NOT install `gnupg`. Does NOT install `dramatiq` / `redis-py>=4` explicitly (transitively from requirements-v6.txt).
- `scripts/docker_entrypoint.sh` — has `serve|sweep|preflight|shell` subcommands but NO `api|worker` subcommand for the v6 split. The `serve` target launches `scripts.live_server:app` (pipeline B UI) NOT `polaris_v6.api.app:app` (v6 backend).
- `docker-compose.yml` — current single-service `web` + optional `chromadb`/`searxng`/`vllm` profiles. No Redis service. No Dramatiq worker service. No Next.js frontend service. Volumes mount host paths for outputs/logs/state/data.
- `requirements-v6.txt` — pins `redis==7.4.0`, `dramatiq==1.18.0`, `fastapi`, `uvicorn[standard]`. PyYAML is transitive via uvicorn[standard].
- `web/` — Next.js frontend; needs a Dockerfile + build-time `NEXT_PUBLIC_*` ARGs for the API base URL rewrite.
- `polaris-controls/CHARTER.md` — verifies admin authority + cage constraints stay in force during deployment.
- `state/polaris_restart/plan.md` §7.B LOCKED B1 — auto-merge stays in force on the deploy branch.

## Scope

5 files added or rewritten + 1 helper script:

1. **NEW `Dockerfile.v6`** — multi-target build for the v6 backend (api + worker share the same image):
   - `FROM python:3.11-slim` base
   - `apt-get install` gnupg + curl + build-essential (gnupg for signing bundles)
   - `WORKDIR /app`
   - `COPY requirements-v6.txt .` + `RUN pip install --no-cache-dir -r requirements-v6.txt`
   - `COPY src/ src/` + `COPY scripts/ scripts/` + `COPY config/ config/`
   - `ENV PYTHONPATH=/app/src:/app` so `from polaris_v6...` resolves without uvicorn `--app-dir` flag
   - `ENV POLARIS_V6_REDIS_URL=redis://redis:6379/0`
   - `RUN mkdir -p /app/outputs /app/logs /app/state /app/data`
   - `COPY scripts/v6_entrypoint.sh /entrypoint.sh && chmod +x /entrypoint.sh`
   - `ENTRYPOINT ["/entrypoint.sh"]` / `CMD ["api"]`
   - HEALTHCHECK curls `/health` on 8000 (existing endpoint per app.py:81)

2. **NEW `scripts/v6_entrypoint.sh`** — `api|worker|migrate|preflight|shell` subcommands:
   - `api`: `exec uvicorn polaris_v6.api.app:app --host 0.0.0.0 --port 8000`
   - `worker`: `exec dramatiq polaris_v6.queue.actors --processes 1 --threads 2`
   - `migrate`: `exec python -c "from polaris_v6.queue.run_store import init_db; init_db()"` (ensures sqlite WAL created + lifecycle_status column migration runs)
   - `preflight`: env-var + redis-ping + GPG-keyring sanity
   - Before exec: `wait-for-redis.sh` polling loop (10s timeout) so worker doesn't crashloop while redis comes up
   - Broker init order: api waits for redis OR fails loud per LAW II; worker waits for redis OR fails loud

3. **NEW `web/Dockerfile`** — multi-stage Next.js 16 build (per memory `next_16_breaking_changes.md`):
   - Stage 1 `deps`: `node:20-alpine` + `npm ci --frozen-lockfile`
   - Stage 2 `builder`: ARG `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`) so frontend Server Actions / fetch baseUrl wire to the API container by service name at compose time
   - `RUN npm run build`
   - Stage 3 `runner`: standalone Next output + `node server.js`
   - Port 3000; HEALTHCHECK curls `/` returning 200

4. **NEW `docker-compose.v6.yml`** — full Carney production stack:
   - `redis`: `redis:7-alpine` with AOF persistence + healthcheck (`redis-cli ping`)
   - `api`: built from `Dockerfile.v6`; depends_on redis (healthy); volumes for state/outputs/logs/data + a read-only mount for the GPG keyring; env `POLARIS_V6_REDIS_URL`, `POLARIS_GPG_KEY_ID`, `POLARIS_V6_RUN_DB=/app/state/v6_runs.sqlite`; ports 8000:8000
   - `worker`: same image as api, command `worker`; depends_on redis (healthy) + api (healthy, for shared sqlite migration); same env + volumes
   - `webui`: built from `web/Dockerfile`; build args `NEXT_PUBLIC_API_URL=http://api:8000` for Server Actions, `NEXT_PUBLIC_BROWSER_API_URL=http://localhost:8000` for browser fetch (rewrites in Next.js next.config); depends_on api; ports 3000:3000
   - `shared_state` named volume mounted to /app/state in api+worker so sqlite v6_runs.sqlite is reachable from both
   - GPG keyring: bind-mounted from host `~/.gnupg-polaris:/root/.gnupg:ro`

5. **NEW `scripts/bootstrap_gpg_demo_key.sh`** — operator-run helper for the Carney demo signing key:
   - Idempotent: skips if key already imported with target keygrip
   - Generates an ed25519 signing-only subkey under a stable user-id `POLARIS Carney Demo <signing@polaris.local>`
   - Writes the fingerprint to `state/polaris_gpg_keyid.txt` for the operator to set `POLARIS_GPG_KEY_ID` in `.env`
   - Exports the public key to `outputs/polaris_demo_pubkey.asc` for the transparency.md page that reviewers will reach (I-carney-003)
   - Prints next steps (set env var, restart compose stack)

6. **NEW `docs/deploy_runbook.md`** — single-page operator runbook:
   - Prereqs: docker compose v2, GPG, `.env` template with required vars listed
   - Step 1: `bash scripts/bootstrap_gpg_demo_key.sh` then export `POLARIS_GPG_KEY_ID=<fingerprint>`
   - Step 2: `docker compose -f docker-compose.v6.yml up -d`
   - Step 3: `curl http://localhost:8000/health` then `curl http://localhost:3000/`
   - Step 4: smoke test via `curl -X POST http://localhost:8000/runs -d '{"template":"clinical","question":"smoke"}'`
   - Rollback: `docker compose down -v` (drops volumes; data loss WARN)
   - Troubleshooting: `docker compose logs worker` if 502s; `docker compose exec api /entrypoint.sh preflight` for env-var diag

## Acceptance criteria

1. `docker compose -f docker-compose.v6.yml config` parses without error (no syntax / missing-image / volume-conflict).
2. `Dockerfile.v6` builds in CI without network access to private registries (use only docker.io public images).
3. `scripts/v6_entrypoint.sh` survives shellcheck linting clean (no SC2046, SC2086, etc.).
4. `wait-for-redis` polling loop respects a 10s timeout; never hangs forever.
5. `bootstrap_gpg_demo_key.sh` is idempotent — running twice does NOT create a second key.
6. `docs/deploy_runbook.md` exists with all 5 required sections (prereqs / start / smoke / rollback / troubleshoot).
7. No secrets committed: `.env` is gitignored; only `.env.example` (added in I-carney-004) ships in repo.
8. Non-Carney deployments (current `Dockerfile` + `docker-compose.yml` for pipeline B) are NOT touched — they continue to work for pipeline B UI deployments.

## Direct questions iter 1

1. New `Dockerfile.v6` + `docker-compose.v6.yml` separate from current files (NOT modifying them) — APPROVE'd? Or want to fold the v6 stack into the existing compose with a profile (v6 vs legacy)?
2. PYTHONPATH=/app/src:/app inside the container — APPROVE'd? Or want to use uvicorn `--app-dir src` instead?
3. Single shared image for api + worker (different ENTRYPOINT command) — APPROVE'd? Or split into `Dockerfile.api` + `Dockerfile.worker`?
4. GPG keyring bind-mount from `~/.gnupg-polaris:/root/.gnupg:ro` — APPROVE'd? Or want the keyring baked into the image at build time (which leaks the private key into the image layers — STRONGLY against, but listed for completeness)?
5. Bootstrap script generates a demo ed25519 signing-only subkey under `signing@polaris.local` — APPROVE'd for the Carney demo? Or want a different user-id / curve / key purpose?
6. Next.js webui rewrites via `NEXT_PUBLIC_API_URL=http://api:8000` build arg — APPROVE'd? Or want a reverse-proxy (nginx/Caddy) in front instead of direct service-name resolution?
7. Anything else blocking iter-1 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
