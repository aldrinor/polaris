M-13 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-13 v2 verdict: PARTIAL with 1 LEAK. _terminal_jobs grew
unbounded; reproducer:

  for i in range(10000):
      bus.prune(f"job_{i}")
  assert len(bus._terminal_jobs) == 10000  # grew forever

Integrated in v3 (commit fe368dc).

## What changed in v3

`progress_surfaces.SurfaceBus`:
- New `terminal_cap` constructor param (default 1024).
- `_terminal_jobs` switched from `set` to `OrderedDict[str, None]`
  for FIFO insertion-order tracking.
- `prune()`:
  * Re-prune of an existing job_id calls `move_to_end()`
    (refreshes position, no growth).
  * New job_id is inserted, then while-loop pops oldest items
    until size ≤ terminal_cap.

Tests: 3 new.
- test_terminal_jobs_set_is_bounded_with_fifo_eviction:
  100 prunes with cap=10 → exactly 10 retained, oldest 90
  evicted; oldest job_ids no longer report terminal.
- test_re_prune_same_job_id_does_not_grow_set: 20 re-prunes of
  the same job_id → size stays at 1.
- test_terminal_cap_default_is_reasonable: default ≥ 1024.

Phase B suite 405 → 408 green.

## Your job

Final verdict on M-13. GREEN / PARTIAL / DISAGREE.

If GREEN, M-13 is locked AND Phase B is COMPLETE (all 6
milestones M-8 through M-13 locked).

## Output

Write to `outputs/codex_findings/m13_v3_review/findings.md`:

```markdown
# Codex final review of M-13 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 leak fix
- [x/no] _terminal_jobs is bounded with FIFO eviction
- [x/no] Re-prune of same job_id doesn't grow the set

## Phase B completion
With M-13 locked, is Phase B done?

## Final word
GREEN to lock M-13 + Phase B / PARTIAL with edits.
```

Be terse. Under 60 lines.
