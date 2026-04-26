# Codex re-review of M-8 v2

## Verdict
STILL-PARTIAL

## Fix integration
- [x] State machine paused → pending (and direct paused → cancelled)
- [x] Cold-start runner registration
- [x] Auto-started JobWorker
- [x] Cancel on paused directly terminates

## New issues
- `POST /api/inspector/jobs/{job_id}/resume` does not start the singleton worker. In-process resume works because the original worker is still polling, but after a cold restart the resumed job flips to `pending` and stays there until some later enqueue happens. That leaves the restart/resume path partially stranded.

## M-9 readiness
Almost, not fully. The `JobRunner` abstraction is usable for V30 wiring and does pass `job.checkpoint` back into `runner.run(...)` on reclaim, but the cold-start resume path should start a worker (or otherwise drain pending jobs) before M-9 is locked.

## Final word
STILL-PARTIAL with one edit: start the worker on `/resume` (or on any path that returns a job to `pending`) and add a cold-start resume regression test.
