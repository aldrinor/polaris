"""I-cap-002 feature 3/4 (#1060): tests for the agentic URL harvester + the pure seed-URL merge core.

Faithfulness-critical: ``harvest_agentic_urls`` must read ONLY discovered URLs and NEVER the
``agentic_research_notebook`` summaries. ``merge_seed_url_evidence`` must reject duplicate-URL sources
and renumber evidence ids without inflation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.polaris_graph.retrieval.agentic_url_harvester import (
    harvest_agentic_urls,
    merge_seed_url_evidence,
)


# --------------------------------------------------------------------------- #
# harvest_agentic_urls
# --------------------------------------------------------------------------- #

def test_harvests_ordered_union_of_web_then_academic():
    result = {
        "web_results": [{"url": "https://a.com/1"}, {"url": "https://b.com/2"}],
        "academic_results": [{"url": "https://c.org/3"}],
        "agentic_url_accumulator": ["https://d.net/4"],
    }
    out = harvest_agentic_urls(result)
    assert out == [
        "https://a.com/1",
        "https://b.com/2",
        "https://c.org/3",
        "https://d.net/4",
    ]


def test_dedup_by_canonical_keeps_original_fetchable_url():
    # http vs https of the same canonical resource -> one entry, the FIRST (original) URL is kept.
    result = {
        "web_results": [
            {"url": "https://example.com/paper"},
            {"url": "http://example.com/paper"},        # same canonical -> dropped
        ],
    }
    out = harvest_agentic_urls(result)
    assert out == ["https://example.com/paper"]
    # the returned URL is the original (scheme intact), NOT the scheme-stripped canonical
    assert out[0].startswith("https://")


def test_notebook_and_summaries_are_never_read():
    # A malicious/である result with a rich notebook + snippets must contribute NOTHING but the urls.
    result = {
        "web_results": [{"url": "https://real.com/x", "snippet": "model paraphrase"}],
        "agentic_research_notebook": [
            {"summary": "LLM-written paraphrase that must never be evidence", "url": "https://fake/note"},
        ],
    }
    out = harvest_agentic_urls(result)
    assert out == ["https://real.com/x"]            # notebook url NOT harvested, snippet ignored


def test_cap_and_empty_and_malformed_are_safe():
    assert harvest_agentic_urls(None) == []
    assert harvest_agentic_urls({}) == []
    assert harvest_agentic_urls({"web_results": []}) == []
    assert harvest_agentic_urls({"web_results": [{"url": "https://a/1"}]}, cap=0) == []
    # malformed records / missing url keys are skipped, not raised
    safe = harvest_agentic_urls({"web_results": ["not a dict", {"no_url": 1}, {"url": ""}, {"url": "https://ok/1"}]})
    assert safe == ["https://ok/1"]
    capped = harvest_agentic_urls(
        {"web_results": [{"url": f"https://h/{i}"} for i in range(50)]}, cap=10
    )
    assert len(capped) == 10
    assert capped[0] == "https://h/0"


# --------------------------------------------------------------------------- #
# merge_seed_url_evidence
# --------------------------------------------------------------------------- #

@dataclass
class _Src:
    url: str


def test_merge_dedup_sources_and_renumber_rows():
    staged_sources = [_Src("https://a/1")]
    staged_rows = [{"evidence_id": "ev_000", "source_url": "https://a/1"}]
    new_sources = [_Src("https://a/1"), _Src("https://b/2")]   # first is a duplicate
    new_rows = [
        {"source_url": "https://a/1", "direct_quote": "dup source row -> rejected"},
        {"source_url": "https://b/2", "direct_quote": "new source row -> accepted"},
    ]
    sources, rows, acc_src, acc_rows = merge_seed_url_evidence(
        staged_sources, staged_rows, new_sources, new_rows
    )
    assert acc_src == 1                              # only b/2 is a new source
    assert acc_rows == 1                             # only the b/2 row is appended
    assert [s.url for s in sources] == ["https://a/1", "https://b/2"]
    # the new row was renumbered from the staged base (len==1 -> ev_001), no collision with ev_000
    assert rows[-1]["evidence_id"] == "ev_001"
    assert rows[-1]["source_url"] == "https://b/2"
    assert len(rows) == 2                            # no inflation: the duplicate-source row was dropped


def test_merge_does_not_mutate_inputs():
    staged_sources = [_Src("https://a/1")]
    staged_rows = [{"evidence_id": "ev_000", "source_url": "https://a/1"}]
    new_rows = [{"source_url": "https://b/2", "direct_quote": "x"}]
    merge_seed_url_evidence(staged_sources, staged_rows, [_Src("https://b/2")], new_rows)
    assert len(staged_sources) == 1                  # caller's list untouched
    assert len(staged_rows) == 1
    assert "evidence_id" not in new_rows[0]          # caller's row dict not mutated
