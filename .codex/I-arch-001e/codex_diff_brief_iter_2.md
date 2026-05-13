HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001e diff iter 2 — P1-1 fix: run_store-aware completion + narrowed stream_unavailable

## Iter 1 finding addressed

**P1 (continuing iter-2 brief P1-3) — run_events.py:188-191:** approved P1-3 behavior was missing. Empty XREAD windows always yielded keepalive forever; reader never checked run_store, so if lifecycle reached completed/failed but the terminal Redis event was lost, /stream never emitted the synthetic run_complete(status=stream_lost) and clients hung indefinitely. Same area mapped every XREAD exception to stream_unavailable rather than only Redis connection failures.

### Fix (src/polaris_v6/queue/run_events.py)

1. **run_store-aware empty-window handling.** On empty XREAD windows, after yielding the SSE keepalive, the reader now calls `_check_lifecycle_terminal(run_id)` (async wrapper around `run_store.get_run`, run via `asyncio.to_thread`). When lifecycle_status is in `{completed, failed}`, the reader tracks `lifecycle_terminal_first_seen` and only after `STREAM_LOST_GRACE_SECONDS` (10s default) without a Redis terminal does it synthesize `run_complete(status=stream_lost)` and close. While lifecycle is queued/in_progress, keepalives continue forever — no false terminal.

2. **Narrowed stream_unavailable.** `_is_connection_failure(exc)` checks instance for `(ConnectionError, TimeoutError, OSError)` plus name-matches `{"ConnectionError", "TimeoutError", "BusyLoadingError", "ConnectionResetError", "RedisConnectionError"}` to handle `redis.asyncio` connection types without a hard import dependency. Only true reachability failures map to `stream_unavailable`; other XREAD exceptions degrade to `stream_lost`.

3. **`_get_lifecycle_status` is best-effort.** Lazy-imports `run_store`, returns None on any exception. Failure of the run_store lookup never propagates — keepalives continue. Tests cover this via monkeypatch.

### Test additions (tests/polaris_v6/queue/test_run_events.py)

Three new tests (now 26 in this file, total 30 across run_events + stream):

- `test_read_events_non_connection_error_yields_stream_lost`: XREAD raising `ValueError` → stream_lost (NOT stream_unavailable). Pins the connection-vs-other distinction.
- `test_read_events_lifecycle_terminal_with_no_redis_event_emits_stream_lost`: monkeypatched `_get_lifecycle_status` returns `"completed"`; shrunk `STREAM_LOST_GRACE_SECONDS` to 0.05s; SSE emits keepalives then a synthetic stream_lost terminal.
- `test_read_events_lifecycle_still_running_keepalives_forever`: monkeypatched lifecycle returns `"in_progress"`; SSE emits 3 keepalives without ever synthesizing a terminal. Confirms stream_lost is gated on lifecycle_status terminal, not just any quiet period.

## Iter-1 P2 — Pipeline-A stage event coverage

Iter 1 P2 flagged "only scope_gate.completed emitted; corpus_adequacy/evidence/strict_verify/generator missing." Captured as follow-up: tracked in I-arch-001e-stage-events (new sub-issue to file) — terminal events are the must-have for SSE consumer's run-state, present at all 7 logical exit paths via 6 call sites (5 abort early-returns + 1 unified teardown). The 4 additional stage emits are P2 nice-to-have for progress UI and do NOT block terminal-event correctness or the deployment-readiness gate.

## Iter-1 P3 — accepted as-is

- Final-emit status derivation from manifest.status: accepted (Codex iter-1 confirmed acceptable, no strict taxonomy abort needed).
- fakeredis-only tests: accepted (Codex iter-1 confirmed hermetic CI is acceptable).
- 27→30 passing tests including the 3 new P1 regression tests.

## Diff

`.codex/I-arch-001e/codex_diff.patch` — 1173 lines (was 948); +225 LOC for the P1 fix region (~100 production + ~125 tests).

## Test results

```
tests/polaris_v6/queue/test_run_events.py: 26 passed
tests/v6/test_api_stream.py: 4 passed
Total: 30 passed in 1.33s
```

## Direct questions iter 2

1. Is the P1-3 implementation as described (run_store sqlite lookup via `asyncio.to_thread`, 10s grace, narrow connection-failure detection) sufficient to APPROVE? Or do you want the grace seconds to be a module-level constant settable via env var (`POLARIS_V6_SSE_STREAM_LOST_GRACE_SECONDS`)?
2. Iter-1 P2 stage events deferred to follow-up — acceptable given terminal events are present at all 7 exit paths, or do you want me to add the 4 remaining stage emits in this iter for completeness?
3. Anything else blocking iter-2 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
