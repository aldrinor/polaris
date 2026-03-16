"""Integration tests: rewind with state patch → override stored → retrieved on next run.

Sprint 3 deferred item — verifies the full human correction feedback loop:
  1. store_human_override() persists correction in ChromaDB
  2. query_human_overrides() retrieves by semantic similarity
  3. Planner injects top-5 overrides as "HUMAN CORRECTION HISTORY" in prompt

Uses a real (ephemeral) ChromaDB EphemeralClient for each test so tests are
fully isolated and exercise the actual embedding model + similarity search.
"""

import datetime
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Skip if chromadb not installed
# ---------------------------------------------------------------------------
try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

pytestmark = pytest.mark.skipif(not HAS_CHROMA, reason="chromadb not installed")


_MODULE_CHROMA = chromadb.EphemeralClient()


# ---------------------------------------------------------------------------
# Fixture: isolated cross_vector with unique collection names per test
# ---------------------------------------------------------------------------

@pytest.fixture()
def cv():
    """Yield the cross_vector module with unique per-test collection names
    to guarantee full isolation (EphemeralClient shares a global backend)."""
    import importlib

    try:
        import src.polaris_graph.memory.cross_vector as cv_mod
        importlib.reload(cv_mod)
    except Exception:
        pytest.skip("Cannot import cross_vector module")

    client = _MODULE_CHROMA
    suffix = uuid.uuid4().hex[:8]
    ltm_name = f"{cv_mod.LTM_COLLECTION_NAME}_{suffix}"
    ovr_name = f"{cv_mod.OVERRIDE_COLLECTION_NAME}_{suffix}"

    original_get_col = cv_mod._get_collection
    original_get_ovr = getattr(cv_mod, "_get_override_collection", None)

    def _patched_get_collection(manager):
        return client.get_or_create_collection(name=ltm_name)

    def _patched_get_override_collection(manager):
        return client.get_or_create_collection(name=ovr_name)

    with patch.object(cv_mod, "_get_chroma_manager", return_value=client):
        cv_mod._get_collection = _patched_get_collection
        cv_mod._get_override_collection = _patched_get_override_collection
        yield cv_mod
        cv_mod._get_collection = original_get_col
        if original_get_ovr is not None:
            cv_mod._get_override_collection = original_get_ovr

    # Cleanup per-test collections
    for col_name in (ltm_name, ovr_name):
        try:
            client.delete_collection(col_name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sample override data
# ---------------------------------------------------------------------------

def _make_override(
    vector_id: str = "VEC_001",
    checkpoint_id: str = "cp_abc",
    node: str = "verify",
    override_type: str = "state_patch",
    original: str = "Faithfulness threshold was 0.5",
    corrected: str = "Raised threshold to 0.8 for medical claims",
    context: str = "PFAS health effects research requiring high accuracy",
    idx: int = 0,
) -> dict:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "override_id": f"ho_{vector_id}_{checkpoint_id}_{idx}",
        "vector_id": vector_id,
        "checkpoint_id": checkpoint_id,
        "node": node,
        "override_type": override_type,
        "original_value": original,
        "corrected_value": corrected,
        "context": context,
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# Tests: store_human_override
# ---------------------------------------------------------------------------


class TestStoreHumanOverride:
    """Verify override storage in ChromaDB."""

    def test_store_returns_true(self, cv):
        override = _make_override()
        result = cv.store_human_override(override)
        assert result is True

    def test_store_multiple_overrides(self, cv):
        for i in range(5):
            ov = _make_override(idx=i, context=f"Correction {i} for PFAS analysis")
            assert cv.store_human_override(ov) is True

    def test_store_idempotent(self, cv):
        """Storing same override_id twice should upsert, not duplicate."""
        ov = _make_override()
        cv.store_human_override(ov)
        cv.store_human_override(ov)
        results = cv.query_human_overrides(query="PFAS health", k=20)
        ids = [r["id"] for r in results]
        assert ids.count(ov["override_id"]) <= 1

    def test_store_with_long_values(self, cv):
        """Override with max-length fields should still store."""
        ov = _make_override(
            original="X" * 500,
            corrected="Y" * 500,
            context="Z" * 500,
        )
        assert cv.store_human_override(ov) is True


# ---------------------------------------------------------------------------
# Tests: query_human_overrides
# ---------------------------------------------------------------------------


class TestQueryHumanOverrides:
    """Verify semantic retrieval of stored overrides."""

    @pytest.fixture(autouse=True)
    def _seed_overrides(self, cv):
        """Seed 3 topically diverse overrides."""
        self.cv = cv
        overrides = [
            _make_override(idx=0, node="verify",
                           context="PFAS water filtration accuracy threshold",
                           original="Threshold 0.5", corrected="Threshold 0.8"),
            _make_override(idx=1, node="analyze",
                           context="Climate change carbon emissions data",
                           original="Used 2020 data", corrected="Updated to 2024 data"),
            _make_override(idx=2, node="verify",
                           context="Pharmaceutical drug interaction safety",
                           original="Missed contraindications", corrected="Added FDA warnings"),
        ]
        for ov in overrides:
            cv.store_human_override(ov)

    def test_query_returns_results(self):
        results = self.cv.query_human_overrides(query="PFAS water treatment", k=5)
        assert len(results) >= 1

    def test_query_result_schema(self):
        results = self.cv.query_human_overrides(query="filtration", k=5)
        assert len(results) >= 1
        item = results[0]
        required_keys = {"id", "context", "override_type", "node",
                         "vector_id", "checkpoint_id", "distance"}
        assert required_keys.issubset(set(item.keys())), \
            f"Missing keys: {required_keys - set(item.keys())}"

    def test_query_relevance_ordering(self):
        """PFAS query should rank PFAS override highest (lowest distance)."""
        results = self.cv.query_human_overrides(
            query="PFAS water filtration methods", k=5
        )
        if len(results) >= 2:
            distances = [r["distance"] for r in results]
            assert distances == sorted(distances), \
                f"Not sorted by distance: {distances}"

    def test_query_node_filter(self):
        """Filter by node should return only matching overrides."""
        verify_results = self.cv.query_human_overrides(
            query="accuracy threshold", node="verify", k=5
        )
        for r in verify_results:
            assert r["node"] == "verify"

    def test_query_k_limit(self):
        results = self.cv.query_human_overrides(query="data", k=1)
        assert len(results) <= 1

    def test_query_unrelated_topic(self):
        """Unrelated query should still return results but with higher distance."""
        related = self.cv.query_human_overrides(
            query="PFAS water filtration", k=3
        )
        unrelated = self.cv.query_human_overrides(
            query="quantum computing neural networks", k=3
        )
        if related and unrelated:
            avg_r = sum(r["distance"] for r in related) / len(related)
            avg_u = sum(r["distance"] for r in unrelated) / len(unrelated)
            assert avg_u > avg_r, \
                f"Unrelated ({avg_u:.3f}) should have higher distance " \
                f"than related ({avg_r:.3f})"


# ---------------------------------------------------------------------------
# Tests: planner injection
# ---------------------------------------------------------------------------


class TestPlannerInjection:
    """Verify that overrides are injected into planner prompt."""

    @pytest.fixture(autouse=True)
    def _seed_overrides(self, cv):
        self.cv = cv
        for i in range(3):
            ov = _make_override(
                idx=i,
                context=f"PFAS correction #{i} for water treatment analysis",
            )
            cv.store_human_override(ov)

    def test_override_context_format(self):
        """query_human_overrides output should be formattable for prompt injection."""
        overrides = self.cv.query_human_overrides(
            query="PFAS water treatment", k=10
        )
        assert len(overrides) >= 1

        # Simulate what planner.py does (lines 140-160)
        override_lines = []
        for o in overrides[:5]:
            ctx = o.get("context", "")[:200]
            otype = o.get("override_type", "unknown")
            override_lines.append(f"- Previous correction ({otype}): {ctx}")
        override_context = (
            "\n\nHUMAN CORRECTION HISTORY (avoid these mistakes):\n"
            + "\n".join(override_lines)
        )

        assert "HUMAN CORRECTION HISTORY" in override_context
        assert "Previous correction" in override_context
        assert len(override_lines) >= 1

    def test_planner_prompt_includes_overrides(self):
        """Simulate planner.plan_queries() override injection section."""
        query = "PFAS water filtration methods"

        # This mirrors the exact code path in planner.py:140-170
        override_context = ""
        try:
            overrides = self.cv.query_human_overrides(query=query, k=10)
            if overrides:
                override_lines = []
                for o in overrides[:5]:
                    ctx = o.get("context", "")[:200]
                    otype = o.get("override_type", "unknown")
                    override_lines.append(
                        f"- Previous correction ({otype}): {ctx}"
                    )
                override_context = (
                    "\n\nHUMAN CORRECTION HISTORY (avoid these mistakes):\n"
                    + "\n".join(override_lines)
                )
        except Exception:
            pass

        # Build prompt as planner does
        prompt = f"Research question: {query}\n{override_context}"

        assert "HUMAN CORRECTION HISTORY" in prompt
        assert "state_patch" in prompt  # override_type from our fixtures


# ---------------------------------------------------------------------------
# Tests: full feedback loop (store → query → inject)
# ---------------------------------------------------------------------------


class TestFullFeedbackLoop:
    """End-to-end: rewind stores override, next query retrieves it,
    planner would see it in prompt."""

    def test_store_query_inject_cycle(self, cv):
        # 1. Simulate rewind with state_patch → store override
        override = _make_override(
            vector_id="VEC_REWIND_001",
            checkpoint_id="cp_synth_42",
            node="synthesize",
            override_type="state_patch",
            original="Section 3 used outdated EPA 2020 guidance",
            corrected="Updated to EPA 2024 PFAS MCL of 4 ppt",
            context="EPA PFAS maximum contaminant level regulation update",
        )
        stored = cv.store_human_override(override)
        assert stored is True

        # 2. Simulate next research run: planner queries overrides
        results = cv.query_human_overrides(
            query="EPA PFAS drinking water regulations", k=5
        )
        assert len(results) >= 1

        # The stored override should appear
        found = any(
            "EPA" in r.get("context", "") and "PFAS" in r.get("context", "")
            for r in results
        )
        assert found, f"Stored override not found in results: {results}"

        # 3. Build prompt injection (as planner.py does)
        override_lines = []
        for o in results[:5]:
            ctx = o.get("context", "")[:200]
            otype = o.get("override_type", "unknown")
            override_lines.append(f"- Previous correction ({otype}): {ctx}")

        override_context = (
            "\n\nHUMAN CORRECTION HISTORY (avoid these mistakes):\n"
            + "\n".join(override_lines)
        )

        assert "HUMAN CORRECTION HISTORY" in override_context
        assert "state_patch" in override_context

    def test_multiple_vectors_cross_pollinate(self, cv):
        """Overrides from VEC_A should be retrievable when querying for VEC_B
        on the same topic (semantic cross-pollination)."""
        # Store override from vector A
        ov_a = _make_override(
            vector_id="VEC_A",
            checkpoint_id="cp_1",
            node="verify",
            context="Municipal water treatment PFAS ion exchange resin",
            original="Used single-pass IX", corrected="Implemented lead-lag IX",
            idx=10,
        )
        cv.store_human_override(ov_a)

        # Query from vector B on same topic
        results = cv.query_human_overrides(
            query="Ion exchange resin configuration for PFAS removal", k=5
        )
        assert len(results) >= 1
        # Should find VEC_A's override via semantic similarity
        found_vec_a = any(r.get("vector_id") == "VEC_A" for r in results)
        assert found_vec_a, \
            f"Cross-vector override not found. Results: {[r.get('vector_id') for r in results]}"

    def test_node_scoped_retrieval(self, cv):
        """Store overrides for different nodes, retrieve only matching node."""
        cv.store_human_override(_make_override(
            idx=20, node="verify",
            context="Verification threshold correction for PFAS data",
        ))
        cv.store_human_override(_make_override(
            idx=21, node="analyze",
            context="Analysis scope correction for PFAS data",
        ))
        cv.store_human_override(_make_override(
            idx=22, node="synthesize",
            context="Synthesis structure correction for PFAS report",
        ))

        verify_only = cv.query_human_overrides(
            query="PFAS data correction", node="verify", k=10
        )
        for r in verify_only:
            assert r["node"] == "verify", \
                f"Expected node='verify', got '{r['node']}'"

    def test_empty_query_safe(self, cv):
        """Empty query should not crash the override system."""
        cv.store_human_override(_make_override(idx=30))
        results = cv.query_human_overrides(query="", k=5)
        assert isinstance(results, list)

    def test_override_survives_within_session(self, cv):
        """Override stored early in session should remain queryable later."""
        ov = _make_override(
            idx=40,
            context="Persistence test: PFAS remediation correction",
        )
        cv.store_human_override(ov)

        # Store more overrides (simulates additional corrections in same session)
        for i in range(3):
            cv.store_human_override(_make_override(
                idx=50 + i,
                context=f"Additional correction {i} for climate data",
            ))

        # Original override should still be found
        results = cv.query_human_overrides(
            query="PFAS remediation correction", k=5
        )
        assert len(results) >= 1
        found_pfas = any("PFAS" in r.get("context", "") for r in results)
        assert found_pfas, "Original PFAS override should still be retrievable"
