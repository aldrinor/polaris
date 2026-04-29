# Codex round 1 — M-INT-7 v1

## Scope
Wires M-NEW substrate (BillingQuotaStore + PlanTier +
QuotaEventKind + QuotaExceededError) into sweep main_async.

## Acceptance bar
1. ✅ Imported (BillingQuotaStore, PlanTier, QuotaEventKind,
   QuotaExceededError)
2. ✅ Invoked (`_check_audit_run_quota` from main_async pre-loop)
3. ✅ Run-log evidence (`[M-INT-7] billing_quota:` line —
   normal use shows used/cap/remaining; EXCEEDED shows reason)
4. ✅ Rollback flag PG_USE_BILLING_QUOTA=0 disables (default 0)
5. ✅ QuotaExceededError → structured summary, NOT raise
6. ✅ Failure does NOT raise (per LAW II)
7. ✅ No-org and no-plan paths return None / exceeded
   summary, never raise

## v1 caveat
- Charges 1 unit per SWEEP INVOCATION (not per query).
  v2 may move to per-query consume in run_one_query if
  required by pricing model.
- Default PG_USE_BILLING_QUOTA=0 keeps existing sweep
  behavior unchanged.
- Quota DB defaults to state/billing_quota.sqlite.

## Tests
- 7/7 M-INT-7 tests pass
- 27/27 M-NEW substrate (test_billing_quota_store) still green

Branch: PL-honest-rebuild-phase-1
Commit: 5f96da6

## Verdict
GREEN | PARTIAL | BLOCKED
