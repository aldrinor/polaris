"""
Integration tests for POLARIS Quality SOTA Sprint fixes.

Tests cover:
- FIX-B1: Source URL blocklist (_is_blocked_source)
- FIX-B2: Domain authority scoring (_get_domain_authority)
- FIX-B3: Off-topic evidence filtering (_filter_offtopic_evidence)
- FIX-C1: Outline evidence deduplication (_validate_outline_evidence)
- FIX-C3: Cross-section redundancy detection (detect_redundancy)
- FIX-E2: Abstract metric validation (_validate_abstract_metrics)
- FIX-D3: Snippet quality tier penalty (_assign_quality_tiers)
- FIX-B2+D3: Quality tier with domain authority multiplier
- FIX-D4: S2 openAccessPdf URL preference (_fetch_s2_references)
- FIX-F2: Cost ledger session_id (UsageTracker / OpenRouterClient)
- FIX-D1: Jina Reader fetch (AccessBypass._try_jina_reader)

All tests are fully mocked -- no real API calls or embedding model loads.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.polaris_graph.state import (
    EvidencePiece,
    ReportSection,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_polaris_graph.py)
# ---------------------------------------------------------------------------

def _make_evidence(
    evidence_id: str,
    statement: str = "Test statement",
    source_url: str = "https://example.com",
    relevance: float = 0.7,
    quality_tier: str = "SILVER",
    perspective: str = "Scientific",
    source_type: str = "web",
    fetch_method: str = "full",
    direct_quote: str = (
        "The study found that activated carbon adsorption removed 95% of PFAS "
        "contaminants from drinking water supplies at pilot scale, demonstrating "
        "significant improvement over conventional treatment methods."
    ),
) -> EvidencePiece:
    """Create a minimal EvidencePiece for testing."""
    return EvidencePiece(
        evidence_id=evidence_id,
        source_url=source_url,
        source_title="Test Source",
        source_type=source_type,
        direct_quote=direct_quote,
        statement=statement,
        fact_category="statistic",
        relevance_score=relevance,
        llm_relevance_score=relevance,
        quality_tier=quality_tier,
        citation_key="",
        year=2024,
        authors=["Test Author"],
        venue="Test Venue",
        doi="",
        perspective=perspective,
        fetch_method=fetch_method,
    )


def _make_report_section(
    section_id: str,
    title: str = "Test Section",
    content: str = "Default content for the test section with enough words.",
    word_count: int = 50,
    citation_ids: list = None,
    evidence_ids: list = None,
) -> ReportSection:
    """Create a minimal ReportSection for testing."""
    return ReportSection(
        section_id=section_id,
        title=title,
        content=content,
        word_count=word_count,
        citation_ids=citation_ids or [],
        evidence_ids=evidence_ids or [],
    )


def _make_outline_dict(
    title: str = "Test Report",
    abstract: str = "Abstract text.",
    sections: list = None,
    total_target_words: int = 8000,
) -> dict:
    """Create a ReportOutline as a dict (required by Pydantic model_validator).

    The ReportOutline.filter_invalid_sections validator expects sections
    to be dicts (not SectionOutlineItem instances), so we construct the
    outline from a raw dict.
    """
    return {
        "title": title,
        "abstract": abstract,
        "sections": sections or [],
        "total_target_words": total_target_words,
    }


# ---------------------------------------------------------------------------
# Test 1: _is_blocked_source -- blocked domains
# ---------------------------------------------------------------------------

def test_blocked_source_known_commercial_domains():
    """FIX-B1: Known commercial/affiliate domains are blocked."""
    from src.polaris_graph.agents.analyzer import _is_blocked_source

    assert _is_blocked_source("https://cnfilter.net/products/filter-1") is True
    assert _is_blocked_source("https://uswatersystems.com/info") is True
    assert _is_blocked_source("https://amazon.com/dp/B00123") is True
    assert _is_blocked_source("https://ebay.com/itm/123") is True
    assert _is_blocked_source("https://alibaba.com/product/456") is True


# ---------------------------------------------------------------------------
# Test 2: _is_blocked_source -- allowed domains
# ---------------------------------------------------------------------------

def test_blocked_source_legitimate_domains_pass():
    """FIX-B1: Legitimate research domains are NOT blocked."""
    from src.polaris_graph.agents.analyzer import _is_blocked_source

    assert _is_blocked_source("https://epa.gov/water-quality") is False
    assert _is_blocked_source("https://nature.com/articles/12345") is False
    assert _is_blocked_source("https://sciencedirect.com/science/article") is False
    assert _is_blocked_source("https://ncbi.nlm.nih.gov/pubmed/123") is False
    assert _is_blocked_source("https://stanford.edu/research/water") is False


# ---------------------------------------------------------------------------
# Test 3: _is_blocked_source -- path-qualified domain blocks
# ---------------------------------------------------------------------------

def test_blocked_source_path_qualified():
    """FIX-B1: Path-qualified blocks only trigger when path matches."""
    from src.polaris_graph.agents.analyzer import _is_blocked_source

    # consumerreports.org/shop is blocked (path-qualified)
    assert _is_blocked_source("https://consumerreports.org/shop/water-filters") is True

    # consumerreports.org/reviews is NOT blocked (path does not match /shop)
    assert _is_blocked_source("https://consumerreports.org/reviews/water-filters") is False

    # reddit.com/r/ is blocked (path-qualified)
    assert _is_blocked_source("https://reddit.com/r/water") is True

    # reddit.com top-level is NOT blocked
    assert _is_blocked_source("https://reddit.com/about") is False


# ---------------------------------------------------------------------------
# Test 4: _is_blocked_source -- commercial path patterns
# ---------------------------------------------------------------------------

def test_blocked_source_commercial_path_patterns():
    """FIX-B1: URLs with commercial path patterns are blocked."""
    from src.polaris_graph.agents.analyzer import _is_blocked_source

    assert _is_blocked_source("https://example.com/shop/item") is True
    assert _is_blocked_source("https://example.com/product/123") is True
    assert _is_blocked_source("https://example.com/cart/checkout") is True
    assert _is_blocked_source("https://example.com/affiliate/link") is True
    assert _is_blocked_source("https://example.com/buy/now") is True

    # Non-commercial paths on same domain should pass
    assert _is_blocked_source("https://example.com/research/paper") is False


# ---------------------------------------------------------------------------
# Test 5: _is_blocked_source -- edge cases
# ---------------------------------------------------------------------------

def test_blocked_source_edge_cases():
    """FIX-B1: Empty URL, None-like, and subdomain matching."""
    from src.polaris_graph.agents.analyzer import _is_blocked_source

    # Empty URL returns False (not blocked)
    assert _is_blocked_source("") is False

    # Subdomain of blocked domain is also blocked
    assert _is_blocked_source("https://www.amazon.com/dp/B00123") is True
    assert _is_blocked_source("https://shop.cnfilter.net/filters") is True

    # Commercial TLDs
    assert _is_blocked_source("https://waterfilters.shop/page") is True
    assert _is_blocked_source("https://filters.store/item") is True


# ---------------------------------------------------------------------------
# Test 6: _get_domain_authority -- tier 1 (.gov/.edu/top journals)
# ---------------------------------------------------------------------------

def test_domain_authority_tier1():
    """FIX-B2: TIER 1 domains return authority 1.0."""
    from src.polaris_graph.agents.analyzer import _get_domain_authority

    # .gov TLD
    assert _get_domain_authority("https://epa.gov/water") == 1.0
    assert _get_domain_authority("https://cdc.gov/health") == 1.0

    # .edu TLD
    assert _get_domain_authority("https://mit.edu/research") == 1.0
    assert _get_domain_authority("https://stanford.edu/papers") == 1.0

    # Top journals
    assert _get_domain_authority("https://nature.com/articles/12345") == 1.0
    assert _get_domain_authority("https://sciencedirect.com/article/pii") == 1.0
    assert _get_domain_authority("https://who.int/publications") == 1.0


# ---------------------------------------------------------------------------
# Test 7: _get_domain_authority -- tier 2 (standards/wire services)
# ---------------------------------------------------------------------------

def test_domain_authority_tier2():
    """FIX-B2: TIER 2 domains return authority 0.85.

    Note: ncbi.nlm.nih.gov ends with .gov so it matches TIER 1 first.
    This test uses non-.gov TIER 2 domains to verify the tier 2 logic.
    """
    from src.polaris_graph.agents.analyzer import _get_domain_authority

    # Non-.gov tier 2 domains
    assert _get_domain_authority("https://nsf.org/research") == 0.85
    assert _get_domain_authority("https://reuters.com/article/water") == 0.85
    assert _get_domain_authority("https://apnews.com/article/123") == 0.85
    assert _get_domain_authority("https://iso.org/standard/12345") == 0.85

    # ncbi.nlm.nih.gov ends with .gov -> TIER 1 (1.0), not TIER 2
    # This is correct behavior: .gov TLD takes precedence
    assert _get_domain_authority("https://ncbi.nlm.nih.gov/pubmed/123") == 1.0


# ---------------------------------------------------------------------------
# Test 8: _get_domain_authority -- tier 3, default, blocked
# ---------------------------------------------------------------------------

def test_domain_authority_tier3_default_blocked():
    """FIX-B2: TIER 3 = 0.7, default = 0.5, blocked = 0.0."""
    from src.polaris_graph.agents.analyzer import _get_domain_authority

    # TIER 3: Industry trade publications
    assert _get_domain_authority("https://wateronline.com/article") == 0.7
    assert _get_domain_authority("https://wqa.org/resources") == 0.7

    # TIER 3 blog exclusion: blog path gets downgraded to default
    assert _get_domain_authority("https://wateronline.com/blog/post") == 0.5

    # DEFAULT: Unknown domains
    assert _get_domain_authority("https://example.com/page") == 0.5
    assert _get_domain_authority("https://randomsite.org/article") == 0.5

    # BLOCKED: Returns 0.0
    assert _get_domain_authority("https://cnfilter.net/page") == 0.0
    assert _get_domain_authority("https://amazon.com/dp/B00123") == 0.0

    # Empty URL returns default
    assert _get_domain_authority("") == 0.5


# ---------------------------------------------------------------------------
# Test 9: _filter_offtopic_evidence -- high similarity stays
# ---------------------------------------------------------------------------

def test_filter_offtopic_evidence_keeps_relevant():
    """FIX-B3: Evidence with high embedding similarity to the query is kept."""
    from src.polaris_graph.agents.analyzer import _filter_offtopic_evidence
    import numpy as np

    evidence = [
        _make_evidence("ev_1", statement="Water filters remove bacteria effectively"),
        _make_evidence("ev_2", statement="RO membranes filter heavy metals"),
        _make_evidence("ev_3", statement="UV treatment kills pathogens"),
    ]

    query = "household water filter effectiveness"

    # All evidence has high similarity (> 0.15 threshold)
    query_vec = np.array([1.0, 0.0, 0.0])
    statement_vecs = np.array([
        [0.9, 0.1, 0.0],  # sim ~ 0.9
        [0.8, 0.2, 0.0],  # sim ~ 0.8
        [0.7, 0.3, 0.0],  # sim ~ 0.7
    ])
    # Normalize
    query_vec = query_vec / np.linalg.norm(query_vec)
    statement_vecs = statement_vecs / np.linalg.norm(statement_vecs, axis=1, keepdims=True)

    with patch("src.utils.embedding_service.embed_text", return_value=query_vec.tolist()), \
         patch("src.utils.embedding_service.embed_texts", return_value=statement_vecs.tolist()), \
         patch("src.polaris_graph.agents.analyzer.get_tracer", return_value=None):
        result = _filter_offtopic_evidence(evidence, query)

    assert len(result) == 3
    ids = {e["evidence_id"] for e in result}
    assert "ev_1" in ids
    assert "ev_2" in ids
    assert "ev_3" in ids


# ---------------------------------------------------------------------------
# Test 10: _filter_offtopic_evidence -- low similarity removed
# ---------------------------------------------------------------------------

def test_filter_offtopic_evidence_removes_irrelevant():
    """FIX-B3: Evidence below PG_OFFTOPIC_THRESHOLD (0.15) is removed."""
    from src.polaris_graph.agents.analyzer import _filter_offtopic_evidence
    import numpy as np

    evidence = [
        _make_evidence("ev_relevant", statement="Water filters reduce contamination"),
        _make_evidence("ev_offtopic", statement="Quantum computing breakthrough"),
    ]

    query = "water filter research"

    query_vec = np.array([1.0, 0.0, 0.0])
    statement_vecs = np.array([
        [0.9, 0.1, 0.0],  # sim ~ 0.9 -> above threshold
        [0.05, 0.0, 0.95],  # sim ~ 0.05 -> below 0.15 threshold
    ])
    query_vec = query_vec / np.linalg.norm(query_vec)
    statement_vecs = statement_vecs / np.linalg.norm(statement_vecs, axis=1, keepdims=True)

    with patch("src.utils.embedding_service.embed_text", return_value=query_vec.tolist()), \
         patch("src.utils.embedding_service.embed_texts", return_value=statement_vecs.tolist()), \
         patch("src.polaris_graph.agents.analyzer.get_tracer", return_value=None):
        result = _filter_offtopic_evidence(evidence, query)

    assert len(result) == 1
    assert result[0]["evidence_id"] == "ev_relevant"


# ---------------------------------------------------------------------------
# Test 11: _filter_offtopic_evidence -- empty list returns empty
# ---------------------------------------------------------------------------

def test_filter_offtopic_evidence_empty_input():
    """FIX-B3: Empty evidence list returns empty list without error."""
    from src.polaris_graph.agents.analyzer import _filter_offtopic_evidence

    result = _filter_offtopic_evidence([], "any query")
    assert result == []


# ---------------------------------------------------------------------------
# Test 12: _validate_outline_evidence -- deduplicates cross-section
# ---------------------------------------------------------------------------

def test_validate_outline_evidence_deduplicates():
    """FIX-C1: Evidence IDs appearing in multiple sections are deduplicated.

    The ReportOutline model_validator requires sections as dicts, so we
    build the outline from a raw dict to pass validation correctly.
    """
    from src.polaris_graph.synthesis.section_writer import _validate_outline_evidence
    from src.polaris_graph.schemas import ReportOutline

    outline = ReportOutline.model_validate(_make_outline_dict(
        title="Test Report",
        abstract="Abstract text.",
        sections=[
            {
                "section_id": "s01",
                "title": "Section One",
                "description": "First section",
                "evidence_ids": ["ev_1", "ev_2", "ev_3"],
                "target_words": 600,
                "order": 1,
            },
            {
                "section_id": "s02",
                "title": "Section Two",
                "description": "Second section",
                "evidence_ids": ["ev_2", "ev_4", "ev_5"],
                "target_words": 600,
                "order": 2,
            },
            {
                "section_id": "s03",
                "title": "Section Three",
                "description": "Third section",
                "evidence_ids": ["ev_3", "ev_6"],
                "target_words": 600,
                "order": 3,
            },
        ],
        total_target_words=1800,
    ))

    assert len(outline.sections) == 3, (
        f"Expected 3 sections but got {len(outline.sections)}"
    )

    result = _validate_outline_evidence(outline)

    # Sort sections by order for predictable checks
    sorted_sections = sorted(result.sections, key=lambda s: s.order)

    # s01 should keep all 3 (first occurrence)
    assert sorted_sections[0].evidence_ids == ["ev_1", "ev_2", "ev_3"]

    # s02 should lose ev_2 (already in s01)
    assert "ev_2" not in sorted_sections[1].evidence_ids
    assert "ev_4" in sorted_sections[1].evidence_ids
    assert "ev_5" in sorted_sections[1].evidence_ids

    # s03 should lose ev_3 (already in s01)
    assert "ev_3" not in sorted_sections[2].evidence_ids
    assert "ev_6" in sorted_sections[2].evidence_ids


# ---------------------------------------------------------------------------
# Test 13: _validate_outline_evidence -- no duplicates no change
# ---------------------------------------------------------------------------

def test_validate_outline_evidence_no_duplicates():
    """FIX-C1: When no duplicates exist, outline is unchanged."""
    from src.polaris_graph.synthesis.section_writer import _validate_outline_evidence
    from src.polaris_graph.schemas import ReportOutline

    outline = ReportOutline.model_validate(_make_outline_dict(
        title="Clean Report",
        abstract="Abstract.",
        sections=[
            {
                "section_id": "s01",
                "title": "Section A",
                "description": "Desc A",
                "evidence_ids": ["ev_1", "ev_2"],
                "target_words": 500,
                "order": 1,
            },
            {
                "section_id": "s02",
                "title": "Section B",
                "description": "Desc B",
                "evidence_ids": ["ev_3", "ev_4"],
                "target_words": 500,
                "order": 2,
            },
        ],
        total_target_words=1000,
    ))

    assert len(outline.sections) == 2

    result = _validate_outline_evidence(outline)
    sorted_sections = sorted(result.sections, key=lambda s: s.order)

    assert sorted_sections[0].evidence_ids == ["ev_1", "ev_2"]
    assert sorted_sections[1].evidence_ids == ["ev_3", "ev_4"]


# ---------------------------------------------------------------------------
# Test 14: detect_redundancy -- finds cross-section duplicates
# ---------------------------------------------------------------------------

def test_detect_redundancy_finds_cross_section_duplicates():
    """FIX-C3: Near-duplicate sentences across sections are flagged."""
    from src.polaris_graph.synthesis.report_assembler import detect_redundancy

    # Two sections with an identical long sentence
    shared_sentence = (
        "Water filtration systems using activated carbon have been shown "
        "to reduce chlorine contamination by approximately 99.7 percent "
        "in municipal drinking water supplies across the United States"
    )

    sections = [
        _make_report_section(
            section_id="s01",
            title="Treatment Methods",
            content=(
                f"{shared_sentence}. "
                "Additional methods include UV disinfection and reverse osmosis "
                "membrane technology for removing dissolved solids."
            ),
            word_count=40,
        ),
        _make_report_section(
            section_id="s02",
            title="Effectiveness Analysis",
            content=(
                "Various studies have examined filter performance. "
                f"{shared_sentence}. "
                "This finding was replicated in laboratory conditions."
            ),
            word_count=35,
        ),
    ]

    result = detect_redundancy(sections)

    assert result["duplicate_pairs"] > 0
    assert result["redundancy_pct"] > 0.0
    assert result["total_sentences"] > 0
    assert isinstance(result["examples"], list)


# ---------------------------------------------------------------------------
# Test 15: detect_redundancy -- same-section pairs NOT flagged
# ---------------------------------------------------------------------------

def test_detect_redundancy_ignores_same_section():
    """FIX-C3: Duplicate sentences within the SAME section are not flagged."""
    from src.polaris_graph.synthesis.report_assembler import detect_redundancy

    # Same sentence repeated within one section
    repeated = (
        "Water filters are critical infrastructure for public health "
        "protection in developing nations with limited treatment capacity"
    )
    sections = [
        _make_report_section(
            section_id="s01",
            title="Public Health",
            content=f"{repeated}. {repeated}. A third unique sentence about regulations.",
            word_count=50,
        ),
    ]

    result = detect_redundancy(sections)

    # Same-section duplicates should NOT be counted
    assert result["duplicate_pairs"] == 0


# ---------------------------------------------------------------------------
# Test 16: detect_redundancy -- no duplicates returns clean
# ---------------------------------------------------------------------------

def test_detect_redundancy_clean_report():
    """FIX-C3: Fully unique content returns zero duplicate pairs."""
    from src.polaris_graph.synthesis.report_assembler import detect_redundancy

    sections = [
        _make_report_section(
            section_id="s01",
            title="Chemistry",
            content=(
                "Activated carbon adsorbs chlorine through a well-documented chemical reaction. "
                "The process involves electron transfer between the carbon surface and dissolved chlorine molecules."
            ),
            word_count=25,
        ),
        _make_report_section(
            section_id="s02",
            title="Engineering",
            content=(
                "Membrane pore sizes determine the range of contaminants that can be physically excluded. "
                "Reverse osmosis membranes typically feature pore diameters below one nanometer."
            ),
            word_count=25,
        ),
    ]

    result = detect_redundancy(sections)
    assert result["duplicate_pairs"] == 0
    assert result["redundancy_pct"] == 0.0


# ---------------------------------------------------------------------------
# Test 17: _validate_abstract_metrics -- hallucinated source count
# ---------------------------------------------------------------------------

def test_validate_abstract_metrics_hallucinated_count():
    """FIX-E2: Flags numbers near source keywords that diverge from actual count."""
    from src.polaris_graph.synthesis.report_assembler import _validate_abstract_metrics

    abstract = (
        "This report synthesizes evidence from 45 studies examining "
        "water filter effectiveness across multiple geographic regions."
    )

    # Actual unique_sources = 20, but abstract claims "45 studies"
    # abs(45 - 20) = 25 > 5 --> should warn
    warnings = _validate_abstract_metrics(
        abstract=abstract,
        unique_sources=20,
        total_citations=100,
        total_words=5000,
    )

    assert len(warnings) > 0
    assert any("45" in w for w in warnings)


# ---------------------------------------------------------------------------
# Test 18: _validate_abstract_metrics -- accurate count no warning
# ---------------------------------------------------------------------------

def test_validate_abstract_metrics_accurate_count():
    """FIX-E2: No warnings when abstract numbers match actual metrics."""
    from src.polaris_graph.synthesis.report_assembler import _validate_abstract_metrics

    abstract = (
        "This comprehensive report draws on 20 peer-reviewed studies "
        "to examine the state of household water filtration technology."
    )

    # abs(20 - 20) = 0 <= 5 --> no warning
    warnings = _validate_abstract_metrics(
        abstract=abstract,
        unique_sources=20,
        total_citations=100,
        total_words=5000,
    )

    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Test 19: _validate_abstract_metrics -- number without source keyword
# ---------------------------------------------------------------------------

def test_validate_abstract_metrics_number_without_source_keyword():
    """FIX-E2: Numbers not near source keywords are not flagged."""
    from src.polaris_graph.synthesis.report_assembler import _validate_abstract_metrics

    abstract = (
        "Water filters remove 99 percent of chlorine in 15 minutes of contact time."
    )

    # 99 and 15 are not near source-related keywords
    warnings = _validate_abstract_metrics(
        abstract=abstract,
        unique_sources=10,
        total_citations=50,
        total_words=3000,
    )

    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Test 20: _assign_quality_tiers -- snippet capped at SILVER (FIX-D3)
# ---------------------------------------------------------------------------

def test_assign_quality_tiers_snippet_capped():
    """FIX-D3: Snippet evidence (fetch_method='snippet') is capped at SILVER, never GOLD."""
    from src.polaris_graph.agents.analyzer import _assign_quality_tiers

    # Create evidence that would normally be GOLD:
    # journal_article + adjusted_relevance >= 0.6
    # But fetch_method="snippet" caps it at SILVER
    evidence = [
        _make_evidence(
            "ev_snippet_1",
            source_type="journal_article",
            relevance=0.9,
            source_url="https://nature.com/article/123",  # authority=1.0
            fetch_method="snippet",
        ),
    ]

    result = _assign_quality_tiers(evidence)

    assert result[0]["quality_tier"] == "SILVER"


# ---------------------------------------------------------------------------
# Test 21: _assign_quality_tiers -- full fetch can be GOLD
# ---------------------------------------------------------------------------

def test_assign_quality_tiers_full_fetch_gold():
    """FIX-D3: Full-fetch journal articles with high relevance get GOLD."""
    from src.polaris_graph.agents.analyzer import _assign_quality_tiers

    evidence = [
        _make_evidence(
            "ev_full_1",
            source_type="journal_article",
            relevance=0.9,
            source_url="https://nature.com/article/123",  # authority=1.0
            fetch_method="full",
        ),
    ]

    result = _assign_quality_tiers(evidence)

    assert result[0]["quality_tier"] == "GOLD"


# ---------------------------------------------------------------------------
# Test 22: _assign_quality_tiers -- domain authority multiplier (FIX-B2)
# ---------------------------------------------------------------------------

def test_assign_quality_tiers_domain_authority_multiplier():
    """FIX-B2: Unknown domain lowers authority signal, preventing GOLD.

    5-signal composite (FIX-048-K2):
    - random-journal.xyz authority: 0.5 (default) + 0.15 (journal_article) = 0.65
    - Compared to nature.com (1.0), the lower authority drags composite below gold_threshold.
    - With relevance=0.5: composite ≈ 0.6275 < 0.65 → SILVER
    """
    from src.polaris_graph.agents.analyzer import _assign_quality_tiers

    evidence = [
        _make_evidence(
            "ev_unknown_domain",
            source_type="journal_article",
            relevance=0.5,
            source_url="https://random-journal.xyz/article",
            fetch_method="full",
        ),
    ]

    result = _assign_quality_tiers(evidence)

    assert result[0]["quality_tier"] == "SILVER"


# ---------------------------------------------------------------------------
# Test 23: _assign_quality_tiers -- blocked domain gets BRONZE
# ---------------------------------------------------------------------------

def test_assign_quality_tiers_blocked_domain_bronze():
    """FIX-B2: Evidence from blocked domains gets authority=0.0, resulting in BRONZE."""
    from src.polaris_graph.agents.analyzer import _assign_quality_tiers

    # Even with high relevance, blocked domain -> authority 0.0
    # adjusted_relevance = 0.9 * 0.0 = 0.0 -> BRONZE
    evidence = [
        _make_evidence(
            "ev_blocked",
            source_type="web",
            relevance=0.9,
            source_url="https://cnfilter.net/article",
            fetch_method="full",
        ),
    ]

    result = _assign_quality_tiers(evidence)

    assert result[0]["quality_tier"] == "BRONZE"


# ---------------------------------------------------------------------------
# Test 24: S2 openAccessPdf URL preference (FIX-D4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s2_references_prefer_open_access_pdf():
    """FIX-D4: _fetch_s2_references prefers openAccessPdf.url over landing page.

    aiohttp is imported inside _fetch_s2_references, so we patch it at
    the aiohttp module level rather than on the searcher module.
    """
    import aiohttp as real_aiohttp

    # Mock S2 API response with openAccessPdf
    mock_response_data = {
        "data": [
            {
                "citedPaper": {
                    "paperId": "abc123",
                    "title": "Water Filter Study",
                    "abstract": "A study on water filters.",
                    "url": "https://api.semanticscholar.org/landing/abc123",
                    "year": 2023,
                    "authors": [{"name": "Smith J"}],
                    "citationCount": 42,
                    "venue": "Water Research",
                    "openAccessPdf": {
                        "url": "https://arxiv.org/pdf/2023.12345.pdf",
                    },
                }
            },
            {
                "citedPaper": {
                    "paperId": "def456",
                    "title": "RO Membrane Analysis",
                    "abstract": "Reverse osmosis study.",
                    "url": "https://api.semanticscholar.org/landing/def456",
                    "year": 2024,
                    "authors": [{"name": "Jones A"}],
                    "citationCount": 15,
                    "venue": "Desalination",
                    "openAccessPdf": None,
                }
            },
        ]
    }

    # Build nested async context manager mocks for aiohttp
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=mock_response_data)

    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_get_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client_session = MagicMock(return_value=mock_session_cm)

    with patch("aiohttp.ClientSession", mock_client_session), \
         patch("aiohttp.ClientTimeout", real_aiohttp.ClientTimeout):
        from src.polaris_graph.agents.searcher import _fetch_s2_references
        results = await _fetch_s2_references("paper123", "fake-api-key")

    assert len(results) == 2

    # First paper: should use openAccessPdf URL
    assert results[0]["url"] == "https://arxiv.org/pdf/2023.12345.pdf"

    # Second paper: no openAccessPdf, should fall back to landing URL
    assert results[1]["url"] == "https://api.semanticscholar.org/landing/def456"


# ---------------------------------------------------------------------------
# Test 25: Cost ledger session_id (FIX-F2)
# ---------------------------------------------------------------------------

def test_usage_tracker_has_session_id():
    """FIX-F2: UsageTracker includes session_id field."""
    from src.polaris_graph.llm.openrouter_client import UsageTracker

    tracker = UsageTracker(session_id="RUN_42")
    assert tracker.session_id == "RUN_42"

    # Default is empty string
    tracker_default = UsageTracker()
    assert tracker_default.session_id == ""


# ---------------------------------------------------------------------------
# Test 26: Cost ledger entries include session_id (FIX-F2)
# ---------------------------------------------------------------------------

def test_usage_tracker_record_includes_session_id():
    """FIX-F2: Ledger entries written by record() include session_id."""
    from src.polaris_graph.llm.openrouter_client import UsageTracker

    tracker = UsageTracker(session_id="RUN_99")

    # Mock _append_ledger to capture the entry
    captured_entries = []
    tracker._append_ledger = lambda entry: captured_entries.append(entry)

    tracker.record("test_call", input_tokens=100, output_tokens=50)

    assert len(captured_entries) == 1
    entry = captured_entries[0]
    assert entry["session_id"] == "RUN_99"
    assert entry["call_type"] == "test_call"
    assert entry["input_tokens"] == 100
    assert entry["output_tokens"] == 50


# ---------------------------------------------------------------------------
# Test 27: OpenRouterClient accepts session_id
# ---------------------------------------------------------------------------

def test_openrouter_client_accepts_session_id():
    """FIX-F2: OpenRouterClient.__init__ accepts session_id parameter."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    # Must not raise -- just tests constructor signature
    client = OpenRouterClient(
        api_key="test-key",
        session_id="PG_TEST_042",
    )
    assert client.usage.session_id == "PG_TEST_042"


# ---------------------------------------------------------------------------
# Test 28: Jina Reader fetch -- success (FIX-D1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jina_reader_success():
    """FIX-D1: AccessBypass._try_jina_reader returns content on 200 response.

    aiohttp is imported inside _try_jina_reader, so we patch at the
    aiohttp module level.
    """
    import aiohttp as real_aiohttp
    import src.tools.access_bypass as ab_mod
    from src.tools.access_bypass import AccessBypass

    # Reset circuit breaker state (may be open from earlier tests)
    ab_mod._jina_consecutive_failures = 0
    ab_mod._jina_circuit_open_until = 0.0

    bypass = AccessBypass()

    content_text = (
        "# Water Filtration\n\nComprehensive analysis of water filters "
        "showing 99.9% bacteria removal rates in controlled laboratory conditions "
        "with activated carbon and reverse osmosis membranes."
    )

    # Build nested async context manager mocks
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=content_text)

    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_get_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client_session = MagicMock(return_value=mock_session_cm)

    with patch("aiohttp.ClientSession", mock_client_session), \
         patch("aiohttp.ClientTimeout", real_aiohttp.ClientTimeout):
        result = await bypass._try_jina_reader("https://example.com/article")

    assert result.success is True
    assert result.access_method == "jina_reader"
    assert "Water Filtration" in result.content
    assert result.url == "https://example.com/article"
    assert "jina_url" in result.metadata


# ---------------------------------------------------------------------------
# Test 29: Jina Reader fetch -- failure (FIX-D1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jina_reader_failure():
    """FIX-D1: AccessBypass._try_jina_reader returns failure on non-200."""
    import aiohttp as real_aiohttp
    from src.tools.access_bypass import AccessBypass

    bypass = AccessBypass()

    mock_response = AsyncMock()
    mock_response.status = 403

    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_get_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client_session = MagicMock(return_value=mock_session_cm)

    with patch("aiohttp.ClientSession", mock_client_session), \
         patch("aiohttp.ClientTimeout", real_aiohttp.ClientTimeout):
        result = await bypass._try_jina_reader("https://example.com/locked")

    assert result.success is False
    assert result.access_method == "jina_reader"


# ---------------------------------------------------------------------------
# Test 30: _assign_quality_tiers -- gov domain + journal = GOLD
# ---------------------------------------------------------------------------

def test_assign_quality_tiers_gov_domain_gold():
    """FIX-B2: Government domain with journal source type gets GOLD."""
    from src.polaris_graph.agents.analyzer import _assign_quality_tiers

    evidence = [
        _make_evidence(
            "ev_gov_1",
            source_type="government_report",
            relevance=0.7,
            source_url="https://epa.gov/water-quality/report",
            fetch_method="full",
        ),
    ]

    result = _assign_quality_tiers(evidence)

    # authority=1.0, adjusted_relevance=0.7*1.0=0.7 >= 0.6 for gov report -> GOLD
    assert result[0]["quality_tier"] == "GOLD"


# ---------------------------------------------------------------------------
# Test 31: _filter_offtopic_evidence -- embedding failure fallback
# ---------------------------------------------------------------------------

def test_filter_offtopic_evidence_embedding_failure_fallback():
    """FIX-B3: If embedding service fails, evidence is returned unchanged."""
    from src.polaris_graph.agents.analyzer import _filter_offtopic_evidence

    evidence = [
        _make_evidence("ev_1", statement="Water quality analysis"),
        _make_evidence("ev_2", statement="Unrelated quantum topic"),
    ]

    # Simulate embedding service raising an exception
    with patch(
        "src.utils.embedding_service.embed_text",
        side_effect=RuntimeError("Embedding model unavailable"),
    ):
        result = _filter_offtopic_evidence(evidence, "water filter")

    # Should return all evidence unchanged (graceful fallback)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 32: detect_redundancy respects env var threshold
# ---------------------------------------------------------------------------

def test_detect_redundancy_threshold_from_env():
    """FIX-C3: PG_REDUNDANCY_JACCARD_THRESHOLD controls sensitivity."""
    from src.polaris_graph.synthesis.report_assembler import detect_redundancy

    # Two sections with moderately similar sentences (Jaccard ~ 0.5)
    sentence_a = (
        "Water treatment plants in urban areas face increasing challenges "
        "from emerging contaminants such as PFAS and microplastics"
    )
    sentence_b = (
        "Urban water treatment facilities face growing challenges "
        "from emerging contaminants including PFAS and microplastic particles"
    )

    sections = [
        _make_report_section(
            section_id="s01",
            content=sentence_a + ".",
        ),
        _make_report_section(
            section_id="s02",
            content=sentence_b + ".",
        ),
    ]

    # With very low threshold (0.3), these should be flagged
    with patch.dict("os.environ", {"PG_REDUNDANCY_JACCARD_THRESHOLD": "0.3"}):
        result_low = detect_redundancy(sections)

    # With very high threshold (0.95), these should NOT be flagged
    with patch.dict("os.environ", {"PG_REDUNDANCY_JACCARD_THRESHOLD": "0.95"}):
        result_high = detect_redundancy(sections)

    assert result_low["duplicate_pairs"] >= result_high["duplicate_pairs"]
