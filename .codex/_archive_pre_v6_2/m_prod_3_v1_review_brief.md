# Codex round 1 — M-PROD-3 v1 (Production observability)

## Pre-flight
- Branch: `polaris`
- Commit: `4773d08`
- Brief format: lean autoloop V3

## Scope
Phase H third milestone per FINAL_PLAN. Exposes
`/api/inspector/metrics` with substrate invocation counters +
endpoint latency histograms.

## Tool hints
- Read: `src/polaris_graph/audit_ir/inspector_router.py:2887-`
  (M-PROD-3 block, ~120 lines)
- Run via TestClient:
  ```python
  client.get('/api/inspector/metrics')
  ```
  → expect 200 with substrate_invocations_total +
  endpoint_requests_total + endpoint_latency
- Public API for instrumentation:
  - `increment_substrate_counter(substrate_id)` — thread-safe
  - `record_endpoint_latency(endpoint, latency_ns)` — thread-safe
  - `_reset_metrics_for_test()` — test isolation

## Acceptance bar
1. **Endpoint exists.** GET /api/inspector/metrics registered.
2. **Counters thread-safe.** `_METRICS_LOCK` guards all reads
   and writes.
3. **Percentiles correct.** p50/p95/p99 from sorted-list
   index lookup.
4. **Rollback flag.** `PG_USE_METRICS_ENDPOINT=0` returns 404.
5. **Auth required.** `require_authenticated_caller` dep.
6. **Public instrumentation API.** `increment_substrate_counter`
   + `record_endpoint_latency` exported, called by Phase E
   substrates eventually (deferred to v2).

## Severity rubric
- **P0** — production-breaker: counter race; auth bypass;
  endpoint crashes; rollback flag broken
- **P1** — phase-rework: acceptance criterion not met
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Verify thread-safety of percentile path: snapshot under lock,
  compute outside lock — check no torn reads.
- Verify the percentile index formula is correct for edge
  cases (single value, even/odd count).

## Skepticism gate
List which files you read + line ranges + whether you actually
invoked the endpoint with seeded counters.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- Suggestions to use Prometheus text format (deferred to v2,
  documented in commit message)
- Suggestions to instrument every Phase E substrate now
  (deferred to v2 per docstring)
- Per-org filtering concerns (process-global by design,
  documented in docstring)

## Verdict format
```
## Files scanned
## Acceptance bar verification
## Findings
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 1 of 5 hard cap.
