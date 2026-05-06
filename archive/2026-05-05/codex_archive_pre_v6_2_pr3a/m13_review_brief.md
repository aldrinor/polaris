M-13 progressive in-run Inspector surfaces — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-12 GREEN-locked across 3 review rounds. M-13 is the final
Phase B milestone per FINAL_PLAN feature #2:

> Replace the 2h25m blank-stare problem with milestone-driven
> Inspector state.
>
> | t (min) | Surface |
> | 0       | Pre-flight estimate          |
> | 0-2     | Upload/parse progress        |
> | 2-15    | Live source discovery + tier |
> | 15-45   | Frame coverage manifest      |
> | 45-90   | Contradiction queue          |
> | 90-120  | First verified claim cards   |
> | 120-145 | Final synthesis              |

After this lands, all six Phase B milestones (M-8 through M-13)
are complete.

## What landed (commit 1d15304)

**`src/polaris_graph/audit_ir/progress_surfaces.py`** (~210 lines):
- `SurfaceKind` enum: PREFLIGHT, PARSE_PROGRESS, TIER_MIX,
  FRAME_COVERAGE, CONTRADICTION_QUEUE, VERIFIED_CLAIM,
  SYNTHESIS_COMPLETE — exactly the 7 from FINAL_PLAN's t-table.
- `SurfaceEvent`: frozen dataclass (job_id, kind, payload,
  emitted_at), JSON-serializable.
- `SurfaceBus`: in-memory pub-sub.
  - `emit(job_id, kind, payload)`: records latest snapshot per
    kind, broadcasts to all subscriber queues for this job_id.
  - **Cross-thread safety**: producers (V30 worker drain thread)
    are NOT in the SSE event loop. asyncio.Queue.put_nowait from
    another thread doesn't wake `await q.get()`. Fix: capture
    each subscriber's loop at subscribe time, dispatch puts via
    `loop.call_soon_threadsafe`.
  - Bounded queues (default 64); drop-oldest on overflow so a
    slow consumer can't pin memory.
  - `prune(job_id)`: drops snapshot + sentinel-None to all
    subscribers so their SSE loops exit. Sentinel also dispatched
    via call_soon_threadsafe.

**`v30_runner.py`**:
- `_PHASE_TO_SURFACE` map from V30 phase keys to the t-table
  milestone they represent (15 phase keys → 7 surface kinds, with
  several phases sharing kinds — e.g. retrieval/corpus →
  TIER_MIX, contradict → CONTRADICTION_QUEUE).
- Initial `control.checkpoint()` is followed by an explicit
  PREFLIGHT emission so the Inspector renders scope/cost/time at
  t=0. Cost cap from `PG_MAX_COST_PER_RUN` env (LAW VI).
- After every successful per-phase checkpoint, emit the mapped
  surface kind with payload including phase key, progress_pct,
  message, and a 300-char tail of the log line.
- Best-effort: bus failures are logged but never fail the run.

**`job_worker.py`**:
- `_prune_surfaces()` called on every terminal transition
  (mark_cancelled, mark_failed, mark_completed). Best-effort —
  never fails the worker.

**`inspector_router.py`** — 2 new endpoints:
- `GET /api/inspector/jobs/{job_id}/surfaces`: snapshot dict
  with the latest event per surface kind. Returns 404 if the
  job_id is unknown to the queue.
- `GET /api/inspector/jobs/{job_id}/stream`: SSE stream.
  Subscribes FIRST, then replays snapshot, then live tails.
  Emits `event: end` + `data: {}` on prune so the client knows
  the stream closed cleanly. Cache-Control + X-Accel-Buffering
  headers prevent proxy buffering.

**Tests: 24 new (18 unit + 6 API). Phase B suite 372 → 396.**

Unit tests cover: emission, snapshot (latest-per-kind, ordered,
isolated per job), subscribe/unsubscribe (idempotent, isolated),
bounded queue drop-oldest under slow-consumer pressure, prune
(clears snapshot, signals subscribers, no-op on unknown), all 7
canonical kinds present.

API tests cover: snapshot 404, snapshot empty, snapshot returns
emitted events, SSE 404, SSE replays snapshot then terminates on
prune, SSE delivers post-subscribe events from a producer thread.

## Anti-scope (deferred — please do NOT push back)

- Persistence of surface history beyond the latest snapshot
  (DB-backed event log) — Phase C.
- Multi-process Postgres LISTEN/NOTIFY scaling — Phase C.
- Frontend Inspector wiring (the React shells from Phase A) —
  Phase C M-13.5.
- Authentication/authorization on the SSE endpoint — Phase C.

## Your job

Code review for M-13. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Cross-thread safety.** `SurfaceBus._dispatch_to_subscriber`
   uses `loop.call_soon_threadsafe`. Are there race conditions
   I missed (loop closed before dispatch lands, lock held during
   the threadsafe call, etc.)?

2. **Memory bounded.** Subscribers can't fall behind forever
   (queue_size=64 default; drop-oldest on overflow). Prune drops
   the snapshot. Are there leak paths I missed (e.g.
   subscriber's loop closes but unsubscribe isn't called)?

3. **SSE termination.** The stream emits `event: end` on prune
   and returns. Test verifies this. Is the framing correct
   (data: ... blank line)?

4. **V30 surface emission semantics.** PREFLIGHT fires at t=0
   regardless of phase log. Other surfaces fire when their phase
   is first detected in run_log.txt. Is the mapping correct per
   FINAL_PLAN's t-table?

5. **Pause/cancel interaction.** Surfaces emit BEFORE the
   per-phase checkpoint that converts Paused → RuntimeError. So
   on pause, the last surface seen is the phase BEFORE the
   pause-triggering one. Acceptable, or should we emit a
   "pause_unsupported" surface explicitly?

6. **Missing surfaces.** PARSE_PROGRESS isn't emitted by the V30
   runner because V30 doesn't upload/parse files. M-11
   workspace_store could emit PARSE_PROGRESS during upload, but
   that's not wired in this commit. Acceptable (the API is
   ready; producers are added incrementally), or blocker?

7. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m13_review/findings.md`:

```markdown
# Codex review of M-13

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Cross-thread safety
Is the call_soon_threadsafe pattern airtight?

## Memory bounds
Any leak paths?

## Recommended changes
If PARTIAL.

## Phase B completion readiness
With M-13 locked, is Phase B done?

## Final word
GREEN to lock M-13 + Phase B / PARTIAL with edits / DISAGREE.
```

Be terse. Under 250 lines.
