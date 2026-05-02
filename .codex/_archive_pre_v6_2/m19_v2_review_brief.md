M-19 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-19 v1 verdict: PARTIAL with 2 specific edits + 1
strengthening recommendation.

1. Missing access-grant/revoke event categories.
2. Attribution not enforced on user_id / org_id.
3. (Strengthen) Add source-level mutation guard.

All 3 integrated in v2 (commit 7cb2e02).

## What changed in v2

`security_audit_log.py`:
- New event types: MEMBERSHIP_ADDED, MEMBERSHIP_REMOVED (both
  default INFO).
- New `_REQUIRES_ATTRIBUTION` set covers AUTH_SUCCEEDED,
  CROSS_TENANT_DENIED, PRIVILEGE_ESCALATION_DENIED,
  API_KEY_CREATED/REVOKED, USER_ROLE_CHANGED,
  MEMBERSHIP_ADDED/REMOVED, DATA_DELETED, AUDIT_BUNDLE_EXPORTED.
  `record_event` raises if user_id or org_id missing for one of
  these types. Anonymous AUTH_FAILED still allowed.

Tests added (4):
- test_membership_added_event_records
- test_membership_removed_event_records
- test_authenticated_events_require_attribution
- test_anonymous_auth_failed_is_allowed
- test_source_contains_no_mutation_sql_for_security_events
  (source-level scan: no UPDATE / DELETE FROM / DROP TABLE /
   TRUNCATE on security_events)

Tests updated (5): existing AUTH_SUCCEEDED call sites now pass
user_id="usr_x" so they satisfy the new attribution requirement.

Module: 23/23 security_audit_log tests green; full Phase C
combined: 304/304.

Note on wire-up: Codex v1 review acknowledged that "v1 substrate
only" is defensible. Wire-up into auth_middleware is the M-19 v2
endpoint integration milestone (deferred — not landing in this
commit).

## Your job

Final verdict on M-19. GREEN / PARTIAL / DISAGREE.

If GREEN, M-19 v2 locks (substrate-only, no wire-up yet). The
endpoint integration ships as M-19 v3 once auth_middleware is
ready to call record_event() on every authenticated request.

## Output

Write to `outputs/codex_findings/m19_v2_review/findings.md`:

```markdown
# Codex re-review of M-19 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] membership_added/removed event types added
- [x/no] attribution enforced for authenticated event types
- [x/no] source-level mutation guard

## Final word
GREEN to lock M-19 substrate + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
