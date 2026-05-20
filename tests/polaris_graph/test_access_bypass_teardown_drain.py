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
    install_teardown_drain_hook,
)


async def _truly_uncancellable() -> Any:
    """A backend whose cancellation-cleanup never returns.

    The handler swallows CancelledError, then re-enters an indefinite
    sleep. Even calling .cancel() on this task will not finalize it —
    the only escape is GeneratorExit via coro.close().
    """
    while True:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # Swallow cancellation; loop indefinitely.
            await asyncio.sleep(3600)


def test_teardown_drain_hook_unblocks_wedged_detached_backend(monkeypatch):
    """asyncio.run completes within bound even with a truly-uncancellable
    detached fetch backend on the loop.
    """
    # Tight timeouts so the test is fast.
    monkeypatch.setenv("PG_BACKEND_FETCH_TIMEOUT", "0.5")
    monkeypatch.setenv("PG_BACKEND_CLEANUP_GRACE", "0.5")

    async def _runner():
        # Install the drain hook on the current loop.
        install_teardown_drain_hook(asyncio.get_event_loop())
        # Trigger a detached backend.
        result = await _bounded_backend(
            "test_wedged", _truly_uncancellable(), "https://test.example/"
        )
        # _bounded_backend returns a failure within timeout + grace.
        assert result.success is False
        # The wedged task is now in _DETACHED_BACKEND_TASKS.
        assert len(_DETACHED_BACKEND_TASKS) >= 1
        return "ok"

    started = time.monotonic()
    out = asyncio.run(_runner())
    elapsed = time.monotonic() - started

    assert out == "ok"
    # Teardown must complete within a small bound. 5s gives headroom for
    # CI slowness but is well below the 3600s the wedged sleep would take.
    assert elapsed < 5.0, (
        f"asyncio.run teardown took {elapsed:.2f}s with a wedged "
        f"detached backend — _force_drop_detached_task hook did not work."
    )
    # After teardown the detached set should be empty (drain hook ran).
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
