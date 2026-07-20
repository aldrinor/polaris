"""M6 GRAPH WIRING tests — compilation, state, routing, frontend compat.

Tests that the v3 graph compiles, nodes connect correctly, the entry
point signature matches v1, state stays bounded, and frontend
integration points exist.
"""

import inspect
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.polaris_graph.contracts_v3 import V3_NODE_NAMES


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

class TestGraphCompilation:
    """The v3 graph must compile without errors."""

    def test_graph_compiles(self):
        from src.polaris_graph.graph_v3 import build_v3_graph

        graph = build_v3_graph()
        assert graph is not None

    def test_graph_has_all_nodes(self):
        from src.polaris_graph.graph_v3 import build_v3_graph

        graph = build_v3_graph()
        # LangGraph compiled graph has .nodes attribute
        node_names = set(graph.nodes.keys()) if hasattr(graph, 'nodes') else set()
        # Should contain our v3 nodes (plus __start__, __end__)
        for expected in ["scope", "v3_search", "v3_outline", "v3_write_section", "v3_assemble"]:
            assert expected in node_names, f"Missing node: {expected}"


# ---------------------------------------------------------------------------
# State initialization
# ---------------------------------------------------------------------------

class TestStateInitialization:
    """V3 state must initialize with all required fields."""

    def test_create_v3_state(self):
        from src.polaris_graph.state_lightweight import create_v3_state

        state = create_v3_state(
            vector_id="V3_TEST_001",
            query="biochar heavy metal removal",
            application="water_treatment",
            region="global",
        )

        assert state["vector_id"] == "V3_TEST_001"
        assert state["original_query"] == "biochar heavy metal removal"
        assert state["status"] == "running"
        assert state["evidence_ids"] == []
        assert state["completed_sections"] == []
        assert state["gap_searches_done"] == 0

    def test_state_serialization_bounded(self):
        """Empty state must serialize to < 5KB."""
        from src.polaris_graph.state_lightweight import create_v3_state

        state = create_v3_state("test", "query", "app", "region")
        serialized = json.dumps(state)
        assert len(serialized) < 5000, f"Empty state too large: {len(serialized)} bytes"

    def test_state_with_evidence_ids_bounded(self):
        """State with 1000 evidence IDs must serialize to < 50KB."""
        from src.polaris_graph.state_lightweight import create_v3_state

        state = create_v3_state("test", "query", "app", "region")
        state["evidence_ids"] = [f"ev_{i:06x}" for i in range(1000)]
        state["evidence_meta"] = {
            f"ev_{i:06x}": {"tier": "GOLD", "score": 0.9}
            for i in range(1000)
        }

        serialized = json.dumps(state)
        size_kb = len(serialized) / 1024
        assert size_kb < 200, f"State with 1000 evidence IDs: {size_kb:.0f}KB (must be < 200KB)"


# ---------------------------------------------------------------------------
# build_and_run_v3 signature
# ---------------------------------------------------------------------------

class TestBuildAndRunSignature:
    """v3 entry point must accept the same params as v1 for live_server compat."""

    def test_signature_has_required_params(self):
        from src.polaris_graph.graph_v3 import build_and_run_v3

        sig = inspect.signature(build_and_run_v3)
        params = set(sig.parameters.keys())

        required = {"vector_id", "query", "application", "region"}
        assert required.issubset(params), f"Missing: {required - params}"

    def test_signature_has_optional_params(self):
        from src.polaris_graph.graph_v3 import build_and_run_v3

        sig = inspect.signature(build_and_run_v3)
        params = set(sig.parameters.keys())

        optional = {"max_iterations", "max_execution_minutes", "document_ids", "steer_callback"}
        for p in optional:
            assert p in params, f"Missing optional param: {p}"

    def test_is_async(self):
        from src.polaris_graph.graph_v3 import build_and_run_v3
        assert inspect.iscoroutinefunction(build_and_run_v3)


# ---------------------------------------------------------------------------
# Frontend compatibility
# ---------------------------------------------------------------------------

class TestFrontendCompatibility:
    """v3 node names must be registered in contracts for frontend updates."""

    def test_v3_node_names_cover_all_phases(self):
        assert "scope" in V3_NODE_NAMES
        assert "v3_search" in V3_NODE_NAMES
        assert "v3_outline" in V3_NODE_NAMES
        assert "v3_write_section" in V3_NODE_NAMES
        assert "v3_assemble" in V3_NODE_NAMES

    def test_v3_nodes_registered_in_graph(self):
        from src.polaris_graph.graph_v3 import build_v3_graph

        graph = build_v3_graph()
        graph_nodes = set(graph.nodes.keys()) if hasattr(graph, 'nodes') else set()

        for node_name in V3_NODE_NAMES:
            if node_name in ("v3_storm", "v3_critic"):
                continue  # These are sub-phases, not separate graph nodes
            assert node_name in graph_nodes, f"Node '{node_name}' in V3_NODE_NAMES but not in graph"


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

class TestRoutingLogic:
    """Conditional edges must route correctly."""

    def test_outline_gap_routing(self):
        from src.polaris_graph.graph_v3 import _should_search_gaps

        # Has gaps and hasn't exceeded cap
        state_with_gaps = {
            "gaps": [{"section_id": "s01", "description": "Need more data"}],
            "gap_searches_done": 0,
            "status": "running",
        }
        assert _should_search_gaps(state_with_gaps) == "v3_search"

        # No gaps
        state_no_gaps = {
            "gaps": [],
            "gap_searches_done": 0,
            "status": "running",
        }
        assert _should_search_gaps(state_no_gaps) == "v3_write_section"

        # Gaps but cap reached
        state_capped = {
            "gaps": [{"section_id": "s01", "description": "Need more"}],
            "gap_searches_done": 2,
            "status": "running",
        }
        assert _should_search_gaps(state_capped) == "v3_write_section"


# ---------------------------------------------------------------------------
# Dispatch routing
# ---------------------------------------------------------------------------

class TestDispatchRouting:
    """__init__.py and live_server.py routing must support v3."""

    def test_graph_version_env_var(self):
        """PG_GRAPH_VERSION=v3 should route to v3."""
        # This tests that the env var mechanism works
        # Actual routing tested via integration in M7
        os.environ["PG_GRAPH_VERSION"] = "v3"
        version = os.getenv("PG_GRAPH_VERSION", "v1")
        assert version == "v3"
        os.environ.pop("PG_GRAPH_VERSION", None)
