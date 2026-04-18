"""
Tests for Phase 2d pre-fetch off-topic filter.

Avoids heavy embedding model loads by mocking the embedder. The goal
is to validate the filter's logic (threshold application, fail-open,
empty-snippet handling, rejection reasons), not the embedder itself.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    FilterResult,
    SearchCandidate,
    filter_search_results,
)


class _StubEmbedder:
    """Returns predetermined embeddings keyed by text.

    The caller sets `vectors` as a dict[str, list[float]]. Unknown
    texts get a zero vector.
    """

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def encode(self, texts, normalize_embeddings: bool = True):
        if isinstance(texts, str):
            return self.vectors.get(texts, [0.0, 0.0, 0.0])
        return [self.vectors.get(t, [0.0, 0.0, 0.0]) for t in texts]


def _mk_candidate(title: str, snippet: str = "", url: str = "http://x/") -> SearchCandidate:
    return SearchCandidate(url=url, title=title, snippet=snippet, source="test")


def test_empty_candidates_returns_empty_result() -> None:
    result = filter_search_results([], "semaglutide efficacy", threshold=0.3)
    assert result.total_in == 0
    assert result.total_kept == 0
    assert result.total_rejected == 0
    assert result.kept == []


def test_empty_query_fails_open(caplog: pytest.LogCaptureFixture) -> None:
    cands = [_mk_candidate("A"), _mk_candidate("B")]
    with caplog.at_level("WARNING"):
        result = filter_search_results(cands, "", threshold=0.5)
    assert result.total_kept == 2
    assert result.total_rejected == 0


def test_threshold_keeps_similar_rejects_dissimilar() -> None:
    # Query is aligned with [1, 0, 0]
    query = "semaglutide efficacy trial"
    cand_on = _mk_candidate("RCT of semaglutide for weight loss")
    cand_off = _mk_candidate("Japan health insurance system overview")
    stub_vectors = {
        query: [1.0, 0.0, 0.0],
        cand_on.snippet_text: [0.9, 0.1, 0.0],
        cand_off.snippet_text: [0.0, 1.0, 0.0],
    }
    with patch(
        "src.polaris_graph.retrieval.prefetch_offtopic_filter._load_embedder",
        return_value=_StubEmbedder(stub_vectors),
    ):
        result = filter_search_results(
            [cand_on, cand_off], query, threshold=0.5,
        )
    assert result.total_kept == 1
    assert result.total_rejected == 1
    assert result.kept[0] is cand_on
    assert result.rejected[0][0] is cand_off
    assert result.rejected[0][1] < 0.5  # similarity
    assert result.rejected[0][2] == "below_prefetch_threshold"


def test_empty_snippet_kept_for_fetch() -> None:
    query = "semaglutide efficacy"
    cand_unknown = _mk_candidate("")  # empty title + empty snippet
    stub = _StubEmbedder({query: [1.0, 0.0, 0.0]})
    with patch(
        "src.polaris_graph.retrieval.prefetch_offtopic_filter._load_embedder",
        return_value=stub,
    ):
        result = filter_search_results(
            [cand_unknown], query, threshold=0.5,
        )
    # No snippet => uncertain => keep
    assert result.total_kept == 1
    assert result.total_rejected == 0


def test_embedder_unavailable_fails_open() -> None:
    cands = [_mk_candidate("A"), _mk_candidate("B")]
    with patch(
        "src.polaris_graph.retrieval.prefetch_offtopic_filter._load_embedder",
        return_value=None,
    ):
        result = filter_search_results(cands, "question", threshold=0.3)
    assert result.total_kept == 2
    assert result.total_rejected == 0
