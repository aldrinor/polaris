M-8 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-8 v2 verdict: STILL-PARTIAL on one issue — resume endpoint did
not start the singleton worker, leaving cold-restart resumes stranded.
Fixed in v3.

## What changed

1. **resume_job()** now calls `get_or_start_job_worker()` after the
   paused→pending transition, ensuring the reclaim actually happens
   even after a cold restart.

2. **New test**: `test_resume_endpoint_starts_worker_after_cold_restart`
   — sets up a paused job WITHOUT auto-starting a worker, hits resume,
   verifies the worker singleton becomes alive and the resumed job
   reaches terminal state.

3. **Eliminated test flakiness** identified during 10× stability runs:
   - `test_resume_after_pause_reaches_terminal`: replaced with
     synchronous variant using `worker.run_one()` so the
     pending→running→paused→pending→completed cycle is deterministic.
   - `test_pause_endpoint_sets_flag`,
     `test_cancel_endpoint_sets_flag_on_running`,
     `test_list_jobs_filters_by_status`: refactored to bypass
     auto-start enqueue endpoint and use direct `queue.enqueue()` for
     deterministic state transitions.
   - Relaxed status assertions in cold-start + list tests to accept
     any non-error status (auto-worker may race-claim before response).
   - Added autouse fixture in conftest.py that resets all M-8
     singletons on every test entry/exit.
   - `_set_job_queue_for_tests` now stops active workers before
     swapping the queue.

Stability: 10 consecutive runs, 0 failures.
Full suite: 233/233 tests pass (Phase A + M-8 v3).

## Your job

Final verdict on M-8. GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- Does resume endpoint really start the worker?
- Cold-restart resume reaches terminal?
- Test flakes addressed?
- Anything else?

## Output

Write to `outputs/codex_findings/m8_v3_review/findings.md`:

```markdown
# Codex final review of M-8 v3

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix verification
- [x/no] resume endpoint starts worker
- [x/no] cold-restart resume reaches terminal

## New issues
none / list

## M-9 readiness
Is M-8 ready to lock for V30 wiring?

## Final word
GREEN to lock M-8 / STILL-PARTIAL with edits.
```

Be terse. Under 80 lines.
