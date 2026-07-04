"""I-deepfix-001 (#1344): FIX-QM2 concurrent-fetch late-racer double-resolution
guard.

The FIX-QM2 concurrent fetch races Crawl4AI (Playwright subprocess) + Jina +
Trafilatura (thread-pool executor) + the clinical-PDF mineru CLI (asyncio
subprocess). A slow racer that is `_bounded_backend`-cancelled at its wall-clock
keeps its underlying subprocess / executor alive. When that abandoned worker
completes LATE — after a faster racer already won and the gather returned, and
even during loop teardown — the library / asyncio transport internals schedule a
`loop.call_soon(future.set_result, None)` on a future that is already done.
`Future.set_result` on a done future raises `asyncio.InvalidStateError`, which
asyncio's Handle runner routes to `loop.call_exception_handler`; the default
handler logs it as a scary "Exception in callback Future.set_result(None)".

These tests reproduce the EXACT routing (a `call_soon(fut.set_result, None)` on
an already-resolved future, run one tick) so they exercise the real
`call_exception_handler` path — NOT a synchronous double `set_result`, which
would never reach the handler.

RED (no guard): the default/recording handler DOES see the InvalidStateError.
GREEN (guard installed): the guard swallows exactly that benign case, delegates
every other exception, and stays active AFTER the orchestration entry returns
(mirroring the real post-gather / teardown timeline where the error fires).
"""

from __future__ import annotations

import asyncio

import pytest

from src.tools.access_bypass import (
    PG_FETCH_LATE_RACER_RACE_GUARD_ENV,
    _install_late_racer_double_resolve_guard,
    _is_late_racer_double_resolution,
    reset_late_racer_guard_state,
)


@pytest.fixture(autouse=True)
def _reset_guard_state():
    """Forget guarded loops before AND after each test (the WeakSet is module
    state)."""
    reset_late_racer_guard_state()
    yield
    reset_late_racer_guard_state()


def _schedule_late_double_resolution(loop: asyncio.AbstractEventLoop) -> None:
    """Reproduce the observed error EXACTLY: resolve a future (the fast racer
    winning), then schedule a SECOND `set_result(None)` via `call_soon` (the slow
    abandoned racer completing late) and run one tick so the Handle runner
    executes it and routes the InvalidStateError through `call_exception_handler`.
    """
    fut = loop.create_future()
    fut.set_result(None)  # fast racer wins / future already done
    loop.call_soon(fut.set_result, None)  # late racer double-resolves
    loop.run_until_complete(asyncio.sleep(0.02))  # run the ready queue one tick


# ---------------------------------------------------------------------------
# RED: without the guard, the benign late double-resolution reaches the handler.
# ---------------------------------------------------------------------------


def test_red_default_handler_sees_late_double_resolution():
    loop = asyncio.new_event_loop()
    seen: list[dict] = []
    loop.set_exception_handler(lambda _loop, ctx: seen.append(ctx))
    try:
        _schedule_late_double_resolution(loop)
    finally:
        loop.close()

    invalid_state = [
        ctx for ctx in seen
        if isinstance(ctx.get("exception"), asyncio.InvalidStateError)
    ]
    # This is the bug: the abandoned late racer's double `set_result` surfaces as
    # a logged asyncio InvalidStateError.
    assert invalid_state, (
        "expected the un-guarded loop to surface the late-racer "
        "InvalidStateError to its exception handler"
    )
    # And it IS the set_result-on-a-done-future shape the guard targets.
    assert _is_late_racer_double_resolution(invalid_state[0])


# ---------------------------------------------------------------------------
# GREEN: the guard swallows exactly that case and delegates everything else.
# ---------------------------------------------------------------------------


def test_green_guard_swallows_late_double_resolution():
    loop = asyncio.new_event_loop()
    delegate_seen: list[dict] = []
    # A recording handler stands in for whatever handler was installed before us
    # (default handler in production). The guard must DELEGATE non-matching
    # exceptions to it and NOT hand it the benign late-racer InvalidStateError.
    loop.set_exception_handler(lambda _loop, ctx: delegate_seen.append(ctx))
    try:
        _install_late_racer_double_resolve_guard(loop)
        _schedule_late_double_resolution(loop)
    finally:
        loop.close()

    swallowed = [
        ctx for ctx in delegate_seen
        if isinstance(ctx.get("exception"), asyncio.InvalidStateError)
    ]
    assert not swallowed, (
        "guard must SWALLOW the benign late-racer InvalidStateError, not pass it "
        "to the delegate handler"
    )


def test_green_guard_delegates_other_exceptions():
    loop = asyncio.new_event_loop()
    delegate_seen: list[dict] = []
    loop.set_exception_handler(lambda _loop, ctx: delegate_seen.append(ctx))
    try:
        _install_late_racer_double_resolve_guard(loop)
        # A genuine, unrelated error must still reach the previous handler.
        loop.call_exception_handler(
            {"message": "boom", "exception": ValueError("real bug")}
        )
    finally:
        loop.close()

    assert any(
        isinstance(ctx.get("exception"), ValueError) for ctx in delegate_seen
    ), "guard must delegate non-late-racer exceptions to the previous handler"


def test_green_guard_delegates_unrelated_invalid_state_error():
    """Narrowness: an InvalidStateError WITHOUT set_result / set_exception
    provenance (e.g. a genuine `task.result()`-before-done bug) must NOT be
    swallowed — real bugs stay visible."""
    loop = asyncio.new_event_loop()
    delegate_seen: list[dict] = []
    loop.set_exception_handler(lambda _loop, ctx: delegate_seen.append(ctx))
    try:
        _install_late_racer_double_resolve_guard(loop)
        loop.call_exception_handler(
            {
                "message": "Task exception was never retrieved",
                "exception": asyncio.InvalidStateError("invalid state"),
            }
        )
    finally:
        loop.close()

    assert any(
        isinstance(ctx.get("exception"), asyncio.InvalidStateError)
        for ctx in delegate_seen
    ), "an InvalidStateError with no set_result provenance must be delegated"


def test_green_guard_still_active_after_orchestration_returns():
    """Mirror the real timeline: `fetch_with_bypass` installs the guard at its
    top and RETURNS; the late-racer error fires much later (post-gather /
    teardown). The guard must still be active then (it is never restored)."""
    loop = asyncio.new_event_loop()
    delegate_seen: list[dict] = []
    loop.set_exception_handler(lambda _loop, ctx: delegate_seen.append(ctx))
    try:
        # Simulate the fetch_with_bypass entry: install, then return.
        def _orchestration_entry():
            _install_late_racer_double_resolve_guard(loop)

        _orchestration_entry()
        # ... time passes, gather has returned ... now the abandoned racer lands.
        _schedule_late_double_resolution(loop)
    finally:
        loop.close()

    assert not any(
        isinstance(ctx.get("exception"), asyncio.InvalidStateError)
        for ctx in delegate_seen
    ), "guard must remain active after the orchestration entry returns"


def test_green_install_is_idempotent_per_loop():
    """Installing twice on the same loop must not double-wrap or clobber the
    delegate captured on the FIRST install."""
    loop = asyncio.new_event_loop()
    delegate_seen: list[dict] = []
    loop.set_exception_handler(lambda _loop, ctx: delegate_seen.append(ctx))
    try:
        _install_late_racer_double_resolve_guard(loop)
        first_handler = loop.get_exception_handler()
        _install_late_racer_double_resolve_guard(loop)
        second_handler = loop.get_exception_handler()
        assert first_handler is second_handler, (
            "second install must be a no-op (idempotent per loop)"
        )
        # Still swallows and still delegates correctly.
        _schedule_late_double_resolution(loop)
        loop.call_exception_handler(
            {"message": "boom", "exception": ValueError("real bug")}
        )
    finally:
        loop.close()

    assert not any(
        isinstance(ctx.get("exception"), asyncio.InvalidStateError)
        for ctx in delegate_seen
    )
    assert any(
        isinstance(ctx.get("exception"), ValueError) for ctx in delegate_seen
    )


# ---------------------------------------------------------------------------
# Predicate unit coverage (narrowness both ways).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context, expected",
    [
        (
            {
                "message": "Exception in callback Future.set_result(None)",
                "exception": asyncio.InvalidStateError("invalid state"),
            },
            True,
        ),
        (
            {
                "message": "Exception in callback Future.set_exception()",
                "exception": asyncio.InvalidStateError("invalid state"),
            },
            True,
        ),
        (
            {
                "message": "Task exception was never retrieved",
                "exception": asyncio.InvalidStateError("invalid state"),
            },
            False,
        ),
        (
            {
                "message": "Exception in callback Future.set_result(None)",
                "exception": ValueError("not an invalid-state error"),
            },
            False,
        ),
        ({"message": "no exception key at all"}, False),
    ],
)
def test_predicate_is_narrow(context, expected):
    assert _is_late_racer_double_resolution(context) is expected


# ---------------------------------------------------------------------------
# Kill-switch: PG_FETCH_LATE_RACER_RACE_GUARD=0 reverts to the noisy default.
# ---------------------------------------------------------------------------


def test_kill_switch_disables_install(monkeypatch):
    monkeypatch.setenv(PG_FETCH_LATE_RACER_RACE_GUARD_ENV, "0")
    loop = asyncio.new_event_loop()
    seen: list[dict] = []
    loop.set_exception_handler(lambda _loop, ctx: seen.append(ctx))
    try:
        _install_late_racer_double_resolve_guard(loop)
        # Handler is unchanged (guard not installed) -> it still sees the error.
        _schedule_late_double_resolution(loop)
    finally:
        loop.close()

    assert any(
        isinstance(ctx.get("exception"), asyncio.InvalidStateError)
        for ctx in seen
    ), "with the kill-switch set, the guard must NOT be installed"
