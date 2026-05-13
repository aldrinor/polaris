HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 diff iter 2 — P1-A + P1-B + P2 GPG resolutions

## P1-A — protobuf conflict (resolved)

`requirements.txt` pins `protobuf<5.0.0` (because google-generativeai's transitive `google-ai-generativelanguage` requires it). `requirements-v6.txt` pins `protobuf==6.33.6` (OTLP). Pip cannot resolve both.

### Fix (Dockerfile.v6 lines 32-44)

`google-generativeai` is consumed only by `src/llm/gemini_client.py` + `src/utils/atomic_decomposer.py` — both part of the frozen pipeline-C / `src/orchestration/` surface that is NEVER reached from pipeline-A or v6 backend. Verified: `grep -rln "from src.llm\|atomic_decomposer" scripts/ src/polaris_v6 src/polaris_graph` returns nothing.

Dockerfile.v6 now sed-strips `google-generativeai` AND `protobuf<` lines from requirements.txt before install:

```dockerfile
RUN sed -e '/^google-generativeai/d' \
        -e '/^protobuf</d' \
        requirements.txt > /tmp/requirements-v6-pipeline-a.txt && \
    pip install --no-cache-dir -r /tmp/requirements-v6-pipeline-a.txt -r requirements-v6.txt
```

Pipeline-B's existing `Dockerfile` is untouched and continues to install both files unmodified — pipeline-C images can still be built when needed.

## P1-B — client bundle bakes Docker hostname (resolved)

The browser cannot resolve `http://api:8000` (Docker service name). Two fixes:

### Fix 1: web/lib/api.ts now hard-codes `/api/v6`

```typescript
const BACKEND_URL = "/api/v6";
```

All fetch calls become browser-relative. The Next.js rewrite (`web/next.config.ts`) forwards `/api/v6/*` server-side to `${INTERNAL_API_URL}`. NEXT_PUBLIC_BACKEND_URL is no longer consulted at runtime so it cannot be baked into the client bundle by accident.

### Fix 2: web/Dockerfile drops the build arg

`NEXT_PUBLIC_BACKEND_URL` is no longer an `ARG` in `web/Dockerfile`. The builder stage relies on api.ts's static `/api/v6` value. INTERNAL_API_URL is a RUNTIME env (read by `next.config.ts` when serving), set on the `webui` service in compose (NOT baked into the bundle).

### Fix 3: docker-compose.v6.yml drops the build arg

```yaml
webui:
  build:
    context: ./web
    dockerfile: Dockerfile
    # NO args block — INTERNAL_API_URL is runtime-only.
  environment:
    INTERNAL_API_URL: http://api:8000
```

## P2 — preflight GPG hardening (resolved)

`check_gpg(strict=True)` (now the default) treats missing `POLARIS_GPG_KEY_ID` as a HARD failure. Signed bundles are the Carney demo's reason for existing, so a deploy missing the GPG key MUST exit non-zero from preflight.

## Test results

```
tests/v6/test_broker.py + test_broker_init_order.py + test_actors.py: 20 passed
docker compose -f docker-compose.v6.yml config --quiet  # exit 0
```

## Direct questions iter 2

1. The protobuf sed-strip approach (drop google-generativeai + protobuf< from the v6 image only; keep pipeline-B's Dockerfile unchanged) — APPROVE'd? Or want google-generativeai removed from requirements.txt entirely?
2. `BACKEND_URL = "/api/v6"` static in web/lib/api.ts (no env var at runtime) — APPROVE'd?
3. `check_gpg(strict=True)` default — APPROVE'd?
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
