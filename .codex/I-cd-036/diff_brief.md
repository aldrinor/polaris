# Codex diff — I-cd-036 (#636) — TLS verification smoke

Canonical-diff-sha256: `ee5007d675d1148e9f26343fdb668f115c35859b17437a301d952047b84f0b87`. 1 file / +69 LOC.

## Diff
- `scripts/verify_production_tls.sh` NEW — 7 mechanical TLS + smoke checks. Exit 0 (all pass) or 1 (any fail with stderr details).
- Caddy + Let's Encrypt substrate already exists in repo (Caddyfile + docker-compose.v6.yml caddy service per I-rdy-015 / #511).
- Operator-action follow-up Issue #699 holds domain procurement + DNS + cert provisioning.

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
