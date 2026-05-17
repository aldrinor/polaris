"""Progressive in-run Inspector surfaces (M-13 — Phase B).

Per FINAL_PLAN.md feature #2: replace the 2h25m blank-stare problem
with milestone-driven Inspector state. From the t-table:

  | t (min) | Surface |
  |--------:|---------|
  | 0       | Pre-flight scope/cost/time/source-count estimate |
  | 0-2     | Upload/parse progress per document |
  | 2-15    | Live source discovery with tier mix bar filling in |
  | 15-45   | Frame coverage manifest filling in as evidence arrives |
  | 45-90   | Contradiction queue appears before final synthesis |
  | 90-120  | First verified claim cards / evidence cards |
  | 120-145 | Final synthesis + complete Evidence Inspector |

Architecture:
- Surfaces are EMITTED by HonestSweepJobRunner (and any future runner) as
  the audit progresses. Emission lands in a `SurfaceBus` keyed by
  job_id.
- Each emission updates a rolling SNAPSHOT (the latest known
  state of every surface kind for that job) and pushes onto a
  per-subscriber asyncio.Queue.
- SSE clients (inspector_router.stream_job_surfaces) subscribe to
  the bus, receive the snapshot first, then live tail subsequent
  events. Disconnect/reconnect replays the snapshot — no events
  are lost (bounded best-effort; clients that fall behind get
  truncated by `max_queue_size`).
- The bus is in-memory, single-process. Phase C upgrades to
  Postgres LISTEN/NOTIFY.

Surface kinds (extensible via `SurfaceKind` enum):
  - preflight
  - parse_progress
  - tier_mix
  - frame_coverage
  - contradiction_queue
  - verified_claim
  - synthesis_complete

The bus exposes:
  - `emit(job_id, kind, payload)`: producers (runners) call this.
  - `latest_snapshot(job_id)`: returns the rolling snapshot.
  - `subscribe(job_id) -> Queue`: SSE clients call this.
  - `unsubscribe(job_id, queue)`: SSE clients call on disconnect.
  - `prune(job_id)`: drops snapshot + subscribers for a finished
    job; called by the worker on terminal transitions.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict
from threading import Lock
from typing import Any


class SurfaceKind(str, Enum):
    """The seven progressive-surface kinds from FINAL_PLAN's
    t-table. Stringly enum so JSON payloads stay readable."""

    PREFLIGHT = "preflight"
    PARSE_PROGRESS = "parse_progress"
    TIER_MIX = "tier_mix"
    FRAME_COVERAGE = "frame_coverage"
    CONTRADICTION_QUEUE = "contradiction_queue"
    VERIFIED_CLAIM = "verified_claim"
    SYNTHESIS_COMPLETE = "synthesis_complete"


@dataclass(frozen=True)
class SurfaceEvent:
    """A single surface update from a runner."""

    job_id: str
    kind: SurfaceKind
    payload: dict[str, Any]
    emitted_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind.value,
            "payload": self.payload,
            "emitted_at": self.emitted_at,
        }


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------


# Each subscriber's queue is bounded so a slow consumer doesn't pin
# memory. Old events drop on overflow per asyncio.QueueFull behavior
# we choose (drop oldest).
_DEFAULT_QUEUE_SIZE = 64

# Codex M-13 v2 review fix: _terminal_jobs is bounded with FIFO
# eviction. Without this, every audit job leaves one permanent
# string in the singleton bus, growing unbounded over the
# process's lifetime. The marker only needs to live long enough
# to cover the subscribe-after-prune race window — minutes is
# more than enough for SSE clients reconnecting after a worker
# transition. 1024 entries comfortably covers a day of activity
# at typical Phase B throughput.
_DEFAULT_TERMINAL_MARK_CAP = 1024


class SurfaceBus:
    """In-memory, thread-safe pub-sub for progressive Inspector
    surfaces. Single instance per process; a module-level singleton
    is provided by `get_surface_bus()`.

    Snapshots are dict[SurfaceKind, latest_event] per job_id, so a
    late-joining SSE client immediately receives the most recent
    state of every surface that's been emitted.
    """

    def __init__(
        self,
        queue_size: int = _DEFAULT_QUEUE_SIZE,
        terminal_cap: int = _DEFAULT_TERMINAL_MARK_CAP,
    ) -> None:
        self._queue_size = queue_size
        self._terminal_cap = max(1, terminal_cap)
        # job_id -> {SurfaceKind: SurfaceEvent}
        self._snapshots: dict[str, dict[SurfaceKind, SurfaceEvent]] = {}
        # job_id -> list of (subscriber_queue, owning_event_loop).
        # Producers may emit from non-async threads (e.g. the V30
        # subprocess drain thread) but the queue belongs to the
        # FastAPI event loop. asyncio.Queue.put_nowait from a
        # different thread does NOT wake `await q.get()`. We
        # capture the loop at subscribe time and dispatch puts via
        # `loop.call_soon_threadsafe`.
        self._subscribers: dict[
            str, list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]]
        ] = {}
        # Codex M-13 v2 review fix: track jobs that have been
        # pruned so a new subscriber arriving AFTER prune sees an
        # immediate sentinel instead of hanging forever on an
        # empty queue.
        # Codex M-13 v3 review fix: bounded with FIFO eviction
        # (OrderedDict-as-LRU). Without this, every audit run
        # leaves one permanent string in the singleton bus,
        # growing the set forever. The marker only needs to
        # outlive the subscribe-after-prune race window (seconds);
        # capping at terminal_cap entries covers many days of
        # Phase B throughput before the oldest entry rolls.
        self._terminal_jobs: OrderedDict[str, None] = OrderedDict()
        # Mutex protects the dicts; producers may emit from worker
        # threads while subscribers run in the FastAPI event loop.
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Producer side
    # ------------------------------------------------------------------

    def emit(
        self,
        job_id: str,
        kind: SurfaceKind | str,
        payload: dict[str, Any],
    ) -> SurfaceEvent:
        """Record a surface update and broadcast to subscribers."""
        if isinstance(kind, str):
            try:
                kind = SurfaceKind(kind)
            except ValueError as exc:
                raise ValueError(
                    f"unknown surface kind: {kind!r}"
                ) from exc
        if not isinstance(payload, dict):
            raise ValueError("surface payload must be a dict")
        event = SurfaceEvent(
            job_id=job_id,
            kind=kind,
            payload=dict(payload),
            emitted_at=time.time(),
        )
        with self._lock:
            self._snapshots.setdefault(job_id, {})[kind] = event
            subs = list(self._subscribers.get(job_id, ()))
        # Push outside the lock — never block the producer. Each
        # subscriber's queue belongs to its event loop, so we
        # schedule the put via call_soon_threadsafe.
        for q, loop in subs:
            self._dispatch_to_subscriber(q, loop, event, job_id=job_id)
        return event

    def _dispatch_to_subscriber(
        self,
        q: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        event: "SurfaceEvent | None",
        job_id: str | None = None,
    ) -> None:
        """Schedule a put onto the subscriber's queue from the
        producer thread. Drops oldest on overflow so the freshest
        event always lands.

        Codex M-13 v2 review fix: if the subscriber's loop is
        closed, sweep the dead (queue, loop) registration so it
        doesn't leak forever. Without this, abandoned subscribers
        whose loops died before `unsubscribe()` accumulated.
        """
        def _put() -> None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
        try:
            loop.call_soon_threadsafe(_put)
        except RuntimeError:
            # Loop is already closed — subscriber went away.
            # Sweep the dead registration if we know the job_id.
            if job_id is not None:
                self.unsubscribe(job_id, q)

    # ------------------------------------------------------------------
    # Consumer side
    # ------------------------------------------------------------------

    def latest_snapshot(self, job_id: str) -> list[SurfaceEvent]:
        """Return the latest event for each surface kind seen for
        this job, ordered by emission time (oldest first)."""
        with self._lock:
            snap = self._snapshots.get(job_id, {})
            events = list(snap.values())
        events.sort(key=lambda e: e.emitted_at)
        return events

    def subscribe(self, job_id: str) -> asyncio.Queue:
        """Create a new subscription queue for SSE. Must be called
        from inside an asyncio event loop (FastAPI handler).
        Caller MUST unsubscribe on disconnect to free memory.

        Note: callers that also want the snapshot for replay
        should use `subscribe_with_snapshot()` to get both
        atomically. Calling subscribe() then latest_snapshot()
        non-atomically can produce duplicates when an event lands
        between the two calls."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.setdefault(job_id, []).append((q, loop))
        return q

    def subscribe_with_snapshot(
        self, job_id: str
    ) -> tuple[asyncio.Queue, list[SurfaceEvent], bool]:
        """Codex M-13 v2 review fix: atomic subscribe + snapshot
        capture. Returns (queue, snapshot_events, is_terminal).

        Without this, a client that called subscribe() then
        latest_snapshot() non-atomically could see an event in
        BOTH the snapshot and the live queue (duplicate delivery).
        The lock here ensures no event lands between the snapshot
        read and the subscribe registration.

        is_terminal=True signals to the caller that the job has
        been pruned (worker already finished); the SSE stream
        should replay the (possibly empty) snapshot and emit
        `event: end` immediately rather than waiting on a queue
        that will never receive a sentinel.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        loop = asyncio.get_running_loop()
        with self._lock:
            terminal = job_id in self._terminal_jobs
            snap = self._snapshots.get(job_id, {})
            events = list(snap.values())
            if not terminal:
                self._subscribers.setdefault(job_id, []).append((q, loop))
        events.sort(key=lambda e: e.emitted_at)
        return q, events, terminal

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        """Remove a subscriber queue. Idempotent."""
        with self._lock:
            subs = self._subscribers.get(job_id)
            if not subs:
                return
            self._subscribers[job_id] = [
                (sq, sl) for (sq, sl) in subs if sq is not q
            ]
            if not self._subscribers[job_id]:
                self._subscribers.pop(job_id, None)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def prune(self, job_id: str) -> None:
        """Drop snapshot + subscribers for a finished job.
        Subscribers receive a sentinel (None) so their SSE loops
        exit cleanly. Sentinel dispatched via call_soon_threadsafe
        because the producer (worker thread) is not in the
        subscriber's loop."""
        with self._lock:
            self._snapshots.pop(job_id, None)
            subs = self._subscribers.pop(job_id, [])
            # Codex M-13 v2 review fix: mark this job_id as
            # terminal so a NEW subscriber arriving after the
            # prune sees an immediate sentinel instead of waiting
            # forever on an empty queue.
            # Codex M-13 v3 fix: FIFO-evict via OrderedDict so the
            # marker set stays bounded. Re-prune of the same
            # job_id refreshes its position.
            if job_id in self._terminal_jobs:
                self._terminal_jobs.move_to_end(job_id)
            else:
                self._terminal_jobs[job_id] = None
                while len(self._terminal_jobs) > self._terminal_cap:
                    self._terminal_jobs.popitem(last=False)
        for q, loop in subs:
            self._dispatch_to_subscriber(q, loop, None, job_id=job_id)

    def is_terminal(self, job_id: str) -> bool:
        """Codex M-13 v2 review fix: SSE stream uses this to
        short-circuit when a client subscribes AFTER the worker
        already pruned the job_id."""
        with self._lock:
            return job_id in self._terminal_jobs

    def clear_for_tests(self) -> None:
        """Reset all state. Tests use this to isolate fixtures."""
        with self._lock:
            self._snapshots.clear()
            self._subscribers.clear()
            self._terminal_jobs.clear()


# Module-level singleton.
_BUS: SurfaceBus | None = None


def get_surface_bus() -> SurfaceBus:
    global _BUS
    if _BUS is None:
        _BUS = SurfaceBus()
    return _BUS


def _set_surface_bus_for_tests(bus: SurfaceBus | None) -> None:
    global _BUS
    _BUS = bus
