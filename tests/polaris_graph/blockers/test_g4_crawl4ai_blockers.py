"""I-pipe-002 (#1227): crawl4ai chromium cross-loop semaphore regression tests.

THE BUG
-------
`src/tools/access_bypass.py` held the crawl4ai browser-concurrency gate as a
SINGLE module-global `asyncio.Semaphore`. `live_retriever._fetch_content` runs
each bypass fetch on a fresh daemon thread, each with its OWN `asyncio.run`
loop. An `asyncio.Semaphore` binds (Python 3.11/3.12 `_LoopBoundMixin`) to the
loop that first WAITS on it. The first worker thread's loop wins; every other
worker loop that contends then raises
`RuntimeError: <Semaphore ...> is bound to a different event loop` inside
`async with`, crashing the fetch -> EPIPE -> ~159 distinct JS-rendered journal
sources (Oxford/Cambridge) never fetched.

THE FIX (default-ON kill-switch `PG_CRAWL4AI_PERLOOP_SEMAPHORE`)
---------------------------------------------------------------
Keep one `asyncio.Semaphore` PER running loop, looked up inside the async
context by the loop OBJECT via a `weakref.WeakKeyDictionary`. Each worker loop
acquires a semaphore bound to ITSELF -> no cross-loop `RuntimeError`. Setting
`PG_CRAWL4AI_PERLOOP_SEMAPHORE=0` reverts to the old single-global behavior.

CONTENTION MATTERS (why these tests force a waiting acquire)
------------------------------------------------------------
`asyncio.Semaphore.acquire()` only calls `_get_loop()` (the loop-binding step)
when the semaphore is already LOCKED and the caller must WAIT. An uncontended
acquire (value > 0) takes the fast path and never touches the loop, so it would
NOT raise even on the old global path. Verified empirically (2026-06-12):
two sequential uncontended acquires on two loops both return True. To exercise
the real binding the tests set PG_CRAWL4AI_CONCURRENCY=1, drain the one slot,
then attempt a SECOND acquire that must wait — that is what binds the loop and
makes the OFF test raise / the ON test discriminating instead of vacuous.

These tests assert:
  (a) flag-OFF (old global path) == current/broken behavior: a CONTENDED acquire
      on the SECOND loop raises the cross-loop RuntimeError (failure mode).
  (b) flag-ON (default, per-loop path): the same CONTENDED pattern SUCCEEDS on
      both loops.

Pure reliability: nothing here touches strict_verify, the NLI judge, the 4-role
audit, or any provenance/verification gate. The fix changes only whether an
already-selected fetch crashes cross-loop, never WHICH urls are fetched.
"""

import asyncio

import pytest

from src.tools import access_bypass


@pytest.fixture(autouse=True)
def _reset_semaphore_state():
    """Reset BOTH semaphore holders before AND after each test so the ON and OFF
    cases never see each other's leftover module-global / per-loop state."""
    access_bypass.reset_crawl4ai_semaphore_state()
    yield
    access_bypass.reset_crawl4ai_semaphore_state()


# Short wait so the SECOND (contended) acquire blocks long enough to enter the
# loop-binding wait path, then times out instead of hanging the test.
_CONTENTION_WAIT_SECONDS = 0.02


def _drain_then_contend_in_fresh_loop():
    """Create a brand-new event loop (mirrors a bypass worker thread). With
    PG_CRAWL4AI_CONCURRENCY=1, acquire the single slot (fast path, no bind) then
    attempt a SECOND acquire that must WAIT — that wait is what binds the
    semaphore to this loop and exercises the cross-loop check.

    Returns True if both the drain and the (timing-out) contended acquire ran
    without a cross-loop RuntimeError. Raises RuntimeError if the semaphore is
    bound to a different (closed) loop — the #1227 failure mode.
    """
    loop = asyncio.new_event_loop()
    try:

        async def _drain_then_wait():
            sem = access_bypass._get_crawl4ai_semaphore()
            await sem.acquire()  # value 1 -> 0, fast path, no loop bind
            try:
                # Must WAIT (value 0) -> enters _get_loop() -> binds THIS loop.
                await asyncio.wait_for(sem.acquire(), _CONTENTION_WAIT_SECONDS)
            except (asyncio.TimeoutError, TimeoutError):
                pass  # expected: nobody releases the slot
            return True

        return loop.run_until_complete(_drain_then_wait())
    finally:
        loop.close()


def _uncontended_acquire_in_fresh_loop():
    """Plain `async with` acquire in a fresh loop (uncontended fast path). Used
    only to show the fix never raises on the simple path either."""
    loop = asyncio.new_event_loop()
    try:

        async def _use_gate():
            async with access_bypass._get_crawl4ai_semaphore():
                return True

        return loop.run_until_complete(_use_gate())
    finally:
        loop.close()


def test_perloop_default_on_two_loops_contended_both_succeed(monkeypatch):
    """FLAG-ON (default): two independent loops each CONTEND on their own per-loop
    semaphore and both succeed. This is the #1227 fix — no cross-loop
    RuntimeError even on the waiting/binding path. Discriminating: the old global
    path raises on loop 2 under this exact pattern."""
    monkeypatch.delenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", raising=False)
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "1")
    assert access_bypass._crawl4ai_perloop_enabled() is True

    assert _drain_then_contend_in_fresh_loop() is True  # first worker loop
    assert _drain_then_contend_in_fresh_loop() is True  # second loop — must NOT raise


def test_perloop_explicit_on_two_loops_contended_both_succeed(monkeypatch):
    """FLAG-ON (explicit '1'): same contended pattern — both loops succeed."""
    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "1")
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "1")
    assert access_bypass._crawl4ai_perloop_enabled() is True

    assert _drain_then_contend_in_fresh_loop() is True
    assert _drain_then_contend_in_fresh_loop() is True


def test_perloop_off_reproduces_cross_loop_runtimeerror(monkeypatch):
    """FLAG-OFF ('0') == OLD/BROKEN behavior: the single module-global semaphore
    binds (on the first CONTENDED wait) to the first loop; a contended acquire on
    the SECOND loop raises the cross-loop RuntimeError.

    Documents the original failure mode AND proves the OFF path is the pre-#1227
    behavior. Must force contention: an uncontended acquire never binds the loop
    and would not raise (verified empirically)."""
    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "0")
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "1")
    assert access_bypass._crawl4ai_perloop_enabled() is False

    # First loop drains + contends -> binds the GLOBAL semaphore to itself.
    assert _drain_then_contend_in_fresh_loop() is True

    # Second loop reuses the SAME global object, bound to the (now closed) first
    # loop. Its contended acquire enters the wait path -> cross-loop RuntimeError.
    loop2 = asyncio.new_event_loop()
    try:

        async def _contended_acquire():
            sem = access_bypass._get_crawl4ai_semaphore()  # same global object
            await sem.acquire()  # may fast-path (value reset? no — same locked obj)
            await asyncio.wait_for(sem.acquire(), _CONTENTION_WAIT_SECONDS)
            return True

        with pytest.raises(RuntimeError, match="different event loop"):
            loop2.run_until_complete(_contended_acquire())
    finally:
        loop2.close()


def test_perloop_off_global_object_is_shared_across_loops(monkeypatch):
    """FLAG-OFF: the accessor returns the SAME global object across loops (the
    root cause). Proves OFF == the old single-global behavior."""
    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "0")
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "2")

    captured = []

    def _capture():
        loop = asyncio.new_event_loop()
        try:

            async def _get():
                return access_bypass._get_crawl4ai_semaphore()

            return loop.run_until_complete(_get())
        finally:
            loop.close()

    captured.append(_capture())
    captured.append(_capture())
    assert captured[0] is captured[1]  # one shared global across both loops


def test_perloop_on_distinct_object_per_loop(monkeypatch):
    """FLAG-ON: the accessor returns a DISTINCT semaphore object per loop (the
    fix). Different loops -> different per-loop semaphores."""
    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "1")
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "2")

    def _capture():
        loop = asyncio.new_event_loop()
        try:

            async def _get():
                return access_bypass._get_crawl4ai_semaphore()

            return loop.run_until_complete(_get())
        finally:
            loop.close()

    sem_a = _capture()
    sem_b = _capture()
    assert sem_a is not sem_b  # distinct per-loop semaphores


def test_perloop_on_uncontended_two_loops_succeed(monkeypatch):
    """FLAG-ON: the plain uncontended `async with` path also succeeds on two
    loops (no regression on the common case)."""
    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "1")
    monkeypatch.delenv("PG_CRAWL4AI_CONCURRENCY", raising=False)

    assert _uncontended_acquire_in_fresh_loop() is True
    assert _uncontended_acquire_in_fresh_loop() is True


def test_perloop_same_loop_returns_cached_semaphore(monkeypatch):
    """FLAG-ON: within ONE loop the accessor returns the SAME cached semaphore on
    repeated calls (proves the per-loop map is keyed by the live loop)."""
    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "1")
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "2")

    loop = asyncio.new_event_loop()
    try:

        async def _twice():
            sem1 = access_bypass._get_crawl4ai_semaphore()
            sem2 = access_bypass._get_crawl4ai_semaphore()
            assert sem1 is sem2
            async with sem1:
                pass
            return True

        assert loop.run_until_complete(_twice()) is True
    finally:
        loop.close()


def test_concurrency_value_honored_and_malformed_falls_back(monkeypatch):
    """The concurrency VALUE is unchanged by the fix: PG_CRAWL4AI_CONCURRENCY is
    honored; a malformed/<=0 value falls back to the default 2 (a bad knob must
    never disable the bound)."""
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "5")
    assert access_bypass._crawl4ai_concurrency() == 5

    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "0")
    assert access_bypass._crawl4ai_concurrency() == 2

    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "not-an-int")
    assert access_bypass._crawl4ai_concurrency() == 2

    monkeypatch.delenv("PG_CRAWL4AI_CONCURRENCY", raising=False)
    assert access_bypass._crawl4ai_concurrency() == 2


def test_perloop_map_does_not_grow_unbounded(monkeypatch):
    """FLAG-ON: the per-loop holder is a WeakKeyDictionary. Uncontended worker
    loops that are GC'd should not accumulate unbounded entries over a long run.

    NOTE: a per-loop semaphore that has BOUND a loop (only under contention)
    holds a strong ref to that loop via `sem._loop`, and the dict's strong value
    ref then keeps the key alive (entry persists). This test uses the
    UNCONTENDED path (sem._loop stays None) so eviction applies; the bound-loop
    retention caveat is disclosed in the StructuredOutput `risk` for #1227."""
    import gc

    monkeypatch.setenv("PG_CRAWL4AI_PERLOOP_SEMAPHORE", "1")
    monkeypatch.delenv("PG_CRAWL4AI_CONCURRENCY", raising=False)

    for _ in range(8):
        _uncontended_acquire_in_fresh_loop()  # created, used, closed, dropped
    gc.collect()

    assert len(access_bypass._crawl4ai_perloop_semaphores) < 8
