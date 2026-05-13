"""SSE /stream endpoint — durable replayable event log via Redis Streams.

I-arch-001e (2026-05-13): replaces canned Phase 0 demo events with real
Redis-Streams-backed SSE. Honors Last-Event-ID HTTP header (set
automatically by EventSource on reconnect) plus ?last_event_id= query
param fallback. Emits each event with `id: <stream_id>` so EventSource
clients resume cleanly. Terminates after a v6 `run_complete` event.

Per docs/carney_delivery_plan_v6_2.md F4, the v6 event protocol is:
scope_decision, retrieval_progress, evidence_id, verifier_verdict,
section_complete, run_complete. Pipeline-A's stage events translate to
these names via polaris_v6.queue.run_events.translate().
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Header
from sse_starlette.sse import EventSourceResponse

from polaris_v6.queue.run_events import read_events, translate

router = APIRouter(prefix="/stream", tags=["stream"])


async def _redis_stream_source(
    run_id: str, last_event_id: str, *, redis_client_async=None
) -> AsyncIterator[dict]:
    """Yield SSE event dicts sourced from the Redis Stream for this run_id.

    Each yielded event includes `id: <stream_id>` so the EventSource client
    resumes via Last-Event-ID on reconnect. Empty XREAD windows yield a
    keepalive comment frame. Terminates after a v6 `run_complete`.
    """
    async for stream_id, raw_event in read_events(
        run_id,
        last_event_id=last_event_id,
        redis_client_async=redis_client_async,
    ):
        if stream_id == "__keepalive__":
            yield {"comment": "keepalive"}
            continue
        v6 = translate(raw_event)
        if v6 is None:
            continue
        v6_name, v6_payload = v6
        yield {
            "id": stream_id,
            "event": v6_name,
            "data": json.dumps({"run_id": run_id, **v6_payload}),
        }
        if v6_name == "run_complete":
            return


@router.get("/{run_id}")
async def stream_run(
    run_id: str,
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
    last_event_id: str = "0-0",
) -> EventSourceResponse:
    """SSE event stream for a research run.

    Reconnect / replay semantics:
        - HTTP `Last-Event-ID: <stream_id>` header (set automatically by
          EventSource on reconnect)
        - `?last_event_id=<stream_id>` query param fallback for manual clients
    """
    effective = last_event_id_header or last_event_id
    return EventSourceResponse(_redis_stream_source(run_id, effective))
