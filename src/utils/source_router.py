#!/usr/bin/env python3
"""
POLARIS Source Router and RRF Fusion
====================================
Sprint 6: SOTA Architecture - Multi-Source Retrieval

Routes queries to domain-appropriate sources and fuses results
using Reciprocal Rank Fusion (RRF).

Reference: RAGRouter, FinSage, RRF
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.question_types import QuestionType, SourceType


# =============================================================================
# SOURCE PROFILES
# =============================================================================

@dataclass
class SourceProfile:
    """Profile for a retrieval source."""
    source_type: SourceType
    name: str
    description: str

    # Domain patterns (for site-restricted search)
    domain_patterns: List[str] = field(default_factory=list)

    # Quality scoring
    authority_score: float = 0.5  # 0.0-1.0 base authority
    recency_weight: float = 0.5  # How much recency matters

    # API endpoints (if applicable)
    api_endpoint: Optional[str] = None
    requires_api_key: bool = False


# Default source profiles
SOURCE_PROFILES: Dict[SourceType, SourceProfile] = {
    SourceType.ACADEMIC: SourceProfile(
        source_type=SourceType.ACADEMIC,
        name="Academic Sources",
        description="Peer-reviewed journals and research papers",
        domain_patterns=[
            "pmc.ncbi.nlm.nih.gov",
            "pubmed.ncbi.nlm.nih.gov",
            "scholar.google.com",
            "nature.com",
            "sciencedirect.com",
            "springer.com",
            "wiley.com",
        ],
        authority_score=0.9,
        recency_weight=0.3,
        api_endpoint="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        requires_api_key=False,
    ),
    SourceType.GOVERNMENT: SourceProfile(
        source_type=SourceType.GOVERNMENT,
        name="Government Sources",
        description="Official government agencies and reports",
        domain_patterns=[
            "cdc.gov",
            "epa.gov",
            "fda.gov",
            "nih.gov",
            "who.int",
            "canada.ca",
            "gov.uk",
            "europa.eu",
        ],
        authority_score=0.85,
        recency_weight=0.4,
    ),
    SourceType.EDUCATIONAL: SourceProfile(
        source_type=SourceType.EDUCATIONAL,
        name="Educational Sources",
        description="Universities and educational institutions",
        domain_patterns=[
            "*.edu",
            "*.ac.uk",
            "university",
            "college",
        ],
        authority_score=0.75,
        recency_weight=0.4,
    ),
    SourceType.INDUSTRY: SourceProfile(
        source_type=SourceType.INDUSTRY,
        name="Industry Sources",
        description="Industry reports and business sources",
        domain_patterns=[
            "statista.com",
            "grandviewresearch.com",
            "marketsandmarkets.com",
            "ibisworld.com",
        ],
        authority_score=0.6,
        recency_weight=0.7,
    ),
    SourceType.NEWS: SourceProfile(
        source_type=SourceType.NEWS,
        name="News Sources",
        description="News outlets and journalism",
        domain_patterns=[
            "reuters.com",
            "bbc.com",
            "nytimes.com",
            "washingtonpost.com",
        ],
        authority_score=0.5,
        recency_weight=0.9,
    ),
    SourceType.GENERAL_WEB: SourceProfile(
        source_type=SourceType.GENERAL_WEB,
        name="General Web",
        description="General web sources",
        domain_patterns=[],
        authority_score=0.3,
        recency_weight=0.5,
    ),
}


# =============================================================================
# SOURCE ROUTING
# =============================================================================

def get_source_priorities(question_type: QuestionType) -> List[SourceType]:
    """
    Get source types in priority order for a question type.

    Args:
        question_type: The classified question type

    Returns:
        List of SourceTypes in priority order
    """
    priorities = {
        QuestionType.QUANTITATIVE_RESEARCH: [
            SourceType.ACADEMIC,
            SourceType.GOVERNMENT,
            SourceType.EDUCATIONAL,
        ],
        QuestionType.MARKET_ANALYSIS: [
            SourceType.INDUSTRY,
            SourceType.NEWS,
            SourceType.GENERAL_WEB,
        ],
        QuestionType.REGULATORY_COMPLIANCE: [
            SourceType.GOVERNMENT,
            SourceType.ACADEMIC,
            SourceType.EDUCATIONAL,
        ],
        QuestionType.PRODUCT_COMPARISON: [
            SourceType.INDUSTRY,
            SourceType.ACADEMIC,
            SourceType.NEWS,
        ],
        QuestionType.QUALITATIVE_RESEARCH: [
            SourceType.ACADEMIC,
            SourceType.NEWS,
            SourceType.EDUCATIONAL,
        ],
        QuestionType.TECHNICAL_SPECIFICATION: [
            SourceType.ACADEMIC,
            SourceType.INDUSTRY,
            SourceType.GOVERNMENT,
        ],
    }
    return priorities.get(question_type, [SourceType.ACADEMIC, SourceType.GENERAL_WEB])


def route_query_to_sources(
    query: str,
    question_type: QuestionType,
    max_sources: int = 3,
) -> List[Tuple[str, SourceProfile]]:
    """
    Route a query to appropriate sources.

    Args:
        query: The search query
        question_type: Question type for source selection
        max_sources: Maximum number of sources to use

    Returns:
        List of (modified_query, SourceProfile) tuples
    """
    priorities = get_source_priorities(question_type)
    routed = []

    for source_type in priorities[:max_sources]:
        profile = SOURCE_PROFILES.get(source_type, SOURCE_PROFILES[SourceType.GENERAL_WEB])

        # Generate site-restricted query if domains available
        if profile.domain_patterns:
            # Use first domain for site restriction
            site = profile.domain_patterns[0]
            if not site.startswith('*'):
                modified_query = f"{query} site:{site}"
            else:
                modified_query = query
        else:
            modified_query = query

        routed.append((modified_query, profile))

    return routed


def get_domain_authority(url: str) -> float:
    """
    Get authority score for a URL based on domain.

    Args:
        url: URL to score

    Returns:
        Authority score (0.0-1.0)
    """
    url_lower = url.lower()

    # Check each source profile
    for source_type, profile in SOURCE_PROFILES.items():
        for pattern in profile.domain_patterns:
            if pattern.startswith('*'):
                # Wildcard pattern (e.g., *.edu)
                suffix = pattern[1:]
                if suffix in url_lower:
                    return profile.authority_score
            elif pattern in url_lower:
                return profile.authority_score

    return SOURCE_PROFILES[SourceType.GENERAL_WEB].authority_score


# =============================================================================
# RECIPROCAL RANK FUSION (RRF)
# =============================================================================

@dataclass
class SearchResult:
    """A single search result."""
    url: str
    title: str
    snippet: str
    rank: int = 0  # Rank in original result list
    source_type: SourceType = SourceType.GENERAL_WEB
    authority_score: float = 0.5
    rrf_score: float = 0.0


def reciprocal_rank_fusion(
    result_lists: List[List[SearchResult]],
    k: int = 60,
) -> List[SearchResult]:
    """
    Fuse multiple ranked lists using Reciprocal Rank Fusion.

    RRF Formula: score(d) = sum(1 / (k + rank(d)))

    Args:
        result_lists: List of ranked result lists from different sources
        k: RRF constant (default 60)

    Returns:
        Fused and re-ranked list of results
    """
    # Calculate RRF scores
    url_scores: Dict[str, Tuple[float, SearchResult]] = {}

    for result_list in result_lists:
        for result in result_list:
            # RRF contribution from this list
            rrf_contribution = 1.0 / (k + result.rank)

            # Add authority boost
            authority_boost = result.authority_score * 0.1

            total_score = rrf_contribution + authority_boost

            if result.url in url_scores:
                # Accumulate scores for same URL across lists
                current_score, _ = url_scores[result.url]
                url_scores[result.url] = (current_score + total_score, result)
            else:
                url_scores[result.url] = (total_score, result)

    # Sort by RRF score
    sorted_results = sorted(
        url_scores.items(),
        key=lambda x: x[1][0],
        reverse=True,
    )

    # Build final list
    fused = []
    for rank, (url, (score, result)) in enumerate(sorted_results, 1):
        result.rrf_score = score
        result.rank = rank
        fused.append(result)

    return fused


def fuse_search_results(
    results_by_source: Dict[SourceType, List[dict]],
    k: int = 60,
) -> List[SearchResult]:
    """
    Fuse search results from multiple sources.

    Args:
        results_by_source: Dict mapping source type to list of result dicts
        k: RRF constant

    Returns:
        Fused list of SearchResult objects
    """
    result_lists = []

    for source_type, results in results_by_source.items():
        profile = SOURCE_PROFILES.get(source_type, SOURCE_PROFILES[SourceType.GENERAL_WEB])

        typed_results = []
        for rank, result in enumerate(results, 1):
            typed_results.append(SearchResult(
                url=result.get('url', ''),
                title=result.get('title', ''),
                snippet=result.get('snippet', ''),
                rank=rank,
                source_type=source_type,
                authority_score=profile.authority_score,
            ))

        result_lists.append(typed_results)

    return reciprocal_rank_fusion(result_lists, k)


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SOURCE ROUTER & RRF SELF-TEST")
    print("=" * 60)

    # Test 1: Source priorities
    print("\n[TEST 1] Source priorities...")
    priorities = get_source_priorities(QuestionType.QUANTITATIVE_RESEARCH)
    assert SourceType.ACADEMIC in priorities
    assert priorities[0] == SourceType.ACADEMIC
    print(f"  [PASS] Quantitative research priorities: {[p.value for p in priorities]}")

    # Test 2: Query routing
    print("\n[TEST 2] Query routing...")
    routed = route_query_to_sources(
        "water contamination rate",
        QuestionType.QUANTITATIVE_RESEARCH,
        max_sources=3,
    )
    assert len(routed) == 3
    assert "site:" in routed[0][0]  # First query should have site restriction
    print(f"  [PASS] Routed to {len(routed)} sources")
    for query, profile in routed:
        print(f"    - {profile.name}: {query[:50]}...")

    # Test 3: Domain authority
    print("\n[TEST 3] Domain authority...")
    auth1 = get_domain_authority("https://pmc.ncbi.nlm.nih.gov/articles/123/")
    auth2 = get_domain_authority("https://randomsite.com/page")
    assert auth1 > auth2
    print(f"  [PASS] PMC authority ({auth1}) > random ({auth2})")

    # Test 4: RRF fusion
    print("\n[TEST 4] RRF fusion...")
    list1 = [
        SearchResult(url="http://a.com", title="A", snippet="", rank=1, authority_score=0.9),
        SearchResult(url="http://b.com", title="B", snippet="", rank=2, authority_score=0.9),
        SearchResult(url="http://c.com", title="C", snippet="", rank=3, authority_score=0.9),
    ]
    list2 = [
        SearchResult(url="http://b.com", title="B", snippet="", rank=1, authority_score=0.5),
        SearchResult(url="http://d.com", title="D", snippet="", rank=2, authority_score=0.5),
        SearchResult(url="http://a.com", title="A", snippet="", rank=3, authority_score=0.5),
    ]
    fused = reciprocal_rank_fusion([list1, list2])
    # B should rank highest (rank 2 + rank 1 = best combined)
    assert fused[0].url == "http://b.com" or fused[0].url == "http://a.com"
    print(f"  [PASS] Fused {len(fused)} results, top: {fused[0].url}")

    # Test 5: Source result fusion
    print("\n[TEST 5] Source result fusion...")
    by_source = {
        SourceType.ACADEMIC: [
            {"url": "http://pubmed.com/1", "title": "Study 1", "snippet": ""},
            {"url": "http://pubmed.com/2", "title": "Study 2", "snippet": ""},
        ],
        SourceType.GOVERNMENT: [
            {"url": "http://cdc.gov/1", "title": "CDC Report", "snippet": ""},
            {"url": "http://pubmed.com/1", "title": "Study 1", "snippet": ""},  # Duplicate
        ],
    }
    fused2 = fuse_search_results(by_source)
    assert len(fused2) == 3  # 4 results, 1 duplicate
    print(f"  [PASS] Fused to {len(fused2)} unique results")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
