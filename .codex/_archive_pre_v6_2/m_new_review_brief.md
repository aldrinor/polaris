M-NEW v1 (billing + quotas) — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-NEW ships the billing + quotas substrate per FINAL_PLAN Phase
C deliverable #6. v1 is the storage + atomic-consume surface.
Out of scope for v1: Stripe integration, per-event metered
pricing, self-serve plan upgrades.

The substrate gates org-level audit-run enqueue, audit-bundle
export, and workspace creation. The runner / endpoints will pre-
check via `check_quota` and consume via `consume` once wired up
(deferred to a follow-up milestone).

## What changed in v1 (commit 5bf4069)

New module: `src/polaris_graph/audit_ir/billing_quota_store.py`

Schema:
  plans(org_id PRIMARY KEY, tier, quotas_json, cycle_start,
    updated_at)
  billing_events(event_id, org_id, kind, user_id, cost_units,
    created_at)
+ idx_billing_events_org_kind_created
+ idx_billing_events_org_created

PlanTier (closed enum, with default per-month caps):
  PILOT       50 runs, 50 bundles, 5 workspaces
  STARTUP     500 / 500 / 25
  PRODUCTION  5000 / 5000 / 100
  ENTERPRISE  unlimited (cap = -1)

QuotaEventKind:
  audit_run_enqueued
  audit_bundle_exported
  workspace_created

Public API:
- assign_plan(org_id, tier, quotas_override) — idempotent
- get_plan(org_id) -> PlanAssignment | None
- reset_monthly_counters(org_id) — bumps cycle_start; preserves
  billing_events rows for invoicing
- check_quota(org_id, kind) -> QuotaCheckResult — orgs with no
  plan get cap=0 + is_exceeded=True
- consume(org_id, kind, user_id, cost_units=1) — atomic
  check-and-increment under BEGIN IMMEDIATE; raises
  QuotaExceededError
- list_events(org_id, kind, since, until, limit)

Tests (23): plan assignment, check_quota, consume, cross-org
isolation, cycle reset, billing-event log preservation,
list_events filters.

## Your job

Verdict on M-NEW v1. GREEN / PARTIAL / DISAGREE.

Look for:

1. **Race-condition gaps.** consume() does check-and-increment
   inside BEGIN IMMEDIATE. Are there interleaving paths where
   two concurrent consume() calls both pass the cap check
   before either inserts? My read: BEGIN IMMEDIATE serializes
   writers, so no.
2. **Cross-org bypass.** Can org_b consume() against org_a's
   plan? My read: no — consume looks up plan by org_id passed
   in, and the billing_events row is tagged with that org_id.
3. **Counter reset correctness.** reset_monthly_counters bumps
   cycle_start — does that correctly zero the "used in cycle"
   reading? My read: yes — _used_in_cycle filters
   `created_at >= cycle_start`.
4. **Quota-override security.** assign_plan accepts a
   quotas_override dict. Should that be operator-only? Right
   now any caller of the store can override; the surfaceable
   risk is "rogue admin upgrades own org to unlimited." For v1
   this is operator-managed (the endpoint hooking up assign_plan
   should be admin-gated), but is the store-level guarantee
   defensible?
5. **Append-only billing events.** Is there any path that
   deletes a billing_events row? My read: no public method;
   reset_monthly_counters explicitly preserves them.
6. **Plan tier defaults.** PILOT 50 runs/mo + 5 workspaces — is
   that defensible for a pilot tier, or do real customers want
   100/10? (This is a numerical-default opinion, not a code
   correctness question — answer if you have a strong view.)
7. **Anything else worth flagging before M-NEW locks.**

If GREEN, M-NEW v1 locks. The endpoint + runner wire-up is a
follow-up milestone (M-NEW v2).

## Output

Write to `outputs/codex_findings/m_new_review/findings.md`:

```markdown
# Codex review of M-NEW v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Race conditions
- [defensible / list issues]

## Cross-org isolation
- [defensible / list issues]

## Counter reset correctness
- [defensible / list issues]

## Append-only billing
- [defensible / list issues]

## Final word
GREEN to lock M-NEW + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
