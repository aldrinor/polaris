"""I-arch-001e — /stream/{run_id} SSE endpoint (Redis Streams).

Verifies the new Redis-Streams-backed SSE endpoint translates pipeline-A
events into the v6 canonical protocol (scope_decision, retrieval_progress,
evidence_id, verifier_verdict, section_complete, run_complete) and honors
Last-Event-ID resume.

Uses fakeredis as a stand-in for both the sync writer and the async reader.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def app_with_stream_router():
    pytest.importorskip("fastapi")
    pytest.importorskip("sse_starlette")
    pytest.importorskip("fakeredis")
    from fastapi import FastAPI
    from polaris_v6.api import stream as stream_module

    app = FastAPI()
    app.include_router(stream_module.router)
    return app


@pytest.fixture
def fake_server():
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeServer()


@pytest.fixture
def sync_fake(fake_server):
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeStrictRedis(server=fake_server)


@pytest.fixture
def async_fake(fake_server):
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.aioredis.FakeRedis(server=fake_server)


def _parse_sse(raw: str) -> list[dict]:
    """Parse the SSE wire format into a list of {event, data, id} dicts.

    Tolerates the keepalive comment (`: keepalive\\n\\n`) by skipping blocks
    that contain no `event:` line.
    """
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    events: list[dict] = []
    for block in normalized.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        evt: dict = {}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith(":"):
                # comment / keepalive
                continue
            if line.startswith("event:"):
                evt["event"] = line[len("event:"):].strip()
            elif line.startswith("data:"):
                evt["data"] = json.loads(line[len("data:"):].strip())
            elif line.startswith("id:"):
                evt["id"] = line[len("id:"):].strip()
        if evt.get("event"):
            events.append(evt)
    return events


def test_stream_translates_pipeline_a_events_to_v6_protocol(
    app_with_stream_router, sync_fake, async_fake, monkeypatch
):
    from fastapi.testclient import TestClient
    from polaris_v6.queue import run_events as re_mod

    # Pre-emit pipeline-A events into fakeredis (before the SSE request fires).
    re_mod.emit_event("rid-xlate", "scope_gate.completed", {"decision": "in_scope", "reason": ""}, redis_client=sync_fake)
    re_mod.emit_event("rid-xlate", "corpus_adequacy.completed", {"pool_size": 7, "tier_counts": {"T1": 3, "T2": 4}}, redis_client=sync_fake)
    re_mod.emit_event("rid-xlate", "strict_verify.section_completed", {"section": "Summary", "local": True, "global": True}, redis_client=sync_fake)
    re_mod.emit_event("rid-xlate", "generator.section_completed", {"section": "Summary", "verified": 5, "dropped": 1}, redis_client=sync_fake)
    re_mod.emit_terminal_event("rid-xlate", "success", redis_client=sync_fake)

    # Monkeypatch read_events to feed the pre-seeded fakeredis to the async reader.
    real_read = re_mod.read_events

    async def _read_with_fake(run_id, last_event_id="0-0", *, block_ms=5000, redis_client_async=None):
        async for sid, raw in real_read(run_id, last_event_id=last_event_id, block_ms=100, redis_client_async=async_fake):
            yield sid, raw

    monkeypatch.setattr(re_mod, "read_events", _read_with_fake)
    # stream.py imported read_events at module load; patch its bound reference too.
    from polaris_v6.api import stream as stream_module
    monkeypatch.setattr(stream_module, "read_events", _read_with_fake)

    client = TestClient(app_with_stream_router)
    resp = client.get("/stream/rid-xlate")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    names = [e["event"] for e in events]
    assert names == ["scope_decision", "retrieval_progress", "verifier_verdict", "section_complete", "run_complete"]
    # Each event carries run_id + an id (stream_id).
    for e in events:
        assert e["data"]["run_id"] == "rid-xlate"
        assert "id" in e


def test_stream_run_complete_carries_pipeline_status(
    app_with_stream_router, sync_fake, async_fake, monkeypatch
):
    from fastapi.testclient import TestClient
    from polaris_v6.queue import run_events as re_mod

    re_mod.emit_terminal_event("rid-abort", "abort_no_sources", error_msg="zero", redis_client=sync_fake)

    real_read = re_mod.read_events

    async def _read_with_fake(run_id, last_event_id="0-0", *, block_ms=5000, redis_client_async=None):
        async for sid, raw in real_read(run_id, last_event_id=last_event_id, block_ms=100, redis_client_async=async_fake):
            yield sid, raw

    from polaris_v6.api import stream as stream_module
    monkeypatch.setattr(stream_module, "read_events", _read_with_fake)

    client = TestClient(app_with_stream_router)
    resp = client.get("/stream/rid-abort")
    events = _parse_sse(resp.text)
    # Single run_complete event with abort status preserved.
    rc = [e for e in events if e["event"] == "run_complete"]
    assert len(rc) == 1
    assert rc[0]["data"]["status"] == "abort_no_sources"
    assert rc[0]["data"]["error"] == "zero"


def test_stream_last_event_id_header_resumes(
    app_with_stream_router, sync_fake, async_fake, monkeypatch
):
    from fastapi.testclient import TestClient
    from polaris_v6.queue import run_events as re_mod

    re_mod.emit_event("rid-resume", "scope_gate.completed", {}, redis_client=sync_fake)
    re_mod.emit_event("rid-resume", "corpus_adequacy.completed", {}, redis_client=sync_fake)
    re_mod.emit_terminal_event("rid-resume", "success", redis_client=sync_fake)

    key = re_mod.EVENT_STREAM_KEY.format(run_id="rid-resume")
    first_id = sync_fake.xrange(key)[0][0].decode()

    real_read = re_mod.read_events

    async def _read_with_fake(run_id, last_event_id="0-0", *, block_ms=5000, redis_client_async=None):
        async for sid, raw in real_read(run_id, last_event_id=last_event_id, block_ms=100, redis_client_async=async_fake):
            yield sid, raw

    from polaris_v6.api import stream as stream_module
    monkeypatch.setattr(stream_module, "read_events", _read_with_fake)

    client = TestClient(app_with_stream_router)
    resp = client.get("/stream/rid-resume", headers={"Last-Event-ID": first_id})
    events = _parse_sse(resp.text)
    names = [e["event"] for e in events]
    # First event consumed → only retrieval_progress + run_complete left.
    assert names == ["retrieval_progress", "run_complete"]


def test_stream_redis_unreachable_emits_stream_unavailable_run_complete(
    app_with_stream_router, monkeypatch
):
    """When the async reader can't connect, the endpoint still serves a terminal
    run_complete with status='stream_unavailable' rather than hanging forever.
    """
    from fastapi.testclient import TestClient
    from polaris_v6.api import stream as stream_module
    from polaris_v6.queue import run_events as re_mod

    async def _read_boom(run_id, last_event_id="0-0", *, block_ms=5000, redis_client_async=None):
        # Single synthetic terminal — same shape as real read_events on redis fail
        yield ("0-0", {"event_type": "run.completed", "payload": json.dumps({"status": "stream_unavailable"})})

    monkeypatch.setattr(stream_module, "read_events", _read_boom)

    client = TestClient(app_with_stream_router)
    resp = client.get("/stream/rid-down")
    events = _parse_sse(resp.text)
    rc = [e for e in events if e["event"] == "run_complete"]
    assert len(rc) == 1
    assert rc[0]["data"]["status"] == "stream_unavailable"
