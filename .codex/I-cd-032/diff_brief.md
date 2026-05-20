# Codex diff — I-cd-032 (#632) — teardown drain

Canonical-diff-sha256: `fcb656802cb605d20a4ce3175d22faa4efcf97e300d40cafacd1a8b6326c5a65` (iter 3; iter-1+iter-2 P0 fixes folded in).

## Iter-2 P0 fixes (this commit)
- `_polaris_cancel_all_tasks` uses `asyncio.wait(timeout=)` instead of `asyncio.wait_for(asyncio.gather(...))` — wait_for+gather still awaits child cleanup past the wall; wait does not.
- New `test_polaris_asyncio_run_drains_UNTRACKED_wedged_task` proves defense-in-depth path bounds an uncancellable task that is NOT in `_DETACHED_BACKEND_TASKS`.
- 3/3 tests pass in 5.19s.

## Iter-1 P0 fixes
- Replaced loop.close() hook (ran too late, AFTER _cancel_all_tasks) with `polaris_asyncio_run()`: drop-in for asyncio.run that drains `_DETACHED_BACKEND_TASKS` BEFORE its own `_polaris_cancel_all_tasks`.
- `_polaris_cancel_all_tasks` adds 2s hard wall + force-close fallback for OTHER wedged tasks not in the detached set.
- Rewrote test backend to swallow EVERY cancel iteration (was only first) via outer while-True + inner sleep + continue on CancelledError.
- 2/2 tests now pass with the polaris_asyncio_run path; standard asyncio.run path would hang indefinitely.

## Diff
- `src/tools/access_bypass.py`: add `_force_drop_detached_task` and `install_teardown_drain_hook`.
- `tests/polaris_graph/test_access_bypass_teardown_drain.py`: regression test asserting `asyncio.run` teardown completes within 5s with a truly-uncancellable detached backend on the loop. 2/2 tests pass.

## Risk checklist
1. `_coro.close()` — Python 3.11+ coroutine close raises GeneratorExit; cannot await. If the coroutine's GeneratorExit handler tries `await`, it raises a RuntimeError per PEP 492 (suppressed).
2. The hook overrides `loop.close()` — caller code that calls `loop.close()` directly still gets the drain. `asyncio.run` calls close at end.
3. `install_teardown_drain_hook` is intended to be called per-loop. Not yet wired into `run_one_query` — that's pipeline-A integration; this PR ships the primitive + the regression test.

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
