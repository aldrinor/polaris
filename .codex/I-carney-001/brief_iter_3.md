HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 iter 3 — Redis/worker + same-origin proxy + all iter-2 P2 fixes

Iter 1 + iter 2 decisions carry forward. Iter 2 P1s + P2s addressed below with code-verified detail.

## P1 from iter 2 → resolution + verification

### P1.1 — Browser-reachable backend URL (NEXT_PUBLIC_BACKEND_URL + Docker-internal hostname)

You wrote:
> "web/lib/api.ts reads NEXT_PUBLIC_BACKEND_URL, but the plan sets NEXT_PUBLIC_API_URL=http://api:8000. Also, `api` is Docker-internal and not resolvable by a user's browser."

**Code-verified**: `web/lib/api.ts:9-10` reads `process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000"`. Confirmed.

**Resolution: same-origin proxy via Next.js rewrites**. Browser only ever hits the Next.js origin; Next proxies `/api/*` and `/runs/*`, `/upload/*`, etc. to the FastAPI service over Docker-internal network.

Plan code change in I-carney-005:

```ts
// web/next.config.ts
const nextConfig = {
  async rewrites() {
    return [
      { source: "/runs/:path*", destination: `${process.env.INTERNAL_API_URL}/runs/:path*` },
      { source: "/upload/:path*", destination: `${process.env.INTERNAL_API_URL}/upload/:path*` },
      { source: "/ambiguity", destination: `${process.env.INTERNAL_API_URL}/ambiguity` },
      { source: "/scope/:path*", destination: `${process.env.INTERNAL_API_URL}/scope/:path*` },
      { source: "/templates/:path*", destination: `${process.env.INTERNAL_API_URL}/templates/:path*` },
      { source: "/api/:path*", destination: `${process.env.INTERNAL_API_URL}/api/:path*` },
      { source: "/health", destination: `${process.env.INTERNAL_API_URL}/health` },
    ];
  },
};
```

`INTERNAL_API_URL=http://api:8000` is **server-side-only** (Node.js fetch inside Next.js rewrite engine resolves Docker DNS). The browser sees only same-origin paths.

`NEXT_PUBLIC_BACKEND_URL` env in `webui` service: **leave empty/unset** so `web/lib/api.ts` falls through to `""` (relative URLs) — actually need to set it to `""` to override the dev default `"http://127.0.0.1:8000"`. Will update `web/lib/api.ts` default to `""` (same-origin) so blank env works.

P3 from iter 2 (terminology): I will NOT introduce `NEXT_PUBLIC_API_URL`. Only `NEXT_PUBLIC_BACKEND_URL` (now defaults to same-origin "") + server-side `INTERNAL_API_URL`.

### P1.2 — Redis + Dramatiq worker missing

You wrote:
> "src/polaris_v6/api/runs.py enqueues Dramatiq to Redis localhost:6379 by default; proposed compose has no redis service, no POLARIS_V6_REDIS_URL, and no worker service. POST /runs will fail or stay queued."

**Code-verified**:
- `src/polaris_v6/queue/broker.py:48` reads `POLARIS_V6_REDIS_URL` env, defaults `redis://localhost:6379/0`
- `src/polaris_v6/queue/broker.py:51` `dramatiq.set_broker(broker)` — module-level on import
- `src/polaris_v6/queue/actors.py` defines `enqueue_research_run` actor; comment confirms import-time broker setup is required
- `src/polaris_v6/api/runs.py:35` `enqueue_research_run.send(...)` — needs broker connected

**Resolution: add `redis` + `worker` compose services + POLARIS_V6_REDIS_URL env on api + worker.**

```yaml
# docker-compose.yml additions
services:
  api:
    # renamed from "web"; serves polaris_v6.api.app:create_app
    build: .
    command: ["uvicorn", "polaris_v6.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
    environment:
      - POLARIS_V6_REDIS_URL=redis://redis:6379/0
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
      - PYTHONPATH=/app/src
    depends_on: [redis, chromadb]

  worker:
    build: .
    command: ["python", "-m", "dramatiq", "polaris_v6.queue.actors", "--processes", "1", "--threads", "2"]
    environment:
      - POLARIS_V6_REDIS_URL=redis://redis:6379/0
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
      - PYTHONPATH=/app/src
      - POLARIS_V6_MAX_CONCURRENT_RUNS=1  # demo cap
    depends_on: [redis, chromadb]

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

  webui:
    build: ./web
    command: ["npm", "start"]
    ports:
      - "${POLARIS_WEB_PORT:-3000}:3000"
    environment:
      - INTERNAL_API_URL=http://api:8000
      - NEXT_PUBLIC_BACKEND_URL=
    depends_on: [api]

volumes:
  chroma_data: {}
  redis_data: {}
```

Worker `--processes 1 --threads 2` matches concurrency=1 active run. To enforce more strictly, `POLARIS_V6_MAX_CONCURRENT_RUNS=1` env will be honored by the queue (Codex P2.2 finding — I will verify the env is actually consulted in the queue code; if not, that's a sub-issue to fix in I-carney-005 before APPROVE).

## P2 from iter 2 → resolutions

### P2.1 — Smoke `/health` not `/api/health`

**Code-verified**: `src/polaris_v6/api/health.py:16` `@router.get("/health", ...)` — mounted root, no prefix. Confirmed. Smoke commands corrected:

- `curl http://localhost:8000/health` returns `HealthResponse`
- `curl http://localhost:3000/health` returns the same (via Next rewrite)

### P2.2 — POLARIS_GPG_KEY_ID GPGSigner startup

**Code-verified**: `src/polaris_v6/api/app.py:132` checks `os.environ.get("POLARIS_GPG_KEY_ID", "").strip()` — empty string skips signer init. Demo posture:

```
POLARIS_GPG_KEY_ID=    # left unset; audit bundle export will be unsigned
```

`docs/transparency.md` notes: "Audit bundles in this demo deployment are not GPG-signed. Sign-on-export is available in the on-prem install. Signing keys would be operator-managed, never co-located with running services."

Alternative if you want signed bundles: install `gnupg` in Dockerfile (`apt-get install gnupg`), mount a key via Docker secret. Adds ~20MB image + key-rotation runbook. **Pick: unsigned for demo, document the upgrade path.** Confirm APPROVE.

### P2.3 — Concurrency=1 enforced on v6 queue, not just session_manager.py

Worker command `--processes 1 --threads 2` is a soft cap (Dramatiq concurrency). For hard cap on simultaneously-running research:

```python
# Verified pattern: src/polaris_v6/queue/middleware/throttle.py exists per actors.py docstring
# "high-retry-rate degradation → throttle middleware"
```

I will inspect that middleware in I-carney-005 brief and confirm it enforces the `MAX_CONCURRENT_RUNS` ceiling. If it only rate-limits retries, I'll add a single-actor mutex via Redis `SET ... NX EX` lock keyed by `research_run` in the actor body. Either way, the runbook (I-carney-007) will state: "Demo deployment guarantees at most 1 concurrent research run; further submissions queue."

## P2.4 — Transparency wording accepted (you already APPROVE'd)
## P3 cosmetic — NEXT_PUBLIC_BACKEND_URL consistency (already addressed P1.1 above)

## AWS deployment topology (refined)

Following your iter-1 AWS pick, the single-instance topology fitting concurrency=1:

```
Internet → Route 53 polaris-demo.example.ca (CNAME)
        → ACM TLS cert (issued in ca-central-1)
        → ALB ca-central-1 (single target group)
        → EC2 m7i-flex.4xlarge (16 vCPU, 64GB RAM, gp3 500GB)
            └─ docker compose up:
                ├─ webui     :3000  (Next.js)
                ├─ api       :8000  (FastAPI polaris_v6)
                ├─ worker           (Dramatiq)
                ├─ redis     :6379
                └─ chromadb  :8001
```

ALB → EC2 instance security group allows :3000 only from ALB SG. EC2 hardening: SSH via SSM Session Manager (no public 22), CloudWatch logs agent, EBS encrypted, IMDSv2-required.

CloudWatch consolidates app logs + OS logs. The v6 OTEL stack (pinned per #123) sends traces — for demo, send to AWS X-Ray via the AWS Distro for OpenTelemetry collector running as a sidecar process on the EC2 instance.

Backup: EBS snapshot daily (data/outputs/state volumes). Retention 7 days for demo.

DNS: `polaris-demo.example.ca` (user-owned domain, please confirm domain available). If user has no domain, use AWS-provided `*.elb.ca-central-1.amazonaws.com` URL — works, less polished for Carney's office.

## Sub-issues (your iter-1 list, ordered + refined)

| ID  | GH# | Title | Days | Owner |
|---|---|---|---|---|
| I-carney-002 | TBD | AWS Canada infra (VPC/EC2/ALB/ACM/SG/SSM/EBS snapshots/Route 53) | 1 | Claude infra |
| I-carney-003 | TBD | Sovereignty posture + transparency endpoint + egress audit | 1-2 | Claude security |
| I-carney-004 | TBD | Demo auth (static_accounts, RBAC, password rotation runbook) | 2 | Claude backend |
| I-carney-005 | TBD | Demo-path feature parity (P1.1 + P1.2 fixes: switch root Docker to polaris_v6.api, add web/Dockerfile, add redis/worker/webui compose services, Next rewrites, concurrency enforcement audit) | 1-3 | Claude fullstack |
| I-carney-006 | TBD | Load + observability + 5 canonical Carney question rehearsal (line-by-line §-1.1 audit) | 3-5 | Claude QA |
| I-carney-007 | TBD | Runbook + transparency.md + fallback laptop + demo script | 6 | Claude ops |

## Direct questions for iter 3

1. Same-origin Next rewrites strategy (vs direct `NEXT_PUBLIC_BACKEND_URL` to public API origin) — APPROVE'd?
2. Single-EC2 docker-compose topology (vs ECS/Fargate split) for concurrency=1 demo — APPROVE'd?
3. `POLARIS_GPG_KEY_ID` unset for demo (audit bundles unsigned, documented in transparency) — APPROVE'd or want gnupg+key-mount?
4. Worker `--processes 1 --threads 2` + Redis-mutex on actor body for hard concurrency=1 cap — APPROVE'd?
5. AWS X-Ray via ADOT sidecar for observability — APPROVE'd or use CloudWatch only?
6. Anything else blocking before I open sub-issues I-carney-002 through I-carney-007 and start I-carney-005 (the deploy-path fix is the highest-leverage week-1 work item)?

## Smoke verification I will run BEFORE opening sub-issue 002

Locally (no AWS yet):
- Pull redis:7-alpine + verify image works
- `docker compose build --no-cache` against new compose
- `docker compose up -d redis chromadb api worker webui`
- `curl http://localhost:8000/health` returns 200 (api direct)
- `curl http://localhost:3000/health` returns 200 (via Next rewrite)
- `curl -X POST http://localhost:8000/runs -d '...'` returns 202 with run_id
- Worker logs show actor pickup; run_store status progresses queued → running → completed
- `curl http://localhost:8000/api/runs/<run_id>/graph` returns F-snowball payload
- Browser visits `http://localhost:3000/runs/<run_id>/graph` → cytoscape canvas renders
- `pytest tests/polaris_graph/api/test_graph_route.py` PASS

Only after local smoke passes do I provision AWS.

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
