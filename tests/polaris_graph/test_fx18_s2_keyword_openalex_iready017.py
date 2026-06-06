"""FX-18 (I-ready-017 #1122): S2 short-keyword lane + wire OpenAlex into the sweep search lane.

S2 bulk is a keyword index — the 40-70-word NL golden queries returned ~0. FX-18 (1) distills `q`
to a short content-keyword phrase for S2 (`distill_keywords`), and (2) wires
`domain_backends.openalex_search` (NL-friendly, fail-open) as a parallel academic backend,
union+deduped via the shared `seen_urls`. Discovery-breadth only — every new source passes the SAME
fetch/tier/strict_verify/4-role gates. Offline, no network.
"""
from __future__ import annotations

import src.polaris_graph.retrieval.domain_backends as _db
import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate
from src.polaris_graph.retrieval.query_decomposer import distill_keywords

_NL = (
    "To what extent will artificial intelligence and automation technologies displace or transform "
    "jobs across the labor market over the next decade, and what does the empirical economics "
    "literature conclude about net employment effects?"
)


def test_distill_keywords_short_stopword_filtered_capped():
    kw = distill_keywords(_NL, max_terms=8)
    toks = kw.split()
    assert 0 < len(toks) <= 8                       # non-empty + capped
    assert len(toks) < len(_NL.split())             # strictly shorter than the NL query
    assert "the" not in toks and "and" not in toks  # stopwords dropped
    assert len(toks) == len(set(toks))              # de-duplicated
    # content terms preserved
    assert "artificial" in toks and "intelligence" in toks


def test_distill_keywords_empty_when_no_content_tokens():
    # all-stopword question -> '' so the caller falls back to the full NL query (never empty search).
    assert distill_keywords("what is the of and to", max_terms=8) == ""


def _stub_fetch(url, max_chars, **kwargs):
    return ("Automation displaced manufacturing jobs in the labor market. " * 8, True, "T", "html", "")


def test_s2_gets_distilled_query_and_openalex_merged_deduped(monkeypatch):
    captured_s2: dict = {}
    monkeypatch.setattr(lr, "_serper_search", lambda q, num=10, api_calls=None: [
        {"url": "https://dup.org/a", "title": "Serper A", "snippet": "labor"}
    ])

    def _fake_s2(query, limit=20):
        captured_s2["q"] = query
        return []
    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)

    def _fake_openalex(query, limit=20):
        return [
            SearchCandidate(url="https://dup.org/a", title="OA dup", snippet="", source="openalex_search"),
            SearchCandidate(url="https://oa.org/b", title="OA new", snippet="", source="openalex_search"),
        ]
    monkeypatch.setattr(_db, "openalex_search", _fake_openalex)
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)

    res = lr.run_live_retrieval(
        research_question=_NL,
        protocol=None,            # no scope validation -> effective_queries = [the NL question]
        anchor_seed=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        fetch_cap=10,
    )

    # (1) S2 received the DISTILLED keyword phrase, not the 33-word NL query.
    assert captured_s2["q"] == distill_keywords(_NL, max_terms=8)
    assert len(captured_s2["q"].split()) <= 8

    rows = {r["source_url"]: r for r in res.evidence_rows}
    # (2) OpenAlex's NEW url merged.
    assert "https://oa.org/b" in rows
    assert rows["https://oa.org/b"]["source"] == "openalex_search"
    # (3) The url OpenAlex shared with serper is deduped — present exactly once, kept as the serper row.
    dup_rows = [r for r in res.evidence_rows if r["source_url"] == "https://dup.org/a"]
    assert len(dup_rows) == 1
    assert dup_rows[0]["source"] == "serper"
