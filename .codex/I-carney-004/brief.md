HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-004 — Static_accounts auth + GPG demo signing + AWS Secrets Manager

GH#472. Critical-path day 16. The auth gate that prevents random internet visitors from running pipeline-A queries on the demo deploy, plus secret hardening for the demo signing key + secret rotation policy.

## Files I have ALSO checked clean (§-1.2 #2)

- `src/polaris_v6/api/app.py` — FastAPI app factory; existing routers mount without auth (Phase-0 demo). Auth middleware will be a global FastAPI dependency injected at app creation.
- `src/polaris_v6/api/health.py` + `/transparency` (from I-carney-003) — these MUST stay public (health probes, reviewer-visible deploy descriptor). Auth dependency uses path allowlist.
- `src/polaris_v6/api/runs.py` + `stream.py` + `bundle.py` + all other endpoints — these MUST require auth (LLM tokens cost money + sovereignty filter applies only to authorized runs).
- `web/lib/api.ts` — fetch calls already use browser-relative `/api/v6` prefix; auth header will be `Authorization: Bearer <token>` injected from a webui login page.
- `infra/aws/ssm_parameters.tf` — SSM Parameter Store already exists for OPENROUTER_API_KEY etc. The static_accounts file (username + bcrypt-hashed password + role) is also a SecureString.
- `scripts/bootstrap_gpg_demo_key.sh` from I-carney-005 — already idempotent; this issue adds AWS Secrets Manager export hook for the PRIVATE key (operator-run path; AWS-side write only).

## Scope

6 NEW files + 3 PATCHes:

1. **NEW `src/polaris_v6/api/auth.py`** (~150 LOC):
   - `StaticAccountsAuth` class: loads YAML from `${POLARIS_STATIC_ACCOUNTS_PATH:-/app/config/static_accounts.yaml}` (env override) with shape `accounts: [{username, password_bcrypt, role}]`.
   - `verify_password(plain, hashed) -> bool` using `passlib.context.CryptContext(["bcrypt"])`.
   - `issue_token(username, role) -> str`: HS256 JWT with sub=username, role, exp=12h.
   - `require_auth() -> User` FastAPI dependency: extracts `Authorization: Bearer <jwt>`, validates HS256 signature with `POLARIS_JWT_SECRET` env, decodes claims, returns User.
   - Allowlisted paths (NO auth required): `/health`, `/transparency/*`. All others require auth.
   - `POST /auth/login` route: accepts `{username, password}`, returns `{access_token, role, expires_in: 43200}`.
   - LAW II: missing JWT secret → app fails to start (no silent degrade).

2. **NEW `config/static_accounts.example.yaml`** — operator template:
   ```yaml
   accounts:
     - username: carney_office
       # bcrypt hash of "REPLACE_ME" (cost=12). Operator generates with:
       #   python -c "from passlib.hash import bcrypt; print(bcrypt.using(rounds=12).hash('your-password'))"
       password_bcrypt: "$2b$12$REPLACE_ME"
       role: reviewer
     - username: ops
       password_bcrypt: "$2b$12$REPLACE_ME"
       role: admin
   ```
   Roles `reviewer` (can POST /runs + GET stream/bundle) and `admin` (also can hit /admin/* in future).

3. **NEW `web/app/login/page.tsx`** (~100 LOC): minimal username+password form → POST /api/v6/auth/login → stores token in httpOnly cookie via Server Action. Redirects to /.

4. **NEW `web/middleware.ts`** — Next.js middleware: protects `/intake`, `/retrieval`, `/runs`, `/api/v6/*` (except login + transparency). Redirects unauth'd to `/login`. Reads JWT from cookie, injects `Authorization: Bearer ...` on /api/v6 rewrites.

5. **NEW `infra/aws/secretsmanager.tf`** (~80 LOC): adds AWS Secrets Manager resources for:
   - `polaris/v6/jwt_secret` — auto-generated 64-char secret used by `auth.py`
   - `polaris/v6/static_accounts_yaml` — operator-set YAML body (multi-line); cloud-init writes to `/etc/polaris/static_accounts.yaml`
   - `polaris/v6/gpg_private_key_armored` — armored ASCII of the demo signing key (manually populated; cloud-init imports). KMS-CMK encrypted. Replaces the README-only manual transfer step from I-carney-002.
   - Rotation policy: AWS Secrets Manager schedule expression (every 90 days) — for the Carney demo window, manual rotation only; rotation_lambda left as Phase-2.

6. **NEW `infra/aws/secretsmanager_iam.tf`** — extends EC2 role to read these specific secret ARNs (NOT `*`).

7. **PATCH `infra/aws/cloud-init.sh`** — fetches the 3 new secrets via `aws secretsmanager get-secret-value`, writes JWT secret to `.env`, writes static_accounts.yaml to `/etc/polaris/`, imports armored private key into the demo GPG keyring (replacing the manual operator step).

8. **PATCH `src/polaris_v6/api/app.py`** — adds `require_auth` as a global dependency with the `/health` + `/transparency*` allowlist; mounts `/auth/login` router.

9. **PATCH `Dockerfile.v6`** — adds `passlib[bcrypt]` and `python-jose[cryptography]` to v6 deps via `requirements-v6.txt`.

10. **NEW tests** at `tests/polaris_v6/api/test_auth.py` (~120 LOC):
    - `POST /auth/login` with valid creds → 200 + JWT
    - `POST /auth/login` with bad password → 401
    - Bearer token grants access to `/runs`
    - Missing Bearer → 401
    - Expired JWT → 401
    - `/health` + `/transparency` reachable without auth

## Acceptance criteria

1. POST /auth/login with valid creds returns 12-hour HS256 JWT
2. All endpoints except `/health` + `/transparency/*` require valid Bearer
3. `POLARIS_JWT_SECRET` missing at app startup → LAW II fail-loud (NOT silent allow-all)
4. Static accounts file uses bcrypt hashes (cost ≥ 10)
5. JWT secret + static accounts + GPG private key are all in AWS Secrets Manager (NOT in SSM Parameter Store; SM has rotation + cross-region replication)
6. EC2 IAM role grants Secrets Manager read on specific ARNs (no `Resource: "*"`)
7. cloud-init fetches all 3 secrets before `docker compose up`
8. New tests pass; existing v6 suite (396+6=402+ passing) does not regress
9. Web /login page works against a stubbed backend (jest test) — frontend test scope is "renders + submits"; deeper SSR / cookie tests are Phase-2

## Direct questions iter 1

1. Static accounts file (bcrypt YAML loaded at app start) vs full auth provider (Cognito / Okta) — APPROVE'd for Carney demo window?
2. HS256 JWT with 12h expiry — APPROVE'd? Or want shorter (1h + refresh)?
3. AWS Secrets Manager (vs SSM Parameter Store for these 3 secrets) — APPROVE'd? Reason: SM has built-in rotation + larger payload size for the multi-line static_accounts YAML.
4. cloud-init imports private GPG key from Secrets Manager (vs manual SSM Session Manager transfer per I-carney-002 README) — APPROVE'd? This replaces the operator-manual-transfer step with an automated one.
5. JWT secret stored in Secrets Manager + injected via cloud-init `.env` — APPROVE'd?
6. Anything else blocking iter-1 APPROVE?

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
