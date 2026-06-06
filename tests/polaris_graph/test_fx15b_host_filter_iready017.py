"""FX-15b (I-ready-017 #1119): host-class junk filter + seed-safe semantic prefetch.

(1) `_is_low_content_host_or_page` — a precision-first structural reject of nav/SERP/conference
    pages, applied to agentic-discovered seed URLs before fetch. MUST never drop a real article.
(2) Step-3 prefetch off-topic filter now EXCLUDES injected seeds (empty-snippet, source in
    _SEED_SOURCE_LABELS) so enabling `enable_prefetch_filter=True` on the agentic seed lane can no
    longer drop every URL-only seed as ~0-similarity off-topic.

Quality/precision fix — no grounding/strict_verify/4-role change. Offline, no network.
"""
from __future__ import annotations

import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.live_retriever import _is_low_content_host_or_page
from src.polaris_graph.retrieval.prefetch_offtopic_filter import FilterResult

# Pure NAV / SERP / TOC / discussion listing pages (held drb_72 trace shapes + synthetic) — REJECT.
_REJECT = [
    "https://www.aeaweb.org/journals/search-results?from=a&page=156&per-page=21",
    "https://www.aeaweb.org/journals/search-results?from=a&page=216&per-page=21",
    "https://www.aeaweb.org/search/index?jelcode=b1&type=&page=504",
    "https://www.aeaweb.org/forum/232/ba-wanting-to-gain-exposure",
    "https://www.aeaweb.org/issues/381",
    "https://www.google.com/search?q=labor+economics",
    "https://example.org/browse/all",
    "https://www.journals.uchicago.edu/toc/jpe/2020/128/6",
    "https://www.journals.uchicago.edu/toc/jpe/current",
]
# Real articles AND pages that CAN bear evidence (conference papers, supplement abstracts,
# annual-meeting papers, working-paper PDFs) — KEEP (post-fetch tier classifier decides). Codex
# iter-1 P1: the structural filter MUST NOT pre-fetch-drop these.
_KEEP = [
    "https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3",
    "https://www.aeaweb.org/articles?id=10.1257/aer.104.8.2509",
    "https://pubs.aeaweb.org/doi/10.1257/aer.104.8.2509",
    "https://arxiv.org/abs/2401.00001",
    "https://www.nber.org/papers/w12345",
    "https://doi.org/10.1056/NEJMoa1107039",
    # Held drb_72 conference program-paper URLs that fetched REAL papers (evidence_pool.json):
    "https://www.aeaweb.org/conference/2025/program/paper/S7SHZQ4n",  # 50k chars
    "https://www.aeaweb.org/conference/2025/program/paper/S25ktKkD",  # 30k chars
    # Same shape, junk in this run — but URL cannot distinguish, so KEEP (post-fetch drops it):
    "https://www.aeaweb.org/conference/2023/program/paper/8A8RRTQY",
    # Conference supplement abstract — bears abstract-level evidence; tier classifier down-tiers it:
    "https://academic.oup.com/ooec/article/3/Supplement_1/i906/7708121",
    "https://soc.org/annual-meeting/2024/program/paper/abc",
]


# Codex iter-1 P1 regression: the EXACT held URLs that fetched real evidence must NEVER be dropped.
_HELD_FALSE_DROP_REGRESSION = [
    "https://www.aeaweb.org/conference/2025/program/paper/S7SHZQ4n",
    "https://www.aeaweb.org/conference/2025/program/paper/S25ktKkD",
]


def test_held_conference_papers_not_dropped_regression():
    """Codex iter-1 P1: these held agentic URLs each fetched a real paper (50k / 30k chars in
    evidence_pool.json). A blanket /conference reject false-dropped them — must stay KEPT."""
    for u in _HELD_FALSE_DROP_REGRESSION:
        assert _is_low_content_host_or_page(u, "") is False, f"P1 regression — must KEEP real paper: {u}"


def test_low_content_filter_rejects_nav_serp_conference():
    for u in _REJECT:
        assert _is_low_content_host_or_page(u, "") is True, f"should REJECT low-content: {u}"


def test_low_content_filter_keeps_real_articles_precision():
    """PRECISION GATE: not a single real article/abstract URL may be dropped."""
    for u in _KEEP:
        assert _is_low_content_host_or_page(u, "") is False, f"must KEEP real source: {u}"


def test_low_content_filter_empty_url_is_kept():
    assert _is_low_content_host_or_page("", "") is False


def _stub_fetch(url, max_chars, **kwargs):
    return (
        "Apixaban reduced stroke versus warfarin in atrial fibrillation patients. " * 8,
        True, "Stub Title", "html", "",
    )


def _reject_all_filter(candidates, research_question, threshold=None):
    """Simulate an embedder that rejects EVERY candidate (worst case for seeds)."""
    return FilterResult(
        kept=[], rejected=list(candidates), threshold_used=0.99,
        total_in=len(candidates), total_kept=0, total_rejected=len(candidates),
    )


def test_step3_excludes_seeds_from_offtopic_filter(monkeypatch):
    """The latent bug FX-15b fixes: with enable_prefetch_filter=True and a reject-all embedder, an
    empty-snippet injected seed must STILL survive (it is excluded from the off-topic filter).
    Pre-fix, the seed would be dropped as ~0-similarity off-topic and produce no evidence row."""
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
    monkeypatch.setattr(lr, "filter_search_results", _reject_all_filter)
    res = lr.run_live_retrieval(
        research_question="anticoagulation in atrial fibrillation",
        seed_urls=["https://www.aeaweb.org/articles?id=10.1257/y"],
        seed_only=True,
        seed_source="agentic_seed",
        seed_query_origin="agentic_seed",
        enable_prefetch_filter=True,   # ON — but seeds are excluded from the filter
        enable_openalex_enrich=False,
        fetch_cap=5,
    )
    rows = [r for r in res.evidence_rows if r["source_url"] == "https://www.aeaweb.org/articles?id=10.1257/y"]
    assert rows, "the agentic seed must survive the off-topic filter (seed-exclusion), not be dropped"
    assert rows[0]["source"] == "agentic_seed"
