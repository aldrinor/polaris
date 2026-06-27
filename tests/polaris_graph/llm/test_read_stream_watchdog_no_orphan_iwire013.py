"""I-wire-013 (#1327) iter-3b LANE B — streaming watchdog must not orphan the inner read task.

The streaming branch of ``OpenRouterClient._call_impl`` used to bound ``_read_stream`` with
``asyncio.wait_for(self._read_stream(...), timeout=...)``. ``wait_for`` wraps the coroutine in a
SEPARATE child task; when the watchdog fires (or a ``ConnectTimeout`` propagates) the cancellation can
race that child task's own exception, leaving it unretrieved -> asyncio logs
``"Task exception was never retrieved"``. It is BENIGN (the retry loop recovers, no response is lost)
but noisy. The fix runs ``_read_stream`` inside an ``asyncio.timeout()`` context manager, so it
executes in the CALLER'S task — there is no child task to orphan.

These tests are HERMETIC / OFFLINE: ``_read_stream`` is monkeypatched, no socket is opened, no live
LLM is called. NO faithfulness gate is touched — this is a transport-noise fix, behaviour-identical on
both the success and the timeout paths.
"""

from __future__ import annotations

import asyncio
import gc

import pytest

from src.polaris_graph.llm import openrouter_client


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Fix the OpenRouter key and reset the global 402 circuit breaker so a prior test cannot
    short-circuit ``_call_impl`` before it reaches the streaming branch."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    monkeypatch.setattr(
        openrouter_client.OpenRouterClient, "_billing_exhausted", False, raising=False
    )
    yield


async def _noop_async_sleep(*_a, **_k):
    """No-op replacement for ``asyncio.sleep`` so retry backoff does not actually wait. Does NOT
    disable the watchdog: ``asyncio.timeout`` schedules its cancellation via ``loop.call_at``, not
    ``asyncio.sleep``."""
    return None


def test_normal_stream_returns_through_asyncio_timeout(monkeypatch):
    """A healthy ``_read_stream`` (returns a normal 4-tuple) flows through the ``asyncio.timeout``
    context manager unchanged and ``_call_impl`` returns the accumulated content."""
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")

    async def _ok_stream(body, timeout):
        return (
            "hello world",
            "",
            {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "finish_reason": "stop"},
            {"provider": "Novita"},
        )

    monkeypatch.setattr(client, "_read_stream", _ok_stream)
    resp = asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "q"}],
            call_type="generate",
            reasoning_enabled=False,
        )
    )
    assert resp.content == "hello world"


def test_watchdog_timeout_does_not_orphan_inner_stream_task(monkeypatch):
    """The watchdog fires while ``_read_stream`` is mid-flight AND the stream raises during its
    cancellation teardown. Two invariants:

      (1) STRUCTURAL — ``_read_stream`` runs in the SAME asyncio task as ``_call_impl`` (no child
          task exists), so there is nothing that can be left orphaned. Under the old
          ``asyncio.wait_for`` the inner coroutine ran in a distinct child task.
      (2) BEHAVIOURAL — the loop's exception handler never receives a "Task exception was never
          retrieved" report, even after a forced GC.
    """
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
    # Shrink the watchdog grace so the timeout fires near-immediately on the tiny per-call timeout.
    monkeypatch.setattr(openrouter_client, "LLM_CALL_WATCHDOG_GRACE_SECONDS", 0.02)
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")

    captured: dict[str, object] = {}

    async def _slow_then_raise_on_cancel(body, timeout):
        captured["inner_task"] = asyncio.current_task()
        try:
            # Block until the watchdog cancels us. Event().wait() awaits a future (no asyncio.sleep),
            # so the no-op sleep patch above does not let it return early.
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # The inner stream raises during teardown — the exact shape that, under wait_for,
            # orphaned a child task whose exception was never retrieved.
            raise RuntimeError("SSE teardown raised during cancellation")
        return "", "", {}, {}

    monkeypatch.setattr(client, "_read_stream", _slow_then_raise_on_cancel)

    handler_contexts: list[dict] = []
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, context: handler_contexts.append(context))
    try:

        async def _drive():
            captured["caller_task"] = asyncio.current_task()
            return await client._call_impl(
                messages=[{"role": "user", "content": "q"}],
                call_type="generate",
                reasoning_enabled=False,
                timeout=0.01,
            )

        # After MAX_RETRIES the teardown RuntimeError re-raises (the except-RuntimeError retry path).
        with pytest.raises(RuntimeError):
            loop.run_until_complete(_drive())

        # (1) No child task was ever spawned — the stream ran in the caller's task.
        assert captured["inner_task"] is captured["caller_task"]

        # Give any (non-existent) orphaned-task finalizers a chance to fire, then assert none did.
        gc.collect()
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        loop.close()

    assert not any(
        "never retrieved" in str(ctx.get("message", "")).lower() for ctx in handler_contexts
    ), f"unexpected unretrieved-task-exception reported to the loop handler: {handler_contexts}"
