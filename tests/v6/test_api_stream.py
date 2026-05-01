"""Tests for /stream/{run_id} SSE endpoint (Phase 0 stub).

Verifies the 5-event Phase 0 stub emits in the documented order with
the expected fields, using FastAPI TestClient (no real HTTP server).
The endpoint is replaced with real pipeline-A bridge events in Phase 1
once the cluster is live; this test pins the contract until then.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("sse_starlette")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def _parse_sse_events(raw: str) -> list[tuple[str, dict]]:
    """Parse the SSE wire format. Server may use `\r\n` line endings; split on
    blank lines (one or more newlines) and strip per-line whitespace.
    """
    # Normalize line endings then split into blocks.
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    events: list[tuple[str, dict]] = []
    for block in normalized.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_payload = ""
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_payload = line[len("data:") :].strip()
        if event_name and data_payload:
            events.append((event_name, json.loads(data_payload)))
    return events


def test_stream_emits_five_phase0_events_in_order(client):
    response = client.get("/stream/test-run-123")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse_events(response.text)
    assert len(events) == 5
    assert [name for name, _ in events] == [
        "scope_decision",
        "retrieval_progress",
        "verifier_verdict",
        "section_complete",
        "run_complete",
    ]


def test_stream_includes_run_id_in_every_event(client):
    response = client.get("/stream/run-with-special-id-_-7")
    events = _parse_sse_events(response.text)
    assert len(events) == 5
    for _, payload in events:
        assert payload["run_id"] == "run-with-special-id-_-7"


def test_stream_scope_decision_payload_shape(client):
    response = client.get("/stream/r1")
    events = dict(_parse_sse_events(response.text))
    sd = events["scope_decision"]
    assert sd["verdict"] == "accepted"
    assert "reason" in sd


def test_stream_retrieval_progress_includes_tier_breakdown(client):
    response = client.get("/stream/r1")
    events = dict(_parse_sse_events(response.text))
    rp = events["retrieval_progress"]
    assert isinstance(rp["sources_found"], int)
    assert rp["sources_found"] > 0
    assert set(rp["tier_breakdown"].keys()) == {"T1", "T2", "T3"}


def test_stream_run_complete_signals_terminal_status(client):
    response = client.get("/stream/r1")
    events = dict(_parse_sse_events(response.text))
    rc = events["run_complete"]
    assert rc["status"] == "completed"


def test_stream_verifier_verdict_includes_pass_flags(client):
    response = client.get("/stream/r1")
    events = dict(_parse_sse_events(response.text))
    vv = events["verifier_verdict"]
    assert vv["local_pass"] is True
    assert vv["global_pass"] is True
    assert "section" in vv
