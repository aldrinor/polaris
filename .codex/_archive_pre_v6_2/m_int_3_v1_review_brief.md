# Codex round 1 — M-INT-3 v1

Wires FreshnessAlertStore + check_freshness substrate into sweep
pre-loop. Stub _StubFreshnessDetector returns UNCHANGED for all
(real Crossref `update-policy` probe is Phase F).

## Acceptance bar
1. ✅ Imported (FreshnessAlertStore, FreshnessStatus, FreshnessDetector,
   FreshnessCheckResult, check_freshness)
2. ✅ Invoked (_check_corpus_freshness called from main_async after
   cache warming)
3. ✅ Run-log evidence (sweep_freshness_summary printed +
   per_status counts + evicted_count)
4. ✅ Rollback flag PG_USE_FRESHNESS_DETECTOR=0 disables

## v1 caveat
_StubFreshnessDetector v1 returns UNCHANGED → no evictions.
Real Crossref/PubMed integration is Phase F. Substrate
import + invocation + SQLite write demonstrated.

Tests: 5/5 passing.

## Verdict
GREEN | PARTIAL | BLOCKED
