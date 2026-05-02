M-8 Phase B Job Queue infrastructure — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase A is GREEN-locked (174/174 tests, 7 modules). Now starting Phase B
per FINAL_PLAN.md. M-8 is the foundation: SQLite-backed durable JobQueue
+ JobWorker + JobRunner abstraction + 6 Inspector router endpoints.

Top-2 user-wishlist demand from real-source research:
1. "Pause / cancel / redirect a long-running run" (9+ named users)
2. "Durable long-running jobs — don't lose state/report" (11 sources)

Both addressed by M-8.

## What landed

Files:
- `src/polaris_graph/audit_ir/job_queue.py` (~430 lines):
  SQLite-backed JobQueue with WAL mode, per-call connections,
  ALLOWED_TRANSITIONS state machine, claim_pending atomic via
  UPDATE-WHERE, record_progress persists checkpoint state.
- `src/polaris_graph/audit_ir/job_runner.py`:
  JobRunner ABC + JobControl (checkpoint() raises Cancelled/Paused)
  + MockJobRunner + register_runner registry.
- `src/polaris_graph/audit_ir/job_worker.py`:
  JobWorker background thread, claim_pending poll, cooperative
  exception handling, run_one() synchronous variant for tests.
- `inspector_router.py`: 6 endpoints (POST jobs, GET list, GET id,
  POST pause/cancel/resume).

Tests: 174 → 226 (52 new):
- 25 queue tests (schema, persistence, transitions, atomic claim
  under threading)
- 8 worker tests (cooperative pause + cancel + resume, drain queue)
- 19 router tests (6 endpoints × happy path + 400/404/409)

## Your job

Code review for M-8. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **State machine correctness.** ALLOWED_TRANSITIONS table at the top
   of job_queue.py — does it cover every legitimate transition? Are
   there transitions I forgot or shouldn't have allowed? Specifically:
   - paused → running via resume_paused (yes)
   - paused → cancelled via mark_cancelled (yes)
   - pending → cancelled directly (yes, via request_cancel — bypasses
     a worker pickup)
   - paused → failed (allowed; runner could fail mid-resume)

2. **Atomicity of claim_pending().** I use SELECT-then-UPDATE-WHERE-status.
   Two workers in different threads racing should get exactly one
   winner. Tested with 8 threads. Is the pattern robust under SQLite
   isolation? Should I use BEGIN IMMEDIATE for stronger guarantees?

3. **Pause/cancel are cooperative, not preemptive.** Workers must call
   control.checkpoint() to honor requests. A buggy/long-running runner
   that never checkpoints will ignore pause/cancel forever. Acceptable
   for Phase B, or should I add a watchdog that mark_failed()s after
   N seconds without checkpoint?

4. **resume_paused does NOT re-run the runner.** It just transitions
   the row back to running. The original worker thread that was
   inside runner.run() already exited via JobControl.Paused. For
   actual resume-from-checkpoint, the worker would need to re-claim
   the job (status='running' isn't pickable by claim_pending which
   targets 'pending'). This is a Phase B gap. How should I close it?
   - Option A: resume_paused transitions to 'pending' instead of
     'running'
   - Option B: claim_pending also picks up 'running' jobs that have
     no live worker (needs heartbeat tracking)
   - Option C: dedicated `claim_paused()` method for resume workers

5. **Per-call connections vs connection pool.** Every method opens
   and closes a connection. SQLite is fine with this, but at hundreds
   of jobs/sec we'd want pooling. Phase B scale is 3-5 concurrent
   audit jobs so this is fine — but flagging.

6. **Checkpoint serialization.** Stored as JSON in checkpoint_json
   column. Mappings are converted via dict() before serialization.
   No size limit enforced. A misbehaving runner could OOM the row.
   Should I cap checkpoint size at e.g. 1 MB?

7. **API surface.** 6 endpoints feel right for Phase B. SSE streaming
   of job events (M-13) will add a 7th. Anything missing?

8. **Singleton queue + test isolation.** I use a module-level
   _job_queue with a _set_job_queue_for_tests() escape hatch.
   Is this acceptable, or should the router accept a Depends() injection?

9. **Anything else.**

## Output

Write to `outputs/codex_findings/m8_review/findings.md`:

```markdown
# Codex review of M-8

## Verdict
GREEN / PARTIAL / DISAGREE

## State machine + atomicity
Concrete issues.

## Resume-from-checkpoint gap
Which option (A/B/C) or alternative.

## Specific issues
file:line bugs / gaps.

## Recommended changes
If PARTIAL.

## M-9 readiness
Is the runner abstraction ready for the V30 sweep?

## Final word
GREEN to lock M-8 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 300 lines.
