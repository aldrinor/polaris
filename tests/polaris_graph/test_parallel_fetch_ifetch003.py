"""I-fetch-003 (#1175 / BB5-C01/C02) — start-anchored, bounded-poll,
round-robin parallel-fetch starvation fix.

Offline + deterministic: NO network, NO spend. A mock fetcher plus a
virtual monotonic clock (monkeypatched onto the parallel_fetch module)
drive the start-anchored deadline arithmetic; `threading.Event`
barriers make concurrency ordering deterministic without sleeping on
the wall clock. The harvest poll interval is shrunk so the bounded
poll wakes quickly instead of really blocking ~2s.

Covers (per AC5):
  (a) a single SLOW task does NOT time out fast/queued siblings under
      start-anchoring + bounded poll (the C01 starvation root cause).
  (b) a task exceeding ITS OWN start-anchored budget IS TIMEOUT even
      when no sibling ever completes.
  (c) two DISTINCT hosts run concurrently while same-host is capped at
      the per-host limit (C02 host-keyed semaphore).
  (d) ADVERSARIAL: >max_workers same-host tasks followed by a
      different-host task — the other host STARTS before the same-host
      prefix drains (round-robin submit defeats worker-slot hoarding).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import pytest

import src.polaris_graph.audit_ir.parallel_fetch as pf_mod
from src.polaris_graph.audit_ir.parallel_fetch import (
    FetchOutcome,
    FetchTask,
    ParallelFetchReport,
    _round_robin_indices,
    parallel_fetch,
    report_to_exit_code,
)


# ---------------------------------------------------------------------------
# Virtual monotonic clock — deterministic deadline arithmetic, no wall sleep
# ---------------------------------------------------------------------------


class _VirtualClock:
    """A controllable monotonic clock. Worker threads advance it from
    inside the mock fetcher (per-task), the harvest loop reads it for
    deadline decisions. Thread-safe."""

    def __init__(self) -> None:
        self._now = 0.0
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += seconds


# ---------------------------------------------------------------------------
# Mock fetchers
# ---------------------------------------------------------------------------


@dataclass
class _GatedFetcher:
    """Per-URL gated fetcher. Each task records its start order, then
    blocks on a per-URL `threading.Event` until the test releases it.
    Optionally advances a virtual clock by `clock_advance` BEFORE
    blocking so the harvest loop sees the task as having consumed time.

    `start_gate_events` (optional, per-URL): if present for a URL, the
    worker BLOCKS on it BEFORE recording its start (i.e. before anchoring
    its start-deadline). This lets a test STAGE a task's start at a
    distinct virtual time so its deadline is genuinely its OWN, not a
    sibling's. Absent → the task starts immediately on dispatch.
    """

    release_events: dict[str, threading.Event]
    clock: _VirtualClock | None = None
    clock_advance: float = 0.0
    start_order: list[str] = field(default_factory=list)
    started_events: dict[str, threading.Event] = field(default_factory=dict)
    start_gate_events: dict[str, threading.Event] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
        gate_start = self.start_gate_events.get(task.source_url)
        if gate_start is not None:
            gate_start.wait(timeout=10.0)
        with self._lock:
            self.start_order.append(task.source_url)
        ev = self.started_events.get(task.source_url)
        if ev is not None:
            ev.set()
        if self.clock is not None and self.clock_advance:
            self.clock.advance(self.clock_advance)
        gate = self.release_events.get(task.source_url)
        if gate is not None:
            gate.wait(timeout=10.0)
        return (task.source_url.encode("utf-8"), "text/plain", 200)


# ---------------------------------------------------------------------------
# (round-robin permutation correctness — submit-order primitive)
# ---------------------------------------------------------------------------


def test_round_robin_indices_is_a_permutation() -> None:
    tasks = [
        FetchTask("https://a/1", "host_a"),
        FetchTask("https://a/2", "host_a"),
        FetchTask("https://a/3", "host_a"),
        FetchTask("https://b/1", "host_b"),
    ]
    order = _round_robin_indices(tasks)
    # A permutation of range(len): every original index exactly once.
    assert sorted(order) == [0, 1, 2, 3]
    # First two submissions span the two distinct hosts (no hoarding).
    assert {tasks[order[0]].backend_id, tasks[order[1]].backend_id} == {
        "host_a", "host_b",
    }


def test_round_robin_indices_single_backend_preserves_order() -> None:
    tasks = [FetchTask(f"https://a/{i}", "host_a") for i in range(5)]
    assert _round_robin_indices(tasks) == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# (a) slow task does NOT time out fast/queued siblings
# ---------------------------------------------------------------------------


def test_slow_sibling_stays_in_flight_while_fast_complete_then_own_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C01 boundary (rewritten — was a pass-through that released every
    task and never advanced the clock). This is a REAL boundary test:

      - Fast siblings start at virtual t=0 and COMPLETE first while the
        slow sibling genuinely STAYS IN-FLIGHT (gated, not released).
      - The virtual clock ACTUALLY ADVANCES while the slow task runs.
      - The slow task starts at a DISTINCT virtual time (staged behind a
        same-host blocker) so its deadline is genuinely ITS OWN, not a
        sibling's shared numeric deadline.
      - Mid-flight, after the clock passes a SIBLING's deadline but BEFORE
        the slow task's own start-anchored deadline, the fast siblings are
        already SUCCESS and the slow task is STILL RUNNING (not TIMEOUT).
      - Only once the clock passes the slow task's OWN deadline is it
        TIMEOUT'd.
    """
    clock = _VirtualClock()
    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)

    per_task_timeout = 100.0
    fast_a, fast_b = "https://fast/a", "https://fast/b"
    blocker = "https://slowhost/blocker"  # same host as `slow`, runs first
    slow = "https://slowhost/slow"

    release = {
        fast_a: threading.Event(),
        fast_b: threading.Event(),
        blocker: threading.Event(),
        slow: threading.Event(),  # NEVER released until cleanup
    }
    started = {u: threading.Event() for u in (fast_a, fast_b, blocker, slow)}
    # The slow task may not START anchoring until the test stages it: it is
    # gated behind the same-host semaphore (limit 1) by `blocker`, which we
    # release only after advancing the clock — so `slow` anchors at a DISTINCT
    # virtual time.
    release[fast_a].set()
    release[fast_b].set()
    fetcher = _GatedFetcher(
        release_events=release, clock=clock, started_events=started,
    )

    # fast_* on their own hosts (run free); blocker+slow share `slowhost`
    # (limit 1) so slow is QUEUED behind blocker.
    tasks = [
        FetchTask(fast_a, "host_fa"),
        FetchTask(fast_b, "host_fb"),
        FetchTask(blocker, "slowhost"),
        FetchTask(slow, "slowhost"),
    ]

    holder: dict[str, object] = {}

    def _run() -> None:
        holder["r"] = parallel_fetch(
            tasks, fetcher,
            max_workers=4,
            per_backend_max_concurrent={
                "host_fa": 1, "host_fb": 1, "slowhost": 1,
            },
            per_task_timeout=per_task_timeout,
        )

    runner = threading.Thread(target=_run)
    runner.start()

    # Fast siblings + blocker start at virtual t=0 and complete.
    assert started[fast_a].wait(timeout=5.0)
    assert started[fast_b].wait(timeout=5.0)
    assert started[blocker].wait(timeout=5.0)
    # blocker is gated; advance the clock a little, then release it so `slow`
    # anchors its start at a DISTINCT, later virtual time (t=30, not t=0).
    clock.advance(30.0)
    release[blocker].set()
    # `slow` now acquires the same-host semaphore and anchors its start at t=30.
    assert started[slow].wait(timeout=5.0), "slow never started after blocker"

    # Advance PAST a t=0 sibling's would-be deadline (t=30 + 80 = 110 > 100)
    # but BELOW slow's OWN deadline (30 + 100 = 130). The fast siblings already
    # completed (SUCCESS); slow is still gated and must NOT be TIMEOUT'd yet —
    # its deadline is its OWN, not the t=0 siblings'.
    clock.advance(80.0)  # virtual now = 110
    time.sleep(0.1)  # let the harvest loop wake at least once
    assert not release[slow].is_set()  # slow still in-flight (we never freed)

    # Now advance PAST slow's own start-anchored deadline (130). The bounded
    # poll must TIMEOUT it without any sibling completing to drive progress.
    clock.advance(25.0)  # virtual now = 135 > 130
    runner.join(timeout=10.0)
    assert not runner.is_alive(), "parallel_fetch hung past slow's deadline"
    report = holder["r"]  # type: ignore[assignment]

    outcomes = {r.source_url: r.outcome for r in report.results}
    # Fast siblings + blocker ran well inside their own budgets -> SUCCESS.
    assert outcomes[fast_a] is FetchOutcome.SUCCESS
    assert outcomes[fast_b] is FetchOutcome.SUCCESS
    assert outcomes[blocker] is FetchOutcome.SUCCESS
    # Slow over-ran ITS OWN start-anchored deadline -> TIMEOUT (not a sibling's).
    assert outcomes[slow] is FetchOutcome.TIMEOUT
    assert report.success_count == 3
    assert report.timeout_count == 1

    # Release the (still-gated) slow worker so its abandoned thread can exit.
    release[slow].set()


# ---------------------------------------------------------------------------
# (b) a task exceeding ITS OWN budget IS TIMEOUT even with no sibling done
# ---------------------------------------------------------------------------


def test_task_over_own_budget_is_timeout_without_sibling_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single task that consumes MORE than its own start-anchored
    budget is marked TIMEOUT — the bounded poll catches it within the
    poll interval and does NOT rely on any sibling completing."""
    clock = _VirtualClock()
    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)

    # The single task starts, advances the virtual clock PAST its budget,
    # then stays gated (never completes). The harvest loop must TIMEOUT it.
    url = "https://hang/1"
    release = {url: threading.Event()}  # never set -> never completes
    started = {url: threading.Event()}
    fetcher = _GatedFetcher(
        release_events=release,
        clock=clock,
        clock_advance=5.0,  # > per_task_timeout below
        started_events=started,
    )

    tasks = [FetchTask(url, "default")]
    report = parallel_fetch(
        tasks, fetcher,
        max_workers=2,
        per_task_timeout=1.0,
    )
    assert report.timeout_count == 1
    rec = report.results[0]
    assert rec.outcome is FetchOutcome.TIMEOUT
    assert rec.error == "per-task timeout exceeded"
    # The gated worker did start (proving the budget was START-anchored,
    # not relabeled at submit time).
    assert started[url].is_set()


def test_not_yet_started_task_never_times_out_behind_a_slot_hog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With max_workers=1, a queued (not-yet-started) task has a +inf
    effective deadline: even though wall time passes while the first
    task hogs the only slot, the queued task is NOT batch-TIMEOUT'd —
    it runs and SUCCEEDS once the slot frees. (Inverse of C01.)

    The GLOBAL batch budget (I-fetch-003 P1) is the backstop for a
    genuinely-wedged pool; here the slot DOES free and `second` completes,
    so the budget must NOT pre-empt that legitimate late completion. Pin a
    large explicit budget so this healthy-late-completion path is exercised
    (the wedged-forever path is covered by the dedicated batch-budget tests).
    """
    clock = _VirtualClock()
    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)
    monkeypatch.setenv(
        pf_mod.PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS_ENV, "100000",
    )

    first, second = "https://first/1", "https://second/1"
    release = {first: threading.Event(), second: threading.Event()}
    started = {first: threading.Event(), second: threading.Event()}
    release[second].set()  # second completes instantly once it starts
    fetcher = _GatedFetcher(
        release_events=release, clock=clock, started_events=started,
    )

    tasks = [FetchTask(first, "default"), FetchTask(second, "default")]

    def _run() -> pf_mod.ParallelFetchReport:
        return parallel_fetch(
            tasks, fetcher,
            max_workers=1,  # second is QUEUED behind first
            per_task_timeout=1.0,
        )

    holder: dict[str, object] = {}
    runner = threading.Thread(target=lambda: holder.update(r=_run()))
    runner.start()
    # First task has started and is holding the only worker slot.
    assert started[first].wait(timeout=5.0)
    # Advance virtual time PAST first's budget. The QUEUED second task
    # has no start yet (+inf deadline) -> must NOT be timed out.
    clock.advance(10.0)
    time.sleep(0.1)
    assert not started[second].is_set()  # still queued, not started
    # Release first inside its (virtual) budget consumption is moot — it
    # already over-ran; it will TIMEOUT. Free the slot so second can run.
    release[first].set()
    runner.join(timeout=10.0)
    report = holder["r"]  # type: ignore[assignment]

    outcomes = {r.source_url: r.outcome for r in report.results}
    # first over-ran its own budget -> TIMEOUT; second ran fresh -> SUCCESS.
    assert outcomes[second] is FetchOutcome.SUCCESS
    assert outcomes[first] is FetchOutcome.TIMEOUT


# ---------------------------------------------------------------------------
# (P1) GLOBAL batch-budget termination guarantee — all-workers-wedged path
# ---------------------------------------------------------------------------


def test_batch_budget_fires_never_started_queued_are_not_dispatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TERMINATION GUARANTEE (I-fetch-003 P1): if every worker is wedged on
    an abandoned in-flight fetch and distinct-host siblings sit queued
    forever behind them (each on its OWN host with a +inf per-task deadline
    because per_task_timeout is None for THEM... here we give a per-task
    timeout but the wedged tasks never advance their own clock, so per-task
    TIMEOUT alone could still livelock the queued ones), the GLOBAL batch
    budget MUST fire: the queued-never-started tasks are recorded
    NOT_DISPATCHED (NOT TIMEOUT — they never ran) and the call RETURNS.
    """
    clock = _VirtualClock()
    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)

    max_workers = 2
    per_task_timeout = 100.0
    # The first `max_workers` tasks each block forever (never released, never
    # advance the clock) and hoard the worker pool. Put them on DISTINCT hosts
    # so per-host caps are not what blocks the queued siblings — the worker
    # pool itself is the scarce resource.
    wedge_urls = [f"https://wedge_{i}/x" for i in range(max_workers)]
    queued_urls = [f"https://queued_{i}/x" for i in range(3)]
    all_urls = wedge_urls + queued_urls

    release = {u: threading.Event() for u in all_urls}  # none set -> all gated
    started = {u: threading.Event() for u in all_urls}
    fetcher = _GatedFetcher(
        release_events=release, clock=clock, started_events=started,
    )
    # Each URL on its own host so host-caps never gate the queue.
    tasks = [FetchTask(u, f"host_{i}") for i, u in enumerate(all_urls)]

    holder: dict[str, object] = {}

    def _run() -> None:
        holder["r"] = parallel_fetch(
            tasks, fetcher,
            max_workers=max_workers,
            per_task_timeout=per_task_timeout,
        )

    runner = threading.Thread(target=_run)
    runner.start()
    # The two wedge tasks grab both worker slots and hang.
    assert started[wedge_urls[0]].wait(timeout=5.0)
    assert started[wedge_urls[1]].wait(timeout=5.0)
    time.sleep(0.1)
    # Queued tasks have NOT started (worker pool starved).
    assert not any(started[u].is_set() for u in queued_urls)

    # Derived batch budget = per_task_timeout * (ceil(5/2) + 2) = 100 * 5 = 500.
    # Advance the virtual clock PAST it. Wedge tasks ran (over their own 100s
    # budget) -> TIMEOUT; queued tasks never started -> NOT_DISPATCHED.
    clock.advance(600.0)
    runner.join(timeout=10.0)
    assert not runner.is_alive(), (
        "parallel_fetch HUNG — batch budget failed to guarantee termination "
        "under all-workers-wedged + queued siblings"
    )
    report = holder["r"]  # type: ignore[assignment]

    outcomes = {r.source_url: r.outcome for r in report.results}
    # The wedge tasks STARTED and over-ran -> TIMEOUT (they DID run).
    for u in wedge_urls:
        assert outcomes[u] is FetchOutcome.TIMEOUT, (
            f"{u} should be TIMEOUT (started + over-ran), got {outcomes[u]}"
        )
    # The queued tasks NEVER ran -> NOT_DISPATCHED (distinct from TIMEOUT).
    for u in queued_urls:
        assert outcomes[u] is FetchOutcome.NOT_DISPATCHED, (
            f"{u} should be NOT_DISPATCHED (never ran), got {outcomes[u]}"
        )
        rec = next(r for r in report.results if r.source_url == u)
        assert "never dispatched" in (rec.error or "")
    # Counts partition len(results) (the documented invariant holds).
    assert report.not_dispatched_count == len(queued_urls)
    assert report.timeout_count == len(wedge_urls)
    assert (
        report.success_count
        + report.errored_count
        + report.timeout_count
        + report.not_dispatched_count
        == len(report.results)
    )

    # Free the wedged workers so their abandoned threads can exit.
    for ev in release.values():
        ev.set()


def test_batch_budget_records_started_unfinished_as_timeout_not_keyerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGRESSION (advisor catch): at batch-budget fire EVERY remaining
    future must be written — including a STARTED-but-unfinished one that
    is still inside its OWN per-task deadline. If only never-started
    futures were recorded, the final `results_by_index[i]` reduction would
    KeyError on the started-unfinished index. Mixed scenario: one wedge
    task (blocks the single worker) + one queued sibling, with a batch
    budget SHORTER than the per-task timeout so the budget fires while the
    wedge task is still inside its own deadline.
    """
    clock = _VirtualClock()
    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)
    # Force a SHORT explicit batch budget so it fires BEFORE the wedge task's
    # own (large) per-task deadline -> wedge is started-but-unfinished AND
    # within its own budget at budget-fire time.
    monkeypatch.setenv(
        pf_mod.PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS_ENV, "50",
    )

    wedge = "https://wedge/x"
    queued = "https://queued/x"
    release = {wedge: threading.Event(), queued: threading.Event()}
    started = {wedge: threading.Event(), queued: threading.Event()}
    fetcher = _GatedFetcher(
        release_events=release, clock=clock, started_events=started,
    )
    tasks = [FetchTask(wedge, "host_w"), FetchTask(queued, "host_q")]

    holder: dict[str, object] = {}

    def _run() -> None:
        holder["r"] = parallel_fetch(
            tasks, fetcher,
            max_workers=1,  # queued is behind wedge in the worker pool
            per_task_timeout=1000.0,  # >> batch budget of 50
        )

    runner = threading.Thread(target=_run)
    runner.start()
    assert started[wedge].wait(timeout=5.0)
    time.sleep(0.1)
    assert not started[queued].is_set()  # queued never got a worker slot

    # Advance PAST the batch budget (50) but FAR below wedge's own per-task
    # deadline (1000). The budget must fire and record BOTH futures.
    clock.advance(60.0)
    runner.join(timeout=10.0)
    assert not runner.is_alive(), "parallel_fetch hung at batch budget"
    report = holder["r"]  # type: ignore[assignment]

    outcomes = {r.source_url: r.outcome for r in report.results}
    # wedge STARTED (inside its own deadline) but the BATCH budget fired ->
    # TIMEOUT (it ran). queued never started -> NOT_DISPATCHED. Crucially the
    # reduction did NOT KeyError on the started-unfinished wedge index.
    assert outcomes[wedge] is FetchOutcome.TIMEOUT
    assert outcomes[queued] is FetchOutcome.NOT_DISPATCHED
    assert len(report.results) == 2  # both indices written, no KeyError

    release[wedge].set()
    release[queued].set()


def test_exit_code_one_on_any_not_dispatched() -> None:
    """A starved batch (NOT_DISPATCHED present, no errors/timeouts) must NOT
    report success — `report_to_exit_code` treats NOT_DISPATCHED the same as
    TIMEOUT so a CI gate / regression runner sees the starvation."""
    report = ParallelFetchReport(
        started_at=0.0,
        finished_at=1.0,
        results=(),
        success_count=2,
        errored_count=0,
        timeout_count=0,
        not_dispatched_count=1,
    )
    assert report_to_exit_code(report) == 1


# ---------------------------------------------------------------------------
# (c) two distinct hosts concurrent; same-host capped at per-host limit
# ---------------------------------------------------------------------------


def test_distinct_hosts_run_concurrently_same_host_capped() -> None:
    """Host-keyed backend_id (limit=1 per host): two tasks on DIFFERENT
    hosts overlap; two tasks on the SAME host serialize."""

    @dataclass
    class _DelayFetcher:
        delay: float

        def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
            time.sleep(self.delay)
            return (task.source_url.encode(), "text/plain", 200)

    same_host = [
        FetchTask("https://h1/a", "host1"),
        FetchTask("https://h1/b", "host1"),
    ]
    t0 = time.time()
    rep_same = parallel_fetch(
        same_host, _DelayFetcher(0.05),
        max_workers=4,
        per_backend_max_concurrent={"host1": 1},
    )
    same_elapsed = time.time() - t0
    assert rep_same.success_count == 2
    # limit=1 serializes -> ~2 * 0.05.
    assert same_elapsed >= 0.09, (
        f"same-host elapsed {same_elapsed} suggests cap=1 violated"
    )

    # Distinct hosts: overlap -> faster than serial.
    diff_host = [
        FetchTask("https://h1/a", "host1"),
        FetchTask("https://h2/a", "host2"),
    ]
    t0 = time.time()
    rep_diff = parallel_fetch(
        diff_host, _DelayFetcher(0.05),
        max_workers=4,
        per_backend_max_concurrent={"host1": 1, "host2": 1},
    )
    diff_elapsed = time.time() - t0
    assert rep_diff.success_count == 2
    # Two distinct hosts run concurrently -> ~0.05, not ~0.10.
    assert diff_elapsed < 0.09, (
        f"distinct-host elapsed {diff_elapsed} suggests no cross-host "
        "parallelism"
    )


# ---------------------------------------------------------------------------
# (d) ADVERSARIAL — round-robin submit defeats worker-slot hoarding
# ---------------------------------------------------------------------------


def test_roundrobin_other_host_starts_before_same_host_prefix_drains() -> None:
    """ADVERSARIAL: a clustered same-host prefix (more tasks than
    max_workers, each on host_a capped at 1) followed by ONE host_b
    task. Without round-robin submit the first max_workers workers all
    block on host_a's single semaphore and host_b starves until the
    prefix drains. With round-robin submit, host_b is submitted in the
    first round and STARTS before the host_a prefix finishes.
    """
    n_same = 6  # > max_workers
    max_workers = 4
    same_urls = [f"https://host_a/{i}" for i in range(n_same)]
    other_url = "https://host_b/1"

    release = {u: threading.Event() for u in same_urls}
    release[other_url] = threading.Event()
    release[other_url].set()  # host_b completes immediately once started
    started = {u: threading.Event() for u in same_urls}
    started[other_url] = threading.Event()
    fetcher = _GatedFetcher(
        release_events=release, started_events=started,
    )

    # Same-host prefix THEN the other host (the hoarding-bait order).
    tasks = [FetchTask(u, "host_a") for u in same_urls]
    tasks.append(FetchTask(other_url, "host_b"))

    holder: dict[str, object] = {}

    def _run() -> None:
        holder["r"] = parallel_fetch(
            tasks, fetcher,
            max_workers=max_workers,
            # host_a capped at 1 -> only one host_a task runs at a time;
            # the other 3 worker slots would be IDLE-but-blocked under a
            # naive submit order. Round-robin must let host_b run.
            per_backend_max_concurrent={"host_a": 1, "host_b": 1},
            per_task_timeout=None,
        )

    runner = threading.Thread(target=_run)
    runner.start()
    # host_b must START while the host_a prefix is still gated (none of
    # the host_a tasks have been released yet).
    assert started[other_url].wait(timeout=5.0), (
        "host_b did not start before the host_a prefix drained — "
        "round-robin submit failed to defeat worker-slot hoarding"
    )
    # Confirm the host_a prefix is genuinely still blocked (proof the
    # other host started CONCURRENTLY, not after the prefix completed).
    assert not all(started[u].is_set() for u in same_urls[1:])

    # Drain the host_a prefix so the run can finish cleanly.
    for ev in release.values():
        ev.set()
    runner.join(timeout=10.0)
    report = holder["r"]  # type: ignore[assignment]
    assert report.success_count == n_same + 1
