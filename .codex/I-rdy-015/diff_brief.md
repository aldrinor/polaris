# Codex DIFF review — I-rdy-015 (#511): Caddy reverse proxy + TLS

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

**This is iter 1 of 5.** DIFF review (code correctness vs the APPROVE'd brief).

## §1. What to review

Diff: `.codex/I-rdy-015/codex_diff.patch`
(canonical-diff-sha256 trailer = `e9b3ec71dd88178dc7aa26d789d0cd6998ab0d2d0d236fae64c6636261a876ee`).
APPROVE'd brief: `.codex/I-rdy-015/brief.md` (Codex APPROVE iter 2,
`.codex/I-rdy-015/codex_brief_verdict.txt`). 5 files, +106 / −44,
config + deploy-script only — no application code, no unit tests.

## §2. Implementation summary (verify against the diff)

- **`Caddyfile`** (NEW) — `{$POLARIS_DOMAIN}` site; ACME CA pinned to
  Let's Encrypt; `handle /health → api:8000`; default `handle →
  webui:3000` (`flush_interval -1`); `email` env-sub with local default.
- **`docker-compose.v6.yml`** — new `caddy` service (only host-published
  ports 80/443; Caddyfile + caddy_data/caddy_config volumes; env_file
  .env; depends_on webui); `api` + `webui` lose host `ports:` → `expose`.
- **`infra/vexxhost/provision.sh`** — host Caddy removed (apt repo +
  install + host Caddyfile + `systemctl reload`); readiness loop → Docker-
  network probes (`docker compose exec` into api / via caddy → webui).
- **`infra/vexxhost/.env.example`** — `POLARIS_DOMAIN` + `POLARIS_ACME_EMAIL`
  replace the obsolete `POLARIS_API_PORT`/`POLARIS_WEB_PORT`.
- **`.env.example`** (root) — `POLARIS_DOMAIN=localhost` + `POLARIS_ACME_EMAIL=`.

## §3. Suggested focus (Red-Team checklist)

1. **Port closure** — after removing `api`/`webui` `ports:`, is anything
   still publishing :8000/:3000 to the host? (`caddy` is the only `ports:`.)
2. **Caddy → upstreams** — `reverse_proxy api:8000` / `webui:3000` resolve
   over the Docker network (compose service names); `caddy depends_on
   webui`. `/health` routed to api, not Next.
3. **provision.sh** — no dangling reference to host Caddy / removed host
   ports; the readiness probes are correct (`exec -T`); §8 no longer
   writes a host Caddyfile or reloads a host service; `set -eo pipefail`
   still holds (the `exec` probes are inside the `if`, failures don't
   abort the loop).
4. **caddy_data persistence** — the volume is declared so the LE cert +
   ACME account survive restarts.
5. **env contract** — `Caddyfile {$POLARIS_DOMAIN}/{$POLARIS_ACME_EMAIL}`
   match `provision.sh` + both `.env.example` files; the compose `caddy`
   service `env_file: .env` feeds them.
6. No secret material in the diff; no `git add -A` collateral; legacy
   `docker-compose.yml` untouched.

## §4. Evidence

- `docker compose -f docker-compose.v6.yml config` — exit 0.
- `bash -n infra/vexxhost/provision.sh` — exit 0.
- `caddy validate` — no caddy binary on this host; Caddyfile by inspection.
- Live Let's Encrypt issuance is deploy-time (real domain + public VM).

## §5. Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
