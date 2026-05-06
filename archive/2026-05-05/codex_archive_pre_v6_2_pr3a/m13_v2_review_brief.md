M-13 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-13 v1 verdict: PARTIAL with 3 issues + 1 leak.

1. SSE hangs forever if client subscribes after prune.
2. subscribe-then-replay duplicates events emitted between the
   two non-atomic calls.
3. PREFLIGHT payload overwritten when "scope" phase emits.
4. (LEAK) _dispatch_to_subscriber swallowed RuntimeError on closed
   loop but left dead (queue, loop) registered.

All 4 integrated in v2 (commit d2ccce1).

## What changed

**Atomic subscribe+snapshot** (`progress_surfaces.SurfaceBus`):
- NEW `subscribe_with_snapshot(job_id) -> (queue, snapshot,
  is_terminal)`: snapshot read AND subscriber registration under
  the same lock. No event lands between the two.
- NEW `is_terminal(job_id)`: tracked via `_terminal_jobs: set`,
  populated by `prune()`. Allows SSE to short-circuit when a
  client subscribes after prune.
- When subscribe_with_snapshot is called on a terminal job, the
  queue is NOT registered (no leak, no false sentinel wait).

**Dead-queue sweep** (`SurfaceBus._dispatch_to_subscriber`):
- On `loop.call_soon_threadsafe RuntimeError` (closed loop), now
  calls `unsubscribe(job_id, q)` to remove the dead registration.

**SSE handler** (`inspector_router.stream_job_surfaces`):
- Uses `subscribe_with_snapshot()`. If `is_terminal=True` after
  snapshot replay, emits `event: end` immediately (no hang).
- Otherwise replays snapshot → live tail → sentinel triggers
  `event: end`.

**PREFLIGHT preservation** (`v30_runner._PHASE_TO_SURFACE`):
- Removed the `"scope" → PREFLIGHT` mapping. The runner's
  explicit emission at t=0 (with estimated_minutes,
  cost_cap_usd) is now the canonical PREFLIGHT source; the scope
  phase is a no-op for surface emission. The progress bar still
  moves via `control.checkpoint`.

**Tests: 9 new (5 unit + 3 API + 1 v30 invariant).**

Verified:
- subscribe_with_snapshot atomicity: each kind in the snapshot+
  live combination delivered exactly once.
- subscribe_with_snapshot when terminal: queue is not registered
  (internal subscriber-list count stays at 0).
- is_terminal pre/post prune.
- SSE post-prune completes within 2 seconds with `event: end`.
- SSE during subscribe-snapshot race: no duplicates.
- v30 _PHASE_TO_SURFACE['scope'] is not PREFLIGHT.

Phase B suite 396 → 405 green.

## Your job

Final verdict on M-13. GREEN / PARTIAL / DISAGREE.

If you find something else, please include the exact reproducer.

If GREEN, M-13 is locked AND Phase B is COMPLETE (all 6
milestones M-8 through M-13 locked).

## Output

Write to `outputs/codex_findings/m13_v2_review/findings.md`:

```markdown
# Codex re-review of M-13 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] SSE post-prune terminates immediately
- [x/no] No duplicate events in subscribe-snapshot race
- [x/no] PREFLIGHT payload survives "scope" phase
- [x/no] Dead-queue sweep on closed loop

## Phase B completion
With M-13 locked, is Phase B done?

## Final word
GREEN to lock M-13 + Phase B / PARTIAL with edits.
```

Be terse. Under 100 lines.
