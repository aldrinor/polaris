"""Fetch-time relevance rerank + per-sub-query reservation (I-meta-002-q1d #951/#943).

Unit tests for `live_retriever._rerank_and_reserve` and `_lexical_relevance_score`. NO network,
NO model load — the rerank is pure-lexical by design (§8.4). Each test asserts a Codex
brief-gate iter-1 required behavior: seed protection, no model loader, no origin monopolization,
fail-open, and that the cap is respected on non-seeds.
"""

from __future__ import annotations

import builtins

import pytest

from src.polaris_graph.retrieval.live_retriever import (
    _lexical_relevance_score,
    _rerank_and_reserve,
)
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate

_QUESTION = "What is the effect of tirzepatide on HbA1c and body weight in type 2 diabetes?"


def _cand(url: str, *, title: str = "", snippet: str = "", source: str = "serper", origin: str = "") -> SearchCandidate:
    return SearchCandidate(url=url, title=title, snippet=snippet, source=source, query_origin=origin)


def _seed(url: str) -> SearchCandidate:
    # Primary-trial DOI seed exactly as live_retriever injects it: empty title/snippet.
    return SearchCandidate(url=url, title="", snippet="", source="primary_trial_doi", query_origin="primary_trial_doi_seed")


# --- P0: seed retained despite empty title/snippet + many higher-scoring non-seeds ----------
def test_seed_retained_despite_empty_text_and_high_scoring_nonseeds():
    seeds = [_seed("https://doi.org/10.1056/seed1"), _seed("https://doi.org/10.1056/seed2")]
    # Many highly-relevant non-seeds that would out-score the empty-text seeds on any metric.
    non_seeds = [
        _cand(f"https://x/{i}", title="tirzepatide HbA1c body weight type 2 diabetes", snippet="effect", origin="q1")
        for i in range(10)
    ]
    out = _rerank_and_reserve(seeds + non_seeds, research_question=_QUESTION, fetch_cap=3, n_seed_injected=2)
    out_urls = {c.url for c in out}
    # Both seeds survive (never ranked / never dropped), and they come FIRST.
    assert out[0].source == "primary_trial_doi" and out[1].source == "primary_trial_doi"
    assert "https://doi.org/10.1056/seed1" in out_urls
    assert "https://doi.org/10.1056/seed2" in out_urls
    # Non-seed selection is capped at fetch_cap (3); total = 2 seeds + 3 non-seeds.
    assert sum(1 for c in out if c.source != "primary_trial_doi") == 3
    assert len(out) == 5


# --- no model loader: rerank works even if sentence_transformers import is BLOCKED -----------
def test_no_embedder_model_loaded(monkeypatch):
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if "sentence_transformers" in name or name == "torch":
            raise AssertionError(f"rerank must not import a model: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)
    non_seeds = [
        _cand("https://a", title="tirzepatide HbA1c diabetes", origin="q1"),
        _cand("https://b", title="unrelated cooking recipe", origin="q2"),
    ]
    out = _rerank_and_reserve(non_seeds, research_question=_QUESTION, fetch_cap=2, n_seed_injected=0)
    assert len(out) == 2  # ran to completion with no model import


# --- relevance: a high-overlap candidate is preferred over a low-overlap one within the cap --
def test_relevance_prefers_on_topic_within_cap():
    on_topic = _cand("https://on", title="tirzepatide reduces HbA1c and body weight in diabetes", origin="q1")
    off_topic = _cand("https://off", title="local sports team wins championship", origin="q1")
    # Same origin so reservation gives only one slot; the on-topic one must win it.
    out = _rerank_and_reserve([off_topic, on_topic], research_question=_QUESTION, fetch_cap=1, n_seed_injected=0)
    assert [c.url for c in out] == ["https://on"]


# --- reservation: no single origin monopolizes the cap; each origin gets >=1 slot -----------
def test_reservation_no_origin_monopoly():
    # Origin q_long has 5 strong candidates; origins q2/q3 have 1 weaker each. With cap=3 each
    # origin must get at least one slot (q_long cannot take all 3).
    long_q = [_cand(f"https://long{i}", title="tirzepatide HbA1c body weight diabetes effect", origin="q_long") for i in range(5)]
    q2 = [_cand("https://q2", title="tirzepatide diabetes", origin="q2")]
    q3 = [_cand("https://q3", title="HbA1c diabetes", origin="q3")]
    out = _rerank_and_reserve(long_q + q2 + q3, research_question=_QUESTION, fetch_cap=3, n_seed_injected=0)
    origins = {c.query_origin for c in out}
    assert origins == {"q_long", "q2", "q3"}  # all three represented; no monopoly
    assert len(out) == 3


# --- fail-open: a scorer error falls back to arrival order, seeds preserved ------------------
def test_fail_open_falls_back_to_arrival_order(monkeypatch):
    import src.polaris_graph.retrieval.live_retriever as lr

    def _boom(*a, **k):
        raise RuntimeError("scorer blew up")

    monkeypatch.setattr(lr, "_lexical_relevance_score", _boom)
    seeds = [_seed("https://seed")]
    non_seeds = [_cand(f"https://n{i}", title="x", origin="q1") for i in range(5)]
    out = _rerank_and_reserve(seeds + non_seeds, research_question=_QUESTION, fetch_cap=2, n_seed_injected=1)
    # Fallback = candidates[:fetch_cap + n_seed_injected] = first 3 in arrival order (seed first).
    assert [c.url for c in out] == ["https://seed", "https://n0", "https://n1"]


# --- cap respected on non-seeds; empty / zero-cap edge cases do not raise --------------------
def test_cap_respected_and_edge_cases():
    non_seeds = [_cand(f"https://n{i}", title="tirzepatide diabetes", origin=f"q{i}") for i in range(8)]
    out = _rerank_and_reserve(non_seeds, research_question=_QUESTION, fetch_cap=4, n_seed_injected=0)
    assert len(out) == 4
    # zero cap → only seeds survive (here none) and no error.
    assert _rerank_and_reserve(non_seeds, research_question=_QUESTION, fetch_cap=0, n_seed_injected=0) == []
    # empty candidate list → empty result.
    assert _rerank_and_reserve([], research_question=_QUESTION, fetch_cap=5, n_seed_injected=0) == []


# --- lexical scorer: empty question or empty candidate text → 0.0 (no crash) -----------------
def test_lexical_relevance_score_edges():
    assert _lexical_relevance_score(_cand("https://x", title="anything"), set()) == 0.0
    assert _lexical_relevance_score(_cand("https://x", title=""), {"tirzepatide"}) == 0.0
    score = _lexical_relevance_score(_cand("https://x", title="tirzepatide hba1c"), {"tirzepatide", "hba1c", "diabetes"})
    assert 0.0 < score <= 1.0
