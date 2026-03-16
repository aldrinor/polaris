"""
Integration tests for checkpoint rewind and resume (Sprint 2 deferred).

Verifies that:
1. list_checkpoints() returns summaries from compiled graph state history
2. get_checkpoint_state() returns full state at a specific checkpoint
3. rewind_to_checkpoint() applies state_patch and resumes execution
4. _extract_state_summary() computes correct metrics from state values
5. API endpoints return correct HTTP status codes for checkpoint operations
6. clear_checkpoint() removes entries from the database

Uses mock LangGraph app objects — no real pipeline execution or LLM calls.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock LangGraph snapshot / config structures
# ---------------------------------------------------------------------------

@dataclass
class MockStateSnapshot:
    """Mimics langgraph StateSnapshot returned by aget_state / aget_state_history."""
    values: dict[str, Any] = field(default_factory=dict)
    next: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    parent_config: dict[str, Any] | None = None


def _make_snapshot(
    checkpoint_id: str,
    node: str,
    thread_id: str = "pg_TEST_CP_001",
    evidence_count: int = 0,
    claims_count: int = 0,
    sections_count: int = 0,
    iteration: int = 0,
    faithfulness: float = -1.0,
    status: str = "unknown",
    query: str = "What is PFAS?",
    final_report: str = "",
    parent_id: str | None = None,
) -> MockStateSnapshot:
    """Build a MockStateSnapshot with typical pipeline state values."""
    values = {
        "vector_id": "TEST_CP_001",
        "original_query": query,
        "evidence": [{"id": f"ev_{i}"} for i in range(evidence_count)],
        "claims": [{"id": f"cl_{i}"} for i in range(claims_count)],
        "sections": [{"id": f"sec_{i}"} for i in range(sections_count)],
        "iteration_count": iteration,
        "faithfulness_score": faithfulness,
        "status": status,
        "final_report": final_report,
    }
    next_nodes = (node,) if node != "__end__" else ()
    parent = {"configurable": {"checkpoint_id": parent_id}} if parent_id else None
    return MockStateSnapshot(
        values=values,
        next=next_nodes,
        config={"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}},
        created_at="2026-03-02T10:00:00Z",
        parent_config=parent,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SNAPSHOTS = [
    _make_snapshot("cp_003", "synthesize", evidence_count=200, claims_count=150,
                   iteration=3, faithfulness=0.85, status="verifying",
                   parent_id="cp_002"),
    _make_snapshot("cp_002", "verify", evidence_count=200, claims_count=0,
                   iteration=2, faithfulness=-1.0, status="analyzing",
                   parent_id="cp_001"),
    _make_snapshot("cp_001", "search", evidence_count=50, claims_count=0,
                   iteration=1, faithfulness=-1.0, status="planning",
                   parent_id=None),
]


def _mock_compiled_app(snapshots: list[MockStateSnapshot] | None = None):
    """Create a mock compiled LangGraph app with checkpoint methods."""
    if snapshots is None:
        snapshots = SNAPSHOTS

    app = MagicMock()

    # aget_state_history: async generator yielding snapshots
    async def _history(config, limit=50):
        for snap in snapshots[:limit]:
            yield snap

    app.aget_state_history = _history

    # aget_state: return specific snapshot by checkpoint_id
    async def _get_state(config):
        cp_id = config.get("configurable", {}).get("checkpoint_id", "")
        for snap in snapshots:
            if snap.config["configurable"]["checkpoint_id"] == cp_id:
                return snap
        # If no checkpoint_id specified, return the latest
        if not cp_id and snapshots:
            return snapshots[0]
        return None

    app.aget_state = AsyncMock(side_effect=_get_state)

    # aupdate_state: return updated config
    async def _update_state(config, values=None, as_node=None):
        return {"configurable": {"thread_id": "pg_TEST_CP_001", "checkpoint_id": "cp_patched"}}

    app.aupdate_state = AsyncMock(side_effect=_update_state)

    # astream: simulate resumed execution yielding node outputs
    async def _stream(input_val, config, stream_mode="updates"):
        yield {"synthesize": {"status": "complete", "final_report": "Rewind report.", "sections": [{"id": "sec_0"}, {"id": "sec_1"}]}}

    app.astream = _stream

    return app


# ---------------------------------------------------------------------------
# Tests: _extract_state_summary
# ---------------------------------------------------------------------------

class TestExtractStateSummary:
    """Test the state summary extraction logic."""

    def test_summary_counts(self):
        """Summary extracts correct evidence, claims, sections counts."""
        from src.polaris_graph.checkpoint_manager import _extract_state_summary

        values = {
            "evidence": [{"id": "ev_1"}, {"id": "ev_2"}, {"id": "ev_3"}],
            "claims": [{"id": "cl_1"}, {"id": "cl_2"}],
            "sections": [{"id": "sec_1"}],
            "iteration_count": 2,
            "faithfulness_score": 0.85,
            "status": "verifying",
            "original_query": "What is PFAS?",
            "final_report": "This is a test report with several words.",
        }

        summary = _extract_state_summary(values)
        assert summary["evidence_count"] == 3
        assert summary["claims_count"] == 2
        assert summary["sections_count"] == 1
        assert summary["iteration"] == 2
        assert summary["faithfulness"] == 85.0
        assert summary["status"] == "verifying"
        assert summary["has_report"] is True
        assert summary["word_count"] == 8
        assert "PFAS" in summary["query"]

    def test_summary_empty_state(self):
        """Summary handles empty state gracefully."""
        from src.polaris_graph.checkpoint_manager import _extract_state_summary

        summary = _extract_state_summary({})
        assert summary["evidence_count"] == 0
        assert summary["claims_count"] == 0
        assert summary["sections_count"] == 0
        assert summary["has_report"] is False
        assert summary["word_count"] == 0

    def test_summary_quality_metrics_faithfulness(self):
        """Summary reads faithfulness from quality_metrics dict first."""
        from src.polaris_graph.checkpoint_manager import _extract_state_summary

        values = {
            "evidence": [],
            "claims": [],
            "sections": [],
            "quality_metrics": {"faithfulness_pct": 92.5},
            "faithfulness_score": 0.70,
        }
        summary = _extract_state_summary(values)
        # quality_metrics takes precedence over faithfulness_score
        assert summary["faithfulness"] == 92.5


# ---------------------------------------------------------------------------
# Tests: list_checkpoints
# ---------------------------------------------------------------------------

class TestListCheckpoints:
    """Test checkpoint listing logic."""

    @pytest.mark.asyncio
    async def test_list_returns_summaries(self):
        """list_checkpoints returns checkpoint summaries in order."""
        from src.polaris_graph.checkpoint_manager import list_checkpoints

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True):
            result = await list_checkpoints("TEST_CP_001", app)

        assert len(result) == 3
        # Most recent first
        assert result[0]["checkpoint_id"] == "cp_003"
        assert result[0]["node"] == "synthesize"
        assert result[0]["evidence_count"] == 200
        assert result[0]["claims_count"] == 150
        assert result[0]["iteration"] == 3
        assert result[0]["faithfulness"] == 85.0
        assert result[0]["parent_checkpoint_id"] == "cp_002"

        # Second checkpoint
        assert result[1]["checkpoint_id"] == "cp_002"
        assert result[1]["node"] == "verify"
        assert result[1]["evidence_count"] == 200

        # Third checkpoint (earliest)
        assert result[2]["checkpoint_id"] == "cp_001"
        assert result[2]["node"] == "search"
        assert result[2]["evidence_count"] == 50
        assert result[2]["parent_checkpoint_id"] is None

    @pytest.mark.asyncio
    async def test_list_empty_when_disabled(self):
        """list_checkpoints returns empty when PG_CHECKPOINT_ENABLED=0."""
        from src.polaris_graph.checkpoint_manager import list_checkpoints

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", False):
            result = await list_checkpoints("TEST_CP_001", app)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_empty_when_no_db(self):
        """list_checkpoints returns empty when checkpoint DB doesn't exist."""
        from src.polaris_graph.checkpoint_manager import list_checkpoints

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("/nonexistent/db.sqlite")):
            result = await list_checkpoints("TEST_CP_001", app)

        assert result == []


# ---------------------------------------------------------------------------
# Tests: get_checkpoint_state
# ---------------------------------------------------------------------------

class TestGetCheckpointState:
    """Test checkpoint state retrieval logic."""

    @pytest.mark.asyncio
    async def test_get_returns_full_state(self):
        """get_checkpoint_state returns metadata + serialized state."""
        from src.polaris_graph.checkpoint_manager import get_checkpoint_state

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True):
            result = await get_checkpoint_state("TEST_CP_001", "cp_003", app)

        assert "metadata" in result
        assert "state" in result
        assert result["metadata"]["checkpoint_id"] == "cp_003"
        assert result["metadata"]["node"] == "synthesize"
        assert result["metadata"]["summary"]["evidence_count"] == 200
        assert result["state"]["vector_id"] == "TEST_CP_001"
        assert len(result["state"]["evidence"]) == 200

    @pytest.mark.asyncio
    async def test_get_returns_error_for_missing(self):
        """get_checkpoint_state returns error for nonexistent checkpoint."""
        from src.polaris_graph.checkpoint_manager import get_checkpoint_state

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True):
            result = await get_checkpoint_state("TEST_CP_001", "cp_nonexistent", app)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_returns_error_when_disabled(self):
        """get_checkpoint_state returns error when checkpointing disabled."""
        from src.polaris_graph.checkpoint_manager import get_checkpoint_state

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", False):
            result = await get_checkpoint_state("TEST_CP_001", "cp_003", app)

        assert "error" in result
        assert "disabled" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tests: rewind_to_checkpoint
# ---------------------------------------------------------------------------

class TestRewindToCheckpoint:
    """Test checkpoint rewind and resume logic."""

    @pytest.mark.asyncio
    async def test_rewind_applies_patch_and_resumes(self):
        """rewind_to_checkpoint applies state_patch and streams execution."""
        from src.polaris_graph.checkpoint_manager import rewind_to_checkpoint

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True), \
             patch.dict(os.environ, {"PG_AUTO_RESUME": "1", "PG_REWIND_MAX_MINUTES": "1"}):
            result = await rewind_to_checkpoint(
                "TEST_CP_001", "cp_003", app,
                state_patch={"max_iterations": 5},
            )

        assert result["status"] == "complete"
        assert result["metadata"]["resume_node"] == "synthesize"
        assert result["metadata"]["patched_keys"] == ["max_iterations"]
        assert result["metadata"]["auto_resume"] is True
        assert result["metadata"]["elapsed_seconds"] >= 0

        # Verify aupdate_state was called with the patch
        app.aupdate_state.assert_called_once()
        call_kwargs = app.aupdate_state.call_args
        assert call_kwargs.kwargs["values"] == {"max_iterations": 5}
        assert call_kwargs.kwargs["as_node"] == "synthesize"

    @pytest.mark.asyncio
    async def test_rewind_without_patch(self):
        """rewind_to_checkpoint resumes without state modification."""
        from src.polaris_graph.checkpoint_manager import rewind_to_checkpoint

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True), \
             patch.dict(os.environ, {"PG_AUTO_RESUME": "1", "PG_REWIND_MAX_MINUTES": "1"}):
            result = await rewind_to_checkpoint("TEST_CP_001", "cp_003", app)

        assert result["status"] == "complete"
        assert result["metadata"]["patched_keys"] == []
        # aupdate_state should NOT be called when no patch
        app.aupdate_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_rewind_no_auto_resume(self):
        """rewind with PG_AUTO_RESUME=0 patches but does not execute."""
        from src.polaris_graph.checkpoint_manager import rewind_to_checkpoint

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True), \
             patch.dict(os.environ, {"PG_AUTO_RESUME": "0"}):
            result = await rewind_to_checkpoint(
                "TEST_CP_001", "cp_003", app,
                state_patch={"needs_iteration": True},
            )

        assert result["status"] == "patched_not_resumed"
        assert result["metadata"]["auto_resume"] is False
        assert "needs_iteration" in result["metadata"]["patched_keys"]

    @pytest.mark.asyncio
    async def test_rewind_end_checkpoint_fails(self):
        """rewind to __end__ checkpoint returns error."""
        from src.polaris_graph.checkpoint_manager import rewind_to_checkpoint

        # Create app with a completed checkpoint (next=())
        end_snap = _make_snapshot("cp_end", "__end__", evidence_count=100,
                                  status="complete", final_report="Done.")
        app = _mock_compiled_app([end_snap])

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True):
            result = await rewind_to_checkpoint("TEST_CP_001", "cp_end", app)

        assert "error" in result
        assert "__end__" in result["error"]

    @pytest.mark.asyncio
    async def test_rewind_missing_checkpoint_fails(self):
        """rewind to nonexistent checkpoint returns error."""
        from src.polaris_graph.checkpoint_manager import rewind_to_checkpoint

        app = _mock_compiled_app()

        with patch("src.polaris_graph.checkpoint_manager.PG_CHECKPOINT_ENABLED", True), \
             patch("src.polaris_graph.checkpoint_manager.CHECKPOINT_DB", Path("state/pg_checkpoints.sqlite")), \
             patch.object(Path, "exists", return_value=True):
            result = await rewind_to_checkpoint("TEST_CP_001", "cp_nonexistent", app)

        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: API endpoints via httpx
# ---------------------------------------------------------------------------

class TestCheckpointAPI:
    """Test the FastAPI checkpoint endpoints."""

    @pytest.mark.asyncio
    async def test_checkpoints_list_endpoint_disabled(self):
        """GET /api/research/checkpoints/{vid} returns empty when disabled."""
        from httpx import ASGITransport, AsyncClient
        from scripts.live_server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("scripts.live_server._PG_CHECKPOINT_ENABLED", False):
                resp = await client.get("/api/research/checkpoints/TEST_CP_001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["checkpoints"] == []
        assert data["checkpoint_enabled"] is False

    @pytest.mark.asyncio
    async def test_checkpoint_detail_endpoint_disabled(self):
        """GET /api/research/checkpoint/{vid}/{cpid} returns 400 when disabled."""
        from httpx import ASGITransport, AsyncClient
        from scripts.live_server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("scripts.live_server._PG_CHECKPOINT_ENABLED", False), \
                 patch("scripts.live_server._CHECKPOINT_AVAILABLE", False):
                resp = await client.get("/api/research/checkpoint/TEST_CP_001/cp_003")

        assert resp.status_code == 400
        assert "disabled" in resp.json().get("error", "").lower()

    @pytest.mark.asyncio
    async def test_rewind_endpoint_disabled(self):
        """POST /api/research/rewind/{vid}/{cpid} returns 400 when disabled."""
        from httpx import ASGITransport, AsyncClient
        from scripts.live_server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("scripts.live_server._PG_CHECKPOINT_ENABLED", False), \
                 patch("scripts.live_server._CHECKPOINT_AVAILABLE", False):
                resp = await client.post(
                    "/api/research/rewind/TEST_CP_001/cp_003",
                    json={"state_patch": {"max_iterations": 5}},
                )

        assert resp.status_code == 400
        assert "disabled" in resp.json().get("error", "").lower()


# ---------------------------------------------------------------------------
# Tests: _serialize_state
# ---------------------------------------------------------------------------

class TestSerializeState:
    """Test state serialization for JSON responses."""

    def test_serialize_plain_values(self):
        """Plain JSON-serializable values pass through unchanged."""
        from src.polaris_graph.checkpoint_manager import _serialize_state

        values = {"a": 1, "b": "hello", "c": [1, 2, 3], "d": {"x": True}}
        result = _serialize_state(values)
        assert result == values

    def test_serialize_pydantic_models(self):
        """Pydantic models are converted via model_dump()."""
        from src.polaris_graph.checkpoint_manager import _serialize_state

        class FakeModel:
            def model_dump(self):
                return {"field": "value"}

        values = {"model": FakeModel()}
        result = _serialize_state(values)
        assert result["model"] == {"field": "value"}

    def test_serialize_list_of_models(self):
        """Lists of Pydantic models are serialized element-wise."""
        from src.polaris_graph.checkpoint_manager import _serialize_state

        class FakeItem:
            def model_dump(self):
                return {"id": 1}

        values = {"items": [FakeItem(), FakeItem()]}
        result = _serialize_state(values)
        assert result["items"] == [{"id": 1}, {"id": 1}]


# ---------------------------------------------------------------------------
# Tests: thread ID generation
# ---------------------------------------------------------------------------

class TestThreadId:
    """Test thread ID generation consistency."""

    def test_thread_id_format(self):
        """get_thread_id generates pg_{vector_id} format."""
        from src.polaris_graph.checkpoint_manager import get_thread_id

        assert get_thread_id("TEST_001") == "pg_TEST_001"
        assert get_thread_id("WEB_20260302T214547_8aff6f") == "pg_WEB_20260302T214547_8aff6f"

    def test_thread_id_deterministic(self):
        """Same vector_id always produces the same thread_id."""
        from src.polaris_graph.checkpoint_manager import get_thread_id

        tid_1 = get_thread_id("VECTOR_ABC")
        tid_2 = get_thread_id("VECTOR_ABC")
        assert tid_1 == tid_2
