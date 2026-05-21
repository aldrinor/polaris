"""I-arch-001e — run_events coverage.

Uses fakeredis so no real Redis broker is required. Verifies:
- Sync emit_event → XADD lands a stream entry
- Async read_events round-trips via XREAD
- Last-Event-ID resume skips already-seen entries
- run.completed terminal closes the stream
- ImportError-free path (emit on missing redis is silent)
- Translator maps the 6 pipeline-A event_types to canonical v6 names
- _validate_last_event_id regex + fallback
- emit_event swallows arbitrary exceptions (observability never blocks pipeline)
"""

from __future__ import annotations

import json

import pytest

from polaris_v6.queue import run_events


# ---------------------------------------------------------------------------
# Unit: validators + translator (pure-function — no Redis needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    (None, "0-0"),
    ("", "0-0"),
    ("0-0", "0-0"),
    ("1700000000000-5", "1700000000000-5"),
    ("garbage", "0-0"),
    ("123", "0-0"),
    ("123-", "0-0"),
    ("-5", "0-0"),
])
def test_last_event_id_validation(raw, expected):
    assert run_events._validate_last_event_id(raw) == expected


@pytest.mark.parametrize("pa_event_type,v6_name", [
    ("scope_gate.completed", "scope_decision"),
    ("corpus_adequacy.completed", "retrieval_progress"),
    ("evidence.id_assigned", "evidence_id"),
    ("strict_verify.section_completed", "verifier_verdict"),
    ("generator.section_completed", "section_complete"),
    ("run.completed", "run_complete"),
])
def test_translator_maps_pipeline_a_events_to_v6_names(pa_event_type, v6_name):
    raw = {"event_type": pa_event_type, "payload": json.dumps({})}
    out = run_events.translate(raw)
    assert out is not None
    name, payload = out
    assert name == v6_name
    assert isinstance(payload, dict)


def test_translator_returns_none_on_unknown_event_type():
    raw = {"event_type": "garbage.unknown", "payload": "{}"}
    assert run_events.translate(raw) is None


def test_translator_tolerates_malformed_payload():
    raw = {"event_type": "run.completed", "payload": "not-json"}
    out = run_events.translate(raw)
    assert out is not None
    name, payload = out
    assert name == "run_complete"
    assert payload == {}


# I-cd-706: the producer (scripts/run_honest_sweep_r3.py) emits these 4 stage
# events with SPECIFIC payload keys. These assert the producer-payload →
# translate contract: the keys the driver sends populate the v6 payload (not
# blanked by a key mismatch). If the driver's emit keys drift, these fail.
@pytest.mark.parametrize("pa_type,producer_payload,expected_v6", [
    (
        "corpus_adequacy.completed",
        {"pool_size": 8, "tier_counts": {"T1": 3, "T3": 5}},
        {"sources_found": 8, "tier_breakdown": {"T1": 3, "T3": 5}},
    ),
    (
        "evidence.id_assigned",
        {"id": "ev_001", "url": "https://oecd.ai/x"},
        {"evidence_id": "ev_001", "source_url": "https://oecd.ai/x"},
    ),
    (
        "strict_verify.section_completed",
        {"section": "Regulatory", "local": True, "global": False},
        {"section": "Regulatory", "local_pass": True, "global_pass": False},
    ),
    (
        "generator.section_completed",
        {"section": "Mechanism", "verified": 9, "dropped": 2},
        {"section": "Mechanism", "verified_sentences": 9, "dropped": 2},
    ),
])
def test_producer_payload_keys_populate_v6_payload(pa_type, producer_payload, expected_v6):
    raw = {"event_type": pa_type, "payload": json.dumps(producer_payload)}
    out = run_events.translate(raw)
    assert out is not None
    _name, payload = out
    assert payload == expected_v6


# ---------------------------------------------------------------------------
# Integration: fakeredis sync emit + async read round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_server():
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeServer()


@pytest.fixture
def sync_fakeredis(fake_server):
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeStrictRedis(server=fake_server)


@pytest.fixture
def async_fakeredis(fake_server):
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.aioredis.FakeRedis(server=fake_server)


def test_emit_event_silent_on_missing_run_id(sync_fakeredis):
    # No external_run_id → CLI sweep mode, no-op.
    run_events.emit_event(None, "scope_gate.completed", {}, redis_client=sync_fakeredis)
    # Stream should not exist
    assert sync_fakeredis.exists(run_events.EVENT_STREAM_KEY.format(run_id="anything")) == 0


def test_emit_event_writes_xadd_entry(sync_fakeredis):
    run_events.emit_event(
        "run_abc",
        "scope_gate.completed",
        {"decision": "in_scope", "reason": ""},
        redis_client=sync_fakeredis,
    )
    key = run_events.EVENT_STREAM_KEY.format(run_id="run_abc")
    entries = sync_fakeredis.xrange(key)
    assert len(entries) == 1
    entry_id, fields = entries[0]
    assert fields[b"event_type"] == b"scope_gate.completed"
    payload = json.loads(fields[b"payload"].decode())
    assert payload == {"decision": "in_scope", "reason": ""}


def test_emit_terminal_event_carries_status(sync_fakeredis):
    run_events.emit_terminal_event(
        "run_def",
        "abort_no_sources",
        error_msg="zero sources",
        redis_client=sync_fakeredis,
    )
    entries = sync_fakeredis.xrange(run_events.EVENT_STREAM_KEY.format(run_id="run_def"))
    assert len(entries) == 1
    _id, fields = entries[0]
    assert fields[b"event_type"] == b"run.completed"
    payload = json.loads(fields[b"payload"].decode())
    assert payload["status"] == "abort_no_sources"
    assert payload["error"] == "zero sources"


def test_emit_event_swallows_arbitrary_exceptions():
    """Per Codex iter-2 P3: pipeline-A error_unexpected cannot be caused by Redis."""

    class BoomClient:
        def xadd(self, *args, **kwargs):
            raise RuntimeError("simulated redis blip")

    # Must not raise — pipeline keeps running even if Redis observability blows up.
    run_events.emit_event(
        "run_boom",
        "scope_gate.completed",
        {},
        redis_client=BoomClient(),
    )


# ---------------------------------------------------------------------------
# Async: read_events round-trip via fakeredis.aioredis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_events_round_trip(sync_fakeredis, async_fakeredis):
    """Emit 3 events via sync; read via async; terminal closes stream."""
    async_client = async_fakeredis

    run_events.emit_event("rid1", "scope_gate.completed", {"decision": "in_scope"}, redis_client=sync_fakeredis)
    run_events.emit_event("rid1", "corpus_adequacy.completed", {"pool_size": 5}, redis_client=sync_fakeredis)
    run_events.emit_terminal_event("rid1", "success", redis_client=sync_fakeredis)

    seen = []
    async for stream_id, raw in run_events.read_events(
        "rid1", last_event_id="0-0", block_ms=100, redis_client_async=async_client
    ):
        if stream_id == "__keepalive__":
            continue
        seen.append(raw["event_type"])
        if raw["event_type"] == "run.completed":
            break
    assert seen == ["scope_gate.completed", "corpus_adequacy.completed", "run.completed"]


@pytest.mark.asyncio
async def test_read_events_resume_via_last_event_id(sync_fakeredis, async_fakeredis):
    """After supplying Last-Event-ID = stream_id of first event, only entries 2+3 are returned."""
    async_client = async_fakeredis
    key = run_events.EVENT_STREAM_KEY.format(run_id="rid2")
    run_events.emit_event("rid2", "scope_gate.completed", {}, redis_client=sync_fakeredis)
    run_events.emit_event("rid2", "corpus_adequacy.completed", {}, redis_client=sync_fakeredis)
    run_events.emit_terminal_event("rid2", "success", redis_client=sync_fakeredis)

    entries = sync_fakeredis.xrange(key)
    first_id = entries[0][0].decode()

    seen = []
    async for stream_id, raw in run_events.read_events(
        "rid2", last_event_id=first_id, block_ms=100, redis_client_async=async_client
    ):
        if stream_id == "__keepalive__":
            continue
        seen.append(raw["event_type"])
        if raw["event_type"] == "run.completed":
            break
    # First event was already seen → only events 2 + terminal returned.
    assert seen == ["corpus_adequacy.completed", "run.completed"]


@pytest.mark.asyncio
async def test_read_events_redis_unreachable_yields_synthetic_terminal():
    """When XREAD raises ConnectionError, the reader emits a single
    stream_unavailable terminal and stops. Per Codex diff iter-1 P1: only
    connection failures map to stream_unavailable.
    """

    class BoomAsyncClient:
        async def xread(self, *args, **kwargs):
            raise ConnectionError("redis down for the test")

        async def aclose(self):
            return None

    seen = []
    async for stream_id, raw in run_events.read_events(
        "rid_boom", last_event_id="0-0", block_ms=100, redis_client_async=BoomAsyncClient()
    ):
        seen.append(raw)
        if raw["event_type"] == "run.completed":
            break
    assert len(seen) == 1
    payload = json.loads(seen[0]["payload"])
    assert payload["status"] == "stream_unavailable"


@pytest.mark.asyncio
async def test_read_events_non_connection_error_yields_stream_lost():
    """Per Codex diff iter-1 P1: XREAD exceptions that are NOT connection-failure
    are stream_lost (degraded), not stream_unavailable (Redis-down). This keeps
    schema bugs / corrupt entries from being misreported as backend outage.
    """

    class BadDataClient:
        async def xread(self, *args, **kwargs):
            raise ValueError("garbled fields from the wire")

        async def aclose(self):
            return None

    seen = []
    async for stream_id, raw in run_events.read_events(
        "rid_bad", last_event_id="0-0", block_ms=100, redis_client_async=BadDataClient()
    ):
        seen.append(raw)
        if raw["event_type"] == "run.completed":
            break
    assert len(seen) == 1
    payload = json.loads(seen[0]["payload"])
    assert payload["status"] == "stream_lost"


@pytest.mark.asyncio
async def test_read_events_lifecycle_terminal_with_no_redis_event_emits_stream_lost(
    sync_fakeredis, async_fakeredis, monkeypatch
):
    """Per Codex diff iter-1 P1 (continuing iter-2 brief P1-3): when run_store
    says lifecycle_status='completed' but no Redis terminal event arrives, the
    SSE stream must NOT hang forever on keepalives. After
    STREAM_LOST_GRACE_SECONDS elapses, emit synthetic stream_lost and close.
    """
    # Force the run_store lookup to report 'completed' so empty XREAD windows
    # trigger the grace-window logic without an actual sqlite DB.
    monkeypatch.setattr(
        run_events,
        "_get_lifecycle_status",
        lambda run_id: "completed",
    )
    # Shrink the grace window to keep the test fast.
    monkeypatch.setattr(run_events, "STREAM_LOST_GRACE_SECONDS", 0.05)

    seen = []
    async for stream_id, raw in run_events.read_events(
        "rid_grace",
        last_event_id="0-0",
        block_ms=10,
        redis_client_async=async_fakeredis,
    ):
        if stream_id == "__keepalive__":
            seen.append("KEEPALIVE")
            continue
        seen.append(raw["event_type"])
        if raw["event_type"] == "run.completed":
            break
    # Expect: at least one keepalive (first empty window), then synthetic terminal.
    assert seen[-1] == "run.completed"
    payload_seen_last = None
    # We need to recover the payload too; rerun on a fresh fakeredis so test
    # is self-contained.
    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeServer()
    async_c = fakeredis.aioredis.FakeRedis(server=fake)
    async for stream_id, raw in run_events.read_events(
        "rid_grace2", last_event_id="0-0", block_ms=10, redis_client_async=async_c,
    ):
        if stream_id == "__keepalive__":
            continue
        payload_seen_last = json.loads(raw["payload"])
        break
    assert payload_seen_last["status"] == "stream_lost"


@pytest.mark.asyncio
async def test_read_events_lifecycle_still_running_keepalives_forever(
    sync_fakeredis, async_fakeredis, monkeypatch
):
    """While lifecycle_status is in_progress, empty XREAD windows must keep
    emitting keepalives — never synthesize stream_lost — even after the grace
    window elapses. Stream_lost is ONLY for the lifecycle-says-done-but-event-
    missing race.
    """
    monkeypatch.setattr(
        run_events,
        "_get_lifecycle_status",
        lambda run_id: "in_progress",
    )
    monkeypatch.setattr(run_events, "STREAM_LOST_GRACE_SECONDS", 0.05)

    seen_kinds = []
    keepalive_budget = 3

    async for stream_id, raw in run_events.read_events(
        "rid_running",
        last_event_id="0-0",
        block_ms=10,
        redis_client_async=async_fakeredis,
    ):
        if stream_id == "__keepalive__":
            seen_kinds.append("KEEPALIVE")
            keepalive_budget -= 1
            if keepalive_budget <= 0:
                # Client disconnect — break out before any terminal would fire.
                break
            continue
        seen_kinds.append(raw.get("event_type"))
        break  # any non-keepalive aborts the test
    assert all(k == "KEEPALIVE" for k in seen_kinds), (
        f"in_progress lifecycle must never synthesize a terminal: got {seen_kinds}"
    )
