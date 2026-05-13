HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-003 iter 2 — 4 P1 resolutions

## P1-001 — ALB / Next.js routing for /transparency

ALB only forwards `/health` to api; everything else (including `/transparency`) goes to webui. FastAPI router alone is invisible from the public URL.

### Fix

**Option A (chosen):** Add Next.js rewrite for `/transparency/:path*` in `web/next.config.ts`:
```typescript
rewrites: [
  { source: "/api/v6/:path*", destination: `${internal}/:path*` },
  { source: "/transparency/:path*", destination: `${internal}/transparency/:path*` },
  { source: "/transparency", destination: `${internal}/transparency` },
]
```

This keeps the ALB rule set minimal (just /health + default) and lets Next.js proxy /transparency to the FastAPI backend at runtime.

## P1-002 — cloud-init must write the armored pubkey to disk

Current cloud-init imports POLARIS_GPG_PUBKEY into the GPG keyring but never writes the armored ASCII file the transparency endpoint reads.

### Fix (`infra/aws/cloud-init.sh`)

After `gpg --import`, also write the armored block to a known path:
```bash
if [ -n "$POLARIS_GPG_PUBKEY" ]; then
    export GNUPGHOME=/var/lib/polaris/gpg
    echo "$POLARIS_GPG_PUBKEY" | gpg --import
    # Also persist the armored ASCII for transparency endpoint to serve.
    echo "$POLARIS_GPG_PUBKEY" > /var/lib/polaris/gpg/polaris_demo_pubkey.asc
    chmod 644 /var/lib/polaris/gpg/polaris_demo_pubkey.asc
fi
```

Compose bind-mount makes /var/lib/polaris/gpg available inside containers at /app/gpg. Endpoint reads `/app/gpg/polaris_demo_pubkey.asc`. **Fallback** when the file is missing (local dev): endpoint shells out to `gpg --export --armor <key_id>` if POLARIS_GPG_KEY_ID env is set. **Strict fail-loud (503)** when neither path works.

## P1-003 — Docker container egress requires DOCKER-USER chain

Host iptables OUTPUT only filters host-originated traffic. Container traffic is bridge-forwarded through FORWARD/DOCKER-USER, so OUTPUT rules don't block it.

### Fix (`scripts/egress_lockdown.sh`)

Install rules in BOTH OUTPUT (host) AND DOCKER-USER (container forwarded traffic):
```bash
# Host outbound (OUTPUT)
iptables -F POLARIS_EGRESS_HOST 2>/dev/null || iptables -N POLARIS_EGRESS_HOST
... (allowlist + drop)
iptables -I OUTPUT 1 -j POLARIS_EGRESS_HOST

# Container forwarded (DOCKER-USER)
iptables -F POLARIS_EGRESS_DOCKER 2>/dev/null || iptables -N POLARIS_EGRESS_DOCKER
... (allowlist + drop)
iptables -I DOCKER-USER 1 -j POLARIS_EGRESS_DOCKER
```

Both chains allow 53/UDP+TCP (DNS), 123/UDP (NTP), 169.254.169.254/32 (AWS metadata), and the resolved A records of the allowlist. Everything else 80/443 → DROP.

## P1-004 — allowlist coverage

### Fix (`config/egress_allowlist.txt`)

Add the missing endpoints:
```
openrouter.ai
api.openrouter.ai
google.serper.dev          # corrected hostname per Codex iter-1 P1-004
api.semanticscholar.org
github.com
codeload.github.com
registry-1.docker.io
auth.docker.io
production.cloudflare.docker.com
ssm.ca-central-1.amazonaws.com
ssmmessages.ca-central-1.amazonaws.com
ec2messages.ca-central-1.amazonaws.com
s3.ca-central-1.amazonaws.com
pypi.org
files.pythonhosted.org
deb.debian.org             # for Dockerfile.v6 apt-get update at build time
registry.npmjs.org         # for web/Dockerfile npm ci at build time
```

cloud-init bundles `config/egress_allowlist.txt` into `/etc/polaris/egress_allowlist.txt` so the lockdown script reads from the canonical path. **README + transparency.md must say "run egress_lockdown.sh AFTER first compose build" so build-time hosts can be removed from the allowlist post-build.**

## P2 (iter-1) resolved

- **8 fields not 7:** acceptance criterion updated to "8 keys" matching scope.
- **Dependency list:** added to `GET /transparency` response as `dependencies: {python: ["fastapi 0.x", "dramatiq 2.1.0", ...], node: ["next 16.x", ...]}` read from `requirements-v6.txt` + `web/package.json` at startup.
- **Build-time vs runtime allowlist:** documented in README that lockdown runs AFTER compose build.

## Direct questions iter 2

1. Next.js rewrite for `/transparency/*` (vs ALB listener rule) — APPROVE'd?
2. cloud-init writes the armored pubkey file alongside the GPG import — APPROVE'd?
3. egress_lockdown.sh installs in BOTH OUTPUT + DOCKER-USER — APPROVE'd?
4. Expanded allowlist with 17 domains — APPROVE'd?
5. Anything else blocking iter-2 APPROVE?

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
