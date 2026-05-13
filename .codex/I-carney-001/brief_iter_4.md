HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 iter 4 — full P1 resolution (5 of 5 from iter 3) + 4 P2 fixes + code-grounded plan

Iter 1 + 2 + 3 decisions carry forward. Iter 3 produced 5 P1 + 4 P2 blockers. All resolved below with code-grounded specifics.

## P1 from iter 3 → resolutions (code-verified)

### P1.1 — Docker ENTRYPOINT subcommand mismatch

You wrote:
> "Dockerfile:47 runs /entrypoint.sh, scripts/docker_entrypoint.sh:25-70 only accepts serve/sweep/research/preflight/shell."

**Code-verified**: confirmed. Adding two subcommands to `scripts/docker_entrypoint.sh`:

```bash
case "${1:-serve}" in
    serve|api)
        # api = canonical name; serve kept as alias for compat
        echo "Starting POLARIS v6 API on port 8000..."
        exec python -m uvicorn polaris_v6.api.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
        ;;
    serve-legacy)
        echo "Starting legacy live_server on port 8000..."
        exec python -m uvicorn scripts.live_server:app --host 0.0.0.0 --port 8000 --workers 1
        ;;
    worker)
        echo "Starting Dramatiq worker..."
        # Import broker init BEFORE actors import (P1.2 fix)
        exec python -m polaris_v6.queue.run_worker
        ;;
    # ... existing sweep/preflight/shell unchanged
esac
```

Compose services use `command: ["api"]` and `command: ["worker"]` — entrypoint script unchanged interface.

### P1.2 — Broker init order

You wrote:
> "Dramatiq broker is still not initialized before actors import. broker.py:48 is the only path reading POLARIS_V6_REDIS_URL; runs.py:16 imports actors directly; actors.py:27-28 says get_broker() must already have run."

**Code-verified**: `actors.py:27-28` comment confirms. Fix:

```python
# NEW: src/polaris_v6/queue/run_worker.py
"""Entrypoint module for the Dramatiq worker.

Importing this module triggers broker init BEFORE importing actors.
Used by `python -m polaris_v6.queue.run_worker`.
"""
import dramatiq.cli

from polaris_v6.queue.broker import get_broker

# Broker MUST be set on the global default before actors module is imported.
get_broker()

from polaris_v6.queue import actors  # noqa: E402, F401 — registers actors

if __name__ == "__main__":
    # Hand off to dramatiq CLI; sys.argv carries --processes/--threads
    import sys
    sys.argv = [sys.argv[0], "polaris_v6.queue.actors"] + sys.argv[1:]
    dramatiq.cli.main()
```

For the API side, modify `src/polaris_v6/api/app.py:create_app()`:

```python
def create_app():
    from polaris_v6.queue.broker import get_broker
    get_broker()  # init broker BEFORE any router imports actors
    
    # ... existing FastAPI setup ...
    from polaris_v6.api.runs import router as runs_router  # imports actors
    app.include_router(runs_router)
```

### P1.3 — Shared run state across api + worker containers

You wrote:
> "run_store.py:29 uses state/v6_runs.sqlite, and actors.py:54-56 only marks completion if the worker can see the inserted row. Without shared /app/state, POST /runs stays queued from the API's perspective."

**Resolution**: mount `state/`, `outputs/`, `data/` as named volumes shared across api + worker:

```yaml
services:
  api:
    volumes:
      - polaris_state:/app/state
      - polaris_outputs:/app/outputs
      - polaris_data:/app/data
      - ./logs:/app/logs
  worker:
    volumes:
      - polaris_state:/app/state
      - polaris_outputs:/app/outputs
      - polaris_data:/app/data
      - ./logs:/app/logs

volumes:
  polaris_state: {}
  polaris_outputs: {}
  polaris_data: {}
  chroma_data: {}
  redis_data: {}
```

SQLite over a shared Docker volume works for concurrency=1 (single writer, multiple readers — WAL mode if needed). For production scale, migrate to Postgres; tracked as post-demo issue.

### P1.4 — Next.js rewrites at build time vs runtime

You wrote:
> "Next writes rewrites into routes-manifest during next build, so compose runtime environment alone is insufficient."

**Resolution**: build-time **ARG** in web/Dockerfile, default to Docker-internal hostname; AWS deploy uses the same default since api+webui colocate on the same EC2 host's docker-compose network.

```dockerfile
# web/Dockerfile (NEW)
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time ARG (default fine for docker-compose; can override at AWS build)
ARG INTERNAL_API_URL=http://api:8000
ENV INTERNAL_API_URL=$INTERNAL_API_URL

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
```

`web/next.config.ts`: also use `output: 'standalone'` for the slim runtime image.

```ts
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const internal = process.env.INTERNAL_API_URL || 'http://api:8000';
    return [
      { source: '/runs/:path*',        destination: `${internal}/runs/:path*` },
      { source: '/upload/:path*',      destination: `${internal}/upload/:path*` },
      { source: '/stream/:path*',      destination: `${internal}/stream/:path*` },
      { source: '/workspaces/:path*',  destination: `${internal}/workspaces/:path*` },
      { source: '/ambiguity',          destination: `${internal}/ambiguity` },
      { source: '/scope/:path*',       destination: `${internal}/scope/:path*` },
      { source: '/templates/:path*',   destination: `${internal}/templates/:path*` },
      { source: '/api/:path*',         destination: `${internal}/api/:path*` },
      { source: '/health',             destination: `${internal}/health` },
    ];
  },
};
export default nextConfig;
```

Per P2 from iter 3 (incomplete rewrite list): added `/stream/:path*` and `/workspaces/:path*`.

Also fix `web/lib/api.ts:10` default from `"http://127.0.0.1:8000"` to `""` (same-origin) so unset NEXT_PUBLIC_BACKEND_URL works. Dev gets a `.env.local` with `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000` if needed.

### P1.5 — Live POST /runs → graph payload (the load-bearing item)

You wrote:
> "actors.py:38-51 is still a deterministic noop, while graph_route.py:234-243 only resolves allowlisted V30 artifacts via registry.py:40/161. Wire the actor to produce/register artifacts, or make the demo use a canonical precomputed run explicitly."

**Code-verified**:
- `graph_v4.py:11,21,211-253` already wraps `scripts.run_honest_sweep_r3.run_one_query` — the bridge is implemented there, not in `adapters/retrieval_bridge.py` (the adapters/ comment is stale)
- `actors.py:47-51` explicitly says "Phase 0 stub; Phase 1 wires once Vast.ai is live" — but the Carney demo uses OpenRouter (option (c)), not Vast.ai
- `registry.py:40` `_PHASE_A_ALLOWLIST: tuple[Path, ...] = (CANONICAL_DEMO_DIR,)` — allowlist of one canonical V30 path
- `registry.py:161` `_RUNS: tuple[RunSummary, ...] = _build_runs()` — frozen at module import; new runs invisible

**Resolution: wire the actor + extend the registry to discover dynamic runs.**

Actor body:

```python
# src/polaris_v6/queue/actors.py (modified)
@dramatiq.actor(max_retries=ENQUEUE_MAX_RETRIES, time_limit=30 * 60 * 1000)
def enqueue_research_run(run_id, request_payload):
    # Stub path preserved for tests
    if run_store.get_run(run_id) is None:
        return {"run_id": run_id, "status": "completed", "echo": request_payload}

    run_store.mark_in_progress(run_id)
    try:
        import asyncio
        from pathlib import Path
        import os
        from src.polaris_graph.graph_v4 import build_and_run_v4

        out_root = Path(os.environ.get("POLARIS_OUTPUT_ROOT", "outputs/carney_demo"))
        out_root.mkdir(parents=True, exist_ok=True)

        result = asyncio.run(build_and_run_v4(
            run_id=run_id,
            payload=request_payload,
            out_root=out_root,
        ))
        run_store.mark_completed(run_id, result)
        return result
    except Exception as exc:
        run_store.mark_failed(run_id, str(exc))
        raise
```

(Note: I'll add a `build_and_run_v4(run_id, payload, out_root)` wrapper in `graph_v4.py` if the existing signature doesn't match — keeps the actor body small.)

Registry extension: replace allowlist-of-one with dynamic discovery:

```python
# src/polaris_graph/audit_ir/registry.py (modified)
def _build_runs() -> tuple[RunSummary, ...]:
    runs: list[RunSummary] = []
    # 1. Canonical V30 demo run (existing)
    runs.extend(_scan_dir(CANONICAL_DEMO_DIR))
    # 2. Demo-runtime runs from POLARIS_OUTPUT_ROOT
    runtime_root = Path(os.environ.get("POLARIS_OUTPUT_ROOT", "outputs/carney_demo"))
    if runtime_root.exists():
        for manifest in sorted(runtime_root.rglob("manifest.json")):
            runs.extend(_scan_dir(manifest.parent))
    return tuple(runs)

def find_run_by_id(run_id: str) -> RunSummary | None:
    # Re-scan if requested run not in static cache (handles runtime-produced runs)
    for run in _RUNS:
        if run.run_id == run_id:
            return run
    # Rebuild cache lazily for runtime-added runs
    global _RUNS
    _RUNS = _build_runs()
    for run in _RUNS:
        if run.run_id == run_id:
            return run
    return None
```

This keeps the V30 canonical allowlist intact AND lets new runs land in the demo path.

## P2 from iter 3 → resolutions

### P2.1 — Same-origin rewrite list complete

Added `/stream/:path*` and `/workspaces/:path*` to rewrites above. P1.4 addresses.

### P2.2 — POLARIS_GPG_KEY_ID and bundle 503

You wrote:
> "audit_bundle_route.py:92-108 returns 503 gpg_unavailable. Either document bundle download as disabled/preview-only, or add gnupg+key mount."

**Code-verified**: confirmed 503 path.

**Resolution: install gnupg in the Dockerfile and mount key via Docker secret.** Audit bundles are core to POLARIS value prop (#137 v6 Phase 1 Task 1.6 F15 audit bundle export substrate). Disabling them on demo deployment weakens the "auditable" pitch to Carney's office.

```dockerfile
# Dockerfile additions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev libcairo2 curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Demo key import via entrypoint
# (key file mounted from compose secret)
```

```yaml
# docker-compose.yml additions
secrets:
  polaris_gpg_key:
    file: ./secrets/polaris_demo_signing_key.asc

services:
  api:
    secrets:
      - polaris_gpg_key
    environment:
      - POLARIS_GPG_KEY_ID=<KEYID>
      - POLARIS_GPG_KEY_FILE=/run/secrets/polaris_gpg_key
```

`docker_entrypoint.sh` runs `gpg --batch --import $POLARIS_GPG_KEY_FILE` on first container start. Key is demo-only, 4096-bit RSA, generated locally before deploy. AWS deploy: key stored in AWS Secrets Manager, sidecar fetches at startup.

Sub-issue I-carney-004 owns this (auth + signing keys + secrets).

### P2.3 — Concurrency=1 hard cap

Worker `--processes 1 --threads 1` (changed from `--threads 2`) plus a Redis mutex in the actor body:

```python
@dramatiq.actor(max_retries=ENQUEUE_MAX_RETRIES, time_limit=30 * 60 * 1000)
def enqueue_research_run(run_id, request_payload):
    from polaris_v6.queue.broker import get_broker
    redis = get_broker().client  # Dramatiq exposes the redis client
    lock_key = "polaris:research:active_lock"
    # Try acquire mutex; TTL 35 min (>time_limit 30 min)
    acquired = redis.set(lock_key, run_id, nx=True, ex=35 * 60)
    if not acquired:
        # Another run is active; defer this message
        from dramatiq.errors import Retry
        raise Retry("active run in progress", delay=10_000)  # retry in 10s
    try:
        # ... run body ...
    finally:
        redis.delete(lock_key)
```

Test: `tests/polaris_v6/queue/test_concurrency_cap.py` submits 3 messages in rapid succession; asserts at most one is in_progress at any time over a 30s window.

### P2.4 — Mount /app/outputs

Already in P1.3 fix (polaris_outputs named volume on both api + worker).

## AWS deployment topology (unchanged from iter 3)

Single EC2 m7i-flex.4xlarge running docker-compose. ALB → EC2 :3000 (webui). Webui rewrites internal /api/* to api:8000. Static accounts auth. CloudWatch logs.

Sub-issue I-carney-002 owns the AWS infra spinup.

## Sub-issues (final ordering — APPROVE to start opening)

| ID  | Title | Days | Critical path |
|---|---|---|---|
| I-carney-005 | Demo-path feature parity (P1.1-P1.5 + P2.1-P2.4 fixes) | 1-3 | ✓ |
| I-carney-002 | AWS Canada infra (after local smoke green) | 1 | ✓ |
| I-carney-003 | Sovereignty + transparency endpoint + egress controls | 1-2 | |
| I-carney-004 | Static accounts auth + GPG signing key + secrets mgmt | 2 | ✓ |
| I-carney-006 | 5 canonical Carney questions rehearsal + §-1.1 audit | 3-5 | ✓ |
| I-carney-007 | Runbook + transparency.md + fallback laptop + demo script | 6 | |

Critical path 002 → 005 → 004 → 006 → 007. 003 in parallel.

## Direct questions for iter 4

1. P1.1 docker_entrypoint `api`/`worker` subcommands — APPROVE'd?
2. P1.2 broker-first via `run_worker.py` + `create_app()` modification — APPROVE'd?
3. P1.3 shared named volumes (polaris_state/outputs/data) — APPROVE'd?
4. P1.4 build-time INTERNAL_API_URL ARG in web/Dockerfile + standalone output — APPROVE'd?
5. P1.5 wire actor to `build_and_run_v4` + dynamic registry discovery — APPROVE'd? Or do you want me to ALSO ship a fallback "canonical pre-computed library" path so the demo still works if live submission fails on demo day?
6. P2.2 gnupg+key-mount path (not leave-unset) — APPROVE'd?
7. P2.3 Redis mutex with explicit nx+ex+delete semantics + concurrency test — APPROVE'd?
8. Anything else blocking opening sub-issues + starting I-carney-005?

## Local smoke I will run before opening I-carney-002 (AWS)

- `docker compose build --no-cache`
- `docker compose up -d redis chromadb api worker webui`
- `curl http://localhost:8000/health` 200
- `curl http://localhost:3000/health` 200 (via Next rewrite)
- `curl -X POST http://localhost:8000/runs -d '{"question":"<canonical Q1>","domain":"...","template_id":"..."}'` → 202 run_id
- Tail worker logs: actor pickup, mutex acquired, build_and_run_v4 starts
- Wait for completion (could be 5-15 min for real run; smoke uses a fast canned question)
- `curl http://localhost:8000/runs/<run_id>` → status: completed
- `curl http://localhost:8000/api/runs/<run_id>/graph` → GraphPayload with non-zero nodes/edges
- Browser visits `http://localhost:3000/runs/<run_id>/graph` → cytoscape canvas with the real graph
- `curl -X POST http://localhost:8000/api/audit-bundle ...` → tar.gz audit bundle (GPG-signed)
- `pytest tests/polaris_v6/ tests/polaris_graph/api/` PASS
- Concurrency test: submit 3 queries in 1s, verify only 1 in_progress at a time

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
