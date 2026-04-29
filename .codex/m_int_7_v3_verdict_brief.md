# M-INT-7 v3 — Codex round-3 GREEN

## Codex verdict (verbatim)
> No findings.
>
> The v3 guard is placed correctly: empty queries_to_run now
> skips _check_audit_run_quota() and preserves the existing
> refusal gate for non-empty sweeps. The added regressions
> match the empty-sweep fix, and the existing exceeded/under-cap
> coverage still reflects the intended gate behavior.
>
> Manual probes (all correct):
> - SWEEP_QUERIES=[] → rc=0, used=0
> - --only nonexistent_slug → rc=2, used=0
> - pre-consumed cap=1 → rc=2, sweep_quota_refusal.json, zero queries
> - available quota → rc=0, query ran, usage=1
>
> VERDICT: GREEN

## Round summary
- R1: BLOCKED (logged but not enforced — gate missing)
- R2: MEDIUM (empty sweep still consumed quota)
- R3: GREEN (empty-sweep no-charge fix verified)

## Acceptance bar — ALL met
1. ✅ Imported (BillingQuotaStore, PlanTier, QuotaEventKind,
   QuotaExceededError)
2. ✅ Invoked (`_check_audit_run_quota` from main_async)
3. ✅ Run-log evidence (`[M-INT-7] billing_quota:` line +
   refusal message + skip message for empty sweep)
4. ✅ Rollback flag PG_USE_BILLING_QUOTA=0 disables (default 0)
5. ✅ EXCEEDED → GATES (rc=2 + refusal.json + zero queries)
6. ✅ Empty sweep → no charge (Codex: rc=0, used=0)
7. ✅ Failure does NOT raise (LAW II)

## Tests
- 11/11 M-INT-7 tests pass (Codex independently verified all paths)
- 27/27 M-NEW substrate green

Branch: PL-honest-rebuild-phase-1
Commit: 4af4125

## Verdict
**GREEN — M-INT-7 LOCKED. Proceeding to M-INT-8.**
