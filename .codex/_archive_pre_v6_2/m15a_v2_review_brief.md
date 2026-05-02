M-15a v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-15a v1 verdict: PARTIAL with 3 issues:
1. HIGH: API-key verify didn't re-check current membership
   (demoted user kept elevated stale key).
2. MED: create_api_key TOCTOU (membership read + insert across
   two connections).
3. MED: verify_password unknown-email used cost-4 bcrypt while
   known-email used cost-12 → existence leaked via timing.

All 3 integrated in v2 (commit 9597540).

## What changed in v2

`verify_api_key()`:
- Re-loads membership on every authenticated call.
- Effective role = `min(stored_role, current_membership_role)`.
- No current membership → raises CredentialError "api key
  principal no longer has membership".
- _row_to_api_key gains `role_override` param so the returned
  ApiKey reflects the effective role.

`create_api_key()`:
- Membership read + key insert wrapped in ONE BEGIN IMMEDIATE
  transaction on a single connection.
- bcrypt hash compute (CPU-bound, slow) happens OUTSIDE the
  transaction so we don't hold the write lock during it.
- Concurrent demotion/removal lands either before our BEGIN
  (we see the demoted role and either accept or block) or
  after our COMMIT (key issued, but verify_api_key's role-cap
  catches it).

`_dummy_hash_for_current_cost()`:
- Precomputed dummy bcrypt hash, cached per-cost in
  _DUMMY_HASH_CACHE.
- verify_password unknown-email path now checkpw() against the
  same-cost dummy so timing matches the wrong-password path.

Tests: 6 new.
- verify_api_key returns effective role after demote (owner →
  admin → key role = admin).
- verify_api_key returns effective role after another demote
  (admin → member).
- verify_api_key fails loud after membership removal.
- verify_api_key does NOT upgrade role after promote (stored
  role caps).
- create_api_key atomic: missing membership → no orphaned row.
- verify_password unknown email: dummy hash cache populated at
  current bcrypt cost.

M-15a module 44 → 50 green.

## Your job

Final verdict on M-15a. GREEN / PARTIAL / DISAGREE.

If GREEN, M-15a locks and Phase C proceeds to M-15b.

## Output

Write to `outputs/codex_findings/m15a_v2_review/findings.md`:

```markdown
# Codex re-review of M-15a v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] verify_api_key re-loads membership; effective role caps
- [x/no] create_api_key atomic with membership check
- [x/no] Dummy bcrypt hash at production cost

## Final word
GREEN to lock M-15a + proceed to M-15b / PARTIAL with edits.
```

Be terse. Under 80 lines.
