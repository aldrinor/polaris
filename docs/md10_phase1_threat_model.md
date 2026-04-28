# M-D10 phase 1 — citation freshness monitoring boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/freshness_monitor.py`
**Tests:** `tests/polaris_graph/test_md10_freshness_monitor.py` (26 passing)
**Pairs with:** M-D7 retrieval cache (commit 74b8962) — eviction hook
**Substrate:** M-21 SQLite per-workspace, one extra `freshness_alerts` table

---

## Scope

Phase 1 ships **detector contract + alerts substrate**:

- `FreshnessDetector` protocol — caller injects real Crossref /
  PubMed / retraction-watch implementations or test stubs
- `FreshnessAlertStore` — SQLite-backed alert log,
  per-workspace isolated (matches M-21 / M-D7 pattern)
- `check_freshness()` coordinator — runs detector, evicts M-D7
  cache on retracted/superseded, persists alert
- `FreshnessStatus` taxonomy: `unchanged | superseded |
  retracted | unreachable`
- CHECK constraint on the SQL column enforces taxonomy at the
  DB layer (defense-in-depth even if a future caller bypasses
  the enum)

Phase 2 (deferred):
- Real Crossref `update-policy` integration
- Real PubMed retraction-status integration
- Polling daemon (watches a workspace's cited URLs on schedule)
- Operator notification callbacks (writes into M-23 review
  queue when alert lands)
- Empirical alert-latency ≤ 24h acceptance test
- Retry-with-backoff for `unreachable` status (transient
  outages shouldn't promote to retracted)

---

## What phase 1 protects against

| Threat | Mitigation |
|---|---|
| Stale cached source after retraction | `check_freshness` calls `RetrievalCacheStore.evict_by_url` on `retracted`/`superseded`. |
| Cached source after superseding revision | Same eviction path; `new_canonical_url` recorded in alert for operator follow-up. |
| Transient outage flushing valid cache | `unreachable` status records the alert but does NOT evict — phase 2 daemon retries with backoff before deciding to evict. |
| Silent eviction when cache is broken | If `evict_by_url` raises, the exception propagates and the alert is NOT recorded. The alert log never claims eviction succeeded when it didn't. |
| Non-deterministic alert-latency tests | `clock` is injected (`Callable[[], float]`); tests use `FixedClock(t)` to assert deterministic `checked_at`. |
| Cross-workspace alert leakage | Every read/write requires `workspace_id`; queries filter on it. Same M-21 / M-D7 isolation contract. |
| Future taxonomy drift | SQL CHECK constraint blocks invalid status strings at the DB layer; `FreshnessStatus` enum blocks at API. |
| Detector coupling at import time | `FreshnessDetector` is a `Protocol`. Phase 1 has no concrete detector implementation — phase 2 will inject Crossref/PubMed. |

---

## Boundary (what phase 1 does NOT do)

### Phase 1 is record-only

When `check_freshness` returns a `retracted` alert:
- ✅ The alert lands in `freshness_alerts` table
- ✅ The M-D7 cache (if provided) is evicted
- ❌ No operator notification fires
- ❌ No M-23 review-queue entry is created
- ❌ No email / Slack / dashboard alert

Phase 2 wires in the operator-notification callback. Phase 1
provides the substrate so phase 2 can layer the callback
without rewriting storage or detection.

### Detector implementations are deferred

The `FreshnessDetector` protocol is the contract. Phase 1
ships:
- The protocol shape
- A test stub (`StubDetector`) that returns a fixed result

Phase 1 does NOT ship:
- Crossref `update-policy` parser
- PubMed `PublicationStatus` integration
- Retraction Watch DOI checker
- Generic HTTP HEAD request fetcher

Those are phase 2 + per-source implementations. Each will be a
separate class implementing `FreshnessDetector`.

### No polling daemon

Phase 1's `check_freshness` is a synchronous, one-shot call.
The caller decides when to invoke it — typically from a phase-2
daemon that walks a workspace's cited URLs on a schedule.

The daemon itself is phase 2. Phase 1 is library code; phase 2
adds the loop, scheduling, and rate-limit handling.

### Pin coupling — same boundary as M-D7

Freshness alert state is workspace-scoped, NOT in
`ModelPin.retrieval_source_versions` (which is run-scoped).
Two pins captured at different times for the same workspace
may have different freshness alert histories without the pins
themselves diverging.

This matches the M-D7 cache decision (see
`docs/md11_phase1_threat_model.md` for the M-D11 pin contract).
If phase 2 needs pin-time freshness state for replay, a new
`workspace_revision` field can be added to the pin in v5.

---

## Eviction contract details

Statuses that trigger eviction:
- `superseded`
- `retracted`

Statuses that do NOT trigger eviction:
- `unchanged` (no change detected)
- `unreachable` (transient outage; phase 2 will retry)

Eviction-error propagation: if the cache raises during
`evict_by_url`, the exception bubbles up and the alert is NOT
persisted. This is intentional — recording an alert that
claims `evicted_cache_key=X` while the eviction silently
failed would mislead phase 2's review-queue downstream.

---

## Phase 2 contract (for future detector + daemon work)

When implementing phase 2, the daemon must:

1. For each cited URL in a workspace's audit history, call
   `check_freshness(workspace_id, url, detector, store, cache,
   clock)` on a schedule (e.g. every 24 hours).
2. After `check_freshness` returns a non-`unchanged` alert,
   notify operators via M-23 review queue (out-of-scope for
   phase 1).
3. For `unreachable` alerts, retry with exponential backoff
   (1h → 6h → 24h → mark as superseded if persistent). Phase 2
   may add a `consecutive_failures` column for this.

---

## Codex review trail

Round-1 brief incoming. Phase 1's tight scope + threat-model-
with-v1-commit pattern (per advisor) targeted at 2-round
convergence.

---

## Lock note

Phase 1 GREEN-lock is the target after Codex round 1-2.
Phase 2 (real detectors + daemon + notification callback)
tracked separately. M-D7 phase 1 + M-D10 phase 1 together
close the "stale cached source = faithfulness liability"
risk that M-D7's design doc flagged.
