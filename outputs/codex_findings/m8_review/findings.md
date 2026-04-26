# Codex review of M-8

## Verdict
PARTIAL

## State machine + atomicity
- `claim_pending()` exclusivity is okay as written. `UPDATE ... WHERE status='pending'` is enough to prevent double-claim under SQLite/WAL; `BEGIN IMMEDIATE` is not required for correctness, only if you want to avoid spurious `None` returns under contention.
- The larger issue is the paused-side state machine. In the current control flow, `JobControl.Paused` exits `runner.run()`, and the worker returns after `mark_paused()`. That means no live executor remains attached to a `paused` job. Under that model, `paused -> running` is not a real transition; it strands the row. The legitimate Phase B resume edge is `paused -> pending`, not `paused -> running`. `paused -> failed` is also not a real runtime edge today unless you add a distinct `resuming` state or worker heartbeat/ownership.

## Resume-from-checkpoint gap
- Recommend Option A, with one extra rule: `resume_paused()` should do `paused -> pending`, clear `pause_requested`, keep `checkpoint_json`, and let a fresh worker claim the job and rerun `runner.run(job, control)` from `job.checkpoint`.
- Do not take Option B for Phase B; heartbeat ownership and stale-running recovery are a much larger design.
- Option C buys little over A and still requires fresh-run-from-checkpoint semantics.
- With A, `request_cancel()` on `paused` should transition directly to `cancelled`, because paused jobs are quiescent.

## Specific issues
1. `src/polaris_graph/audit_ir/inspector_router.py:336-343`
   `enqueue_job()` validates `template_id` before `get_job_queue()` runs. On a cold process the runner registry is empty, so `POST /api/inspector/jobs` rejects `"mock"` with 400 until some other endpoint initializes the queue. I reproduced this directly.
2. `src/polaris_graph/audit_ir/inspector_router.py:62-77`
   The router never constructs or starts a `JobWorker`. Enqueued jobs stay `pending` indefinitely in the actual app path. I reproduced `list_jobs()` -> `enqueue_job(mock)` -> sleep -> `get_job()` and status remained `pending`.
3. `src/polaris_graph/audit_ir/job_queue.py:285-300`, `src/polaris_graph/audit_ir/job_worker.py:106-108`, `src/polaris_graph/audit_ir/job_queue.py:209-234`
   `resume_paused()` sets `status='running'`, but `claim_pending()` only pulls `pending` and the original worker has already exited after `JobControl.Paused`. A resumed job is stranded in `running` and never progresses.
4. `src/polaris_graph/audit_ir/job_queue.py:270-283`
   `request_cancel()` on `paused` only sets `cancel_requested=1`. Because paused jobs are already quiescent, this also strands the job unless resume logic later requeues it. The user-visible cancel path is incomplete for paused jobs.
5. `tests/polaris_graph/test_job_worker.py:148-176`, `tests/polaris_graph/test_job_router.py:154-166`
   The resume tests currently encode the broken behavior: they assert only that status flips back to `running`, not that a resumed job is reclaimable and reaches terminal state.
6. `tests/polaris_graph/test_job_router.py:23-26`
   The fixture pre-registers `mock`, which masks the router cold-start bug above.

## Recommended changes
- In router init, call `get_job_queue()` before validating templates, or move runner registration out of `get_job_queue()` into deterministic startup.
- Add explicit app-lifespan wiring for a singleton `JobWorker` and start/stop it with the app.
- Change resume to `paused -> pending`; add `paused -> pending` to the allowed graph and remove `paused -> running` unless you also add worker ownership/heartbeat. Consider removing `paused -> failed` too under the current model.
- Make `request_cancel()` on `paused` transition directly to `cancelled`.
- Add one end-to-end test: cold-start `POST /jobs` with no prior route hit, plus one resume test that proves pause -> resume -> completed/cancelled.

## M-9 readiness
- `JobRunner` / `JobControl` is good enough for M-9 V30 wiring once resume semantics are fixed. Passing the full `Job` snapshot into `runner.run()` already gives the runner access to `job.checkpoint`; no ABC reshaping is needed.
- I would not lock M-8 GREEN until the startup wiring and paused-job lifecycle are corrected, because M-9 depends on jobs actually being enqueueable and runnable in the app path.

## Final word
PARTIAL with edits.
