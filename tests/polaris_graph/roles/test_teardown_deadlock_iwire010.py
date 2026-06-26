"""I-wire-010 (#1324): the final-phase futex-deadlock teardown fix — offline, no live calls.

THE DEADLOCK: on a 4-role D8 seam-wall timeout the main thread escapes and writes the HELD manifest +
terminal events, but the orphaned seam worker keeps an inner claim ThreadPoolExecutor whose NON-DAEMON
workers park in `AdaptiveConcurrencyController.acquire()` -> `self._cond.wait()`. At interpreter exit the
stdlib atexit join of those workers hangs forever on a futex — even though every artifact is on disk.

THE FIX, proven here without any network/spend:
  1. `AdaptiveConcurrencyController.release_all()` wakes EVERY parked acquirer so a real
     `pool.shutdown(wait=True)` join completes instead of hanging (real-pool tests below).
  2. `release_all_adaptive_controllers()` drives that across the per-role registry.
  3. the process-level teardown WALL force-exits a wedged interpreter past the atexit join
     (injectable exit_fn so the assertion never kills the test runner).
Everything is FAITHFULNESS-NEUTRAL (concurrency/lifecycle only) and env-gated default-safe.
"""

from __future__ import annotations

import concurrent.futures
import threading

import pytest

from src.polaris_graph.roles.adaptive_concurrency import AdaptiveConcurrencyController
import src.polaris_graph.roles.openrouter_role_transport as _transport
import scripts.run_honest_sweep_r3 as _sweep


# === prong 1: release_all() unblocks a parked acquirer on a REAL pool ============================
def test_release_all_unblocks_a_parked_worker_and_pool_join_completes():
    """A worker wedged in acquire() (in_flight == limit) is freed by release_all(), so the real
    ThreadPoolExecutor join (`shutdown(wait=True)`) no longer hangs — the exact deadlock dissolving."""
    c = AdaptiveConcurrencyController(min_limit=1, max_limit=1, probe_window=8)
    c.acquire()  # fill the only slot: in_flight == limit == 1, so the next acquire MUST block.

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(c.acquire)  # parks in self._cond.wait()
        with pytest.raises(concurrent.futures.TimeoutError):
            fut.result(timeout=1.0)  # proves it is genuinely blocked (not yet acquired).

        c.release_all()  # teardown latch + notify_all -> the parked worker wakes ungated.
        fut.result(timeout=5.0)  # returns now; raises if the fix failed to wake it.

        # The real join must complete promptly now that no worker is parked (the deadlock site).
        done = threading.Event()
        threading.Thread(target=lambda: (pool.shutdown(wait=True), done.set()), daemon=True).start()
        assert done.wait(timeout=5.0), "pool.shutdown(wait=True) still hung after release_all()"
    finally:
        pool.shutdown(wait=False)


def test_normal_acquire_release_is_byte_identical_when_release_all_never_called():
    """The `and not self._shutdown` guard must not change the normal path: acquire/release balances."""
    c = AdaptiveConcurrencyController(min_limit=2, max_limit=4, probe_window=8)
    c.acquire()
    c.acquire()
    assert c.in_flight == 2
    c.release()
    assert c.in_flight == 1
    c.release()
    assert c.in_flight == 0


# === prong 2: registry helper walks every per-role controller ====================================
def test_release_all_adaptive_controllers_walks_the_registry(monkeypatch):
    a = AdaptiveConcurrencyController(min_limit=1, max_limit=1, probe_window=8)
    b = AdaptiveConcurrencyController(min_limit=1, max_limit=1, probe_window=8)
    monkeypatch.setattr(_transport, "_ADAPTIVE_CONTROLLERS", {"judge": a, "sentinel": b})

    released = _transport.release_all_adaptive_controllers()

    assert released == 2
    assert a._shutdown is True and b._shutdown is True


def test_registry_helper_never_raises_on_a_bad_controller(monkeypatch):
    class _Boom:
        def release_all(self):
            raise RuntimeError("wedged")

    monkeypatch.setattr(_transport, "_ADAPTIVE_CONTROLLERS", {"judge": _Boom()})
    assert _transport.release_all_adaptive_controllers() == 0  # swallowed, count unchanged


# === prong 3: the process-level teardown WALL ====================================================
def test_wall_fires_os_exit_when_interpreter_stays_wedged():
    """done_event never set within the deadline -> the wall force-exits with the run's return code."""
    calls = []
    never = threading.Event()
    _sweep._teardown_wall_target(
        return_code=7, deadline_s=0.05, done_event=never,
        exit_fn=calls.append, notify=lambda _m: None,
    )
    assert calls == [7]


def test_wall_does_not_fire_when_exit_is_clean():
    """A clean interpreter exit sets the event before the deadline -> the wall must NOT force-exit."""
    calls = []
    done = threading.Event()
    done.set()
    _sweep._teardown_wall_target(
        return_code=0, deadline_s=5.0, done_event=done,
        exit_fn=calls.append, notify=lambda _m: None,
    )
    assert calls == []


def test_arm_teardown_wall_is_daemon_and_fires_when_not_disarmed():
    calls = []
    thread, _event = _sweep._arm_teardown_wall(3, 0.05, exit_fn=calls.append)
    assert thread.daemon is True  # must never itself block process exit.
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert calls == [3]


def test_arm_teardown_wall_disarms_via_event():
    calls = []
    thread, event = _sweep._arm_teardown_wall(0, 5.0, exit_fn=calls.append)
    event.set()  # simulate the interpreter reaching a clean exit first.
    thread.join(timeout=5.0)
    assert calls == []


# === env gate: OFF is a true no-op ===============================================================
def test_run_process_teardown_is_a_noop_when_disabled(monkeypatch):
    monkeypatch.setenv(_sweep._TEARDOWN_WALL_ENV, "0")
    armed = []
    released = []
    monkeypatch.setattr(_sweep, "_arm_teardown_wall", lambda *a, **k: armed.append(a))
    monkeypatch.setattr(
        _transport, "release_all_adaptive_controllers", lambda: released.append(1),
    )
    _sweep._run_process_teardown(0)
    assert armed == [] and released == []


def test_run_process_teardown_arms_when_enabled(monkeypatch):
    monkeypatch.setenv(_sweep._TEARDOWN_WALL_ENV, "1")
    monkeypatch.setenv(_sweep._TEARDOWN_WALL_SECONDS_ENV, "12")
    armed = []
    monkeypatch.setattr(_sweep, "_arm_teardown_wall", lambda rc, secs, **k: armed.append((rc, secs)))
    _sweep._run_process_teardown(5)
    assert armed == [(5, 12.0)]
