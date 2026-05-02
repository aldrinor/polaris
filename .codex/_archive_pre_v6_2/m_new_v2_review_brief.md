M-NEW v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-NEW v1 verdict: PARTIAL with 4 specific edits.

1. Race in reset_monthly_counters / assign_plan (timestamp before lock).
2. Negative quota_override silently meant unlimited.
3. assign_plan not truly idempotent (refreshed cycle on redundant call).
4. Privileged-only posture not documented.

All 4 integrated in v2 (commit 7ae5c09).

## What changed in v2

`billing_quota_store.py`:
- reset_monthly_counters and assign_plan now wrap operations in
  BEGIN IMMEDIATE / COMMIT and capture `now = time.time()` AFTER
  lock acquisition.
- assign_plan rejects negative override values except -1 (the
  explicit unlimited sentinel).
- assign_plan checks if (tier, quotas_json) match existing row
  before refreshing cycle_start; redundant re-assigns preserve
  cycle_start. Real composition changes still refresh.
- Class-level docstring documents PRIVILEGED-ONLY posture and
  the endpoint's responsibility to gate caller authority.

Tests added (4):
- test_negative_quota_override_rejected_unless_unlimited
- test_redundant_assign_plan_does_not_refresh_cycle
- test_changing_tier_does_refresh_cycle
- test_changing_quota_override_refreshes_cycle

Module: 27/27 billing_quota_store tests green.

## Your job

Final verdict on M-NEW. GREEN / PARTIAL / DISAGREE.

If GREEN, M-NEW v2 locks (substrate-only). The endpoint wire-up
is a follow-up milestone.

## Output

Write to `outputs/codex_findings/m_new_v2_review/findings.md`:

```markdown
# Codex re-review of M-NEW v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] cycle-timestamp captured inside BEGIN IMMEDIATE
- [x/no] negative quota override rejected (except -1)
- [x/no] redundant assign_plan idempotent
- [x/no] privileged-only posture documented

## Final word
GREEN to lock M-NEW + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
