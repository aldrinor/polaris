# Codex review of M-9

## Verdict
PARTIAL

## Specific issues
1. `src/polaris_graph/audit_ir/v30_runner.py:75-98`
   The phase matcher is not aligned to the real V30 sweep output. The checked-in phase-2 runs, including run-14, emit `[scope]`, `[retrieval]`, `[adequacy]`, `[generation]`, `[judge]`, `[eval_gate]`, `[V30-P2]`, `[V30]`, and `[status]`, not the canonical strings used here (`scripts/run_honest_sweep_r3.py:466-468,592,666-681,1052-1053,1094-1100,1201-1202,1693-1714,1750,1896-1923`; `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/run_log.txt:6,9,12,17-20,27,33-40,42`). Running the current classifier over run-14 only yields `generation_started` and `v30_phase1`, so a live job will effectively jump `1 -> 70 -> 90 -> completed`. Also, the current milestone order is not the script’s real order: `[V30-P2]` logs happen before evaluator/judge, while the `M-56` / `[V30]` lines happen after `eval_gate`. If you only add missing patterns without reordering milestones, progress will regress.

2. `scripts/run_honest_sweep_r3.py:426-433` and `src/polaris_graph/audit_ir/v30_runner.py:281-298`
   Artifact identity is not per-job. The sweep always writes to `out_root/<domain>/<slug>/`, and the runner resolves by `slug` plus newest mtime. Same-slug reruns therefore overwrite prior job artifacts even sequentially, and multi-process / future multi-worker runs would race on the same directory. Capturing `run_id` from stdout is not sufficient by itself; the output path also needs to become job-unique.

## Pause-unsupported handling
Yes. Do not ship `paused -> resume -> rerun from scratch` as if it were normal resume semantics. Prefer capability-based rejection at the API/router layer for `v30_clinical`. If that is too large for M-9, fail loudly on pause with a clear message instead of marking the job paused/resumable.

## Recommended changes
- Rebase phase detection on what the sweep actually emits, or better, instrument `run_honest_sweep_r3.py` to print explicit canonical markers. Then add a regression test against the checked-in run-14 log or a distilled excerpt. A live `PG_RUN_LIVE=1` sweep test is not necessary here.
- Make the child output root job-unique, e.g. pass `cfg.out_root / job.job_id` (or a run-id-scoped root) so the final artifact path is deterministic and immutable per job.
- Keep the subprocess model. On Windows this is acceptable for the current single-child sweep: `wait()` means no zombie parent, but `terminate()` is a hard kill, not graceful shutdown. If the sweep later starts spawning child processes, move to a Job Object / process-group-based teardown.
- Checkpoint volume is fine. ~8700 SQLite updates over ~2h25m is about 1 write/sec on one row in WAL mode; not a blocker.

## M-10 readiness
The runner registry plumbing is fine for a curated template router. I would not lock M-9 as the M-10 base until phase telemetry matches the real sweep and artifact paths are job-isolated.

## Final word
PARTIAL with edits. The subprocess wiring and cancel path are acceptable, but the current phase telemetry is not validated against the real sweep, and artifact identity is not stable per job.
