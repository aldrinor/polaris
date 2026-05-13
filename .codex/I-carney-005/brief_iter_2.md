HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 iter 2 — 6 P1 resolutions

## P1-001 — Broker init order

`src/polaris_v6/queue/broker.py:get_broker()` sets the default broker via `dramatiq.set_broker(broker)`. Actors in `polaris_v6.queue.actors` decorate against `dramatiq.get_broker()` at import time, so the broker must be set FIRST.

### Resolution

`scripts/v6_entrypoint.sh` calls `polaris_v6.queue.broker.get_broker()` BEFORE the api or worker exec. New helper `scripts/v6_init_broker.py`:

```python
"""Idempotent broker initialization. Called by entrypoint before api / worker."""
import os
from polaris_v6.queue.broker import get_broker

if os.environ.get("POLARIS_V6_QUEUE_USE_STUB") == "1":
    get_broker(use_stub=True)
else:
    get_broker()  # reads POLARIS_V6_REDIS_URL
print("[v6_init_broker] broker initialized")
```

Entrypoint runs `python -m scripts.v6_init_broker` then exec's the actual command. For uvicorn `api`, the broker init also fires inside `app.py:_lifespan` to belt-and-suspenders the order; for `dramatiq` worker invocation, the worker CLI imports `polaris_v6.queue.actors` which will pick up the already-set broker via `dramatiq.get_broker()`.

## P1-002 — Dockerfile.v6 dependency surface

The v6 backend runs pipeline-A in the Dramatiq worker, which imports the full pipeline-A surface (`langchain_core`, `numpy`, `pandas`, `openai`, `aiohttp`, etc. — all in `requirements.txt`, NOT just `requirements-v6.txt`). Also `python-gnupg` is in `requirements.txt`.

### Resolution

`Dockerfile.v6` installs BOTH requirement files:
```dockerfile
COPY requirements.txt requirements-v6.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-v6.txt
```

## P1-003 — Compose env passthrough

API + worker need OPENROUTER_API_KEY, SERPER_API_KEY, SEMANTIC_SCHOLAR_API_KEY, and PG_* controls per pipeline-A.

### Resolution

```yaml
services:
  api:
    env_file:
      - .env
    environment:
      POLARIS_V6_REDIS_URL: redis://redis:6379/0
      POLARIS_V6_RUN_DB: /app/state/v6_runs.sqlite
      POLARIS_GPG_KEY_ID: ${POLARIS_GPG_KEY_ID}
      GNUPGHOME: /app/gpg
```

`env_file: .env` pulls every var from the host `.env`. Explicit `environment:` overrides set container-specific values that override .env (POLARIS_V6_REDIS_URL has to be `redis://redis:6379/0` inside the container, not the operator's localhost value).

`.env.example` is updated to document every required v6 var (deferred to I-carney-004 per CLAUDE.md §-1.2 scope discipline, but a TODO comment lands in this PR's runbook).

## P1-004 — Next.js standalone output

`web/next.config.ts` currently has no `output:` setting → standalone runner won't work.

### Resolution

Patch `web/next.config.ts`:
```typescript
const nextConfig: NextConfig = {
  output: 'standalone',
};
```

This enables `.next/standalone/server.js` so the multi-stage Dockerfile final stage can copy + run with just `node server.js`. Tested via local `npm run build && node .next/standalone/server.js`.

## P1-005 — Frontend env var name

`web/lib/api.ts:10` reads `NEXT_PUBLIC_BACKEND_URL`, not `NEXT_PUBLIC_API_URL`.

### Resolution

`web/Dockerfile` build arg: `ARG NEXT_PUBLIC_BACKEND_URL=http://api:8000` (matches `api.ts:10`). Compose `webui` service passes `build.args.NEXT_PUBLIC_BACKEND_URL=http://api:8000` so the Server-Side `fetch()` resolves the api container by service name.

For the browser-side `fetch()` (when the user's browser hits webui:3000 then needs to call api:8000), browser CAN'T reach `http://api:8000` — that's a Docker network name. So either:
- Option A: reverse-proxy the API under `/api/*` via Next.js rewrites
- Option B: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` and have the browser hit the host's exposed 8000 port

Going with Option A: `web/next.config.ts` adds rewrites:
```typescript
async rewrites() {
  return [
    { source: '/api/v6/:path*', destination: `${process.env.INTERNAL_API_URL || 'http://api:8000'}/:path*` },
  ];
},
```

`api.ts` is patched to call `/api/v6/runs` etc., which the Next.js dev/prod server proxies server-side to `http://api:8000/runs`. Browser only ever talks to webui:3000.

**Scope correction:** since this changes `api.ts` (frontend), it MUST be in scope for this PR. Will patch `web/lib/api.ts` to use `/api/v6` prefix.

## P1-006 — Writable GPG homedir

GnuPG needs writable `GNUPGHOME` for agent sockets / trustdb / random_seed.

### Resolution

- Mount `~/.gnupg-polaris:/app/gpg` (writable, NOT `:ro`)
- Set `GNUPGHOME=/app/gpg` in compose env (replaces the implicit `/root/.gnupg`)
- `bootstrap_gpg_demo_key.sh` writes to `${HOME}/.gnupg-polaris` on the host
- Container runs as root by default (no USER directive), so /app/gpg writable as root is fine
- Permissions: `chmod 700 ~/.gnupg-polaris` and `chmod 600` for key files (the bootstrap script enforces this)

## P2 — accepted with corrections

- **healthcheck on webui**: replacing curl with `wget --spider` (busybox built-in on alpine) or `node -e "fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1))"`. Going with `wget --spider http://localhost:3000 || exit 1` (alpine has busybox wget).
- **preflight redis ping**: using redis-py (`python -c "import redis; redis.from_url(...).ping()"`) instead of `redis-cli` so we don't add redis-tools.
- **idempotent bootstrap_gpg_demo_key.sh**: keys off stable UID `POLARIS Carney Demo <signing@polaris.local>`; checks `gpg --list-keys "POLARIS Carney Demo"` for existence; exports public key to `outputs/polaris_demo_pubkey.asc` (idempotent overwrite is fine — same key = same export).

## Updated scope (delta from iter 1)

ADD:
- `scripts/v6_init_broker.py` (P1-001 broker init helper)
- `web/lib/api.ts` patch (P1-005 — change BACKEND_URL fetch baseUrl + introduce `/api/v6` prefix usage)
- `web/next.config.ts` patch (P1-004 standalone + P1-005 rewrites)

CHANGE:
- `Dockerfile.v6` installs both `requirements.txt` + `requirements-v6.txt` (P1-002)
- `docker-compose.v6.yml` uses `env_file: .env` (P1-003) + writable GPG homedir at `/app/gpg` (P1-006)
- `web/Dockerfile` uses `NEXT_PUBLIC_BACKEND_URL` not `NEXT_PUBLIC_API_URL` (P1-005)

## Direct questions iter 2

1. The 6 P1 resolutions as described — APPROVE'd?
2. Next.js rewrites `/api/v6/*` → `http://api:8000/*` (option A) chosen over host-port-exposure (option B) for browser→backend traffic — APPROVE'd?
3. `web/lib/api.ts` patch IS in scope for this PR (since otherwise the browser can't reach the API container) — APPROVE'd?
4. Anything else blocking iter-2 APPROVE?

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
