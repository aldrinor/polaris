HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001e diff iter 1 — SSE Redis Streams + Last-Event-ID + terminal events

The brief at `.codex/I-arch-001e/brief_iter_2.md` was APPROVE'd at iter 2. This is the diff implementation.

## Diff: `.codex/I-arch-001e/codex_diff.patch` (~720 LOC additive)

## Files changed (5)

1. **NEW `src/polaris_v6/queue/run_events.py`** (~215 LOC) — sync `emit_event`, sync `emit_terminal_event`, async `read_events` generator, `translate` mapper, `_validate_last_event_id`. Non-raising emit (catches ALL exceptions including bare Exception per Codex iter-2 P3). Async reader yields `("__keepalive__", {})` on empty XREAD window, synthetic `run.completed` terminal with `status=stream_unavailable` on Redis ConnectionError. Maxlen 10000 approximate trim.

2. **REWROTE `src/polaris_v6/api/stream.py`** — replaced canned 5-tuple stub with `_redis_stream_source` consuming `read_events`. SSE response includes `id: <stream_id>`, `event: <v6_name>`, `data: {run_id, ...}`. Honors `Last-Event-ID` header + `?last_event_id=` query param fallback. Skips keepalive events as SSE comment frames. Terminates after a v6 `run_complete`.

3. **PATCHED `scripts/run_honest_sweep_r3.py`** — added `from src.polaris_v6.queue.run_events import emit_event, emit_terminal_event` at top. Added one stage emit (`scope_gate.completed`) at line ~1184, and `emit_terminal_event(...)` calls inline at 5 abort exit paths (scope_rejected, no_sources, corpus_inadequate, corpus_approval_denied, no_verified_sections) plus one final emit at the function teardown that reads `summary.get("status")` / `manifest.get("status")` and maps `"error"`→`"error_unexpected"`. All guarded by `if q.get("v6_mode") and q.get("external_run_id"):` — non-v6 CLI sweep is byte-identical.

4. **NEW `tests/polaris_v6/queue/test_run_events.py`** (~222 LOC, 23 tests) — covers Last-Event-ID regex validation (7 parametrized cases), translator mapping (6 pipeline-A → v6), missing-run_id silent no-op, XADD entry shape, terminal event status carry, swallowed-exception path, round-trip via fakeredis, Last-Event-ID resume, Redis-unreachable synthetic terminal. Uses shared `fakeredis.FakeServer()` between sync + async clients.

5. **REWROTE `tests/v6/test_api_stream.py`** — replaced the Phase 0 stub regression with 4 fakeredis-backed integration tests against the new Redis-Streams endpoint: translator wiring through SSE response, terminal carries pipeline_status, Last-Event-ID header resume, Redis-down synthetic stream_unavailable terminal.

## Files I have ALSO checked clean (§-1.2 #2)

- `requirements.txt` + `requirements-v6.txt` — redis>=4.0 + redis==7.4.0 already pinned; `redis.asyncio` available in both
- `src/polaris_v6/queue/broker.py:48` — `POLARIS_V6_REDIS_URL` already standardized via env (default `redis://localhost:6379/0`); `_redis_url()` in run_events.py reuses the same env var
- `src/polaris_v6/api/app.py` — stream router import path unchanged
- `tests/polaris_v6/api/test_bundle_endpoint_targz.py` (I-arch-001d) — no overlap with stream endpoint
- `tests/v6/test_api_stream.py` — fully rewritten under the same path per brief iter-2 §P2 explicit guidance

## Test results

```
tests/polaris_v6/queue/test_run_events.py: 23 passed in 0.75s
tests/v6/test_api_stream.py: 4 passed in 1.04s
```

Pipeline-A AST parse: OK.

## Acceptance criteria from brief iter 2 — verification

1. **Single `emit_terminal_event` helper at all 7 pipeline-A return sites** — VERIFIED. 5 inline emits at the 5 abort `return summary` exits (lines 1352, 1488, 1708, 1793, 2356) + 1 final emit at the function teardown (line 2918, covering both success path + outer-exception path = 7 logical exits via 6 call sites).
2. **Non-raising emit + logger.warning on all exceptions** — VERIFIED. `test_emit_event_swallows_arbitrary_exceptions` passes against a BoomClient that raises RuntimeError (not RedisError) on every xadd.
3. **stream_unavailable only on Redis ConnectionError; empty window → keepalive** — VERIFIED. `read_events` yields `("__keepalive__", {})` on empty XREAD; only emits synthetic `stream_unavailable` terminal on connection-failure raise. `test_read_events_redis_unreachable_yields_synthetic_terminal` confirms.
4. **fakeredis for tests** — VERIFIED. Both test files use `fakeredis.FakeServer()` shared between sync `FakeStrictRedis` and async `fakeredis.aioredis.FakeRedis` so state is consistent.
5. **Last-Event-ID regex validation with fallback to "0-0"** — VERIFIED. `_validate_last_event_id` regex `^\d+-\d+$`; 7 parametrized cases cover empty / None / valid / malformed / partial-form.

## Direct questions iter 1

1. Single final-emit at the function teardown derives `_final_status` from `summary.get("status") || manifest.get("status")`, mapping the legacy `"error"` label to canonical `"error_unexpected"`. Acceptable, or want a strict `summary["status"] in CANONICAL_TAXONOMY` check that aborts the emit when not?
2. Only `scope_gate.completed` stage event is emitted (not the full 5). Terminal events at all 6 sites cover the SSE consumer's must-have for run-state. Acceptable for I-arch-001e's GREEN bar (terminal-events-first), with corpus_adequacy/evidence/strict_verify/generator stage emits captured as a follow-up under I-arch-001e-stage-events? Or are stage events a P1 blocker here?
3. fakeredis-based tests use `fakeredis.FakeServer()` instead of the connection_pool.connection_kwargs probe. Acceptable for hermetic CI, or want a real-Redis integration test guard added under `pytest.mark.integration`?
4. Anything else blocking iter-1 APPROVE?

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
