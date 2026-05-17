# Claude architect audit — I-rdy-015 (#511)

**Issue:** Workstream L — Caddy reverse proxy + Let's Encrypt TLS for
polarisresearch.ca; close direct :8000/:3000 public exposure.
**Branch:** `bot/I-rdy-015-caddy-tls` off `polaris`.
**Canonical diff sha256:** `e9b3ec71dd88178dc7aa26d789d0cd6998ab0d2d0d236fae64c6636261a876ee`
**Brief:** Codex APPROVE iter 2 (`.codex/I-rdy-015/codex_brief_verdict.txt`).
Config-only; no application code; no unit-test surface.

## Diff-vs-brief verification (file by file)

### `Caddyfile` (NEW, +41)
- Global block: `email {$POLARIS_ACME_EMAIL:internal@localhost}` (env-sub
  with a harmless local default — Codex iter-2 P2-002); `acme_ca` pinned to
  `https://acme-v02.api.letsencrypt.org/directory` (the issue specifies a
  Let's Encrypt cert — Codex iter-2 P2-001).
- `{$POLARIS_DOMAIN}` site: `encode zstd gzip`; `handle /health →
  api:8000` (Codex iter-1 P1-002 — Next does not rewrite `/health`);
  default `handle → webui:3000` with `flush_interval -1` (SSE keepalive,
  carried from the prior host Caddyfile). **Verified.**

### `docker-compose.v6.yml` (+41 / −4 net per `--stat`; +28/−4 logical)
- New `caddy` service: `caddy:2-alpine`, `ports: 80:80 + 443:443` (the
  only host-published ports), `Caddyfile` ro-mount + `caddy_data` +
  `caddy_config` volumes (`caddy_data` persists the cert/ACME account —
  re-request avoidance), `env_file: .env`, `depends_on: webui`.
- `api`: `ports:` block removed → `expose: ["8000"]` (Docker-network only).
- `webui`: `ports:` block removed → `expose: ["3000"]`.
- New named volumes `caddy_data`, `caddy_config`.
- **Verified** by `docker compose -f docker-compose.v6.yml config` (exit 0).

### `infra/vexxhost/provision.sh` (+? / −? net; host Caddy removed)
- §1: removed the Caddy Cloudsmith apt-repo + `apt-get install caddy`
  (Caddy is now a compose container) — Codex iter-1 P1-001.
- §7: the readiness loop's `curl localhost:8000/health` +
  `curl localhost:3000/` (host ports — now removed) replaced with
  Docker-network probes: `docker compose exec -T api curl ...localhost:8000
  /health` (api self-check) + `docker compose exec -T caddy wget ...
  webui:3000` (webui over the network; `caddy:2-alpine` ships `wget`).
  The 60×5s loop + fail-loud-on-timeout retained.
- §8: removed the host `/etc/caddy/Caddyfile` heredoc + `caddy fmt` +
  `systemctl reload caddy` + `/var/log/caddy`; replaced with an echo —
  the compose `caddy` service owns TLS. **Verified** by `bash -n` (exit 0).

### `infra/vexxhost/.env.example` (+? / −?)
- The obsolete "Compose port mapping" section (`POLARIS_API_PORT` /
  `POLARIS_WEB_PORT` — unreferenced once the host `ports:` are gone) is
  replaced by a "Caddy TLS / reverse proxy" section with
  `POLARIS_DOMAIN=polarisresearch.ca` + `POLARIS_ACME_EMAIL=REPLACE_ME`.

### `.env.example` (root, +8)
- `POLARIS_DOMAIN=localhost` + `POLARIS_ACME_EMAIL=` added under
  DOCKER/DEPLOYMENT — `localhost` makes Caddy use its internal CA for a
  local `docker compose -f docker-compose.v6.yml up` (no public domain /
  ACME). Codex iter-2 P2-001/002 naming consistency.

## Verification evidence
- `docker compose -f docker-compose.v6.yml config` — exit 0 (caddy service
  + volumes resolve; no api/webui host `ports:`).
- `bash -n infra/vexxhost/provision.sh` — exit 0.
- `caddy validate` — no caddy binary on this host; Caddyfile validated by
  inspection (standard Caddy v2 syntax: global block + one site block,
  two `handle` routes). Live Let's Encrypt issuance is deploy-time
  (real domain + public VM) — the honest boundary.

## §-1.1 note
Not a clinical-content change — no report claims, citations, or evidence
spans. Infrastructure config; the clinical line-by-line audit standard
does not apply.

## Acceptance
"`https://polarisresearch.ca` serves the app" — Caddy site block on
`{$POLARIS_DOMAIN}` proxies to the stack; cert auto-provisions at deploy.
"Direct ports closed" — `api`/`webui` host `ports:` removed; Docker never
binds :8000/:3000 to the host. Both met at the config layer; runtime
proof is deploy-time. Recommend APPROVE.
