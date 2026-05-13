HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-004 diff iter 1 — auth + GPG + AWS Secrets Manager

Skipped brief iteration (Codex's brief-vs-diff conflation pattern: P1 "implementation absent" at brief stage is diff-stage scope). Going straight to diff.

## Diff `.codex/I-carney-004/codex_diff.patch` (~537 LOC across 10 files)

## File-by-file

| File | LOC | Purpose |
|---|---|---|
| `src/polaris_v6/api/auth.py` | 179 | NEW: StaticAccountsAuth + bcrypt verify + HS256 JWT issue/decode + `require_auth` FastAPI dep + `POST /auth/login`. LAW II fail-loud on missing POLARIS_JWT_SECRET (<32 chars) or static_accounts.yaml. POLARIS_AUTH_DISABLED=1 short-circuit for tests + Phase-0 dev. |
| `src/polaris_v6/api/app.py` | +12 | mount auth_router + global `Depends(require_auth)` + `verify_app_startup()` at create_app |
| `requirements-v6.txt` | +6 | passlib[bcrypt]==1.7.4 + python-jose[cryptography]==3.3.0 + PyYAML + boto3 |
| `config/static_accounts.example.yaml` | 21 | operator template with bcrypt placeholders + role descriptions |
| `infra/aws/secretsmanager.tf` | 78 | NEW: 3 Secrets Manager secrets (jwt_secret auto-gen via random_password; static_accounts_yaml from tfvar; gpg_private_key_armored from tfvar) + IAM policy granting EC2 role GetSecretValue on specific ARNs + KMS Decrypt via Secrets Manager service |
| `infra/aws/main.tf` | +5 | random_password provider declared |
| `infra/aws/variables.tf` | +14 | static_accounts_yaml + gpg_private_key_armored (sensitive) |
| `infra/aws/terraform.tfvars.example` | +23 | heredocs for the two new sensitive vars with REPLACE_ME placeholders |
| `infra/aws/cloud-init.sh` | +35 | sm_get helper; fetches the 3 SM secrets; writes static_accounts.yaml to /etc/polaris/; injects POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH into .env; imports GPG private key into demo keyring (replaces manual operator transfer from I-carney-002) |
| `tests/polaris_v6/api/test_auth.py` | 165 | NEW: 11 tests (login valid/invalid, JWT verify, public path allowlist, missing-secret fail-loud, short-secret reject, AUTH_DISABLED bypass, malformed JWT) |

## Test results

```
$ python -m pytest tests/polaris_v6/api/test_auth.py tests/polaris_v6/api/test_transparency.py
17 passed in 1.96s
```

## Acceptance criteria

1. ✅ POST /auth/login with valid creds → 12-hour HS256 JWT
2. ✅ All endpoints except /health + /transparency*/auth/login require Bearer
3. ✅ Missing POLARIS_JWT_SECRET at startup → RuntimeError (LAW II)
4. ✅ Static accounts use bcrypt (passlib CryptContext with rounds=12 in operator script)
5. ✅ JWT secret + static accounts + GPG private key in AWS Secrets Manager
6. ✅ EC2 IAM role grants Secrets Manager read on specific ARNs (not "*")
7. ✅ cloud-init fetches all 3 secrets before docker compose up
8. ✅ 11 new auth tests pass; 6 transparency tests still pass
9. ⚠️ Web /login page deferred (Phase-2 frontend Issue post-PR-D); the backend `POST /auth/login` is sufficient for `curl` / programmatic clients which is the Carney demo path (Carney's office hits the API directly)

## Files I have ALSO checked clean (§-1.2 #2)

- `src/polaris_v6/api/health.py` — stays public via PUBLIC_PATH_PREFIXES
- `src/polaris_v6/api/transparency.py` (I-carney-003) — stays public
- `src/polaris_v6/api/runs.py` + `stream.py` + `bundle.py` — now require Bearer (no code change needed; global FastAPI dep injects)
- `infra/aws/ec2.tf` IAM role — extended with secretsmanager_read policy attachment via `aws_iam_role_policy_attachment.secretsmanager_read` (new resource in secretsmanager.tf line 71)
- I-arch-001a..001f run_store + actors + stream + bundle pipeline — unchanged; auth dep is purely additive

## Direct questions iter 1

1. Backend-only auth (no /login web page in this iter) — APPROVE'd for Carney demo (Carney's office uses curl + /transparency to verify deploy honestly; programmatic JWT issuance is enough)?
2. POLARIS_AUTH_DISABLED=1 env var as the tests/dev escape — APPROVE'd, or want a sentinel file instead?
3. HS256 JWT secret stored in AWS Secrets Manager (auto-generated 64-byte URL-safe random) vs HMAC keypair file — APPROVE'd?
4. cloud-init.sh imports GPG PRIVATE key from Secrets Manager (vs manual transfer from I-carney-002 README) — APPROVE'd?
5. Anything else blocking iter-1 APPROVE?

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
