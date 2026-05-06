# Codex round 2 — M-INT-7 v2

## Round-1 BLOCKED close
v1 BLOCKED with "quota overage is logged but not enforced".
Codex repro: exhausted quota + stubbed run_one_query → main_async
still ran the query and returned 0.

v2 fix (commit 895cf23):
- After `billing_summary["exceeded"]` is set, main_async returns
  rc=2 BEFORE the query loop (was: just printed and continued)
- Writes sweep_quota_refusal.json with structured refusal record
  (status=abort_quota_exceeded, queries_attempted=0, billing_quota
  payload preserved)
- Also fixed Codex round-1 MEDIUM (test gap): added 2 main_async
  integration tests that drive the gate behavior end-to-end:
  - test_main_async_aborts_when_quota_exceeded: pre-exhaust quota,
    assert calls==[], rc==2, refusal.json exists
  - test_main_async_proceeds_when_quota_under_cap: inverse — quota
    available → queries run normally, rc==0, no refusal.json

## Acceptance bar
1. ✅ Imported (substrates)
2. ✅ Invoked (main_async pre-loop)
3. ✅ Run-log evidence (`[M-INT-7] billing_quota:` line + refusal
   message when exceeded)
4. ✅ Rollback flag PG_USE_BILLING_QUOTA=0 disables (default 0)
5. ✅ EXCEEDED → GATES (rc=2 + refusal.json + zero queries run)
6. ✅ Failure does NOT raise (LAW II)
7. ✅ M-NEW substrate tests (27/27) still green

## Tests
- 9/9 M-INT-7 (7 v1 + 2 v2 gate-enforcement)
- 27/27 M-NEW substrate

Branch: PL-honest-rebuild-phase-1
Commit: 895cf23

## Verdict
GREEN | PARTIAL | BLOCKED
