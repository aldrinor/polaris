M-D10 phase 1 review (commit 7bece98).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D M-D10 (citation freshness monitoring). Pairs with
M-D7 retrieval cache (commit 74b8962, GREEN-locked) via
evict_by_url hookup. Per advisor: tight scope, threat-model
doc shipped with v1 (NOT as round-N response).

This commit ships **bootstrap detector contract + alerts
substrate**. Phase 2 (real Crossref/PubMed detectors +
polling daemon + operator notification callbacks) deferred.

## Files

`src/polaris_graph/audit_ir/freshness_monitor.py`:
  - FreshnessStatus enum: unchanged | superseded | retracted |
    unreachable
  - FreshnessCheckResult: detector return shape
  - FreshnessAlert: persisted record
  - FreshnessDetector Protocol (caller injects)
  - FreshnessAlertStore: M-21 substrate, freshness_alerts
    table with CHECK constraint enforcing taxonomy at SQL
    layer
    - record / list_alerts / latest_for_url / count
    - 3 indexes (ws+time, ws+status, ws+url+time)
  - check_freshness() coordinator: detect → conditionally
    evict_by_url(M-D7 cache) → record alert
  - Clock injected for testability (FixedClock pattern)

`tests/polaris_graph/test_md10_freshness_monitor.py`: 26 tests.

`docs/md10_phase1_threat_model.md`: scope, eviction contract,
phase-2 deferred work, pin coupling boundary (mirrors M-D7).

## Eviction contract

  - superseded / retracted → evict cache + record alert
  - unchanged / unreachable → record alert only (transient
    outages don't justify dropping valid cache)
  - If evict raises → exception propagates, alert NOT recorded
    (record-after-evict contract: never claim eviction
    succeeded when it didn't)

## Your job

GREEN / PARTIAL / DISAGREE.

1. **Scope cut**: detector contract + storage + cache eviction
   coordination. Phase 2 = real fetchers + daemon. Right cut?

2. **Status taxonomy completeness**: 4 statuses
   (unchanged/superseded/retracted/unreachable). Anything
   missing? (e.g. expression-of-concern as separate from
   retracted? errata? embargo lifted?)

3. **Eviction-error propagation**: cache.evict raises →
   monitor re-raises → alert NOT recorded. Correct semantics,
   or should we record a "cache_eviction_failed" alert?

4. **Detector protocol shape**: `detect(source_url) ->
   FreshnessCheckResult`. Phase 2 detectors will need
   internal state (HTTP session, rate limiter) — is this the
   right interface or should it be class-based with explicit
   lifecycle?

5. **CHECK constraint at SQL layer**: defense-in-depth on the
   taxonomy. Right call, or unnecessary belt-and-suspenders?

6. **Pin coupling**: alert state workspace-scoped, NOT in
   ModelPin (mirrors M-D7). Documented in threat-model doc.
   Right boundary?

7. **Phase 2 readiness**: with phase 1 substrate stable, can
   real Crossref/PubMed detectors + daemon layer cleanly?

## Output

`outputs/codex_findings/md10_phase1_review/findings.md`:

```markdown
# Codex review of M-D10 phase 1 (commit 7bece98)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [scope concern, if any]
- [taxonomy gap, if any]
- [eviction-error contract concern, if any]
- [detector protocol concern, if any]
- [SQL CHECK concern, if any]
- [pin coupling concern, if any]
- [phase-2 readiness concern, if any]

## Final word
GREEN to lock M-D10 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
