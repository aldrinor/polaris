"""I-cd-032 (#632) — asyncio.run teardown must not await a wedged
detached fetch backend.

Models the parent #552 acceptance: "a regression test models a backend
that ignores cancellation entirely and asserts the enclosing
asyncio.run still tears down within a bound."

The wedged-cancellation backend (from #551) bounds `_bounded_backend`
return — but the still-pending task remains on the loop. Without the
I-cd-032 `_force_drop_detached_task` shutdown hook, `asyncio.run`'s
_cancel_all_tasks would await that task indefinitely.

The test runs `asyncio.run(...)` of a coroutine that triggers a
detached backend, then asserts teardown completes within a small
wall-clock bound. Without the I-cd-032 fix this would hang past the
bound (in theory infinite, in practice Playwright's own SIGTERM saves
us in production — the test stub has no Playwright, so the wedge is
truly unbounded if untreated).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from src.tools.access_bypass import (
    _DETACHED_BACKEND_TASKS,
    _bounded_backend,
    polaris_asyncio_run,
)


async def _truly_uncancellable() -> Any:
    """A backend whose cancellation-cleanup never returns.

    EVERY iteration of the infinite loop catches CancelledError and
    re-enters sleep. asyncio.run's standard `_cancel_all_tasks` calls
    .cancel() once and awaits — which is intercepted again indefinitely.
    The only escape is GeneratorExit via `_coro.close()`, which
    polaris_asyncio_run triggers BEFORE the cancel-all-tasks phase.
    """
    while True:
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # Swallow EVERY cancellation; loop forever.
            continue


def test_polaris_asyncio_run_drains_wedged_detached_backend(monkeypatch):
    """polaris_asyncio_run completes within bound even with a truly-
    uncancellable detached fetch backend on the loop.

    Without the drain (e.g. with stdlib asyncio.run), the wedged
    detached task would hang the standard `_cancel_all_tasks` phase
    indefinitely because every cancel attempt is swallowed by the
    test backend's iterative CancelledError handler.
    """
    monkeypatch.setenv("PG_BACKEND_FETCH_TIMEOUT", "0.5")
    monkeypatch.setenv("PG_BACKEND_CLEANUP_GRACE", "0.5")

    async def _runner():
        result = await _bounded_backend(
            "test_wedged", _truly_uncancellable(), "https://test.example/"
        )
        assert result.success is False
        assert len(_DETACHED_BACKEND_TASKS) >= 1
        return "ok"

    started = time.monotonic()
    out = polaris_asyncio_run(_runner())
    elapsed = time.monotonic() - started

    assert out == "ok"
    assert elapsed < 5.0, (
        f"polaris_asyncio_run teardown took {elapsed:.2f}s with a "
        f"truly-uncancellable detached backend — drain did not work."
    )
    assert len(_DETACHED_BACKEND_TASKS) == 0


def test_force_drop_detached_task_handles_done_task():
    """Calling _force_drop_detached_task on an already-done task is a no-op."""
    from src.tools.access_bypass import _force_drop_detached_task

    async def _runner():
        task = asyncio.ensure_future(asyncio.sleep(0))
        await task
        # Task is done; the helper must not raise.
        _force_drop_detached_task(task)

    asyncio.run(_runner())
