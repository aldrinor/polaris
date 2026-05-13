HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-004 diff iter 2 — 4 P1 resolutions

## P1 (iter-1) — /etc/polaris not mounted into container (resolved)

`docker-compose.v6.yml` api+worker services now bind `${POLARIS_ETC_DIR:-/etc/polaris}:/etc/polaris:ro`. cloud-init populates the host path; container reads `/etc/polaris/static_accounts.yaml` via the env-var override `POLARIS_STATIC_ACCOUNTS_PATH=/etc/polaris/static_accounts.yaml` set in `.env`.

## P1 (iter-1) — Terraform depends_on for Secrets Manager (resolved)

`infra/aws/ec2.tf:aws_instance.polaris.depends_on` extended with:
- `aws_secretsmanager_secret_version.jwt_secret`
- `aws_secretsmanager_secret_version.static_accounts`
- `aws_secretsmanager_secret_version.gpg_private_key`
- `aws_iam_role_policy_attachment.secretsmanager_read`

First boot can never race the secret population or IAM attachment.

## P1 (iter-1) — cloud-init xtrace secret leakage (resolved)

`infra/aws/cloud-init.sh:9` changed `set -euxo pipefail` → `set -eo pipefail`. xtrace OFF prevents POLARIS_JWT_SECRET / POLARIS_STATIC_ACCOUNTS_YAML / POLARIS_GPG_PRIVKEY from echoing into cloud-init logs or journald. Comment documents why.

## P1 (iter-1) — existing tests fail under verify_app_startup (resolved)

Added `POLARIS_AUTH_DISABLED=1` to BOTH `tests/v6/conftest.py` (module top, before app imports) AND new `tests/polaris_v6/conftest.py`. Existing tests bypass `verify_app_startup()`; auth-specific tests opt back in via `monkeypatch.delenv("POLARIS_AUTH_DISABLED")`.

### Test evidence

```
$ python -m pytest tests/v6/ tests/polaris_v6/
500 passed, 7 xfailed in 33.66s
```

(7 xfailed are pre-existing, not auth-related.)

## P2 (iter-1) — also addressed

- **gpg --import || true masking failure:** removed the `|| true`. Now fails loud on import error (private key is the bundle-signing prerequisite; silent failure would let the deploy serve 503s on /runs/{id}/bundle.tar.gz indefinitely).

## P2 deferred

- `/docs`, `/redoc`, `/openapi.json` allowlist: kept public for operator ergonomics during the Carney demo. Documented as known-public in PUBLIC_PATH_PREFIXES. Phase-2 follow-up: gate behind admin role.
- Web /login page: backend POST /auth/login + JWT issuance is sufficient for Carney's office (curl + programmatic verify per docs/transparency.md). Frontend /login page is captured as Phase-2 Issue.

## Direct questions iter 2

1. The 4 P1 fixes + 1 P2 (gpg fail-loud) — APPROVE'd?
2. Auth-disabled conftest default for existing tests (with per-test opt-in for auth tests) — APPROVE'd?
3. /docs + /redoc + /openapi.json staying public for the demo window — APPROVE'd, or want them gated?
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
