"""Tests for queue.actors — research-run actor stubs.

Verifies the Phase 0 actor surface:
  - enqueue_research_run echoes payload + reports completed status
  - enqueue_research_run carries max_retries=3 + 30-min time_limit
  - cancel_research_run records cancel_requested intent
  - cancel_research_run uses max_retries=0 (cancel is fire-and-forget)
  - module-level ENQUEUE_MAX_RETRIES constant matches actor decoration

These tests pin the contract so the Phase 1 bridge wiring (when
adapters/retrieval_bridge.py replaces the noop) can't silently change
the public interface.
"""

from __future__ import annotations

import pytest

pytest.importorskip("dramatiq")

from polaris_v6.queue.broker import get_broker  # noqa: E402

# Activate stub broker BEFORE importing actors so the @dramatiq.actor
# decorator registers against the right broker.
get_broker(use_stub=True)

from polaris_v6.queue.actors import (  # noqa: E402
    ENQUEUE_MAX_RETRIES,
    cancel_research_run,
    enqueue_research_run,
)


def test_enqueue_returns_completed_status_and_echoes_payload():
    payload = {"question": "ozempic CV?", "template": "clinical"}
    result = enqueue_research_run.fn("run-001", payload)
    assert result == {
        "run_id": "run-001",
        "status": "completed",
        "echo": payload,
    }


def test_enqueue_handles_empty_payload():
    result = enqueue_research_run.fn("run-empty", {})
    assert result["run_id"] == "run-empty"
    assert result["status"] == "completed"
    assert result["echo"] == {}


def test_enqueue_max_retries_constant_is_3():
    assert ENQUEUE_MAX_RETRIES == 3


def test_enqueue_actor_carries_max_retries_3():
    """The @dramatiq.actor decoration must match the documented constant."""
    assert enqueue_research_run.options.get("max_retries") == 3


def test_enqueue_actor_time_limit_is_30_minutes_in_ms():
    """30 minutes = 1,800,000 ms — long enough for cluster runs."""
    assert enqueue_research_run.options.get("time_limit") == 30 * 60 * 1000


def test_cancel_returns_cancel_requested_status():
    result = cancel_research_run.fn("run-002")
    assert result == {"run_id": "run-002", "status": "cancel_requested"}


def test_cancel_actor_max_retries_is_0():
    """Cancel is fire-and-forget — never retry."""
    assert cancel_research_run.options.get("max_retries") == 0


def test_actors_are_dramatiq_actor_instances():
    """Both actors must be wrapped via the @dramatiq.actor decorator."""
    assert hasattr(enqueue_research_run, "send")  # actor.send() enqueues
    assert hasattr(enqueue_research_run, "fn")    # actor.fn is the unwrapped callable
    assert hasattr(cancel_research_run, "send")
    assert hasattr(cancel_research_run, "fn")
