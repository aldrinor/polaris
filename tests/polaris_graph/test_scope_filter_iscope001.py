"""
I-scope-001 (#1244) — scope filter unit tests.

Covers the three DEFAULT-OFF selection-side gates that stop the breadth-opened
pipeline from citing off-topic + low-credibility sources, WITHOUT touching the
faithfulness engine (strict_verify / NLI / 4-role / provenance):

1. Low-cred domain denylist (gate 1, pure, no LLM) in evidence_selector.
2. Semantic LLM topic-relevance gate (gate 2) in topic_relevance_gate — tested
   with a STUB llm_callable (no OpenRouter key required), including fail-open.
3. arXiv -> journal version preference (gate 3, pure) in evidence_selector.

Every test asserts the byte-identical no-op when the controlling env flag is
unset, per the default-OFF contract.
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    _apply_scope_denylist,
    _netloc_matches_denylist,
    _row_netloc,
    _scope_denylist_domains,
    prefer_journal_over_arxiv,
    select_evidence_for_generation,
)
from src.polaris_graph.retrieval.topic_relevance_gate import (
    classify_topic_relevance,
    topic_gate_enabled,
    topic_batch_size,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _scored(rows):
    """Wrap rows into the `scored` tuple shape the denylist gate consumes:
    (original_index, relevance_score, tier, row)."""
    return [(i, 0.5, "T2", r) for i, r in enumerate(rows)]


def _row(url, *, title="Some title", **extra):
    r = {"source_url": url, "title": title}
    r.update(extra)
    return r


@pytest.fixture(autouse=True)
def _clean_scope_env(monkeypatch):
    """Ensure no scope env leaks between tests."""
    for var in (
        "PG_SCOPE_DENYLIST_DOMAINS",
        "PG_SCOPE_TOPIC_GATE",
        "PG_SCOPE_TOPIC_BATCH",
        "PG_SCOPE_PREFER_JOURNAL",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


# ── gate 1: low-cred domain denylist ──────────────────────────────────────────

def test_denylist_empty_env_is_noop(monkeypatch):
    """Env unset => denylist () => `_apply_scope_denylist` returns input
    UNCHANGED (byte-identical no-op)."""
    rows = [_row("https://facebook.com/post/123"),
            _row("https://en.wikipedia.org/wiki/X"),
            _row("https://www.nature.com/articles/abc")]
    scored = _scored(rows)
    kept, dropped, netlocs = _apply_scope_denylist(scored, None)
    assert kept == scored
    assert dropped == 0
    assert netlocs == []


def test_denylist_drops_denylisted_domain(monkeypatch):
    monkeypatch.setenv(
        "PG_SCOPE_DENYLIST_DOMAINS",
        "facebook.com,scribd.com,en.wikipedia.org",
    )
    rows = [
        _row("https://www.facebook.com/some/post"),   # suffix match -> drop
        _row("https://en.wikipedia.org/wiki/Topic"),  # exact match -> drop
        _row("https://www.nature.com/articles/abc"),  # keep
    ]
    kept, dropped, netlocs = _apply_scope_denylist(_scored(rows), None)
    assert dropped == 2
    kept_urls = [item[3]["source_url"] for item in kept]
    assert kept_urls == ["https://www.nature.com/articles/abc"]
    assert "www.facebook.com" in netlocs
    assert "en.wikipedia.org" in netlocs


def test_denylist_keeps_gov_edu_doi():
    """Credibility is not journal-only: gov / edu / doi.org / nber are NOT in
    the suggested denylist, so they survive even when the gate is ON."""
    os.environ["PG_SCOPE_DENYLIST_DOMAINS"] = (
        "facebook.com,scribd.com,en.wikipedia.org,blogspot,wordpress,"
        "reddit,quora,medium.com"
    )
    try:
        rows = [
            _row("https://www.cdc.gov/report"),
            _row("https://mit.edu/paper"),
            _row("https://doi.org/10.1000/xyz"),
            _row("https://www.nber.org/papers/w12345"),
        ]
        kept, dropped, _ = _apply_scope_denylist(_scored(rows), None)
        assert dropped == 0
        assert len(kept) == 4
    finally:
        del os.environ["PG_SCOPE_DENYLIST_DOMAINS"]


def test_denylist_bare_token_substring(monkeypatch):
    """Bare tokens (no dot) match on substring-in-netloc."""
    monkeypatch.setenv("PG_SCOPE_DENYLIST_DOMAINS", "blogspot,reddit")
    rows = [
        _row("https://someone.blogspot.com/x"),  # substring -> drop
        _row("https://old.reddit.com/r/x"),       # substring -> drop
        _row("https://www.thelancet.com/x"),       # keep
    ]
    kept, dropped, _ = _apply_scope_denylist(_scored(rows), None)
    assert dropped == 2
    assert len(kept) == 1


def test_denylist_does_not_overmatch_suffix(monkeypatch):
    """A dotted entry must NOT match a domain that merely CONTAINS it as a
    prefix label (`facebook.com.evil.org` is not facebook.com)."""
    monkeypatch.setenv("PG_SCOPE_DENYLIST_DOMAINS", "facebook.com")
    netloc = _row_netloc(_row("https://facebook.com.evil.org/x"))
    assert _netloc_matches_denylist(netloc, ("facebook.com",)) is False
    # but the real subdomain DOES match
    assert _netloc_matches_denylist("m.facebook.com", ("facebook.com",)) is True


def test_denylist_exempts_marquee_anchor(monkeypatch):
    """A marquee / required-entity anchor on a denylisted host is EXEMPT."""
    monkeypatch.setenv("PG_SCOPE_DENYLIST_DOMAINS", "facebook.com")
    rows = [
        _row("https://facebook.com/x", is_marquee=True),       # exempt -> keep
        _row("https://facebook.com/y"),                         # drop
    ]
    kept, dropped, _ = _apply_scope_denylist(_scored(rows), None)
    assert dropped == 1
    assert kept[0][3].get("is_marquee") is True


def test_denylist_noop_through_full_selection(monkeypatch):
    """End-to-end via select_evidence_for_generation on the relevance-floor
    path: env unset => the keep set is identical with/without the gate code."""
    monkeypatch.delenv("PG_SCOPE_DENYLIST_DOMAINS", raising=False)
    rows = [
        {"source_url": "https://facebook.com/x", "statement": "topic alpha beta",
         "authority_score": 1.0},
        {"source_url": "https://www.nature.com/y", "statement": "topic alpha beta",
         "authority_score": 1.0},
    ]
    sel = select_evidence_for_generation(
        research_question="topic alpha beta",
        protocol=None,
        classified_sources=[],
        evidence_rows=rows,
        max_rows=10,
        relevance_floor=0.10,
    )
    # No denylist -> both rows survive the floor.
    assert len(sel.selected_rows) == 2


# ── gate 2: semantic LLM topic-relevance gate ─────────────────────────────────

def _topic_rows():
    return [
        {"title": "Semaglutide cardiovascular outcomes in T2D",
         "source_url": "https://nejm.org/a"},
        {"title": "Spinal cord stimulation for chronic pain",
         "source_url": "https://spine.org/b"},
    ]


def test_topic_gate_disabled_default():
    assert topic_gate_enabled() is False
    assert topic_batch_size() == 25


def test_topic_gate_drops_offtopic_keeps_ontopic():
    """Stub LLM marks source index 0 ON and index 1 OFF -> the off-topic
    spinal-cord row is dropped, the on-topic semaglutide row kept."""
    rows = _topic_rows()

    def _stub(prompt: str) -> str:
        # Two sources requested -> return exactly two verdict lines.
        return "0: ON\n1: OFF"

    result = classify_topic_relevance(rows, "semaglutide CV outcomes", _stub)
    assert result.n_in == 2
    assert result.n_dropped_offtopic == 1
    assert result.n_kept == 1
    kept_titles = [r["title"] for r in result.kept_rows]
    assert kept_titles == ["Semaglutide cardiovascular outcomes in T2D"]
    assert any("Spinal cord" in t for t in result.dropped_titles)


def test_topic_gate_fails_open_on_llm_error():
    """A raising llm_callable => keep the whole batch (never drop on error)."""
    rows = _topic_rows()

    def _boom(prompt: str) -> str:
        raise RuntimeError("LLM down")

    result = classify_topic_relevance(rows, "semaglutide CV outcomes", _boom)
    assert result.n_dropped_offtopic == 0
    assert result.n_kept == 2


def test_topic_gate_fails_open_on_count_mismatch():
    """A response with the wrong number of verdicts => keep the whole batch."""
    rows = _topic_rows()

    def _short(prompt: str) -> str:
        return "0: OFF"  # only one verdict for two sources

    result = classify_topic_relevance(rows, "semaglutide CV outcomes", _short)
    assert result.n_dropped_offtopic == 0
    assert result.n_kept == 2


def test_topic_gate_fails_open_on_garbage():
    """Unparseable response => keep the whole batch."""
    rows = _topic_rows()

    def _garbage(prompt: str) -> str:
        return "I think the first one is fine and the second is unrelated."

    result = classify_topic_relevance(rows, "semaglutide CV outcomes", _garbage)
    assert result.n_dropped_offtopic == 0
    assert result.n_kept == 2


def test_topic_gate_exempts_marquee_even_if_offtopic():
    """A marquee anchor is NEVER classified/dropped, even if the stub would
    have called it OFF."""
    rows = [
        {"title": "Required trial primary paper",
         "source_url": "https://nejm.org/a", "is_marquee": True},
        {"title": "Blockchain sustainability review",
         "source_url": "https://x.org/b"},
    ]

    def _stub(prompt: str) -> str:
        # Only ONE non-exempt source reaches the LLM -> one verdict line.
        return "0: OFF"

    result = classify_topic_relevance(rows, "semaglutide CV outcomes", _stub)
    assert result.n_exempt == 1
    assert result.n_dropped_offtopic == 1
    kept_titles = [r["title"] for r in result.kept_rows]
    assert "Required trial primary paper" in kept_titles


def test_topic_gate_batches_bound_calls(monkeypatch):
    """PG_SCOPE_TOPIC_BATCH bounds sources per LLM call -> 3 sources at batch
    size 2 means 2 calls."""
    monkeypatch.setenv("PG_SCOPE_TOPIC_BATCH", "2")
    rows = [
        {"title": f"src {i}", "source_url": f"https://x.org/{i}"}
        for i in range(3)
    ]
    calls = {"n": 0}

    def _stub(prompt: str) -> str:
        calls["n"] += 1
        # Reply ON for local indices 0..1 (max batch size 2). The parser
        # ignores any verdict whose index is not in the batch, so the final
        # single-source batch (index 0 only) parses cleanly.
        return "0: ON\n1: ON"

    result = classify_topic_relevance(
        rows, "topic", _stub, batch_size=2,
    )
    # 3 sources, batch 2 -> 2 calls; all ON -> nothing dropped.
    assert calls["n"] == 2
    assert result.n_dropped_offtopic == 0
    assert result.n_kept == 3


# ── gate 3: arXiv -> journal version preference ───────────────────────────────

def test_prefer_journal_default_off():
    """The pure helper drops twins; the ENV gate is checked in the orchestrator.
    Here we assert the helper's own no-twin no-op and twin-drop behavior."""
    # No journal twin present -> arXiv row survives (twinless never dropped).
    rows = [
        {"title": "Scaling laws for neural language models",
         "source_url": "https://arxiv.org/abs/2001.00001"},
    ]
    kept, dropped, titles = prefer_journal_over_arxiv(rows)
    assert dropped == 0
    assert len(kept) == 1
    assert titles == []


def test_prefer_journal_drops_arxiv_twin():
    rows = [
        {"title": "A Great Paper On Things",
         "source_url": "https://arxiv.org/abs/2401.12345"},
        {"title": "A great paper on things!",  # same normalized title
         "source_url": "https://doi.org/10.1000/great", "doi": "10.1000/great"},
    ]
    kept, dropped, titles = prefer_journal_over_arxiv(rows)
    assert dropped == 1
    kept_urls = [r["source_url"] for r in kept]
    assert kept_urls == ["https://doi.org/10.1000/great"]
    assert titles and "Great Paper" in titles[0]


def test_prefer_journal_keeps_arxiv_without_twin():
    """An arXiv row whose title has no journal/DOI twin is NEVER dropped, even
    when OTHER (different-title) journal rows exist in the pool."""
    rows = [
        {"title": "Unique preprint result",
         "source_url": "https://arxiv.org/abs/2402.00002"},
        {"title": "Completely different journal paper",
         "source_url": "https://doi.org/10.1000/other", "doi": "10.1000/other"},
    ]
    kept, dropped, _ = prefer_journal_over_arxiv(rows)
    assert dropped == 0
    assert len(kept) == 2


def test_prefer_journal_two_arxiv_versions_both_survive():
    """Two arXiv versions of the SAME paper with NO journal twin both survive."""
    rows = [
        {"title": "Same paper",
         "source_url": "https://arxiv.org/abs/2403.00003v1"},
        {"title": "Same paper",
         "source_url": "https://arxiv.org/abs/2403.00003v2"},
    ]
    kept, dropped, _ = prefer_journal_over_arxiv(rows)
    assert dropped == 0
    assert len(kept) == 2


def test_scope_denylist_parser():
    """Env parser: empty => (); populated => lowercased stripped tuple."""
    assert _scope_denylist_domains() == ()
    os.environ["PG_SCOPE_DENYLIST_DOMAINS"] = " Facebook.com , SCRIBD.com ,, "
    try:
        assert _scope_denylist_domains() == ("facebook.com", "scribd.com")
    finally:
        del os.environ["PG_SCOPE_DENYLIST_DOMAINS"]
