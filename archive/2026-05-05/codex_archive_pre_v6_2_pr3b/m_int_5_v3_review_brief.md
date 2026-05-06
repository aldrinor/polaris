# Codex round 3 — M-INT-5 v3

## Round-2 close
v2 had 1 HIGH + 1 MEDIUM. Both fixed in v3 (commit d17ec1c):

### HIGH: helper raise not caught (FIXED)
- v2 only protected against malformed dict shapes. If
  `_classify_scope_with_llm` itself raised (helper bug,
  monkeypatched stub, future regression), exception escaped
  to outer fatal handler with status=error.
- v3 fix: wrap the helper call itself in try/except in run_one_query.
  Defense-in-depth: helper has its own try/except internally;
  sweep adds a second layer per LAW II "best-effort telemetry
  must not gate sweep".

### MEDIUM: HIGH-fix regression test was weak (FIXED)
- v2 stubbed `run_live_retrieval` as `async def` but production
  signature is sync. asyncio.run consumed an unawaited coroutine
  silently, so the test could pass after an unrelated failure.
- v3 fix: sync stub matching production. Plus new test
  test_run_one_query_survives_scope_llm_helper_raise that
  monkeypatches the M-INT-4 helper to RAISE directly (not
  return malformed dict) — proves the v3 outer try/except
  prevents abort.

## Acceptance bar — re-verify
1. ✅ Imported (substrates)
2. ✅ Invoked (sweep wiring)
3. ✅ Run-log evidence
4. ✅ Rollback flag PG_USE_DOMAIN_ROUTER=0 disables (default 0)
5. ✅ UNCERTAIN-verdict fallback → REJECTED_UNCERTAIN
6. ✅ Failure does NOT raise (per LAW II — HIGH closed via
   defense-in-depth wrap)

## Tests
- 12/12 M-INT-5 (7 v1 + 4 v2 + 1 v3 helper-raise)
- 68/68 across M-INT-0a..5

Branch: PL-honest-rebuild-phase-1
Commit: d17ec1c

## Verdict expected
GREEN — both round-2 findings closed.
