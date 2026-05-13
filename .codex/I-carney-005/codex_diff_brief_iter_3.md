HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 diff iter 3 — INTERNAL_API_URL as build ARG

## Continuing P1-B from iter 2 (resolved)

Codex iter-2: Next.js evaluates `rewrites()` destinations during `next build` and bakes them into the routes manifest, so `INTERNAL_API_URL` must be a build arg, not a runtime env. With only-runtime env, the standalone image bakes the `localhost:8000` fallback and `/api/v6/*` proxies to webui itself (broken).

### Fix

**web/Dockerfile builder stage:**
```dockerfile
ARG INTERNAL_API_URL=http://api:8000
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
...
RUN npm run build
```

`ARG` makes the value available during `npm run build`; the `ENV` line keeps `next.config.ts:process.env.INTERNAL_API_URL` populated for the build's `rewrites()` evaluation. The destination `http://api:8000` is then baked into the standalone routes manifest.

**docker-compose.v6.yml webui service:**
```yaml
webui:
  build:
    context: ./web
    dockerfile: Dockerfile
    args:
      INTERNAL_API_URL: http://api:8000
  environment:
    NODE_ENV: production
```

`INTERNAL_API_URL` is passed as build arg (NOT runtime env). It's not prefixed `NEXT_PUBLIC_*`, so it does NOT leak into the client bundle — only the server-side routes manifest sees it.

`web/lib/api.ts` stays unchanged (`BACKEND_URL = "/api/v6"` — browser-relative).
`web/next.config.ts` stays unchanged (process.env.INTERNAL_API_URL reads the build-time ARG).

### Verification

`docker compose -f docker-compose.v6.yml config --quiet` → exit 0.

Build behavior: when Next.js builds, `process.env.INTERNAL_API_URL=http://api:8000` is set (from ENV), so `rewrites()` returns `{ source: '/api/v6/:path*', destination: 'http://api:8000/:path*' }` and Next bakes this into `.next/routes-manifest.json`. The standalone runner serves with this baked destination.

## Direct questions iter 3

1. INTERNAL_API_URL as ARG+ENV in builder stage, then build arg in compose — APPROVE'd?
2. No client-bundle leak (verified: only NEXT_PUBLIC_* prefix leaks; INTERNAL_API_URL stays server-side) — APPROVE'd?
3. Anything else blocking iter-3 APPROVE?

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
