"""
R-6 Gap-2 regression tests: domain-routed retrieval backends.

HTTP calls are stubbed — we verify dispatcher logic, fail-open
behavior, and arXiv XML parsing deterministically.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.polaris_graph.retrieval.domain_backends import (
    _parse_arxiv_feed,
    run_domain_backends,
)
from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    SearchCandidate,
)


ARXIV_SAMPLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2506.00054v1</id>
    <title>Retrieval-Augmented Generation: A Comprehensive Survey</title>
    <summary>This survey reviews RAG approaches across 2020-2025 with
    focus on retrieval quality, generation faithfulness, and
    deployment patterns in production systems.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2408.12345v2</id>
    <title>Long-Context Transformers via YaRN Scaling</title>
    <summary>We propose an extension of YaRN to 128K+ context with
    competitive recall.</summary>
  </entry>
</feed>
"""


def test_r6_arxiv_xml_parse() -> None:
    cands = _parse_arxiv_feed(ARXIV_SAMPLE_XML, limit=10)
    assert len(cands) == 2
    assert cands[0].url.startswith("https://arxiv.org/abs/") or \
           cands[0].url.startswith("http://arxiv.org/abs/")
    assert "Retrieval-Augmented" in cands[0].title
    assert cands[0].source == "arxiv"
    assert "RAG approaches" in cands[0].snippet


def test_r6_arxiv_parse_empty_feed() -> None:
    assert _parse_arxiv_feed("", limit=10) == []
    assert _parse_arxiv_feed("<feed></feed>", limit=10) == []


def test_r6_arxiv_parse_limit_honored() -> None:
    cands = _parse_arxiv_feed(ARXIV_SAMPLE_XML, limit=1)
    assert len(cands) == 1


def test_r6_tech_dispatcher_calls_arxiv_and_github() -> None:
    with patch(
        "src.polaris_graph.retrieval.domain_backends.arxiv_search",
        return_value=[SearchCandidate(
            url="https://arxiv.org/abs/xxx", title="paper",
            snippet="", source="arxiv",
        )],
    ) as mock_arxiv, patch(
        "src.polaris_graph.retrieval.domain_backends.github_search_repos",
        return_value=[SearchCandidate(
            url="https://github.com/x/y", title="repo",
            snippet="", source="github",
        )],
    ) as mock_gh:
        result = run_domain_backends(
            domain="tech",
            research_question="retrieval augmented generation",
        )
    assert mock_arxiv.called
    assert mock_gh.called
    assert len(result.candidates) == 2
    sources = {c.source for c in result.candidates}
    assert sources == {"arxiv", "github"}
    assert set(result.backends_used) == {"arxiv", "github"}


def test_r6_policy_dispatcher_calls_serper_policy_only() -> None:
    with patch(
        "src.polaris_graph.retrieval.domain_backends.policy_targeted_serper",
        return_value=[SearchCandidate(
            url="https://www.federalregister.gov/documents/xxx",
            title="Federal Register notice",
            snippet="", source="serper_policy",
        )],
    ) as mock_pol, patch(
        "src.polaris_graph.retrieval.domain_backends.arxiv_search",
        return_value=[],
    ) as mock_ax:
        result = run_domain_backends(
            domain="policy",
            research_question="FDA PCCP AI-enabled devices",
        )
    assert mock_pol.called
    assert not mock_ax.called
    assert all(c.source == "serper_policy" for c in result.candidates)


def test_r6_due_diligence_dispatcher_calls_sec() -> None:
    with patch(
        "src.polaris_graph.retrieval.domain_backends.sec_edgar_search",
        return_value=[SearchCandidate(
            url="https://www.sec.gov/Archives/edgar/data/x/y.htm",
            title="Novo Nordisk 10-K",
            snippet="", source="sec_edgar",
        )],
    ) as mock_sec:
        result = run_domain_backends(
            domain="due_diligence",
            research_question="Novo Nordisk obesity market",
        )
    assert mock_sec.called
    assert all(c.source == "sec_edgar" for c in result.candidates)


def test_r6_clinical_dispatcher_uses_no_domain_backends() -> None:
    result = run_domain_backends(
        domain="clinical",
        research_question="semaglutide weight loss",
    )
    # Clinical defers to generic Serper+S2 — no specific backends
    assert result.candidates == []
    assert result.backends_used == []


def test_r6_unknown_domain_returns_empty() -> None:
    result = run_domain_backends(
        domain="made_up_domain",
        research_question="anything",
    )
    assert result.candidates == []


def test_r6_backend_exception_fails_open() -> None:
    """If a backend raises, the dispatcher swallows it and returns
    results from the other backends."""
    def _raising(q, limit):
        raise RuntimeError("API down")

    with patch(
        "src.polaris_graph.retrieval.domain_backends.arxiv_search",
        side_effect=_raising,
    ), patch(
        "src.polaris_graph.retrieval.domain_backends.github_search_repos",
        return_value=[SearchCandidate(
            url="https://github.com/x/y", title="repo",
            snippet="", source="github",
        )],
    ):
        result = run_domain_backends(
            domain="tech",
            research_question="anything",
        )
    # arxiv crashed but github still contributed
    assert len(result.candidates) == 1
    assert result.candidates[0].source == "github"


def test_r6_dispatcher_dedupes_across_backends() -> None:
    dup_url = "https://shared.example.com/page"
    with patch(
        "src.polaris_graph.retrieval.domain_backends.arxiv_search",
        return_value=[SearchCandidate(
            url=dup_url, title="via arxiv", snippet="", source="arxiv",
        )],
    ), patch(
        "src.polaris_graph.retrieval.domain_backends.github_search_repos",
        return_value=[SearchCandidate(
            url=dup_url, title="via github", snippet="", source="github",
        )],
    ):
        result = run_domain_backends(
            domain="tech", research_question="x",
        )
    assert len(result.candidates) == 1
    # First backend to surface wins (arxiv) — github drops as duplicate
    assert result.candidates[0].source == "arxiv"
