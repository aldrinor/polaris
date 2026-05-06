M-24 v1 (customer support ticket store) — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-24 ships the customer-support ticket store per FINAL_PLAN
Phase C deliverable #10. Minimum viable surface: org-scoped
ticket queue with status transitions + append-only message
thread. Out of scope for v1: email integration, SLA timers,
Slack/PagerDuty hooks, knowledge base.

## What changed in v1 (commit 7c95cd4)

New module: `src/polaris_graph/audit_ir/support_ticket_store.py`

State machine:
  OPEN --assign()--> IN_PROGRESS
                       --resolve()--> RESOLVED
                       --close()--> CLOSED
  RESOLVED|CLOSED --reopen()--> IN_PROGRESS

Closed enums: TicketStatus / TicketCategory (billing | audit |
integration | data_request | other) / TicketPriority.

Public API:
- open_ticket(...) — validates non-empty fields + enum types
- assign / resolve / close / reopen — under BEGIN IMMEDIATE
- append_message — verifies ticket-in-org before write
- list_messages — returns [] for cross-org (no existence leak)
- get_ticket — None for cross-org
- list_by_org with status/category/assignee filters

Cross-tenant invariants enforced at the SQL level (every method
takes org_id and filters on it).

Tests (25): open + validation, state transitions, cross-tenant
isolation, list filters, append-only thread, serialization.

## Your job

Verdict on M-24 v1. GREEN / PARTIAL / DISAGREE.

Look for:

1. **Cross-tenant bypass.** Can org_b read/write/delete an org_a
   ticket or message via any path? My read: no — every method
   takes org_id and SQL-filters on it; append_message verifies
   the ticket is in-org first; list_messages returns [] for
   cross-org rather than leaking existence.
2. **State-machine bypasses.** Can a ticket flip OPEN → CLOSED
   without going through IN_PROGRESS? close() allows OPEN as a
   from-state intentionally (for won't-fix / duplicate
   closures). Is that defensible?
3. **Append-only message thread.** No public delete/edit method.
   Is the source-level guarantee strong enough or do we need a
   source-scan test?
4. **Reopen from CLOSED.** Currently allowed. Some support
   workflows treat CLOSED as final-final. Is the current "you
   can always reopen" choice defensible?
5. **Back-link integrity.** related_run_slug / related_review_id
   / related_workspace_id are stored as TEXT with no foreign-key
   validation. A ticket can reference a non-existent run. Is
   that defensible (denormalized for ergonomics) or should we
   validate at write time?
6. **Anything else worth flagging before M-24 locks.**

If GREEN, M-24 v1 locks.

## Output

Write to `outputs/codex_findings/m24_review/findings.md`:

```markdown
# Codex review of M-24 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Cross-tenant isolation
- [defensible / list issues]

## State machine
- [defensible / list issues]

## Append-only thread
- [defensible / list issues]

## Final word
GREEN to lock M-24 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
