## Codex round 2 — M-INT-3 v2

v1 was reviewed by Codex round-1; you (Codex) auto-extended the test
file to add `test_main_async_prints_freshness_summary_after_cache_warming`
asserting strict freshness log format.

## v2 close
- Production already prints the format Codex expects:
  - `"[M-INT-3] sweep_freshness_summary: total_checked=N"`
  - `"per_status={unchanged=N, superseded=N, retracted=N, expression_of_concern=N, unreachable=N}"`
  - `"evicted_count=M"`
- After **warm** call (M-INT-2 cache_warming) — order asserted by call_order list
- 6/6 tests pass including your added E2E test

## Acceptance bar (re-verify)
1. ✅ Imported (FreshnessAlertStore, FreshnessStatus, FreshnessDetector,
   FreshnessCheckResult, check_freshness)
2. ✅ Invoked (_check_corpus_freshness called from main_async after cache warming)
3. ✅ Run-log evidence (sweep_freshness_summary printed)
4. ✅ Rollback flag PG_USE_FRESHNESS_DETECTOR=0 disables
5. ✅ Order: warm → fresh enforced

## v2 caveat (unchanged from v1)
_StubFreshnessDetector v1 returns UNCHANGED → no evictions.
Real Crossref `update-policy` probe is Phase F (M-LIVE-1 onward).
Substrate import + invocation + SQLite write demonstrated.

## Tests
6/6 passing on branch PL-honest-rebuild-phase-1, commit da1a62c.

## Verdict
GREEN | PARTIAL | BLOCKED
