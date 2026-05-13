HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-007 diff iter 2 — 3 P1 resolutions

## P1-1 — sign-off evidence ingestion (resolved)

Runbook §7 now instructs the operator to COPY the brief to a working file, RUN each /health, /transparency, GPG-verify, iptables-list command, and APPEND actual outputs to the working file. The shipped-to-Codex file contains real evidence, not placeholders.

Explicit abort condition: if the evidence file still contains `<your-domain>` placeholders, the operator stops because Codex would otherwise sign off on the template.

## P1-2 — egress lockdown install step (resolved)

Runbook §1b added BETWEEN §1 (deploy) and §2 (smoke test). Operator opens an SSM session, runs `sudo bash /opt/polaris/scripts/egress_lockdown.sh`, and verifies via `iptables -L POLARIS_EGRESS_HOST -n -v` that both chains show DROP rules at the bottom. Without this, `/transparency`'s `enforcement_layer` claim is false.

## P1-3 — fallback laptop env + setup (resolved)

Runbook §5 expanded to a 5-step one-time-setup script that:
- Pulls 7 env vars from Secrets Manager → `.env` (NOT `/etc/polaris/.env`)
- Mirrors `/etc/polaris/static_accounts.yaml` from SM
- Imports the GPG private key into `~/.gnupg-polaris`
- Runs `docker compose up -d --build`
- Smoke tests /health + /transparency

Compose reads `.env` at repo root (matches `docker-compose.v6.yml:env_file: .env`). `/etc/polaris/static_accounts.yaml` matches the mount path required by I-carney-004 P1 fix.

## Direct questions iter 2

1. Sign-off evidence ingestion via heredoc-append (not static pipe) — APPROVE'd?
2. egress lockdown §1b as mandatory step between deploy + smoke — APPROVE'd?
3. Fallback laptop env file at repo-root `.env` (matching compose) — APPROVE'd?
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
