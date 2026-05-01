"""SSE /stream endpoint — emits per-event updates for a research run.

Per docs/carney_delivery_plan_FINAL.md F4 (live audit run UI), the
frontend subscribes to /stream/{run_id} and receives Server-Sent Events
as the run progresses: scope_decision, retrieval_progress, evidence_id,
verifier_verdict, section_complete, run_complete.

Phase 0 stub: yields a small set of synthetic events with deterministic
timing for frontend wiring tests. Real event emission wires to the
pipeline-A bridge in Phase 1 once the cluster is live.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/stream", tags=["stream"])

PHASE_0_STUB_EVENTS = [
    ("scope_decision", {"verdict": "accepted", "reason": "single-meaning question"}),
    ("retrieval_progress", {"sources_found": 14, "tier_breakdown": {"T1": 3, "T2": 7, "T3": 4}}),
    ("verifier_verdict", {"section": "summary", "local_pass": True, "global_pass": True}),
    ("section_complete", {"section": "summary", "verified_sentences": 8, "dropped": 1}),
    ("run_complete", {"status": "completed"}),
]


async def _phase_0_event_source(run_id: str) -> AsyncIterator[dict]:
    for event_name, payload in PHASE_0_STUB_EVENTS:
        await asyncio.sleep(0.05)
        yield {
            "event": event_name,
            "data": json.dumps({"run_id": run_id, **payload}),
        }


@router.get("/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    return EventSourceResponse(_phase_0_event_source(run_id))
