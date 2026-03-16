#!/usr/bin/env python3
"""
POLARIS Source Quality Scorer (SOTA: PaperQA2 RCS Map)
======================================================
Implements source quality scoring using Semantic Scholar API.

Based on PaperQA2 methodology:
- Citation count and influential citations
- Field-weighted citation impact
- Venue quality (journal prestige)
- Recency weighting
- Open access bonus

Also includes RCS Map step: contextual summarization for each chunk.

References:
- PaperQA2: https://arxiv.org/abs/2312.07559
- Semantic Scholar API: https://api.semanticscholar.org/api-docs

Usage:
    from src.utils.source_quality import SourceQualityScorer, score_source_quality

    scorer = SourceQualityScorer()
    quality = await scorer.get_paper_quality(doi="10.1234/example")
"""

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Import centralized blacklist module
try:
    from src.utils.url_blacklist import is_url_blacklisted
except ImportError:
    # Fallback if module not available (for standalone testing)
    is_url_blacklisted = None


@dataclass
class PaperQuality:
    """Quality metrics for an academic paper source."""
    # Identifiers
    doi: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    title: Optional[str] = None

    # Citation metrics
    citation_count: int = 0
    influential_citation_count: int = 0
    reference_count: int = 0

    # Field and venue
    fields_of_study: List[str] = field(default_factory=list)
    venue: Optional[str] = None
    venue_type: Optional[str] = None  # journal, conference, preprint

    # Temporal
    publication_year: Optional[int] = None

    # Access
    is_open_access: bool = False

    # Computed quality score (0.0 - 1.0)
    quality_score: float = 0.0

    # Metadata
    source_api: str = "unknown"
    fetched_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "doi": self.doi,
            "semantic_scholar_id": self.semantic_scholar_id,
            "title": self.title,
            "citation_count": self.citation_count,
            "influential_citation_count": self.influential_citation_count,
            "reference_count": self.reference_count,
            "fields_of_study": self.fields_of_study,
            "venue": self.venue,
            "venue_type": self.venue_type,
            "publication_year": self.publication_year,
            "is_open_access": self.is_open_access,
            "quality_score": self.quality_score,
            "source_api": self.source_api,
            "fetched_at": self.fetched_at,
        }


@dataclass
class ContextualSummary:
    """RCS Map output: relevance score + contextual summary for a chunk."""
    chunk_id: str
    relevance_score: float  # 0.0 - 1.0
    contextual_summary: str  # Brief summary of how this chunk relates to query
    key_claims: List[str] = field(default_factory=list)
    cited_entities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "relevance_score": self.relevance_score,
            "contextual_summary": self.contextual_summary,
            "key_claims": self.key_claims,
            "cited_entities": self.cited_entities,
        }


# =============================================================================
# DOMAIN QUALITY TIERS (SOTA: Source Hygiene)
# =============================================================================

# Tier 1: Highest quality academic/government sources
TIER1_DOMAINS = {
    # Government
    "cdc.gov", "epa.gov", "fda.gov", "nih.gov", "who.int", "europa.eu",
    "canada.ca", "gov.uk", "health.gov.au",
    # Academic
    "ncbi.nlm.nih.gov", "pubmed", "pmc.ncbi", "nature.com", "science.org",
    "sciencedirect.com", "springer.com", "wiley.com", "tandfonline.com",
    "cell.com", "thelancet.com", "bmj.com", "jama", "nejm.org",
    # Preprints (peer review pending)
    "arxiv.org", "biorxiv.org", "medrxiv.org",
}

# Tier 2: Professional/organizational sources
TIER2_DOMAINS = {
    "awwa.org",  # American Water Works Association
    "nsf.org",   # NSF International
    "waterrf.org",  # Water Research Foundation
    ".edu",      # Educational institutions
    ".org",      # Non-profits (general)
}

# Tier 3: News/media (lower quality for research)
TIER3_DOMAINS = {
    "reuters.com", "bbc.com", "nytimes.com", "washingtonpost.com",
    "theguardian.com", "forbes.com", "bloomberg.com",
}

# Blacklisted: Commercial/vendor/spam (quality = 0)
BLACKLIST_DOMAINS = {
    # Market research spam
    "grandviewresearch", "mordorintelligence", "researchnester",
    "marketresearch", "statista", "polarismarketresearch",
    # E-commerce
    "amazon.com", "alibaba", "ebay", "walmart", "homedepot",
    # Social media
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "tiktok.com", "reddit.com", "quora.com", "pinterest.com",
    # SEO spam
    "medium.com/", "blog.", "/blog/",
}


def get_domain_tier(url: str) -> Tuple[int, float]:
    """
    Get domain quality tier and base score.

    Returns:
        Tuple of (tier_number, base_quality_score)
        - Tier 1: 0.9 base score (academic/government)
        - Tier 2: 0.7 base score (professional/educational)
        - Tier 3: 0.50 base score (news/media) [FIX-148: raised from 0.4]
        - Tier 4: 0.35 base score (generic .com) [FIX-148: raised from 0.2]
        - Blacklist: 0.0 (rejected)
    """
    if not url:
        return 4, 0.35  # FIX-148: raised from 0.2

    url_lower = url.lower()

    # Check centralized blacklist first (if available)
    if is_url_blacklisted is not None:
        is_blacklisted, _ = is_url_blacklisted(url, include_news=False)
        if is_blacklisted:
            return 0, 0.0

    # Fallback: Check local blacklist
    for pattern in BLACKLIST_DOMAINS:
        if pattern in url_lower:
            return 0, 0.0

    # Check tier 1
    for domain in TIER1_DOMAINS:
        if domain in url_lower:
            return 1, 0.9

    # Check tier 2
    for domain in TIER2_DOMAINS:
        if domain in url_lower:
            return 2, 0.7

    # Check tier 3
    for domain in TIER3_DOMAINS:
        if domain in url_lower:
            return 3, 0.50  # FIX-148: raised from 0.4

    # Default: generic .com or unknown
    # FIX-148: Tier 4 raised from 0.2 to 0.35 to prevent "Impossible Silver"
    # (old math: even perfect relevance 1.0 + 0.2 source / 2 = 0.60 < 0.65 SILVER)
    if ".com" in url_lower:
        return 4, 0.35

    return 4, 0.35  # FIX-148: aligned unknown TLD with Tier 4 (was 0.3)


# =============================================================================
# SEMANTIC SCHOLAR API CLIENT
# =============================================================================

class SourceQualityScorer:
    """
    SOTA source quality scorer using Semantic Scholar API.

    Implements PaperQA2-style source quality assessment:
    1. Fetch paper metadata from Semantic Scholar
    2. Compute citation-based quality score
    3. Apply venue weighting
    4. Apply recency weighting
    5. Combine with domain tier
    """

    # Semantic Scholar API base
    S2_API_BASE = "https://api.semanticscholar.org/graph/v1"

    # Rate limiting (1 req/sec for free tier)
    RATE_LIMIT = 1.0

    # Cache TTL (24 hours)
    CACHE_TTL = 86400

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize scorer.

        Args:
            api_key: Semantic Scholar API key (optional, increases rate limit)
        """
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        self._last_request_time = 0.0
        self._cache: Dict[str, Tuple[PaperQuality, float]] = {}  # key -> (quality, timestamp)

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT:
            await asyncio.sleep(self.RATE_LIMIT - elapsed)
        self._last_request_time = time.time()

    def _get_from_cache(self, key: str) -> Optional[PaperQuality]:
        """Get cached result if not expired."""
        if key in self._cache:
            quality, timestamp = self._cache[key]
            if time.time() - timestamp < self.CACHE_TTL:
                return quality
            else:
                del self._cache[key]
        return None

    def _add_to_cache(self, key: str, quality: PaperQuality) -> None:
        """Add result to cache."""
        self._cache[key] = (quality, time.time())

    async def get_paper_quality(
        self,
        doi: Optional[str] = None,
        url: Optional[str] = None,
        title: Optional[str] = None,
    ) -> PaperQuality:
        """
        Get quality metrics for a paper.

        Tries multiple identification methods:
        1. DOI lookup
        2. URL-based DOI extraction
        3. Title search

        Args:
            doi: Digital Object Identifier
            url: Source URL (may contain DOI)
            title: Paper title for search fallback

        Returns:
            PaperQuality with computed quality_score
        """
        # Try to extract DOI from URL if not provided
        if not doi and url:
            doi = self._extract_doi(url)

        # Check cache
        cache_key = doi or url or title or ""
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        quality = PaperQuality()
        quality.doi = doi
        quality.fetched_at = datetime.now(UTC).isoformat()

        # Try Semantic Scholar API
        if doi:
            s2_quality = await self._fetch_semantic_scholar(doi)
            if s2_quality:
                quality = s2_quality

        # If no S2 data, use domain-based scoring
        if quality.quality_score == 0.0 and url:
            tier, base_score = get_domain_tier(url)
            quality.quality_score = base_score
            quality.source_api = "domain_tier"

        # Compute final quality score
        quality.quality_score = self._compute_quality_score(quality, url)

        # Cache result
        self._add_to_cache(cache_key, quality)

        return quality

    async def _fetch_semantic_scholar(self, doi: str) -> Optional[PaperQuality]:
        """
        Fetch paper data from Semantic Scholar API.

        Fields requested:
        - title, authors, year, venue
        - citationCount, influentialCitationCount, referenceCount
        - fieldsOfStudy, isOpenAccess, openAccessPdf
        """
        await self._rate_limit()

        # Construct API URL
        paper_id = f"DOI:{doi}"
        fields = "title,year,venue,citationCount,influentialCitationCount,referenceCount,fieldsOfStudy,isOpenAccess,externalIds"
        url = f"{self.S2_API_BASE}/paper/{quote(paper_id, safe='')}?fields={fields}"

        headers = {"User-Agent": "POLARIS/1.0 Research System"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=30) as resp:
                    if resp.status == 404:
                        # Paper not found in S2
                        return None
                    if resp.status == 429:
                        # Rate limited
                        # LOW-019: Log error instead of print
                        logger.debug("Semantic Scholar rate limited")
                        return None
                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    quality = PaperQuality(
                        doi=doi,
                        semantic_scholar_id=data.get("paperId"),
                        title=data.get("title"),
                        citation_count=data.get("citationCount", 0) or 0,
                        influential_citation_count=data.get("influentialCitationCount", 0) or 0,
                        reference_count=data.get("referenceCount", 0) or 0,
                        venue=data.get("venue"),
                        publication_year=data.get("year"),
                        is_open_access=data.get("isOpenAccess", False),
                        source_api="semantic_scholar",
                        fetched_at=datetime.now(UTC).isoformat(),
                    )

                    # Extract fields of study
                    fos = data.get("fieldsOfStudy") or []
                    quality.fields_of_study = fos

                    # Determine venue type
                    venue = data.get("venue", "") or ""
                    venue_lower = venue.lower()
                    if "arxiv" in venue_lower or "preprint" in venue_lower:
                        quality.venue_type = "preprint"
                    elif "conference" in venue_lower or "proceedings" in venue_lower:
                        quality.venue_type = "conference"
                    elif venue:
                        quality.venue_type = "journal"

                    return quality

        except asyncio.TimeoutError:
            # LOW-020: Log error instead of print
            logger.debug(f"Semantic Scholar timeout for {doi}")
            return None
        except aiohttp.ClientError as e:
            # LOW-021: Log error instead of print
            logger.debug(f"Semantic Scholar error: {e}")
            return None
        except Exception as e:
            # LOW-022: Log error instead of print
            logger.debug(f"Source quality unexpected error: {e}")
            return None

    def _extract_doi(self, url: str) -> Optional[str]:
        """Extract DOI from URL."""
        # Standard DOI pattern
        match = re.search(r'(10\.\d{4,}/[^\s\]"\'<>]+)', url)
        if match:
            return match.group(1).rstrip('.')
        return None

    def _compute_quality_score(
        self,
        quality: PaperQuality,
        url: Optional[str] = None,
    ) -> float:
        """
        Compute final quality score (0.0 - 1.0).

        Scoring components (SOTA aligned with PaperQA2):
        1. Citation impact (40%): Log-scaled citations + influential weighting
        2. Venue quality (20%): Journal > Conference > Preprint
        3. Recency (15%): Newer papers get slight boost
        4. Domain tier (15%): Government/academic boost
        5. Open access (10%): Small bonus for OA
        """
        score = 0.0

        # 1. Citation impact (40%)
        # Use log scale to prevent highly-cited papers from dominating
        # Formula: min(1.0, log10(citations + 1) / 3) * 0.4
        # This gives: 0 citations = 0, 10 = 0.13, 100 = 0.27, 1000 = 0.4
        if quality.citation_count > 0:
            citation_score = min(1.0, (quality.citation_count ** 0.5) / 50)

            # Influential citation bonus (up to 20% boost)
            if quality.influential_citation_count > 0:
                influential_ratio = quality.influential_citation_count / max(quality.citation_count, 1)
                citation_score *= (1 + influential_ratio * 0.2)

            score += citation_score * 0.4

        # 2. Venue quality (20%)
        venue_score = 0.5  # Default for unknown venue
        if quality.venue_type == "journal":
            venue_score = 1.0
        elif quality.venue_type == "conference":
            venue_score = 0.8
        elif quality.venue_type == "preprint":
            venue_score = 0.4
        score += venue_score * 0.2

        # 3. Recency (15%)
        if quality.publication_year:
            current_year = datetime.now().year
            age = current_year - quality.publication_year
            # Papers from last 5 years get full score, older papers decay
            recency_score = max(0.0, 1.0 - (age / 20))  # 20 year decay
            score += recency_score * 0.15
        else:
            score += 0.5 * 0.15  # Unknown year gets middle score

        # 4. Domain tier (15%)
        if url:
            tier, domain_score = get_domain_tier(url)
            if tier == 0:  # Blacklisted
                return 0.0  # Override everything
            score += domain_score * 0.15
        else:
            score += 0.5 * 0.15  # Unknown domain gets middle score

        # 5. Open access bonus (10%)
        if quality.is_open_access:
            score += 0.10
        else:
            score += 0.05  # Non-OA gets partial score

        return min(1.0, max(0.0, score))


# =============================================================================
# BATCH SCORING
# =============================================================================

async def score_sources_batch(
    sources: List[Dict[str, Any]],
    scorer: Optional[SourceQualityScorer] = None,
    max_concurrent: int = 5,
) -> List[Dict[str, Any]]:
    """
    Score multiple sources in batch.

    Args:
        sources: List of dicts with 'url', 'doi', or 'title' keys
        scorer: Optional pre-initialized scorer
        max_concurrent: Max concurrent API calls

    Returns:
        Sources with added 'quality_score' and 'quality_data' fields
    """
    if scorer is None:
        scorer = SourceQualityScorer()

    semaphore = asyncio.Semaphore(max_concurrent)

    async def score_one(source: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            quality = await scorer.get_paper_quality(
                doi=source.get("doi"),
                url=source.get("url") or source.get("source_url"),
                title=source.get("title"),
            )
            source["quality_score"] = quality.quality_score
            source["quality_data"] = quality.to_dict()
            return source

    tasks = [score_one(s) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions
    scored_sources = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # LOW-023: Log error instead of print
            logger.debug(f"Source quality scoring failed for source {i}: {result}")
            sources[i]["quality_score"] = 0.0
            sources[i]["quality_data"] = {}
            scored_sources.append(sources[i])
        else:
            scored_sources.append(result)

    return scored_sources


# =============================================================================
# RCS MAP: CONTEXTUAL SUMMARIZATION
# =============================================================================

async def generate_contextual_summary(
    chunk_text: str,
    query: str,
    chunk_id: str,
    llm_client: Any = None,
) -> ContextualSummary:
    """
    RCS Map step: Generate contextual summary for a chunk.

    This implements the PaperQA2 "Map" step where each chunk is:
    1. Scored for relevance to the query
    2. Summarized in context of the query
    3. Key claims extracted

    Args:
        chunk_text: The chunk content
        query: Research question
        chunk_id: Chunk identifier
        llm_client: Optional LLM client for summarization

    Returns:
        ContextualSummary with relevance score and summary
    """
    # If no LLM client, use simple extractive approach
    if llm_client is None:
        return _extractive_contextual_summary(chunk_text, query, chunk_id)

    # LLM-based contextual summarization
    prompt = f"""Given this research question and text chunk, provide:
1. A relevance score (0.0-1.0) for how relevant the chunk is to answering the question
2. A 1-2 sentence summary of what this chunk contributes to answering the question
3. Key factual claims from the chunk (up to 3)

Research Question: {query}

Text Chunk:
{chunk_text[:1500]}

Respond in JSON format:
{{
    "relevance_score": 0.X,
    "summary": "...",
    "key_claims": ["claim1", "claim2", ...]
}}"""

    try:
        response = await llm_client.generate(prompt)

        # Parse JSON response
        import json
        # Find JSON in response
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return ContextualSummary(
                chunk_id=chunk_id,
                relevance_score=float(data.get("relevance_score", 0.5)),
                contextual_summary=data.get("summary", ""),
                key_claims=data.get("key_claims", []),
            )
    except Exception as e:
        # LOW-024: Log error instead of print
        logger.debug(f"RCS-MAP LLM summarization failed: {e}")

    # Fallback to extractive
    return _extractive_contextual_summary(chunk_text, query, chunk_id)


def _extractive_contextual_summary(
    chunk_text: str,
    query: str,
    chunk_id: str,
) -> ContextualSummary:
    """
    Simple extractive contextual summary without LLM.

    Uses keyword overlap and sentence extraction.
    """
    # Extract query keywords (simple approach)
    stop_words = {"what", "where", "when", "which", "who", "how", "why", "is", "are", "the", "a", "an", "in", "on", "for", "of", "and", "or", "to"}
    query_words = set(re.findall(r'\b[a-z]{3,}\b', query.lower())) - stop_words

    # Calculate simple relevance score based on keyword overlap
    chunk_lower = chunk_text.lower()
    matches = sum(1 for w in query_words if w in chunk_lower)
    relevance_score = min(1.0, matches / max(len(query_words), 1))

    # Extract first substantive sentence as summary
    sentences = re.split(r'(?<=[.!?])\s+', chunk_text)
    summary = ""
    for sent in sentences:
        if len(sent) > 50 and any(w in sent.lower() for w in query_words):
            summary = sent[:200]
            break

    if not summary and sentences:
        summary = sentences[0][:200]

    # Extract potential claims (sentences with data/numbers)
    key_claims = []
    for sent in sentences:
        if re.search(r'\d+%|\d+\s*(mg|μg|ppm|cfu|log)', sent, re.IGNORECASE):
            if len(sent) > 30 and len(sent) < 300:
                key_claims.append(sent)
                if len(key_claims) >= 3:
                    break

    return ContextualSummary(
        chunk_id=chunk_id,
        relevance_score=relevance_score,
        contextual_summary=summary,
        key_claims=key_claims,
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def score_source_quality_sync(
    url: Optional[str] = None,
    doi: Optional[str] = None,
) -> float:
    """
    Synchronous wrapper for quick quality scoring.

    Uses domain-based scoring only (no API call).

    Args:
        url: Source URL
        doi: DOI (for future use)

    Returns:
        Quality score (0.0 - 1.0)
    """
    if url:
        tier, score = get_domain_tier(url)
        return score
    return 0.3  # Unknown


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("SOURCE QUALITY SCORER SELF-TEST")
        print("=" * 60)

        scorer = SourceQualityScorer()

        # Test 1: Domain tier scoring
        print("\n[TEST 1] Domain Tier Scoring")
        test_urls = [
            ("https://pubmed.ncbi.nlm.nih.gov/12345/", "Tier 1 - Academic"),
            ("https://www.cdc.gov/water/quality.html", "Tier 1 - Government"),
            ("https://www.awwa.org/research", "Tier 2 - Professional"),
            ("https://www.nytimes.com/health", "Tier 3 - News"),
            ("https://randomfilters.com/product", "Tier 4 - Commercial"),
            ("https://www.grandviewresearch.com/market", "Blacklist - Market spam"),
        ]

        for url, expected in test_urls:
            tier, score = get_domain_tier(url)
            print(f"  {expected:30} -> Tier {tier}, Score {score:.2f}")

        # Test 2: Semantic Scholar API (if key available)
        if os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
            print("\n[TEST 2] Semantic Scholar API")
            test_doi = "10.1016/j.watres.2019.115111"
            quality = await scorer.get_paper_quality(doi=test_doi)
            print(f"  DOI: {test_doi}")
            print(f"  Title: {quality.title}")
            print(f"  Citations: {quality.citation_count}")
            print(f"  Quality Score: {quality.quality_score:.3f}")
        else:
            print("\n[TEST 2] Skipped - No S2 API key")

        # Test 3: Extractive contextual summary
        print("\n[TEST 3] Extractive Contextual Summary")
        test_chunk = """
        Studies have shown that household water filters can reduce E. coli
        contamination by 99.9% when properly maintained. However, biofilm
        formation after 30 days of use can reduce effectiveness by 50%.
        Regular replacement of filter cartridges is essential for
        maintaining water quality standards.
        """
        test_query = "What pathogen contamination rates exist in household water filters?"

        summary = _extractive_contextual_summary(test_chunk, test_query, "test_001")
        print(f"  Relevance Score: {summary.relevance_score:.2f}")
        print(f"  Summary: {summary.contextual_summary[:100]}...")
        print(f"  Key Claims: {len(summary.key_claims)}")

        print("\n" + "=" * 60)
        print("SELF-TEST COMPLETE")
        print("=" * 60)

    asyncio.run(test())
