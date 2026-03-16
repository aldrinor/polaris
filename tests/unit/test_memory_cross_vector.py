"""Unit tests for cross_vector LTM memory module."""

import pytest
from unittest.mock import MagicMock, patch

from src.polaris_graph.memory.cross_vector import (
    promote_to_ltm,
    query_ltm,
    get_ltm_stats,
)


def test_promote_empty_list():
    result = promote_to_ltm([], "v_test")
    assert result == 0


@patch("src.polaris_graph.memory.cross_vector._get_chroma_manager")
def test_promote_no_chromadb(mock_manager):
    mock_manager.return_value = None
    result = promote_to_ltm(
        [{"evidence_id": "ev1", "statement": "test", "quality_tier": "GOLD", "faithfulness": 1.0}],
        "v_test",
    )
    assert result == 0


@patch("src.polaris_graph.memory.cross_vector._get_chroma_manager")
def test_query_ltm_no_chromadb(mock_manager):
    mock_manager.return_value = None
    result = query_ltm("water filter effectiveness")
    assert result == []


@patch("src.polaris_graph.memory.cross_vector._get_chroma_manager")
def test_get_ltm_stats_no_chromadb(mock_manager):
    mock_manager.return_value = None
    stats = get_ltm_stats()
    assert stats["available"] is False
    assert stats["total_items"] == 0
