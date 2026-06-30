"""
Tests for the pre-fetch off-topic ORDERING (DEMOTE-NOT-DROP, §-1.3).

I-deepfix-001 D3 (2026-06-29): the pre-fetch off-topic stage was converted from a
hard FILTER (below-threshold candidates moved to `rejected`, never fetched) to a
DEMOTE-NOT-DROP ordering (every candidate KEPT; cosine is a WEIGHT/ordering signal;
below-threshold candidates demoted to the tail and DISCLOSED via `demoted`). These
tests bank the new behaviour: `total_rejected == 0` by default, `total_demoted`
carries the below-threshold count, and `kept` is cosine-ordered (most-relevant
first). The ONLY sanctioned hard DROP in the pipeline is the downstream faithfulness
engine — never this pre-fetch stage.

Avoids heavy embedding model loads by stubbing the embedder. The goal is to
validate the filter's ORDERING logic (demote-not-drop, cosine ordering, fail-open,
empty-snippet handling), not the embedder itself.
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
    assert result.total_demoted == 0
    assert result.kept == []


def test_empty_query_fails_open(caplog: pytest.LogCaptureFixture) -> None:
    cands = [_mk_candidate("A"), _mk_candidate("B")]
    with caplog.at_level("WARNING"):
        result = filter_search_results(cands, "", threshold=0.5)
    assert result.total_kept == 2
    assert result.total_rejected == 0


def test_demote_not_drop_keeps_all_orders_by_cosine() -> None:
    """§-1.3 DEMOTE-NOT-DROP: a below-threshold candidate is KEPT (demoted to the
    tail), never hard-dropped. `kept` is cosine-DESC ordered, `total_rejected == 0`,
    and the below-threshold candidate is counted in `total_demoted` + `demoted`."""
    # Query aligned with [1, 0, 0].
    query = "semaglutide efficacy trial"
    cand_on = _mk_candidate("RCT of semaglutide for weight loss", url="http://on/")
    cand_mid = _mk_candidate("Mixed metabolic outcomes review", url="http://mid/")
    cand_off = _mk_candidate("Japan health insurance system overview", url="http://off/")
    stub_vectors = {
        query: [1.0, 0.0, 0.0],
        cand_on.snippet_text: [0.9, 0.1, 0.0],   # cosine ~0.994 (above 0.5)
        cand_mid.snippet_text: [0.6, 0.8, 0.0],  # cosine  0.600 (above 0.5)
        cand_off.snippet_text: [0.0, 1.0, 0.0],  # cosine  0.000 (BELOW 0.5 -> demoted)
    }
    with patch(
        "src.polaris_graph.retrieval.prefetch_offtopic_filter._load_embedder",
        return_value=_StubEmbedder(stub_vectors),
    ):
        result = filter_search_results(
            [cand_off, cand_mid, cand_on], query, threshold=0.5,
        )
    # DEMOTE-NOT-DROP: nothing is hard-dropped; all three survive to fetch.
    assert result.total_kept == 3
    assert result.total_rejected == 0
    assert result.rejected == []
    # The below-threshold candidate is DEMOTED, not dropped — and DISCLOSED.
    assert result.total_demoted == 1
    assert [c.url for c, _sim in result.demoted] == ["http://off/"]
    assert result.demoted[0][1] < 0.5  # the demoted candidate's sim
    # `kept` is cosine-DESCENDING ordered: most-relevant first, demoted tail last.
    assert [c.url for c in result.kept] == ["http://on/", "http://mid/", "http://off/"]


def test_healthy_embedder_demotes_does_not_drop() -> None:
    """FAIL-LOUD breadth guard: a HEALTHY embedder scoring a candidate below the
    threshold must DEMOTE it (keep at the tail, count in `demoted`), NEVER drop it.
    A regression that re-introduces the §-1.3-banned pre-fetch hard FILTER would
    push the below-threshold candidate into `rejected` and shrink `kept` — this
    assertion catches that."""
    query = "semaglutide cardiovascular outcomes"
    cand_off = _mk_candidate("Unrelated tourism article", url="http://off/")
    stub_vectors = {
        query: [1.0, 0.0, 0.0],
        cand_off.snippet_text: [0.0, 1.0, 0.0],  # cosine 0.0 — far below any floor
    }
    with patch(
        "src.polaris_graph.retrieval.prefetch_offtopic_filter._load_embedder",
        return_value=_StubEmbedder(stub_vectors),
    ):
        result = filter_search_results([cand_off], query, threshold=0.35)
    assert result.total_rejected == 0, "pre-fetch hard FILTER regressed (§-1.3 violation)"
    assert result.total_kept == 1, "the below-threshold source must SURVIVE (demoted)"
    assert result.total_demoted == 1
    assert result.kept[0] is cand_off  # kept, just demoted to the tail (here the only slot)


def test_empty_snippet_kept_for_fetch_not_demoted() -> None:
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
    # No snippet => uncertain => keep (fetch to know). It carries no relevance
    # signal, so it is NOT counted as demoted — but it still SURVIVES.
    assert result.total_kept == 1
    assert result.total_rejected == 0
    assert result.total_demoted == 0


def test_embedder_unavailable_fails_open() -> None:
    cands = [_mk_candidate("A"), _mk_candidate("B")]
    with patch(
        "src.polaris_graph.retrieval.prefetch_offtopic_filter._load_embedder",
        return_value=None,
    ):
        result = filter_search_results(cands, "question", threshold=0.3)
    assert result.total_kept == 2
    assert result.total_rejected == 0
    assert result.total_demoted == 0
