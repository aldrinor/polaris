HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank for iter 6.
- Surface ALL findings now; do not hold back.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001e — SSE Redis Streams + async aredis + Last-Event-ID + terminal events

GH#467. Critical-path day 9-10. Replaces the canned demo events in stream.py with durable, replayable Redis-Streams-backed SSE.

## Files I have ALSO checked clean (§-1.2 #2)

- `src/polaris_v6/api/stream.py:33-44` — current `_phase_0_event_source` is a canned 5-tuple loop emitting `(scope_decision, retrieval_progress, evidence_id, verifier_verdict, section_complete, run_complete)` with hardcoded payloads
- `requirements.txt:N` — `redis>=4.0,<8.0` (supports `redis.asyncio`)
- `requirements-v6.txt` — `redis==7.4.0`
- `src/polaris_v6/queue/broker.py:48` — `POLARIS_V6_REDIS_URL` env (default `redis://localhost:6379/0`)
- `scripts/run_honest_sweep_r3.py` — pipeline-A logger-based stage events; need to add Redis Stream XADD calls

## Scope

1. NEW `src/polaris_v6/queue/run_events.py`:
   - `emit_event(external_run_id, event_type, payload, *, redis_client=None)` — non-async writer for pipeline-A (Dramatiq actor lives in sync thread). Uses `redis.Redis` (sync) with XADD to `polaris:events:{run_id}` stream. Trim with MAXLEN ~10000.
   - `read_events(external_run_id, last_id="0-0", *, redis_client_async)` — async generator yielding `(stream_id, event_dict)` via XREAD with 5s block. Used by SSE endpoint.
   - `EVENT_STREAM_KEY = "polaris:events:{run_id}"` constant.
   - Translator `_translate(pa_event) -> tuple[v6_event_name, v6_payload] | None` maps pipeline-A event types to the 6 canonical v6 names (scope_decision / retrieval_progress / evidence_id / verifier_verdict / section_complete / run_complete).
   - Terminal events: `run.completed`, `run.aborted` (each abort_*), `run.failed` → v6 `run_complete` with `payload.status` carrying the original pipeline_status.
2. REPLACE `src/polaris_v6/api/stream.py:_phase_0_event_source` with `_redis_stream_source(run_id, last_event_id)`:
   - Use `redis.asyncio` client
   - Honor `Last-Event-ID` HTTP header (FastAPI `Header(None, alias="Last-Event-ID")`) + `?last_event_id=` query param fallback
   - Emit each event with SSE `id: <stream_id>` so EventSource replays from last_id on reconnect
   - Yield keepalive comment every 5s no-data window
   - Terminate stream when v6 `run_complete` emitted
   - Fallback path: when POLARIS_V6_REDIS_URL unreachable OR no events in stream after 30s wait, emit a single `run_complete` with `payload.status="stream_unavailable"` and close (test compatibility with the old canned path)
3. Pipeline-A wiring: ~20 LOC additive in `scripts/run_honest_sweep_r3.py`:
   - After `set_current_run_id(run_id)` near line ~1133: call `emit_event(q.get("external_run_id"), "scope_gate.completed", {decision, reason})` etc. at the 5 stage transitions
   - Guarded by `if q.get("v6_mode") and q.get("external_run_id"):` — non-v6 sweep is byte-identical
4. Tests in `tests/polaris_v6/queue/test_run_events.py` + `tests/polaris_v6/api/test_stream_redis.py`:
   - emit + read round-trip (sync emit, async read)
   - Last-Event-ID resume (emit 3, read with last_id=stream_id_of_event_1 → only 2 + 3 returned)
   - Terminal event closes stream
   - Redis unreachable → fallback path emits stream_unavailable run_complete
   - Translator: each pipeline-A event_type → correct v6 name + payload mapping

## Acceptance criteria

1. NEW `run_events.py` with sync `emit_event` + async `read_events` + 6-event translator
2. stream.py uses Redis Streams (not canned tuples)
3. Last-Event-ID header support
4. Terminal `run_complete` on success/abort/error/stream_unavailable
5. Pipeline-A v6_mode-guarded emit calls at 5 stage sites
6. Tests pass; existing `tests/polaris_v6/api/test_stream.py` regression-safe (or updated)
7. LOC budget ~300

## Direct questions iter 1

1. sync `redis.Redis` + XADD in pipeline-A emit (since Dramatiq actor + sweep CLI are sync) + async `redis.asyncio` in SSE reader — APPROVE'd?
2. MAXLEN ~10000 stream trim — APPROVE'd?
3. Fallback "stream_unavailable" when Redis unreachable after 30s — APPROVE'd, or want hard 503?
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
