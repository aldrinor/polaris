# POLARIS v6 deploy runbook (Carney demo)

**Scope:** single-host `docker compose` deployment for the Carney demo. Production AWS Canada Central infrastructure is tracked separately in **I-carney-002**.

## Prereqs

- Docker Engine + Compose v2 (`docker compose version` returns 2.x)
- GPG installed on host (`gpg --version` returns 2.2+)
- A `.env` file at repo root with at minimum:

```
OPENROUTER_API_KEY=<your-key>
SERPER_API_KEY=<your-key>
SEMANTIC_SCHOLAR_API_KEY=<optional>
POLARIS_GPG_KEY_ID=<set after Step 1>
POLARIS_GPG_HOMEDIR=~/.gnupg-polaris
POLARIS_API_PORT=8000
POLARIS_WEB_PORT=3000
PG_MAX_COST_PER_RUN=5.00
```

`.env` is gitignored; do NOT commit it. A skeleton lives at `.env.example` (added in I-carney-004).

## Step 1 — Bootstrap the GPG demo signing key

```
bash scripts/bootstrap_gpg_demo_key.sh
```

Idempotent: skips if the `POLARIS Carney Demo` key already exists under `$GNUPGHOME`. On success it prints the fingerprint and writes the public key to `outputs/polaris_demo_pubkey.asc`. Copy the printed `POLARIS_GPG_KEY_ID=<fingerprint>` line into your `.env`.

## Step 2 — Bring up the stack

```
docker compose -f docker-compose.v6.yml up -d --build
```

This builds the v6 backend image (`Dockerfile.v6`) and the Next.js webui image (`web/Dockerfile`), then starts four services: `redis`, `api`, `worker`, `webui`.

Watch the startup:

```
docker compose -f docker-compose.v6.yml logs -f
```

`api` and `worker` will wait for `redis` healthcheck before they start. Expect `[entrypoint] redis reachable` then `[entrypoint] starting uvicorn` (api) or `starting dramatiq worker` (worker).

## Step 3 — Smoke test

```
# Backend health
curl -fsS http://localhost:8000/health

# Webui
curl -fsS http://localhost:3000/

# Submit a sample run (browser-side fetch lands here via /api/v6/runs)
curl -fsS -X POST http://localhost:8000/runs \
    -H 'content-type: application/json' \
    -d '{"template":"clinical","question":"Is tirzepatide effective for type 2 diabetes?"}'
```

The response is a `RunStatusResponse` with `run_id` (UUID), `lifecycle_status="queued"`. Within a few seconds the Dramatiq worker picks it up and pipeline-A runs.

Stream events:

```
curl -N http://localhost:8000/stream/<run_id>
```

## Step 4 — Rollback

```
docker compose -f docker-compose.v6.yml down
```

For a clean wipe (drops Redis AOF + sqlite v6_runs.sqlite — DATA LOSS):

```
docker compose -f docker-compose.v6.yml down -v
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `api` keeps restarting; logs show `redis unreachable after 10s` | Redis service hasn't initialized | `docker compose logs redis` — usually first-run AOF setup; wait 30s |
| 503 `gpg_unavailable` from `/runs/{id}/bundle.tar.gz` | `POLARIS_GPG_KEY_ID` empty or key missing | Re-run Step 1; verify `docker compose exec api gpg --list-keys` shows the key |
| Webui returns 502 from `/api/v6/*` | Internal proxy can't reach `api` service | `docker compose exec webui wget --spider http://api:8000/health` |
| `state/v6_runs.sqlite` not writable | `shared_state` volume permissions | `docker compose exec api ls -la /app/state`; rebuild volume |
| Pipeline-A 400 `cited_span_unreachable_after_snapshot` | Evidence pool full_text shorter than cited span | Check `outputs/<run_id>/evidence_pool.json` snippet length |

For env-var diagnostics:

```
docker compose -f docker-compose.v6.yml exec api /entrypoint.sh preflight
```

This runs `scripts/v6_preflight.py` which checks env vars, redis reachability, GPG keyring, and run_store write perms — exits non-zero with a checklist of failures.

## Reference

- I-carney-005 Codex artifacts: `.codex/I-carney-005/` (brief iters 1-5, diff iter 1+)
- I-arch-001a..001f chain (run_store → SSE → bundle): merged in PRs #475-#480
