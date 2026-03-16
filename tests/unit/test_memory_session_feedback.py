"""Unit tests for session_feedback memory module."""

import os
import pytest
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp()
os.environ["PG_CACHE_DIR"] = _tmp_dir

from src.polaris_graph.memory.session_feedback import (
    record_feedback,
    get_best_strategies,
    get_source_performance,
    get_session_summary,
)


@pytest.fixture(autouse=True)
def _clean_db():
    db_path = Path(_tmp_dir) / "pg_session_feedback.sqlite"
    if db_path.exists():
        db_path.unlink()
    yield


@pytest.mark.asyncio
async def test_record_and_get_strategies():
    for i in range(5):
        await record_feedback(
            session_id="sess1", vector_id="v1",
            query_text="water filter effectiveness",
            search_type="serper", source_url=f"https://source{i}.com",
            evidence_count=3, avg_relevance=0.8, faithfulness_contribution=0.7,
        )
    best = await get_best_strategies(min_evidence=3)
    assert len(best) > 0
    assert best[0]["total_evidence"] >= 3


@pytest.mark.asyncio
async def test_source_performance():
    for i in range(4):
        await record_feedback(
            session_id="sess2", vector_id="v2",
            query_text=f"query {i}", search_type="s2",
            source_url="https://goodsource.com",
            evidence_count=5, avg_relevance=0.9, faithfulness_contribution=0.95,
        )
    perf = await get_source_performance(min_entries=3)
    assert len(perf) > 0
    assert perf[0]["source_url"] == "https://goodsource.com"


@pytest.mark.asyncio
async def test_session_summary():
    await record_feedback(
        session_id="sess3", vector_id="v3",
        query_text="test", search_type="exa", source_url="https://test.com",
        evidence_count=10, avg_relevance=0.75, faithfulness_contribution=0.8,
    )
    summary = await get_session_summary("sess3")
    assert summary["session_id"] == "sess3"
    assert summary["total_queries"] == 1
    assert summary["total_evidence"] == 10


@pytest.mark.asyncio
async def test_empty_db_returns_defaults():
    best = await get_best_strategies(min_evidence=1)
    assert best == []
    summary = await get_session_summary("nonexistent")
    assert summary["total_queries"] == 0
