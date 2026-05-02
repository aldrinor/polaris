M-19 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-19 ships the pilot-grade security audit log per FINAL_PLAN
Phase C deliverable #9: "Pilot-grade SOC2 readiness (procurement-
friendly, not formally certified)."

The minimum viable security audit log a procurement reviewer
asks for: every authenticated action attributed to user_id +
org_id, every auth failure recorded, every cross-tenant access
attempt recorded as WARN-level event (not silently 403'd),
append-only storage with timestamps.

Wire-up into auth_middleware deferred to M-19 v2 (the org-scoped
retrofit of run-* endpoints in M-15c is the natural insertion
point). v1 ships the storage substrate + schema that procurement
reviewers ask to inspect.

## What changed in v1 (commit b50f144)

New module: `src/polaris_graph/audit_ir/security_audit_log.py`

Schema (SQLite, WAL):
  security_events(event_id, event_type, severity, user_id,
    org_id, source_ip, user_agent, request_method, request_path,
    details_json, created_at)
  + idx_security_events_severity_created (DESC)
  + idx_security_events_org_created (DESC)
  + idx_security_events_user_created (DESC)

Event types (closed enum, stable strings):
  auth_succeeded                 INFO
  auth_failed                    WARN
  cross_tenant_denied            WARN
  privilege_escalation_denied    WARN
  api_key_created                INFO
  api_key_revoked                INFO
  user_role_changed              INFO
  data_deleted                   INFO
  audit_bundle_exported          INFO

Severity levels: INFO / WARN / CRITICAL.

Public API:
  record_event(event_type, severity, user_id, org_id,
    source_ip, user_agent, request_method, request_path,
    details) -> SecurityEvent
  list_events(org_id, user_id, severity, event_type,
    since, until, limit) -> list[SecurityEvent]
  get_event(event_id) -> SecurityEvent | None

LAW II / SOC2 invariant: NO public mutation API beyond
record_event. No update_event, no delete_event, no purge, no
truncate, no clear. `test_log_has_no_update_or_delete_method`
enforces this via dir(SecurityAuditLog) inspection.

Tests (18):
- 6 record_event (defaults, override, failure-default, details
  preservation, unserializable fallback, non-enum rejection)
- 8 list/get (newest-first ordering, severity/event_type/org/user
  filters, time-range, limit cap, limit range validation, unknown
  id, get round-trip)
- 1 append-only invariant
- 3 serialization

Module: 18/18 security_audit_log tests green.

## Your job

Verdict on M-19 v1. GREEN / PARTIAL / DISAGREE.

I'm asking you to look for:

1. **SOC2 procurement-completeness gaps.** Are there security-
   event categories a SOC2 reviewer expects to see but I missed?
   E.g. session_started/session_ended, password_changed,
   2fa_enrolled, data_export_initiated.
2. **Schema flaws for SOC2.** SOC2 typically expects retention
   policy + tamper-evidence (hash-chained or signed events).
   Acceptable for "pilot-grade not formally certified" to skip
   tamper-evidence in v1?
3. **Wire-up risk.** v1 doesn't actually call record_event from
   auth_middleware yet — is that a blocker, or defensible as
   "v2 wires it; v1 ships the substrate"? My read: the
   substrate is what procurement asks to inspect; the wire-up
   is operational coverage.
4. **Index choices.** Are the three indexes (severity_created,
   org_created, user_created) the right ones? Should I add
   event_type_created too?
5. **details_json being TEXT.** Should we use a JSON1 virtual
   column for indexed structured queries, or is keeping it as
   opaque TEXT defensible?
6. **No mutation API invariant.** test_log_has_no_update_or_
   delete_method covers public-method scanning. Is that strict
   enough, or should we also assert the SQL surface (no
   UPDATE/DELETE in the source file)?
7. **Anything else worth flagging before M-19 locks.**

If GREEN, M-19 v1 locks. The wire-up + endpoint ship as v2 once
M-15c retrofit lands.

## Output

Write to `outputs/codex_findings/m19_review/findings.md`:

```markdown
# Codex review of M-19 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## SOC2 completeness
- [defensible / list missing event types]

## Schema flaws
- [defensible / list issues]

## Wire-up risk
- [defensible / blocker]

## No-mutation invariant
- [defensible / strengthen]

## Final word
GREEN to lock M-19 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
