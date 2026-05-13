# I-arch-001e Claude architect audit

**Issue:** GH#467 — SSE Redis Streams + async aredis + Last-Event-ID + terminal events
**Branch:** `bot/I-arch-001e-sse-redis-streams`
**Codex brief verdict:** APPROVE iter 2 of 5 (`.codex/I-arch-001e/codex_brief_verdict.txt`)
**Codex diff verdict:** APPROVE iter 2 of 5 (`.codex/I-arch-001e/codex_diff_audit_iter_2.txt`)

## Surface area shipped

| Component | Status |
|---|---|
| `src/polaris_v6/queue/run_events.py` (NEW, ~290 LOC) | sync `emit_event` (non-raising), sync `emit_terminal_event`, async `read_events` generator with run_store-aware completion + STREAM_LOST_GRACE_SECONDS window, `translate` mapper, `_validate_last_event_id` regex + fallback |
| `src/polaris_v6/api/stream.py` (REWRITTEN) | Replaces canned Phase 0 stub with Redis-Streams reader; honors `Last-Event-ID` HTTP header + `?last_event_id=` query fallback; SSE comment frame for keepalives |
| `scripts/run_honest_sweep_r3.py` (PATCHED) | 1 stage emit (scope_gate.completed) + 5 inline terminal emits at the abort early-returns + 1 final-teardown emit covering success + outer-exception (7 logical exit paths via 6 call sites). All v6_mode-guarded; non-v6 sweep is byte-identical. |
| `tests/polaris_v6/queue/test_run_events.py` (NEW, 26 tests) | Last-Event-ID regex (7 cases), translator (6 mappings + unknown + malformed), emit no-op without run_id, XADD shape, terminal status carry, non-raising emit, fakeredis round-trip, Last-Event-ID resume, Redis-unreachable stream_unavailable, non-connection ValueError → stream_lost, lifecycle-terminal-without-Redis-event → grace + stream_lost, lifecycle-in_progress → keepalives forever |
| `tests/v6/test_api_stream.py` (REWRITTEN, 4 tests) | translator wiring through SSE response, terminal carries pipeline_status, Last-Event-ID resume, Redis-down synthetic terminal |

## Test evidence

```
$ python -m pytest tests/polaris_v6/queue/test_run_events.py tests/v6/test_api_stream.py
30 passed in 1.33s
```

Pipeline-A AST parse: OK.

## Codex iter-1 diff finding (now closed)

**P1 (continuing iter-2 brief P1-3):** `read_events` was missing run_store-aware empty-window handling and was mapping every XREAD exception to `stream_unavailable`. Fixed in `run_events.py:174-280`:

- `_check_lifecycle_terminal(run_id)` async wrapper around `run_store.get_run` via `asyncio.to_thread`.
- `STREAM_LOST_GRACE_SECONDS = 10.0` module constant; first-seen-at tracked; synthetic `run_complete(status=stream_lost)` only after window elapses with no Redis terminal.
- `_is_connection_failure(exc)` narrows `stream_unavailable` to actual reachability failures (`ConnectionError`, `TimeoutError`, `OSError`, plus name-matched `redis.asyncio` types). Non-reachability XREAD exceptions degrade to `stream_lost` rather than misreporting backend outage.
- Three new regression tests added: `_non_connection_error_yields_stream_lost`, `_lifecycle_terminal_with_no_redis_event_emits_stream_lost`, `_lifecycle_still_running_keepalives_forever`.

## Verifications against acceptance criteria

| Criterion (from brief iter 2) | Status |
|---|---|
| `emit_terminal_event` helper at all 7 pipeline-A return sites | VERIFIED — 5 inline + 1 final-teardown = 7 logical exits |
| Non-raising emit + logger.warning on all exceptions | VERIFIED — `test_emit_event_swallows_arbitrary_exceptions` covers bare Exception |
| stream_unavailable only on Redis ConnectionError; empty → keepalive | VERIFIED — `_is_connection_failure` narrows; non-reachability → stream_lost |
| fakeredis for tests | VERIFIED — shared `FakeServer()` across sync + async clients |
| Last-Event-ID regex validation with fallback to "0-0" | VERIFIED — 7 parametrized cases |
| run_store-aware lifecycle terminal handling with grace window | VERIFIED — `_check_lifecycle_terminal` + `STREAM_LOST_GRACE_SECONDS` + 2 regression tests |

## Follow-up captured

- **I-arch-001e-stage-events (P2 from Codex iter-1 diff):** Add the 4 remaining pipeline-A stage emits (corpus_adequacy / evidence / strict_verify / generator) for progress UI. Terminal events are sufficient for SSE consumer's run-state per Codex iter-2 accept_remaining. Tracked as P2 follow-up Issue.

## Risk assessment

- **Pipeline-A non-v6 sweep correctness:** All emit calls guarded by `if q.get("v6_mode") and q.get("external_run_id"):`. CLI sweep code path is byte-identical.
- **Redis dependency surface:** lazy imports (`_get_sync_redis`, `redis.asyncio`). Tests do not require real Redis. Pipeline-A continues even when Redis observability fails.
- **run_store sqlite lookup cost:** Called only on empty XREAD windows (every ~5s under no event flow), via `asyncio.to_thread` so the SSE event loop is not blocked.

## Verdict

READY TO MERGE. All Codex required artifacts present:
- `.codex/I-arch-001e/brief.md` + `brief_iter_2.md`
- `.codex/I-arch-001e/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-arch-001e/codex_diff.patch`
- `.codex/I-arch-001e/codex_diff_audit_iter_2.txt` (APPROVE)
- `outputs/audits/I-arch-001e/claude_audit.md` (this file)
