# I-carney-004 Claude architect audit

**Issue:** GH#472 — Static_accounts auth + GPG demo signing key + AWS Secrets Manager
**Branch:** `bot/I-carney-004-auth-secrets`
**Codex brief verdict:** APPROVE (skipped formal brief stage per pattern; design APPROVE'd at diff review)
**Codex diff verdict:** APPROVE iter 2 of 5

## Surface

11 files (8 new + 3 patches).

| File | LOC | Purpose |
|---|---|---|
| `src/polaris_v6/api/auth.py` | 179 | NEW: bcrypt + HS256 JWT + require_auth FastAPI dep + POST /auth/login. LAW II fail-loud on missing JWT secret / accounts. |
| `src/polaris_v6/api/app.py` | +12 | mount auth_router + global Depends(require_auth) + verify_app_startup |
| `requirements-v6.txt` | +6 | passlib + python-jose + PyYAML + boto3 |
| `config/static_accounts.example.yaml` | 21 | operator template |
| `infra/aws/secretsmanager.tf` | 78 | NEW: 3 SM secrets + IAM policy (specific ARNs, not *) |
| `infra/aws/main.tf` | +5 | random provider |
| `infra/aws/variables.tf` | +14 | sensitive vars for accounts + GPG private key |
| `infra/aws/terraform.tfvars.example` | +23 | heredoc placeholders |
| `infra/aws/ec2.tf` | +4 lines | depends_on extended for SM substrate (4 new entries) |
| `infra/aws/cloud-init.sh` | +35 | sm_get helper; fetches 3 secrets; injects POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH; imports GPG private; xtrace OFF (P1-3 fix) |
| `docker-compose.v6.yml` | +6 | bind ${POLARIS_ETC_DIR}:/etc/polaris:ro for api + worker (P1-1 fix) |
| `tests/v6/conftest.py` | +5 | POLARIS_AUTH_DISABLED=1 default for existing tests |
| `tests/polaris_v6/conftest.py` | 11 | NEW: same auth-disabled default |
| `tests/polaris_v6/api/test_auth.py` | 165 | NEW: 11 auth tests |
| `docs/deploy_runbook.md` | +5 | Updated smoke test with /auth/login token flow + Bearer header |

## Codex iteration trail

| Doc | Iter | Outcome | Real findings |
|---|---|---|---|
| diff | 1 | REQUEST_CHANGES | P1-1 /etc/polaris not mounted; P1-2 Terraform depends_on; P1-3 xtrace leaks secrets; P1-4 existing tests broken |
| diff | 2 | **APPROVE** | zero P0/P1; 3 P2 (docs gate deferred, runbook update done, malformed-account validation Phase-2) |

## P1 resolutions verified

1. **P1-1 container can't see /etc/polaris:** docker-compose.v6.yml api+worker now mount `${POLARIS_ETC_DIR:-/etc/polaris}:/etc/polaris:ro`. POLARIS_STATIC_ACCOUNTS_PATH=/etc/polaris/static_accounts.yaml in .env (cloud-init).
2. **P1-2 Terraform race:** `aws_instance.polaris.depends_on` extended with `aws_secretsmanager_secret_version.{jwt_secret,static_accounts,gpg_private_key}` + `aws_iam_role_policy_attachment.secretsmanager_read`. First-apply boot can never race.
3. **P1-3 xtrace secret leak:** cloud-init.sh:9 `set -eo pipefail` (no x). Comment documents why. Errors-only mode prevents echoing POLARIS_JWT_SECRET / static_accounts_yaml / GPG private key.
4. **P1-4 existing tests:** tests/v6/conftest.py + tests/polaris_v6/conftest.py set `POLARIS_AUTH_DISABLED=1` at module-top (before any create_app() import). Auth-specific tests use `monkeypatch.delenv("POLARIS_AUTH_DISABLED")` to opt back in.

## Test evidence

```
$ python -m pytest tests/v6/ tests/polaris_v6/
500 passed, 7 xfailed in 33.66s
```

7 xfailed are pre-existing (not auth-related).

## Verdict

READY TO MERGE. All Codex artifacts present:
- `.codex/I-carney-004/brief.md`
- `.codex/I-carney-004/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-carney-004/codex_diff.patch`
- `.codex/I-carney-004/codex_diff_audit_iter_2.txt` (APPROVE)
- `outputs/audits/I-carney-004/claude_audit.md` (this file)
