"""Integration tests for memory system activation."""

import asyncio
import os
import pytest
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp()
os.environ["PG_CACHE_DIR"] = _tmp_dir


from src.polaris_graph.memory.evidence_hierarchy import (
    store_evidence,
    get_l0_summaries,
    get_by_perspective,
    count_by_tier,
)
from src.polaris_graph.memory.session_feedback import (
    record_feedback,
    get_best_strategies,
    get_session_summary,
)


@pytest.fixture(autouse=True)
def _clean_dbs():
    for db_name in ["pg_evidence_hierarchy.sqlite", "pg_session_feedback.sqlite"]:
        db_path = Path(_tmp_dir) / db_name
        if db_path.exists():
            db_path.unlink()
    yield


class TestEvidenceHierarchyIntegration:
    @pytest.mark.asyncio
    async def test_async_round_trip(self):
        """Store and retrieve evidence in a real SQLite DB."""
        ok = await store_evidence(
            evidence_id="ev_int_01", vector_id="v_int",
            cluster_id="c1", l0_summary="Chlorine kills bacteria",
            l1_overview="Chlorine kills bacteria in water. Source: WHO. Quality: GOLD",
            l2_json={"evidence_id": "ev_int_01", "statement": "Chlorine kills bacteria"},
            perspective="Public_Health", quality_tier="GOLD", relevance_score=0.9,
        )
        assert ok
        summaries = await get_l0_summaries("v_int")
        assert any(s["evidence_id"] == "ev_int_01" for s in summaries)

    @pytest.mark.asyncio
    async def test_perspective_gap_detection(self):
        """Missing perspectives should be detectable."""
        perspectives = ["Scientific", "Regulatory", "Scientific"]
        for i, p in enumerate(perspectives):
            await store_evidence(
                evidence_id=f"ev_gap_{i}", vector_id="v_gap",
                cluster_id="c1", l0_summary=f"Fact {i}", l1_overview=f"Overview {i}",
                l2_json={}, perspective=p, quality_tier="BRONZE", relevance_score=0.5,
            )
        sci = await get_by_perspective("v_gap", "Scientific")
        eco = await get_by_perspective("v_gap", "Economic")
        assert len(sci) == 2
        assert len(eco) == 0  # Gap detected

    @pytest.mark.asyncio
    async def test_concurrent_writes(self):
        """10 parallel writes should not corrupt the database."""
        tasks = []
        for i in range(10):
            tasks.append(store_evidence(
                evidence_id=f"ev_conc_{i}", vector_id="v_conc",
                cluster_id="c1", l0_summary=f"Fact {i}", l1_overview=f"Overview {i}",
                l2_json={"i": i}, perspective="Scientific", quality_tier="GOLD",
                relevance_score=0.5 + i * 0.05,
            ))
        results = await asyncio.gather(*tasks)
        assert all(r is True for r in results)
        counts = await count_by_tier("v_conc")
        assert counts.get("GOLD", 0) == 10


class TestSessionFeedbackIntegration:
    @pytest.mark.asyncio
    async def test_async_round_trip(self):
        """Record and retrieve session feedback."""
        await record_feedback(
            session_id="int_sess", vector_id="v_int",
            query_text="water filter bacteria", search_type="serper",
            source_url="https://who.int/water", evidence_count=5,
            avg_relevance=0.85, faithfulness_contribution=0.9,
        )
        summary = await get_session_summary("int_sess")
        assert summary["total_evidence"] == 5


class TestCrossVectorGraceful:
    def test_graceful_degradation(self):
        """Cross-vector should degrade gracefully without ChromaDB."""
        from src.polaris_graph.memory.cross_vector import query_ltm, get_ltm_stats
        # Should not raise, just return empty/defaults
        result = query_ltm("test query")
        assert isinstance(result, list)
        stats = get_ltm_stats()
        assert isinstance(stats, dict)
