HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 iter 2 — P1 deploy-path resolution + P2 confirmations

Iter 1 decisions (you APPROVE'd these): sovereignty (c) / AWS ca-central-1 / static_accounts / concurrency 1 / 7-day phasing. All carry forward.

## P1 from iter 1 — VERIFIED REAL, RESOLUTION PLANNED

You wrote:
> "Demo-path blocker: Docker serve starts scripts.live_server:app, while F-snowball graph endpoint/page are in polaris_v6/web. Current compose does not deploy the Next web app and live_server does not mount /api/runs/{run_id}/graph."

I verified by reading code:

| File | What it is | F-snowball mount? |
|---|---|---|
| `scripts/live_server.py:1379` `app = FastAPI(...)` | Older "Live Monitor" FastAPI. Includes `auth_router`, `inspector_router`. | **NO graph_router** |
| `src/polaris_v6/api/app.py:64` `create_app()` | Newer v6 FastAPI. Includes ALL feature routers: health, runs, stream, ambiguity, bundle, scope, upload, charts, followup, compare, memory, templates, intake, disambiguation, **graph (line 165)**, retrieval. | **YES** |
| `web/` | Next.js 16 app (next dev / next build / next start) — talks to `/api/*` endpoints. | Has `/runs/[runId]/graph` page. |
| `web/Dockerfile` | **MISSING.** | — |
| `Dockerfile` (root) | Serves `scripts/live_server.py` via `docker_entrypoint.sh` CMD `serve`. | — |
| `docker-compose.yml` | `web` service builds root Dockerfile (= live_server). `chromadb` service. No Next.js service. | — |

**Resolution plan for iter-2 APPROVE**:

1. **Switch Docker root CMD to `polaris_v6.api.app:create_app`** (uvicorn factory mode). This is the canonical FastAPI app that mounts ALL features including F-snowball.
2. **Add `web/Dockerfile`** — multi-stage `node:20-alpine` builder → `next build` → `next start` runtime on port 3000.
3. **Add `webui` service to `docker-compose.yml`** — builds `./web`, env `NEXT_PUBLIC_API_URL=http://api:8000`, depends_on `api` (rename `web` → `api` for clarity), exposes 3000.
4. **Update `docker_entrypoint.sh`** — `serve` subcommand now runs `uvicorn polaris_v6.api.app:create_app --factory --host 0.0.0.0 --port 8000`.
5. **Rename existing `web` service in docker-compose to `api`** (avoid name collision; current `web` is misleading since it's FastAPI not web UI).
6. **Mount `chromadb` env into `api` service** (`CHROMA_HOST=chromadb`, `CHROMA_PORT=8000`).
7. **Verify import path**: `polaris_v6.api.app` requires `PYTHONPATH=/app/src`. Dockerfile already sets WORKDIR /app and COPY src/ src/, but PYTHONPATH may need explicit env. Confirm in iter-2 review.

**P1 follow-up sub-issue**: I-carney-005 (Demo-path feature parity) becomes the work item to land this fix. Owner: Claude. Brief + diff Codex-reviewed before merge.

## P2 confirmations / resolutions

### P2.1 — Sovereignty disclosure (your iter-1 point)
> "Do not claim full sovereignty. Under (c), foreign API egress is intentional and must be disclosed."

**Resolution in deploy**: a new public footer line + `/api/transparency` endpoint:

```
"Canadian-hosted public-policy research system. Inference services
(OpenRouter, Serper, Semantic Scholar) reside outside Canada. No
personal health information, no client-confidential documents are
sent to external services. See /transparency for full data-flow."
```

Plus a `docs/transparency.md` page rendered at `/transparency` listing each external API + what data crosses the border. This goes in I-carney-003 (Sovereignty posture + egress controls).

### P2.2 — Concurrency = 1 active research run
> "Concurrency is 1 active research run. Any claim of multiple active staff-launched research runs needs new queue/workflow verification."

**Confirmed**: `MAX_CONCURRENT_RESEARCH=1` in session_manager.py is the production default. Demo posture: 1 active research run at a time + N viewers reading existing results. The `static_accounts` auth model + session queue handle this: subsequent submissions go to `status: queued` until current run completes. This will be in I-carney-006 (Load / observability / rehearsal gate) — 1 concurrent + 10 viewers tested via Playwright.

If Carney's office wants N concurrent runs, that's a post-demo sub-issue requiring Dramatiq queue + worker pool sizing (substrate already exists per #118 v6 Phase 0 Task 0.5).

### P2.3 — Observability not unified
> "Observability is not fully unified on Docker serve; verify live_server metrics/log path, not only v6 OTEL."

**Resolution**: Switching root Docker to `polaris_v6.api.app` (per P1 fix) consolidates onto the v6 OTEL stack (already pinned per #123 v6 Phase 0 Task 0.10 — OpenTelemetry GenAI semconv pinned). Single observability path. CloudWatch + AWS X-Ray ingestion is the AWS-side surface. Will be in I-carney-006.

### P3 cosmetic — terminology
> "Use 'Canadian-hosted public-policy research' wording instead of broad 'sovereign Canadian AI'."

**Adopted across all demo materials** — runbook, transparency page, public footer, demo script all use "Canadian-hosted public-policy research." No "sovereign" claim. Will be in I-carney-007 (Runbook + fallback package).

## Final sub-issue plan (your iter-1 list confirmed + ordered)

| ID | Title | Days | Owner |
|---|---|---|---|
| I-carney-002 | AWS Canada deploy (EC2/EBS/ALB/ACM/DNS/backup) | 1 | Claude infra |
| I-carney-003 | Sovereignty posture + egress controls (transparency endpoint + OpenRouter ZDR config) | 1-2 | Claude security |
| I-carney-004 | Demo auth + RBAC (static_accounts, admin/operator/user, password rotation) | 2 | Claude backend |
| I-carney-005 | Demo-path feature parity (P1 fix: switch deploy to polaris_v6.api + web Dockerfile + compose) | 1-3 | Claude fullstack |
| I-carney-006 | Load + observability + rehearsal gate (5 canonical Carney questions §-1.1 line-by-line audit) | 3-5 | Claude QA |
| I-carney-007 | Runbook + fallback (laptop tunnel, demo script, monitoring alerts) | 6 | Claude ops |

GH#462 stays as umbrella. Sub-issues I-carney-002 through I-carney-007 opened immediately after this APPROVE.

## Direct questions for iter 2

1. P1 resolution plan above (switch root Docker to `polaris_v6.api.app` + add web Dockerfile + compose webui service) — APPROVE'd?
2. P2.1 transparency disclosure wording — APPROVE'd as-is or revise?
3. P2.2 concurrency=1 + queue posture — APPROVE'd as the demo bar?
4. Anything else blocking before I open the 6 sub-issues + start I-carney-002?

## Smoke verification I will do BEFORE opening sub-issue 002

Locally (no AWS yet):
- `docker compose build --no-cache` against new compose
- `docker compose up -d api webui chromadb`
- `curl http://localhost:8000/api/health` returns 200
- `curl http://localhost:3000` returns Next.js homepage
- `curl http://localhost:8000/api/runs/<test_run_id>/graph` returns the F-snowball payload (verifies P1 fix landed)
- `curl http://localhost:3000/runs/<test_run_id>/graph` returns the graph page HTML
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
