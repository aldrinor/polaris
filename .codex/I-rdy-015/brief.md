# Codex brief — I-rdy-015 (#511): TLS/HTTPS for polarisresearch.ca (Caddy reverse proxy)

## §0. HARD ITERATION CAP (verbatim, CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**This is iter 2 of 5.** BRIEF review (acceptance-criteria correctness), not a diff review.

## §0.5 Changes since iter 1

iter 1 = REQUEST_CHANGES, 2 P1 + 3 P2. All verified against the codebase
this fire and addressed:
- **P1-001 (provision.sh):** verified — `infra/vexxhost/provision.sh`
  installs a **host** Caddy (`apt-get install caddy`, lines 72-80), polls
  `localhost:8000`/`localhost:3000` (lines 147-148), writes a host
  `/etc/caddy/Caddyfile` + `systemctl reload caddy` (lines 162-187). It is
  now **in scope** — §3.3.
- **P1-002 (`/health`):** verified — the demo smoke curls
  `https://.../health`; `web/next.config.ts` rewrites only `/api/v6/*` +
  `/transparency*`, so `/health` would hit Next. The Caddyfile now has an
  explicit `handle /health → api:8000` route — §3.1.
- **P2-001 (env naming):** `provision.sh` already uses `POLARIS_DOMAIN` +
  `POLARIS_ACME_EMAIL`. The Caddyfile + compose now use those exact names
  (not `ACME_EMAIL`). `infra/vexxhost/.env.example` is now in scope — §3.4.
- **P2-002 / P2-003:** Codex confirmed — proceed before #494; compose
  port-removal alone satisfies "direct ports closed". No change needed.

## §1. Issue

**GH #511 — I-rdy-015, Workstream L.** Body verbatim:
> Workstream L (parallel, after Phase 2). Caddy reverse proxy; Let's Encrypt cert; close direct :8000 and :3000 public exposure.
> Acceptance: https://polarisresearch.ca serves the app; direct ports closed; Codex APPROVE.
> Depends on: I-bug-113 (#494).

## §2. Grounded current state (verified by Read this fire)

- **`docker-compose.v6.yml`** = the v6 stack (`redis` + `api` + `worker` +
  `webui`). `api` publishes `${POLARIS_API_PORT:-8000}:8000`; `webui`
  publishes `${POLARIS_WEB_PORT:-3000}:3000` — both host/public-exposed.
  No `caddy` service. (`docker-compose.yml` = frozen legacy pipeline-B, out
  of scope.)
- **`infra/vexxhost/provision.sh`** (the live deploy script) currently
  *owns* Caddy on the host: installs the `caddy` apt package, after
  `docker compose up` polls `localhost:8000/health` + `localhost:3000/`,
  then writes `/etc/caddy/Caddyfile` (already includes a
  `handle /health → localhost:8000` route + `flush_interval -1` for SSE)
  and `systemctl reload caddy`. This collides with a compose-managed Caddy.
- **`infra/vexxhost/.env.example`** (the deploy `.env` template, copied to
  `/root/.env`) has a "Compose port mapping" section with
  `POLARIS_API_PORT=8000` + `POLARIS_WEB_PORT=3000`, and **no**
  `POLARIS_DOMAIN` / `POLARIS_ACME_EMAIL`.
- Root `.env.example` has neither domain nor ACME email.
- `web/next.config.ts` rewrites `/api/v6/*` + `/transparency*` → `api:8000`;
  it does NOT rewrite `/health`.
- Documented topology (`infra/vexxhost/README.md` §Architecture):
  `Internet → 443 → Caddy (TLS+LE) → webui:3000 → /api/v6 rewrite → api:8000`.

## §3. Proposed approach

### 3.1 New `Caddyfile` (repo root)

```
{
	email {$POLARIS_ACME_EMAIL}
}

{$POLARIS_DOMAIN} {
	encode zstd gzip

	# /health probes FastAPI directly — Next does NOT rewrite /health
	# (only /api/v6/* and /transparency/*). Codex iter-1 P1-002.
	handle /health {
		reverse_proxy api:8000
	}

	# Everything else → webui; its Next server rewrites /api/v6/* and
	# /transparency/* to api:8000 server-side. flush_interval -1 keeps
	# the SSE stream (/api/v6/stream/*) unbuffered.
	handle {
		reverse_proxy webui:3000 {
			flush_interval -1
		}
	}
}
```

- Caddy v2 auto-provisions a Let's Encrypt cert for `{$POLARIS_DOMAIN}`
  (ACME HTTP-01 on :80 → serves :443). `{$POLARIS_ACME_EMAIL}` =
  ACME account email. Both env-substituted — no hardcoded domain/email
  (LAW VI), names matching `provision.sh` (Codex iter-1 P2-001).

### 3.2 `docker-compose.v6.yml`

- **New `caddy` service:** `image: caddy:2-alpine`; `ports: ["80:80",
  "443:443"]` (the ONLY host-published ports after this change);
  `volumes: ./Caddyfile:/etc/caddy/Caddyfile:ro`, `caddy_data:/data`
  (cert + ACME account — MUST persist or restarts re-request the cert and
  risk the LE rate limit), `caddy_config:/config`; `env_file: [.env]`
  (so the container sees `POLARIS_DOMAIN` + `POLARIS_ACME_EMAIL`);
  `depends_on: [webui]`; `restart: unless-stopped`.
- **`api`:** remove the `ports:` block; add `expose: ["8000"]`.
- **`webui`:** remove the `ports:` block; add `expose: ["3000"]`.
- **New named volumes:** `caddy_data`, `caddy_config`.

### 3.3 `infra/vexxhost/provision.sh` (Codex iter-1 P1-001)

Caddy moves from a host package to a compose container:
- **§1 (apt):** remove the Caddy Cloudsmith apt-repo lines + `apt-get
  install caddy`. Keep `docker.io`, `docker-compose-v2`, `git`, `gnupg`,
  `curl`, `jq`, etc.
- **§7 (readiness):** the `curl localhost:8000/health` +
  `curl localhost:3000/` loop no longer works (host ports removed).
  Replace with Docker-network checks: `docker compose -f
  docker-compose.v6.yml exec -T api curl -fsS http://localhost:8000/health`
  (api self-check inside its container) AND `docker compose -f
  docker-compose.v6.yml exec -T caddy wget -qO- http://webui:3000/`
  (webui over the Docker network; the `caddy:2-alpine` image ships
  `wget`). Same 60×5s loop + fail-loud-on-timeout behaviour retained.
- **§8 (Caddy):** remove the `/etc/caddy/Caddyfile` heredoc, `caddy fmt`,
  `systemctl reload caddy`, and the `/var/log/caddy` mkdir. The compose
  `caddy` service now owns `:80/:443` and uses the repo `Caddyfile`
  (Caddy logs to stdout → `docker compose logs caddy`). Replace §8 with a
  short echo: Caddy is compose-managed and auto-provisions LE for
  `$POLARIS_DOMAIN`. The final verify echo (`curl https://$POLARIS_DOMAIN/
  health`) stays.

### 3.4 `.env.example` files

- **`infra/vexxhost/.env.example`** (deploy template → `/root/.env` →
  `/opt/polaris/.env`): replace the now-obsolete "Compose port mapping"
  section (`POLARIS_API_PORT` / `POLARIS_WEB_PORT` — unreferenced once the
  host `ports:` blocks are gone) with a "Caddy TLS / reverse proxy"
  section: `POLARIS_DOMAIN=polarisresearch.ca` and
  `POLARIS_ACME_EMAIL=REPLACE_ME` (with a comment that this is the Let's
  Encrypt account email).
- **Root `.env.example`** (dev template): add `POLARIS_DOMAIN=localhost`
  + `POLARIS_ACME_EMAIL=` — for a local `docker compose -f
  docker-compose.v6.yml up`, `localhost` makes Caddy use its internal CA
  (no ACME, no public domain needed); deploy overrides to the real domain.

### 3.5 Verification (offline)

- `docker compose -f docker-compose.v6.yml config` — validates the merged
  compose (caddy service + volumes; no api/webui host `ports:`).
- `bash -n infra/vexxhost/provision.sh` — shell syntax check.
- `Caddyfile` — `caddy validate --adapter caddyfile --config Caddyfile` if
  a caddy binary is present; else inspection (standard Caddy v2 syntax).
- Live Let's Encrypt issuance needs the real domain + a public VM — that
  is deploy-time (dress-rehearsal G1 / the runbook). #511 ships the config;
  this is the honest boundary.

## §4. Deliverables + LOC

| File | Change | ~LOC |
|---|---|---|
| `Caddyfile` | NEW | +16 |
| `docker-compose.v6.yml` | caddy service + volumes; drop api/webui host ports | ~+28 / −4 |
| `infra/vexxhost/provision.sh` | drop host-Caddy install + §8 host Caddyfile + reload; Docker-network readiness checks | ~+12 / −32 |
| `infra/vexxhost/.env.example` | Caddy TLS section replaces obsolete port section | ~+6 / −4 |
| `.env.example` (root) | `POLARIS_DOMAIN` + `POLARIS_ACME_EMAIL` | ~+3 |

**Total ≈ 110 LOC, config + deploy-script only, no application code, no
unit tests** (verification = `docker compose config` + `bash -n` +
`caddy validate`). Well under the 200-LOC cap.

## §5. Files I have ALSO checked and they are clean

- `docker-compose.yml` (legacy pipeline-B) — untouched, out of scope.
- `Dockerfile.v6` — not modified (#494 dependency is soft, confirmed iter-1).
- `web/next.config.ts` — the `/api/v6` + `/transparency` rewrites mean the
  Caddyfile needs only the `/health` special-case + a default `webui:3000`.
- `scripts/egress_lockdown.sh` / `egress_runtime_tighten.sh` — egress
  iptables only; no ingress port allowlist to amend (Codex iter-1 P2-003).
- `infra/vexxhost/README.md` — already documents the Caddy topology; doc
  text is consistent (a wording refresh is optional — flag if wanted).

## §6. Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

All iter-1 findings addressed: provision.sh in scope (§3.3), `/health`
route (§3.1), env-name consistency `POLARIS_DOMAIN`/`POLARIS_ACME_EMAIL`
(§3.1/§3.4). No open decisions.
