"""I-deepfix-001 (#1344) journal_genre_stamp — offline RED->GREEN tests.

The W5 (llm_tiering) deferred path in ``run_live_retrieval`` calls ``_classify_source_tier_rules``
DIRECTLY, bypassing the ``classify_source_tier`` dispatcher — so it skipped the dispatcher's
per-citation document-GENRE stamp (``_m2_dt``). The fix imports ``_m2_dt`` and calls it right after
the rules classify on the W5 path, IDENTICALLY to the OFF-path dispatcher, so a real journal article
(JEP/QJE/Science/Nature) is no longer mislabeled non-journal downstream.

``_m2_dt`` is PURE (no network/LLM), gated by ``PG_DOCUMENT_TYPE_WEIGHT`` (byte-identical no-op when
OFF), fail-open, and touches NO faithfulness surface (strict_verify / NLI / 4-role / provenance are
FROZEN). Offline: no GPU, no network, no paid LLM.
"""
from __future__ import annotations

import inspect

import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    _classify_source_tier_rules,
    _m2_dt,
)


def _journal_signals() -> ClassificationSignals:
    return ClassificationSignals(
        url="https://example.org/paper.pdf",
        title="A Randomized Study of X",
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
        openalex_venue="Journal of Economic Perspectives",
        doi="10.1234/abcd",
    )


def test_w5_path_wires_m2_dt_after_rules_classify():
    """WIRING GUARD: run_live_retrieval's W5 deferred path calls ``_m2_dt(tier_result, signals)``
    AFTER ``_classify_source_tier_rules(signals)`` and BEFORE the deferred-signals append
    (RED pre-fix: the call was absent so the W5 winner path never stamped the genre)."""
    src = inspect.getsource(lr.run_live_retrieval)
    assert "_m2_dt(tier_result, signals)" in src
    rules_idx = src.index("tier_result = _classify_source_tier_rules(signals)")
    stamp_idx = src.index("_m2_dt(tier_result, signals)")
    append_idx = src.index("_deferred_tier_signals.append(signals)")
    assert rules_idx < stamp_idx < append_idx


def test_rules_path_alone_misses_journal_genre_which_m2dt_stamps(monkeypatch):
    """The rules-classify alone leaves document_type/is_journal_article None (the W5 bug); the
    wired ``_m2_dt`` stamps the JOURNAL_ARTICLE genre when PG_DOCUMENT_TYPE_WEIGHT is ON."""
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    sig = _journal_signals()
    result = _classify_source_tier_rules(sig)
    assert result.document_type is None          # rules path alone never stamps genre
    assert result.is_journal_article is None
    _m2_dt(result, sig)                          # the wired call the W5 path now makes
    assert result.document_type == "JOURNAL_ARTICLE"
    assert result.is_journal_article is True


def test_stamp_is_gated_off_byte_identical(monkeypatch):
    """PG_DOCUMENT_TYPE_WEIGHT OFF => the genre stays None (byte-identical no-op / LAW VI gate)."""
    monkeypatch.delenv("PG_DOCUMENT_TYPE_WEIGHT", raising=False)
    sig = _journal_signals()
    result = _classify_source_tier_rules(sig)
    _m2_dt(result, sig)
    assert result.document_type is None
    assert result.is_journal_article is None
