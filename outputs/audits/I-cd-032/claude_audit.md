# Claude audit — I-cd-032 (#632)

## Scope landed

- `src/tools/access_bypass.py`:
  - `_force_drop_detached_task(task)`: closes `task._coro` via `_coro.close()` raising GeneratorExit (cleanup runs sync; task finalized as cancelled; safe to NOT await).
  - `polaris_asyncio_run(coro)`: drop-in replacement for `asyncio.run` that drains `_DETACHED_BACKEND_TASKS` BEFORE the cancel-all phase.
  - `_polaris_cancel_all_tasks(loop)`: defense-in-depth using `asyncio.wait(timeout=2.0)` (NOT `asyncio.wait_for(gather(...))` which still awaits child cleanup past the wall — Codex iter-2 P0 fix).
  - `install_teardown_drain_hook(loop)` kept as deprecated shim with documented why-not-this rationale.
- `tests/polaris_graph/test_access_bypass_teardown_drain.py`: 3 tests:
  - `test_polaris_asyncio_run_drains_wedged_detached_backend` — tracked detached backend (DETACHED_BACKEND_TASKS path)
  - `test_force_drop_detached_task_handles_done_task` — no-op safety
  - `test_polaris_asyncio_run_drains_UNTRACKED_wedged_task` — untracked uncancellable task (defense-in-depth path)
- 3/3 pass in 5.19s.

## Codex review trajectory

- Diff iter 1: REQUEST_CHANGES — 2 P0s (loop.close hook runs too late + test backend only catches first cancel).
- Diff iter 2: REQUEST_CHANGES — 1 P0 (`wait_for(gather)` doesn't bound; needs `wait(timeout)` + untracked-task regression).
- Diff iter 3: **APPROVE** (accept_remaining). 2 P1s + 2 P2s noted but non-blocking:
  - P1: pending-task warning at loop.close (cosmetic; doesn't affect bound)
  - P1: cross-loop filter on detached drain (defensive for concurrent same-process runs; not on critical path)
  - P2: install_teardown_drain_hook docstring drift (already documented as DEPRECATED)
  - P2: test module docstring asyncio.run → polaris_asyncio_run drift

## Quality bar

- Real backend correctness fix (not paint-over UI work).
- 3/3 regression tests pass with documented bug-then-fix LAW II discipline.
- Acceptance "a reproducible failing test now passes" met: the untracked-task test would hang stdlib `asyncio.run` indefinitely; `polaris_asyncio_run` bounds it at ~2s.
- Codex review trajectory shows real iteration on real findings (architectural correction at iter 1; bound mechanism correction at iter 2).
