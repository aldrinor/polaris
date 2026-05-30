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
    europe_pmc_search,
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


def test_r6_clinical_dispatcher_calls_europe_pmc() -> None:
    # I-meta-002-q1d (#942-clinical): clinical now adds the Europe PMC backend on top of Serper+S2.
    with patch(
        "src.polaris_graph.retrieval.domain_backends.europe_pmc_search",
        return_value=[SearchCandidate(
            url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/",
            title="A clinical trial", snippet="", source="europe_pmc",
        )],
    ) as mock_epmc:
        result = run_domain_backends(
            domain="clinical",
            research_question="semaglutide weight loss",
        )
    assert mock_epmc.called
    assert result.backends_used == ["europe_pmc"]
    assert all(c.source == "europe_pmc" for c in result.candidates)


def test_r6_clinical_europe_pmc_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("PG_CLINICAL_EUROPE_PMC", "0")
    with patch(
        "src.polaris_graph.retrieval.domain_backends.europe_pmc_search",
        return_value=[SearchCandidate(url="https://x", title="t", snippet="", source="europe_pmc")],
    ) as mock_epmc:
        result = run_domain_backends(domain="clinical", research_question="q")
    assert not mock_epmc.called
    assert result.candidates == []


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


# --- I-meta-002-q1d (#942-clinical): Europe PMC backend URL priority + skip + fail-open ----------
def _epmc_result(*, pmcid="", doi="", pmid="", title="t", abstract="a"):
    return {"pmcid": pmcid, "doi": doi, "pmid": pmid, "title": title, "abstractText": abstract}


def test_europe_pmc_url_priority_pmcid_first() -> None:
    # PMCID present (even with doi+pmid) → PMC full-text URL wins (Codex brief-gate: PMC is the
    # strongest keyless fetchable path).
    payload = {"resultList": {"result": [_epmc_result(pmcid="PMC555", doi="10.1/x", pmid="999")]}}
    with patch("src.polaris_graph.retrieval.domain_backends._http_get_json", return_value=payload):
        out = europe_pmc_search("metformin renal")
    assert out[0].url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC555/"
    assert out[0].source == "europe_pmc"
    assert out[0].metadata["doi"] == "10.1/x"


def test_europe_pmc_url_priority_doi_then_pmid() -> None:
    payload = {"resultList": {"result": [
        _epmc_result(doi="10.1056/abc", pmid="111"),   # no pmcid → doi
        _epmc_result(pmid="222"),                       # only pmid → pubmed
    ]}}
    with patch("src.polaris_graph.retrieval.domain_backends._http_get_json", return_value=payload):
        out = europe_pmc_search("q")
    assert out[0].url == "https://doi.org/10.1056/abc"
    assert out[1].url == "https://pubmed.ncbi.nlm.nih.gov/222/"


def test_europe_pmc_skips_record_with_no_resolvable_id() -> None:
    # A record with none of pmcid/doi/pmid is SKIPPED — never a europepmc.org landing URL.
    payload = {"resultList": {"result": [
        _epmc_result(title="no ids"),
        _epmc_result(doi="10.1/keep"),
    ]}}
    with patch("src.polaris_graph.retrieval.domain_backends._http_get_json", return_value=payload):
        out = europe_pmc_search("q")
    assert len(out) == 1
    assert out[0].url == "https://doi.org/10.1/keep"
    assert all("europepmc.org" not in c.url for c in out)


def test_europe_pmc_fails_open_on_empty_or_error() -> None:
    with patch("src.polaris_graph.retrieval.domain_backends._http_get_json", return_value=None):
        assert europe_pmc_search("q") == []
    with patch("src.polaris_graph.retrieval.domain_backends._http_get_json", return_value={"bad": "shape"}):
        assert europe_pmc_search("q") == []
    # Codex diff-gate iter-1 P1: a helper/network EXCEPTION must also fail open (not escape).
    with patch(
        "src.polaris_graph.retrieval.domain_backends._http_get_json",
        side_effect=RuntimeError("network down"),
    ):
        assert europe_pmc_search("q") == []
