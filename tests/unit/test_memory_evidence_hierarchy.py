"""Unit tests for evidence_hierarchy memory module."""

import asyncio
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Override cache DB path before importing
_tmp_dir = tempfile.mkdtemp()
os.environ["PG_CACHE_DIR"] = _tmp_dir

from src.polaris_graph.memory.evidence_hierarchy import (
    store_evidence,
    get_l0_summaries,
    get_l1_overviews,
    get_l2_full,
    get_by_perspective,
    get_high_quality,
    count_by_tier,
)


@pytest.fixture(autouse=True)
def _clean_db():
    """Clean the test DB before each test."""
    db_path = Path(_tmp_dir) / "pg_evidence_hierarchy.sqlite"
    if db_path.exists():
        db_path.unlink()
    yield


@pytest.mark.asyncio
async def test_store_and_get_l0():
    ok = await store_evidence(
        evidence_id="ev_test01",
        vector_id="v_test",
        cluster_id="c1",
        l0_summary="Water filters remove bacteria",
        l1_overview="Water filters remove bacteria. Quality: GOLD. Relevance: 0.9",
        l2_json={"evidence_id": "ev_test01", "statement": "Water filters remove bacteria"},
        perspective="Scientific",
        quality_tier="GOLD",
        relevance_score=0.9,
    )
    assert ok is True
    summaries = await get_l0_summaries("v_test")
    assert len(summaries) == 1
    assert summaries[0]["evidence_id"] == "ev_test01"
    assert "bacteria" in summaries[0]["l0_summary"]


@pytest.mark.asyncio
async def test_store_and_get_l1():
    await store_evidence(
        evidence_id="ev_l1_01", vector_id="v_l1", cluster_id="c2",
        l0_summary="UV sterilization", l1_overview="UV sterilization kills 99.9%",
        l2_json={}, perspective="Public_Health", quality_tier="SILVER",
        relevance_score=0.7,
    )
    overviews = await get_l1_overviews("v_l1")
    assert len(overviews) == 1
    assert overviews[0]["quality_tier"] == "SILVER"


@pytest.mark.asyncio
async def test_store_and_get_l2():
    full_data = {"evidence_id": "ev_l2_01", "statement": "Full detail", "source": "http://test.com"}
    await store_evidence(
        evidence_id="ev_l2_01", vector_id="v_l2", cluster_id="c3",
        l0_summary="summary", l1_overview="overview", l2_json=full_data,
        perspective="Regulatory", quality_tier="GOLD", relevance_score=0.95,
    )
    result = await get_l2_full("ev_l2_01")
    assert result is not None
    assert result["statement"] == "Full detail"


@pytest.mark.asyncio
async def test_get_by_perspective():
    for i, p in enumerate(["Scientific", "Scientific", "Regulatory"]):
        await store_evidence(
            evidence_id=f"ev_persp_{i}", vector_id="v_persp", cluster_id="c1",
            l0_summary=f"Summary {i}", l1_overview=f"Overview {i}",
            l2_json={}, perspective=p, quality_tier="BRONZE", relevance_score=0.5,
        )
    sci = await get_by_perspective("v_persp", "Scientific")
    assert len(sci) == 2
    reg = await get_by_perspective("v_persp", "Regulatory")
    assert len(reg) == 1


@pytest.mark.asyncio
async def test_get_high_quality():
    for i, (rel, tier) in enumerate([(0.9, "GOLD"), (0.3, "BRONZE"), (0.7, "SILVER")]):
        await store_evidence(
            evidence_id=f"ev_hq_{i}", vector_id="v_hq", cluster_id="c1",
            l0_summary="s", l1_overview="o", l2_json={},
            perspective="Scientific", quality_tier=tier, relevance_score=rel,
        )
    high = await get_high_quality("v_hq", min_relevance=0.5)
    assert len(high) == 2  # 0.9 and 0.7, not 0.3


@pytest.mark.asyncio
async def test_count_by_tier():
    for i, tier in enumerate(["GOLD", "GOLD", "SILVER", "BRONZE", "BRONZE", "BRONZE"]):
        await store_evidence(
            evidence_id=f"ev_tier_{i}", vector_id="v_tier", cluster_id="c1",
            l0_summary="s", l1_overview="o", l2_json={},
            perspective="Scientific", quality_tier=tier, relevance_score=0.5,
        )
    counts = await count_by_tier("v_tier")
    assert counts.get("GOLD", 0) == 2
    assert counts.get("SILVER", 0) == 1
    assert counts.get("BRONZE", 0) == 3
