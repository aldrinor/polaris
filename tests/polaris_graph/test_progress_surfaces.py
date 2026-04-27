"""Tests for src/polaris_graph/audit_ir/progress_surfaces.py (M-13)."""

from __future__ import annotations

import asyncio

import pytest

from src.polaris_graph.audit_ir.progress_surfaces import (
    SurfaceBus,
    SurfaceEvent,
    SurfaceKind,
)


@pytest.fixture
def bus() -> SurfaceBus:
    return SurfaceBus(queue_size=4)


# ---------------------------------------------------------------------------
# Emission + snapshot
# ---------------------------------------------------------------------------


def test_emit_creates_snapshot_entry(bus: SurfaceBus) -> None:
    event = bus.emit("job_1", SurfaceKind.PREFLIGHT, {"slug": "x"})
    assert isinstance(event, SurfaceEvent)
    assert event.kind == SurfaceKind.PREFLIGHT
    snap = bus.latest_snapshot("job_1")
    assert len(snap) == 1
    assert snap[0].kind == SurfaceKind.PREFLIGHT
    assert snap[0].payload == {"slug": "x"}


def test_emit_string_kind_normalizes_to_enum(bus: SurfaceBus) -> None:
    event = bus.emit("j", "tier_mix", {"t1": 5})
    assert event.kind == SurfaceKind.TIER_MIX


def test_emit_unknown_string_kind_raises(bus: SurfaceBus) -> None:
    with pytest.raises(ValueError, match="unknown surface kind"):
        bus.emit("j", "not_a_real_kind", {})


def test_emit_non_dict_payload_raises(bus: SurfaceBus) -> None:
    with pytest.raises(ValueError, match="must be a dict"):
        bus.emit("j", SurfaceKind.PREFLIGHT, "not a dict")  # type: ignore[arg-type]


def test_snapshot_keeps_latest_per_kind(bus: SurfaceBus) -> None:
    """Multiple emissions of the same kind → snapshot has only the
    most recent."""
    bus.emit("j", SurfaceKind.TIER_MIX, {"t1": 1})
    bus.emit("j", SurfaceKind.TIER_MIX, {"t1": 5})
    snap = bus.latest_snapshot("j")
    assert len(snap) == 1
    assert snap[0].payload == {"t1": 5}


def test_snapshot_includes_all_kinds_emitted(bus: SurfaceBus) -> None:
    bus.emit("j", SurfaceKind.PREFLIGHT, {"a": 1})
    bus.emit("j", SurfaceKind.TIER_MIX, {"b": 2})
    bus.emit("j", SurfaceKind.FRAME_COVERAGE, {"c": 3})
    snap = bus.latest_snapshot("j")
    kinds = {e.kind for e in snap}
    assert kinds == {
        SurfaceKind.PREFLIGHT,
        SurfaceKind.TIER_MIX,
        SurfaceKind.FRAME_COVERAGE,
    }


def test_snapshot_ordered_by_emission_time(bus: SurfaceBus) -> None:
    import time
    bus.emit("j", SurfaceKind.PREFLIGHT, {})
    time.sleep(0.001)
    bus.emit("j", SurfaceKind.TIER_MIX, {})
    snap = bus.latest_snapshot("j")
    times = [e.emitted_at for e in snap]
    assert times == sorted(times)


def test_snapshot_isolated_per_job(bus: SurfaceBus) -> None:
    bus.emit("job_a", SurfaceKind.PREFLIGHT, {"who": "a"})
    bus.emit("job_b", SurfaceKind.PREFLIGHT, {"who": "b"})
    a = bus.latest_snapshot("job_a")
    b = bus.latest_snapshot("job_b")
    assert a[0].payload == {"who": "a"}
    assert b[0].payload == {"who": "b"}


# ---------------------------------------------------------------------------
# Subscribe / unsubscribe
# ---------------------------------------------------------------------------


def test_subscribe_receives_subsequent_emissions(bus: SurfaceBus) -> None:
    async def go() -> list[SurfaceEvent]:
        q = bus.subscribe("j")
        bus.emit("j", SurfaceKind.PREFLIGHT, {"a": 1})
        bus.emit("j", SurfaceKind.TIER_MIX, {"b": 2})
        results: list[SurfaceEvent] = []
        for _ in range(2):
            results.append(await asyncio.wait_for(q.get(), timeout=1.0))
        bus.unsubscribe("j", q)
        return results

    events = asyncio.run(go())
    kinds = [e.kind for e in events]
    assert kinds == [SurfaceKind.PREFLIGHT, SurfaceKind.TIER_MIX]


def test_subscribe_does_not_get_pre_subscribe_emissions(bus: SurfaceBus) -> None:
    """Snapshot replay is the SSE endpoint's job; the bus itself
    only delivers events emitted AFTER subscribe."""
    async def go() -> int:
        bus.emit("j", SurfaceKind.PREFLIGHT, {"early": True})
        q = bus.subscribe("j")
        # No event waiting in the queue yet.
        try:
            await asyncio.wait_for(q.get(), timeout=0.05)
            got_one = True
        except asyncio.TimeoutError:
            got_one = False
        bus.unsubscribe("j", q)
        return 1 if got_one else 0

    assert asyncio.run(go()) == 0


def test_subscribers_isolated_per_job(bus: SurfaceBus) -> None:
    async def go() -> tuple[bool, bool]:
        qa = bus.subscribe("job_a")
        qb = bus.subscribe("job_b")
        bus.emit("job_a", SurfaceKind.PREFLIGHT, {"who": "a"})
        a_got = False
        b_got = False
        try:
            ea = await asyncio.wait_for(qa.get(), timeout=1.0)
            a_got = ea.payload == {"who": "a"}
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.wait_for(qb.get(), timeout=0.05)
            b_got = True
        except asyncio.TimeoutError:
            pass
        bus.unsubscribe("job_a", qa)
        bus.unsubscribe("job_b", qb)
        return a_got, b_got

    a_got, b_got = asyncio.run(go())
    assert a_got and not b_got


def test_unsubscribe_is_idempotent(bus: SurfaceBus) -> None:
    async def go() -> None:
        q = bus.subscribe("j")
        bus.unsubscribe("j", q)
        bus.unsubscribe("j", q)  # second call must not crash

    asyncio.run(go())


def test_slow_subscriber_does_not_block_producer(bus: SurfaceBus) -> None:
    """If a subscriber's queue fills up, the producer drops oldest
    instead of blocking. The bus is bounded (queue_size=4 in
    fixture)."""
    async def go() -> int:
        q = bus.subscribe("j")
        # Emit 10 events into a 4-slot queue; producer must not
        # block. With drop-oldest behavior, the queue ends with
        # the 4 most recent.
        for i in range(10):
            bus.emit("j", SurfaceKind.PREFLIGHT, {"i": i})
        results: list[int] = []
        try:
            while True:
                e = await asyncio.wait_for(q.get(), timeout=0.05)
                results.append(e.payload["i"])
        except asyncio.TimeoutError:
            pass
        bus.unsubscribe("j", q)
        return len(results)

    n = asyncio.run(go())
    assert 1 <= n <= 4, f"got {n} events through 4-slot queue"


# ---------------------------------------------------------------------------
# Lifecycle: prune
# ---------------------------------------------------------------------------


def test_prune_clears_snapshot(bus: SurfaceBus) -> None:
    bus.emit("j", SurfaceKind.PREFLIGHT, {"x": 1})
    bus.prune("j")
    assert bus.latest_snapshot("j") == []


def test_prune_signals_subscribers_with_sentinel(bus: SurfaceBus) -> None:
    """Prune sends None to each subscriber so their SSE loops exit
    cleanly."""
    async def go() -> bool:
        q = bus.subscribe("j")
        bus.prune("j")
        e = await asyncio.wait_for(q.get(), timeout=1.0)
        return e is None

    assert asyncio.run(go()) is True


def test_prune_unknown_job_is_noop(bus: SurfaceBus) -> None:
    bus.prune("never_emitted")  # must not raise


# ---------------------------------------------------------------------------
# SurfaceEvent serialization
# ---------------------------------------------------------------------------


def test_event_to_dict_contains_required_fields(bus: SurfaceBus) -> None:
    event = bus.emit("j", SurfaceKind.PREFLIGHT, {"a": 1})
    d = event.to_dict()
    assert d["job_id"] == "j"
    assert d["kind"] == "preflight"
    assert d["payload"] == {"a": 1}
    assert isinstance(d["emitted_at"], float)


# ---------------------------------------------------------------------------
# All seven canonical surface kinds present
# ---------------------------------------------------------------------------


def test_all_seven_canonical_surface_kinds_exist() -> None:
    """FINAL_PLAN's t-table specifies these seven."""
    expected = {
        "preflight",
        "parse_progress",
        "tier_mix",
        "frame_coverage",
        "contradiction_queue",
        "verified_claim",
        "synthesis_complete",
    }
    actual = {k.value for k in SurfaceKind}
    assert actual == expected
