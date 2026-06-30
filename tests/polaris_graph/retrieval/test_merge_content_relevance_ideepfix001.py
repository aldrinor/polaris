"""I-deepfix-001 (#1344): the multi-query merge (fs_researcher + iterresearch) MUST carry
the W5 content-relevance telemetry through to the merged LiveRetrievalResult, so the
winner-firing gate does NOT false-abort "the judge never ran" when the reranker actually
fired every round. Behavioral replay harness for the winner-gate false-negative blocker.

Pure-Python: no GPU, no network, no live retrieval — exercises the merge fn + the gate.
"""
from types import SimpleNamespace

from src.polaris_graph.retrieval.fs_researcher_query_gen import (
    merge_retrieval_results as fs_merge,
)
from src.polaris_graph.retrieval.iterresearch_query_gen import (
    merge_retrieval_results as iter_merge,
)
from src.polaris_graph.retrieval.winner_firing_gate import evaluate_winner_firing


def _factory(**kw):
    """Stand-in for LiveRetrievalResult — captures exactly what the merge passes."""
    return SimpleNamespace(**kw)


def _round(cr, url):
    """A per-query LiveRetrievalResult stub carrying a content_relevance dict (or None)."""
    return SimpleNamespace(
        evidence_rows=[{"source_url": url, "evidence_id": "ev_000"}],
        classified_sources=[],
        api_calls={},
        notes=[],
        journal_metadata_sidecar=None,
        corpus_truncated=False,
        retrieval_wall_hit=False,
        semantic_relevance_fell_back=False,
        retrieval_queries_skipped=0,
        retrieval_candidates_unclassified=0,
        total_candidates_pre_filter=1,
        candidates_kept_by_scope=1,
        candidates_kept_by_offtopic=1,
        candidates_fetched=1,
        candidates_failed_fetch=0,
        candidates_total=1,
        candidates_processed=1,
        content_relevance=cr,
    )


def _gate_dark(merged):
    """True iff the winner-firing gate marks W5 structurally dark for this merged result."""
    verdict = evaluate_winner_firing(
        content_relevance=getattr(merged, "content_relevance", None),
        embedder_cache_sentinel=None,
        w6_requested=False,   # isolate W5 — do not let W6/W7 trip the verdict
        w5_requested=True,    # W5 force-ON (the real-run condition)
        w7_requested=False,
    )
    return "W5_content_relevance" in verdict.dark_winners


def test_fs_merge_carries_fired_report_and_gate_passes():
    # Two rounds fired: cuda:1 (n_scored=219) and "" device (n_scored=464, the full-corpus pass).
    # The empty device is NOT a load failure (gate treats only "unavailable" as dark).
    rounds = [
        _round({"reranker_device": "cuda:1", "n_scored": 219, "n_demoted": 164}, "http://a"),
        _round({"reranker_device": "", "n_scored": 464, "n_demoted": 443}, "http://b"),
    ]
    merged = fs_merge(rounds, _factory)
    assert merged.content_relevance is not None, "merge dropped content_relevance (the bug)"
    # the most comprehensive fired round (largest n_scored) is carried
    assert int(merged.content_relevance["n_scored"]) == 464
    assert not _gate_dark(merged), "W5 fired but the gate still aborts (false-negative)"


def test_iter_merge_carries_fired_report_and_gate_passes():
    rounds = [_round({"reranker_device": "cuda:0", "n_scored": 30, "n_demoted": 13}, "http://c")]
    merged = iter_merge(rounds, _factory)
    assert merged.content_relevance is not None
    assert not _gate_dark(merged)


def test_merge_keeps_dark_when_every_round_reranker_failed():
    # A GENUINE load failure (reranker_device == 'unavailable') must STILL mark W5 dark —
    # the fix must not mask a real winner-dark condition.
    rounds = [
        _round({"reranker_device": "unavailable", "n_scored": 0}, "http://d"),
        _round({"reranker_device": "unavailable", "n_scored": 0}, "http://e"),
    ]
    merged = fs_merge(rounds, _factory)
    assert merged.content_relevance is not None
    assert merged.content_relevance["reranker_device"] == "unavailable"
    assert _gate_dark(merged), "a genuine reranker load-failure must remain dark"


def test_merge_prefers_loaded_round_over_unavailable():
    # Mixed: one round failed to load, one fired. The merged telemetry must reflect the
    # round that FIRED (so the gate honestly passes — the reranker did run).
    rounds = [
        _round({"reranker_device": "unavailable", "n_scored": 0}, "http://f"),
        _round({"reranker_device": "cuda:1", "n_scored": 200, "n_demoted": 50}, "http://g"),
    ]
    merged = fs_merge(rounds, _factory)
    assert merged.content_relevance["reranker_device"] == "cuda:1"
    assert int(merged.content_relevance["n_scored"]) == 200
    assert not _gate_dark(merged)


def test_merge_none_when_no_round_produced_a_report():
    # W5 truly never ran any round -> None -> gate still dark (honest, not masked).
    rounds = [_round(None, "http://h")]
    merged = fs_merge(rounds, _factory)
    assert merged.content_relevance is None
    assert _gate_dark(merged)
