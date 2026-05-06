M-15a auth substrate — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase C plan v2 GREEN-locked. M-15a is the auth SUBSTRATE per
your pass-1 split recommendation:
  - M-15a: orgs / users / roles / memberships / API keys.
  - M-15b: endpoint authz retrofit + exhaustive sweep (separate).

The dominant Phase C risk is cross-tenant leakage. M-15b will
gate every M-1..M-13 endpoint on workspace ownership. M-15a
provides the substrate: who is which user, in which org, with
which role.

## What landed (commit dffa112)

`src/polaris_graph/audit_ir/auth_store.py` (~520 lines):
- 4 roles with explicit rank: viewer < member < admin < owner.
- AuthStore SQLite-backed (WAL, FK on, per-call conn,
  BEGIN IMMEDIATE for atomic transactions). Mirrors M-11
  workspace_store patterns.
- Tables: orgs, users, memberships, api_keys.
- Org slug regex: `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$` (2-64
  chars, must start/end alnum).
- User email lowercased + pragmatic-regex validated.
  Bcrypt-hashed password (PG_BCRYPT_ROUNDS env, default 12,
  clamped 4-15).
- Membership: composite (org_id, user_id) → role. **Last-owner
  protection**: demoting or removing the last owner of an org
  raises InvalidRoleError per LAW II.
- API keys: plaintext returned EXACTLY ONCE at creation; bcrypt
  hash stored. Plaintext format: `polaris_<32 url-safe random>`
  (PG_API_KEY_PREFIX env-overridable).
- API-key role capped at user's current membership role (admin
  can't mint owner-scoped key) — fails LOUD per LAW II.
- verify_password: constant-time-safe — even unknown email runs
  a bcrypt round to avoid leaking existence via timing.
- verify_api_key: linear bcrypt scan over non-revoked keys
  (Phase C OK; Phase D adds key_id prefix lookup); updates
  last_used_at on success; raises CredentialError on
  revoked/unknown/format-invalid.
- revoke_api_key: idempotent.
- role_geq() helper for the M-15b authz retrofit.

Errors: AuthStoreError base + DuplicateError, NotFoundError,
InvalidRoleError, CredentialError.

## Tests: 44

Coverage:
- Org CRUD + slug regex (8 invalid forms rejected) + duplicate
  detection.
- User CRUD + email regex + email lowercasing + short password
  rejection + duplicate email rejection.
- Password verify: success, wrong password, unknown user (all
  return CredentialError with same message — timing-safe).
- Membership add/get/list/update/remove.
- Membership unknown org / unknown user / unknown role / 
  duplicate membership.
- Last-owner protection on BOTH demote and remove paths.
- Multi-owner case allows demote/remove.
- API key create returns plaintext + record.
- API key role capped at membership role.
- API key empty-label rejected.
- API key verify success/wrong/revoked/invalid-format.
- Revoke idempotent.
- Revoke unknown raises NotFoundError.
- ROLE_RANK ordering, role_geq() helper.

## Anti-scope (deferred — please don't push back)

- Endpoint authz retrofit → M-15b (next milestone).
- SSO / OAuth / SAML → Phase D.
- Email verification / 2FA → Phase D.
- Password reset flows → Phase D.
- Multi-user concurrent membership-update races (BEGIN IMMEDIATE
  handles, but worth calling out).

## Your job

Code review for M-15a. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Last-owner protection.** Walk through update_membership_role
   + remove_membership and convince yourself an org cannot end up
   with zero owners via any single mutation. Multi-step races
   (two concurrent calls demoting two owners) are guarded by
   BEGIN IMMEDIATE — one transaction sees one owner remaining and
   blocks. Agree?

2. **Role escalation block on API key.** An admin creates an
   API key with role="owner" → fails. Test verifies. Any path
   I missed where a lower-role user gets an owner-scoped key?

3. **Constant-time-safe verify_password.** Unknown email runs a
   bcrypt round to avoid timing leak. Effective?

4. **API key linear scan.** verify_api_key iterates all
   non-revoked rows in the DB and bcrypt.checkpw each. Phase C
   bound on org size keeps this OK; Phase D adds a prefix index.
   Acceptable for Phase C?

5. **bcrypt rounds env.** Clamped to [4, 15]. 12 is the default.
   Lower → fast tests, higher → fast attacker. Right tradeoff?

6. **Slug regex.** `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$`. Any
   bypass for reserved names ("admin", "api", "auth")? Phase B
   M-11 didn't reserve names; should M-15a?

7. **Email regex.** Pragmatic, not RFC 5322. Will it accept
   legitimate-but-uncommon forms (plus addressing, subdomains)?

8. **Anything else.**

## Output

Write to `outputs/codex_findings/m15a_review/findings.md`:

```markdown
# Codex review of M-15a

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Last-owner protection
Airtight under concurrency?

## Role escalation block on API key
Any bypass?

## Recommended changes
If PARTIAL.

## M-15b readiness
Is the substrate ready for the endpoint authz retrofit?

## Final word
GREEN to lock M-15a / PARTIAL with edits / DISAGREE.
```

Be terse. Under 200 lines.
