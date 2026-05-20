# Codex brief — I-cd-032 (#632) — retrieval-concurrency teardown drain

Parent #552: asyncio.run teardown can await a detached fetch backend whose cancellation cleanup wedges. Fix:
- `_force_drop_detached_task(task)`: closes `task._coro` via `_coro.close()` (raises GeneratorExit; cleanup runs sync; task finalizes as cancelled).
- `install_teardown_drain_hook(loop)`: wraps `loop.close()` to drain `_DETACHED_BACKEND_TASKS` before standard teardown.
- Regression test models a truly-uncancellable backend (swallows CancelledError + re-enters indefinite sleep). `asyncio.run(...)` of a runner triggering a detached backend asserts teardown < 5s (wedged sleep is 3600s). Without the hook → hangs. With the hook → 2/2 tests pass.
