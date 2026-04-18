#!/usr/bin/env python3
"""
POLARIS Phase 4: Relevance Filtering
=====================================
Fetch content, chunk, and filter by relevance.

Purpose:
- Fetch content from URLs found in Phase 3
- Chunk content into manageable pieces
- Apply two-stage relevance filtering (embedding + cross-encoder)
- Output filtered chunks with relevance tiers

Usage:
    python src/phases/p04_relevance_filter.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --input outputs/P3/S1V1...json --output outputs/P4/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --input: Required. Path to Phase 3 output JSON.
    --output: Optional. Output directory (default: outputs/P4/)
    --self-test: Run self-test mode
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase3Output, Phase4Output, SearchResult, RelevanceTier
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.utils.ingest import ContentFetcher, get_fetcher, clean_html, extract_title_from_url, is_garbage_content, extract_metadata_from_html
from src.utils.academic_fetcher import AcademicFetcher, classify_url, extract_doi_from_url
from src.utils.semantic_chunking import SemanticChunker, get_chunker_for_stage
from src.utils.source_quality import (
    SourceQualityScorer,
    get_domain_tier,
    score_source_quality_sync,
    _extractive_contextual_summary,
)
from src.utils.url_blacklist import (
    is_url_blacklisted,
    is_content_seo_spam,
    SEO_CONTENT_BLACKLIST,
)
from src.utils.geographic_tagger import (
    tag_content_geography,
    extract_region_from_vector_id,
)
from src.audit import get_audit


# =============================================================================
# CONTENT FETCHING
# =============================================================================

@dataclass
class FetchResult:
    """Result of fetching a URL with metadata."""
    content: str
    status: int
    method: str
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    # SOTA: Source-level geographic metadata from API
    author_countries: Optional[List[str]] = None
    citation_count: Optional[int] = None


# SOTA: Region codes for source-level geographic filtering
REGION_COUNTRY_MAP = {
    "NORTH_AMERICA": {"US", "CA", "MX"},
    "EUROPE": {"GB", "DE", "FR", "IT", "ES", "NL", "BE", "SE", "NO", "DK", "FI", "AT", "CH", "IE", "PT", "PL", "CZ", "GR", "HU", "RO"},
    "ASIA_PACIFIC": {"CN", "JP", "KR", "IN", "AU", "NZ", "SG", "MY", "TH", "ID", "PH", "VN", "TW", "HK"},
}


def derive_geo_region_from_countries(
    author_countries: Optional[List[str]],
    target_region: str,
) -> Tuple[str, float]:
    """
    SOTA: Derive geographic region and confidence from author country codes.

    This enables source-level geographic filtering using API metadata (OpenAlex)
    instead of text pattern matching.

    Args:
        author_countries: ISO 3166-1 alpha-2 country codes from author affiliations
        target_region: Target region from vector_id (e.g., "NORTH_AMERICA")

    Returns:
        Tuple of (geo_region, geo_confidence)
        - geo_region: Detected region or "GLOBAL"
        - geo_confidence: 0.0-1.0 based on how many authors are from the region
    """
    if not author_countries:
        return "GLOBAL", 0.0

    # Count authors by region
    region_counts = {region: 0 for region in REGION_COUNTRY_MAP.keys()}
    region_counts["OTHER"] = 0

    for country in author_countries:
        country_upper = country.upper()
        found = False
        for region, countries in REGION_COUNTRY_MAP.items():
            if country_upper in countries:
                region_counts[region] += 1
                found = True
                break
        if not found:
            region_counts["OTHER"] += 1

    # Determine dominant region
    total = len(author_countries)
    max_count = 0
    dominant_region = "GLOBAL"

    for region, count in region_counts.items():
        if region != "OTHER" and count > max_count:
            max_count = count
            dominant_region = region

    # Compute confidence
    if total == 0:
        return "GLOBAL", 0.0

    confidence = max_count / total

    # If majority is from target region, high confidence
    target_count = region_counts.get(target_region, 0)
    if target_count > total * 0.5:
        return target_region, confidence

    # If majority is from a different specific region, use that
    if dominant_region != "GLOBAL" and max_count > total * 0.5:
        return dominant_region, confidence

    # Mixed or global
    return "GLOBAL", 0.3


def _format_authors(authors: Optional[List[str]]) -> str:
    """
    Format author list for citation.

    Args:
        authors: List of author names

    Returns:
        Formatted author string (e.g., "Smith et al." or "Smith, Jones")
    """
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    elif len(authors) == 2:
        return f"{authors[0]}, {authors[1]}"
    else:
        return f"{authors[0]} et al."


def _is_garbage_title(title: str) -> bool:
    """
    Check if a title is garbage/placeholder and should be rejected.

    FIX: Prevents bad titles like "References", "Author contributions", PMC IDs,
    domain fallbacks, and truncated citation metadata.

    Args:
        title: Title string to check

    Returns:
        True if title is garbage
    """
    if not title:
        return True

    title_lower = title.lower().strip()

    # Exact garbage titles
    garbage_exact = [
        "references",
        "author contributions",
        "authors contributions",
        "author contribution",
        "acknowledgements",
        "acknowledgments",
        "conflicts of interest",
        "conflict of interest",
        "funding",
        "supplementary material",
        "supplementary data",
        "supporting information",
        "data availability",
        "ethics statement",
        "competing interests",
        "untitled",
        "unknown",
        "bibliography",
        "methods",
        "materials and methods",
        "introduction",
        "conclusion",
        "conclusions",
        "discussion",
        "results",
        "abstract",
        "",
    ]
    if title_lower in garbage_exact:
        return True

    # Garbage patterns
    garbage_patterns = [
        r"^pmc\d+$",  # PMC IDs like "Pmc7159610"
        r"^pmid\s*\d+$",  # PMID references
        r"^\d+\.\s*[a-z]+\s+j\s+",  # Citation text like "1. Eur J Clin..."
        r"^\d+\.\s+[a-z].*\d{4}.*doi",  # Truncated citation metadata with doi
        r"^table\s*\d+",  # Table titles
        r"^figure\s*\d+",  # Figure titles
        r"^fig\.\s*\d+",  # Abbreviated figure
        r"^s\d+\s+",  # Supplementary item numbers
        r"^\d{8}[_\s]",  # Filename patterns like "20190805_2017grant" or "20190805 2017grant"
        r"^article from ",  # Domain fallback titles like "Article from pmc.ncbi.nlm.nih.gov"
        r"executivesummary$",  # Filename patterns
        r"^\d+\s+health\s+effects",  # Chapter titles like "2 Health Effects Assessment"
    ]
    for pattern in garbage_patterns:
        if re.match(pattern, title_lower):
            return True

    # Check for domain-based fallback titles
    domain_indicators = [
        "pmc.ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov",
        "doi.org",
        ".gov/",
        ".edu/",
    ]
    for indicator in domain_indicators:
        if indicator in title_lower:
            return True

    # Too short
    if len(title) < 10:
        return True

    # Mostly numbers/symbols
    alpha_count = sum(1 for c in title if c.isalpha())
    if alpha_count < len(title) * 0.5:
        return True

    # Contains truncated citation metadata indicators
    if title_lower.endswith("doi:") or title_lower.endswith("doi"):
        return True

    return False


def format_citation_title(
    title: Optional[str],
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    url: Optional[str] = None,
) -> str:
    """
    Format a proper citation-style title.

    Examples:
        "Smith et al. (2023). Water Filter Contamination Study"
        "CDC. Drinking Water Guidelines"
    """
    if not title:
        if url:
            return extract_title_from_url(url)
        return "Untitled"

    # Clean up title
    title = title.strip()
    title = re.sub(r'\s+', ' ', title)

    # Format with authors and year if available
    if authors and len(authors) > 0:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} & {authors[1]}"
        else:
            author_str = f"{authors[0]} et al."

        if year:
            return f"{author_str} ({year}). {title}"
        return f"{author_str}. {title}"

    if year:
        return f"({year}). {title}"

    return title


async def fetch_content_batch(
    urls: List[str],
    max_concurrent: int = 10,
    timeout: float = 30.0,
) -> Tuple[Dict[str, FetchResult], Dict[str, int]]:
    """
    Fetch content from URLs in parallel with academic paper support.

    Includes robust fallback chain:
    1. Academic API (for DOI/academic URLs)
    2. Direct HTTP fetch
    3. Jina Reader fallback (for 403/blocked)
    4. PubMed API (for PMC/PubMed URLs)
    5. Retry with backoff for transient failures

    Args:
        urls: List of URLs to fetch
        max_concurrent: Maximum concurrent fetches
        timeout: Timeout per fetch

    Returns:
        Tuple of (content_map, fetch_methods_count)
        - content_map: Dict mapping URL to FetchResult with content and metadata
        - fetch_methods_count: Dict counting fetches by method
    """
    import httpx

    fetcher = get_fetcher()
    academic_fetcher = AcademicFetcher()
    results = {}
    fetch_methods = defaultdict(int)

    # Use semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    # Jina Reader base URL
    JINA_BASE = "https://r.jina.ai/"

    # Domains that need special handling
    ACADEMIC_BLOCKED_DOMAINS = [
        "pmc.ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "sciencedirect.com",
        "doi.org",
        "efsa.europa.eu",
        "springer.com",
        "wiley.com",
        "tandfonline.com",
    ]

    # Government domains that are slow - use longer timeout
    SLOW_DOMAINS = [".gov", ".gc.ca", "canada.ca"]

    async def fetch_with_jina(url: str) -> Optional[str]:
        """Fetch URL using Jina Reader as proxy."""
        jina_url = f"{JINA_BASE}{url}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    jina_url,
                    headers={"User-Agent": "Mozilla/5.0 POLARIS/1.0 Research Bot"},
                    timeout=60.0,
                    follow_redirects=True,
                )
                if response.status_code == 200 and len(response.text) > 100:
                    return response.text
        except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError) as e:
            # Network/HTTP errors expected - return None to try other fetch methods
            return None
        return None

    async def fetch_pubmed_content(url: str) -> Optional[Tuple[str, str]]:
        """
        Fetch content from PubMed/PMC using E-utilities API.

        Returns (content, title) or None.
        """
        import re
        import xml.etree.ElementTree as ET

        # Extract PMID or PMCID from URL
        pmid_match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", url)
        pmcid_match = re.search(r"pmc\.ncbi\.nlm\.nih\.gov/articles/(PMC\d+)", url)

        if not pmid_match and not pmcid_match:
            return None

        async def get_title_from_esummary(client: httpx.AsyncClient, pmid: str = None, pmcid: str = None) -> str:
            """Get article title using NCBI ESummary API (reliable fallback)."""
            try:
                if pmcid:
                    # Use ESummary directly on PMC database (simpler than ID conversion)
                    # Extract numeric ID from PMCID (e.g., "PMC9291231" -> "9291231")
                    pmcid_num = pmcid.replace("PMC", "")
                    esummary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id={pmcid_num}&retmode=json"
                    resp = await client.get(esummary_url, timeout=15.0, follow_redirects=True)
                    if resp.status_code == 200:
                        data = resp.json()
                        result = data.get("result", {})
                        if pmcid_num in result:
                            return result[pmcid_num].get("title", "")

                if pmid:
                    # Use ESummary on PubMed database for PMID
                    esummary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
                    resp = await client.get(esummary_url, timeout=15.0, follow_redirects=True)
                    if resp.status_code == 200:
                        data = resp.json()
                        result = data.get("result", {})
                        if pmid in result:
                            return result[pmid].get("title", "")
            except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError, KeyError, ValueError, TypeError) as e:
                # HIGH-005: Log API errors instead of silent pass
                logger.debug(f"PubMed/PMC title lookup failed (will use fallback): {e}")
            return ""

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                content = ""
                title = ""

                if pmcid_match:
                    # Fetch from PMC OA service
                    pmcid = pmcid_match.group(1)
                    api_url = f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode"
                    response = await client.get(api_url, timeout=30.0)
                    if response.status_code == 200:
                        data = response.json()
                        # BioC format returns a list with one collection
                        if isinstance(data, list) and len(data) > 0:
                            data = data[0]
                        # Extract text passages from BioC format
                        passages = []
                        for doc in data.get("documents", []):
                            for passage in doc.get("passages", []):
                                text = passage.get("text", "")
                                if text:
                                    passages.append(text)
                                    # First passage is usually title
                                    if not title and passage.get("infons", {}).get("type") == "title":
                                        title = text
                        if passages:
                            content = "\n\n".join(passages)

                    # FIX: If BioC didn't give us a title, use ESummary as fallback
                    if content and not title:
                        title = await get_title_from_esummary(client, pmcid=pmcid)

                    if content:
                        return content, title

                if pmid_match:
                    # Fetch abstract from E-utilities
                    pmid = pmid_match.group(1)
                    api_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&rettype=abstract&retmode=text"
                    response = await client.get(api_url, timeout=30.0)
                    if response.status_code == 200 and len(response.text) > 50:
                        content = response.text

                        # FIX: Use ESummary for reliable title extraction instead of parsing text
                        title = await get_title_from_esummary(client, pmid=pmid)

                        # Fallback: parse title from response (first non-empty line)
                        if not title:
                            lines = response.text.strip().split("\n")
                            for line in lines:
                                line = line.strip()
                                if line and len(line) > 20:  # Skip short lines
                                    title = line
                                    break

                        return content, title

        except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError, KeyError, ValueError) as e:
            # API errors expected - return None to try other fetch methods
            return None
        return None

    async def fetch_one(url: str) -> Tuple[str, FetchResult]:
        """Fetch single URL with robust fallback chain."""
        async with semaphore:
            url_type = classify_url(url)
            url_lower = url.lower()

            # Determine if URL needs special handling
            is_academic_blocked = any(d in url_lower for d in ACADEMIC_BLOCKED_DOMAINS)
            is_slow_domain = any(d in url_lower for d in SLOW_DOMAINS)
            is_pubmed = "pubmed.ncbi.nlm.nih.gov" in url_lower or "pmc.ncbi.nlm.nih.gov" in url_lower

            try:
                # STRATEGY 1: PubMed API for PMC/PubMed URLs (most reliable)
                if is_pubmed:
                    pubmed_result = await fetch_pubmed_content(url)
                    if pubmed_result:
                        content, title = pubmed_result
                        return (url, FetchResult(
                            content=content,
                            status=200,
                            method="pubmed_api",
                            title=title,
                        ))

                # STRATEGY 2: Academic fetcher for DOI/academic URLs
                if url_type == "academic":
                    doi = extract_doi_from_url(url)
                    if doi:
                        paper = await academic_fetcher.fetch_paper(doi=doi)
                        if paper and paper.full_text:
                            return (url, FetchResult(
                                content=paper.full_text,
                                status=200,
                                method="academic_api",
                                title=paper.title,
                                authors=paper.authors,
                                year=paper.metadata.get("year"),
                                doi=paper.doi,
                            ))
                        elif paper and paper.abstract:
                            return (url, FetchResult(
                                content=f"{paper.title}\n\n{paper.abstract}",
                                status=200,
                                method="academic_abstract",
                                title=paper.title,
                                authors=paper.authors,
                                year=paper.metadata.get("year"),
                                doi=paper.doi,
                            ))

                # STRATEGY 3: PDF extraction
                if url_type == "pdf" or url.lower().endswith(".pdf"):
                    paper = await academic_fetcher.fetch_paper(url=url)
                    if paper and paper.full_text:
                        return (url, FetchResult(
                            content=paper.full_text,
                            status=200,
                            method="pdf_extract",
                            title=paper.title,
                            authors=paper.authors,
                            year=paper.metadata.get("year"),
                            doi=paper.doi,
                        ))

                # STRATEGY 4: Direct HTTP fetch with retry
                max_retries = 2
                last_status = 0

                for attempt in range(max_retries + 1):
                    if attempt > 0:
                        # Exponential backoff
                        await asyncio.sleep(1.5 ** attempt)

                    result = await fetcher.fetch(url)
                    content = result.content or ""
                    status = result.status_code or 0
                    last_status = status

                    if status == 200 and len(content) > 100:
                        return (url, FetchResult(
                            content=content,
                            status=status,
                            method="requests",
                            title=None,
                        ))

                    # Don't retry for certain status codes
                    if status in [404, 410, 451]:  # Not found, Gone, Unavailable for legal reasons
                        break

                # STRATEGY 5: Jina Reader fallback for blocked/failed
                if last_status in [403, 429, 503] or is_academic_blocked or (last_status == 0):
                    jina_content = await fetch_with_jina(url)
                    if jina_content and len(jina_content) > 100:
                        return (url, FetchResult(
                            content=jina_content,
                            status=200,
                            method="jina_reader",
                            title=None,
                        ))

                # All strategies failed
                return (url, FetchResult(content="", status=last_status, method="failed"))

            except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError, ValueError, KeyError) as e:
                # Final fallback: try Jina Reader
                try:
                    jina_content = await fetch_with_jina(url)
                    if jina_content and len(jina_content) > 100:
                        return (url, FetchResult(
                            content=jina_content,
                            status=200,
                            method="jina_fallback",
                            title=None,
                        ))
                except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError):
                    # Jina fallback also failed - proceed to return failed result
                    return (url, FetchResult(content="", status=0, method="failed"))

                return (url, FetchResult(content="", status=0, method="failed"))

    tasks = [fetch_one(url) for url in urls]
    completed = await asyncio.gather(*tasks)

    for url, fetch_result in completed:
        results[url] = fetch_result
        if fetch_result.status == 200 and fetch_result.content:
            fetch_methods[fetch_result.method] += 1
        else:
            fetch_methods["failed"] += 1

    return results, dict(fetch_methods)


# =============================================================================
# CHUNKING
# =============================================================================

def chunk_content(
    content: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    min_chunk_size: int = 100,
) -> List[str]:
    """
    Split content into overlapping chunks.

    Args:
        content: Raw text content
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks
        min_chunk_size: Minimum chunk size to keep

    Returns:
        List of text chunks
    """
    if not content or len(content) < min_chunk_size:
        return []

    # Clean content
    content = re.sub(r'\s+', ' ', content).strip()

    # Split by sentences (roughly)
    sentences = re.split(r'(?<=[.!?])\s+', content)

    chunks = []
    current_chunk = []
    current_size = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_size + sentence_len <= chunk_size:
            current_chunk.append(sentence)
            current_size += sentence_len
        else:
            # Save current chunk
            if current_size >= min_chunk_size:
                chunks.append(' '.join(current_chunk))

            # Start new chunk with overlap
            # Take last sentences that fit within overlap
            overlap_sentences = []
            overlap_size = 0
            for s in reversed(current_chunk):
                if overlap_size + len(s) <= chunk_overlap:
                    overlap_sentences.insert(0, s)
                    overlap_size += len(s)
                else:
                    break

            current_chunk = overlap_sentences + [sentence]
            current_size = overlap_size + sentence_len

    # Add final chunk
    if current_size >= min_chunk_size:
        chunks.append(' '.join(current_chunk))

    return chunks


# =============================================================================
# SOTA: NER-BASED STUDY LOCATION EXTRACTION (from upgrade plan)
# Uses spaCy to extract geographic entities from abstracts/content
# =============================================================================

_nlp_model = None


def load_spacy_model():
    """
    Load spaCy model for NER.
    Uses en_core_web_sm for efficiency.

    Returns:
        spaCy language model or None if unavailable
    """
    global _nlp_model
    if _nlp_model is not None:
        return _nlp_model

    try:
        import spacy
        try:
            _nlp_model = spacy.load("en_core_web_sm")
            print("[PHASE-4][SOTA] spaCy NER model loaded (en_core_web_sm)")
        except OSError:
            # Try to download
            print("[PHASE-4][SOTA] Downloading spaCy model en_core_web_sm...")
            from spacy.cli import download
            download("en_core_web_sm")
            _nlp_model = spacy.load("en_core_web_sm")
        return _nlp_model
    except Exception as e:
        # LOW-059: Use logger instead of print
        logger.warning(f"[PHASE-4][SOTA] spaCy not available: {e}")
        return None


def extract_study_location_ner(
    text: str,
    max_chars: int = 3000,
) -> Dict[str, Any]:
    """
    SOTA: Extract study location from text using spaCy NER.

    Extracts GPE (geo-political entity) and LOC (location) entities
    to determine where a study was conducted.

    Args:
        text: Text to analyze (typically abstract or first few paragraphs)
        max_chars: Maximum characters to process (for performance)

    Returns:
        Dict with:
        - locations: List of extracted location names
        - countries: List of likely country names
        - confidence: Confidence score 0-1
        - method: "ner" or "fallback"
    """
    nlp = load_spacy_model()

    if nlp is None:
        return {
            "locations": [],
            "countries": [],
            "confidence": 0.0,
            "method": "fallback",
        }

    # Truncate text for performance
    text_sample = text[:max_chars]

    try:
        doc = nlp(text_sample)

        # Extract GPE and LOC entities
        locations = []
        countries = []

        # Common country names to identify
        COUNTRY_NAMES = {
            "united states", "usa", "u.s.", "america", "us",
            "canada", "mexico", "uk", "united kingdom", "england",
            "germany", "france", "italy", "spain", "netherlands",
            "china", "japan", "india", "australia", "korea",
            "brazil", "argentina", "russia", "poland", "sweden",
        }

        for ent in doc.ents:
            if ent.label_ in ("GPE", "LOC"):
                loc_text = ent.text.strip()
                if len(loc_text) > 1:  # Skip single characters
                    locations.append(loc_text)

                    # Check if it's a country
                    if loc_text.lower() in COUNTRY_NAMES:
                        countries.append(loc_text)

        # Deduplicate while preserving order
        locations = list(dict.fromkeys(locations))
        countries = list(dict.fromkeys(countries))

        # Calculate confidence based on number of entities found
        confidence = min(1.0, len(locations) / 3) if locations else 0.0

        return {
            "locations": locations[:10],  # Limit to top 10
            "countries": countries[:5],
            "confidence": confidence,
            "method": "ner",
        }

    except Exception as e:
        # LOW-060: Use logger instead of print
        logger.warning(f"[PHASE-4][SOTA] NER extraction failed: {e}")
        return {
            "locations": [],
            "countries": [],
            "confidence": 0.0,
            "method": "fallback",
        }


# =============================================================================
# SOTA: ADAPTIVE STOPPING RULE (from upgrade plan)
# Stop processing when sufficient high-quality content is found
# =============================================================================

class AdaptiveStoppingRule:
    """
    SOTA: Adaptive stopping rule for relevance filtering.

    Stops processing additional chunks when we have accumulated
    sufficient high-quality content, saving computation.

    Thresholds:
    - min_gold_chunks: Minimum gold-tier chunks required
    - min_silver_chunks: Minimum silver-tier chunks required
    - max_chunks_total: Hard limit on total chunks
    """

    def __init__(
        self,
        min_gold_chunks: int = 15,
        min_silver_chunks: int = 30,
        min_total_chunks: int = 50,
        max_chunks_total: int = 500,
    ):
        self.min_gold = min_gold_chunks
        self.min_silver = min_silver_chunks
        self.min_total = min_total_chunks
        self.max_total = max_chunks_total

        # Tracking
        self.gold_count = 0
        self.silver_count = 0
        self.total_count = 0
        self._stopped = False
        self._stop_reason = None

    def record_chunk(self, tier: str):
        """Record a chunk and its tier."""
        self.total_count += 1
        if tier == "gold":
            self.gold_count += 1
        elif tier == "silver":
            self.silver_count += 1

    def should_stop(self) -> bool:
        """
        Check if we should stop processing more chunks.

        Stops when either:
        1. We have enough gold AND silver chunks
        2. We've hit the hard maximum
        """
        if self._stopped:
            return True

        # Hard maximum
        if self.total_count >= self.max_total:
            self._stopped = True
            self._stop_reason = f"max_chunks_reached ({self.max_total})"
            return True

        # Quality threshold - need minimum total first
        if self.total_count >= self.min_total:
            if self.gold_count >= self.min_gold and self.silver_count >= self.min_silver:
                self._stopped = True
                self._stop_reason = f"quality_threshold_met (gold={self.gold_count}, silver={self.silver_count})"
                return True

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            "gold_count": self.gold_count,
            "silver_count": self.silver_count,
            "total_count": self.total_count,
            "stopped": self._stopped,
            "stop_reason": self._stop_reason,
        }


# =============================================================================
# SOTA: BM25 SPARSE RETRIEVAL + RECIPROCAL RANK FUSION (RRF)
# Based on: Hybrid retrieval combining sparse (BM25) and dense (embedding) signals
# =============================================================================

_bm25_index = None
_bm25_corpus = None


def compute_bm25_scores(
    query: str,
    chunks: List[Dict[str, Any]],
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[str, float]:
    """
    SOTA: Compute BM25 sparse retrieval scores for chunks.

    BM25 captures exact term matching that dense embeddings may miss,
    especially for technical terms, acronyms, and specific phrases.

    Args:
        query: Search query
        chunks: List of chunk dicts with 'id' and 'text'
        k1: BM25 k1 parameter (term saturation)
        b: BM25 b parameter (length normalization)

    Returns:
        Dict mapping chunk_id to BM25 score
    """
    import math
    from collections import Counter

    if not chunks:
        return {}

    # Tokenize query and documents (simple whitespace tokenization)
    def tokenize(text: str) -> List[str]:
        import re
        # Lowercase and extract words
        words = re.findall(r'\b[a-z0-9]+\b', text.lower())
        return words

    query_tokens = tokenize(query)
    if not query_tokens:
        return {c["id"]: 0.0 for c in chunks}

    # Build document token lists and compute document frequencies
    doc_tokens = []
    doc_lengths = []
    df = Counter()  # Document frequency

    for chunk in chunks:
        tokens = tokenize(chunk.get("text", ""))
        doc_tokens.append(tokens)
        doc_lengths.append(len(tokens))
        # Count unique terms per document
        for term in set(tokens):
            df[term] += 1

    # Average document length
    N = len(chunks)
    avgdl = sum(doc_lengths) / N if N > 0 else 1

    # Compute BM25 score for each document
    scores = {}
    for i, chunk in enumerate(chunks):
        tokens = doc_tokens[i]
        doc_len = doc_lengths[i]
        tf = Counter(tokens)  # Term frequency in this document

        score = 0.0
        for term in query_tokens:
            if term in tf:
                # IDF component
                n = df.get(term, 0)
                idf = math.log((N - n + 0.5) / (n + 0.5) + 1)

                # TF component with saturation and length normalization
                freq = tf[term]
                tf_component = (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * (doc_len / avgdl)))

                score += idf * tf_component

        scores[chunk["id"]] = score

    return scores


def reciprocal_rank_fusion(
    ranked_lists: List[Dict[str, float]],
    k: int = 60,
) -> Dict[str, float]:
    """
    SOTA: Combine multiple ranked lists using Reciprocal Rank Fusion (RRF).

    RRF is robust to score scale differences between retrieval methods.
    Formula: RRF(d) = sum(1 / (k + rank_i(d))) for each ranking i

    Args:
        ranked_lists: List of dicts mapping item_id to score (higher = better)
        k: RRF constant (default 60 per original paper)

    Returns:
        Dict mapping item_id to fused RRF score
    """
    if not ranked_lists:
        return {}

    # Convert score dicts to ranked lists
    rankings = []
    for scores in ranked_lists:
        # Sort by score descending, get ranks
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        rank_dict = {item_id: rank + 1 for rank, (item_id, _) in enumerate(sorted_items)}
        rankings.append(rank_dict)

    # Compute RRF scores
    all_items = set()
    for scores in ranked_lists:
        all_items.update(scores.keys())

    rrf_scores = {}
    for item_id in all_items:
        rrf_score = 0.0
        for rank_dict in rankings:
            if item_id in rank_dict:
                rank = rank_dict[item_id]
                rrf_score += 1.0 / (k + rank)
        rrf_scores[item_id] = rrf_score

    return rrf_scores


def compute_hybrid_scores(
    query: str,
    chunks: List[Dict[str, Any]],
    embedding_model=None,
    alpha: float = 0.5,
) -> Dict[str, float]:
    """
    SOTA: Compute hybrid scores combining BM25 and dense embedding retrieval.

    Uses Reciprocal Rank Fusion (RRF) to combine:
    1. BM25 sparse scores (exact term matching)
    2. Dense embedding similarity (semantic matching)

    Args:
        query: Search query
        chunks: List of chunk dicts with 'id' and 'text'
        embedding_model: Pre-loaded embedding model
        alpha: Weight for dense scores (1-alpha for sparse)

    Returns:
        Dict mapping chunk_id to hybrid score
    """
    if not chunks:
        return {}

    # Compute BM25 sparse scores
    bm25_scores = compute_bm25_scores(query, chunks)

    # Compute dense embedding scores
    dense_scores = {}
    if embedding_model is not None:
        for chunk in chunks:
            try:
                embeddings = embedding_model.encode([query, chunk.get("text", "")[:1000]])
                from numpy import dot
                from numpy.linalg import norm
                similarity = dot(embeddings[0], embeddings[1]) / (norm(embeddings[0]) * norm(embeddings[1]) + 1e-8)
                dense_scores[chunk["id"]] = float(similarity)
            except Exception:
                dense_scores[chunk["id"]] = 0.0
    else:
        # Fallback: use BM25 only
        return bm25_scores

    # Combine using RRF
    hybrid_scores = reciprocal_rank_fusion([bm25_scores, dense_scores])

    return hybrid_scores


def rerank_chunks_hybrid(
    query: str,
    chunks: List[Dict[str, Any]],
    embedding_model=None,
    cross_encoder_model=None,
    top_k: int = 50,
) -> List[Dict[str, Any]]:
    """
    SOTA: Two-stage hybrid reranking pipeline.

    Stage 1: Hybrid BM25 + Dense retrieval with RRF
    Stage 2: Cross-encoder neural reranking on top candidates

    Args:
        query: Search query
        chunks: List of chunk dicts
        embedding_model: For dense retrieval
        cross_encoder_model: For neural reranking
        top_k: Number of top candidates for cross-encoder

    Returns:
        Reranked list of chunks with hybrid_score field
    """
    if not chunks:
        return []

    # Stage 1: Hybrid retrieval
    print(f"[PHASE-4][HYBRID] Stage 1: BM25 + Dense fusion on {len(chunks)} chunks...")
    hybrid_scores = compute_hybrid_scores(query, chunks, embedding_model)

    # Sort by hybrid score
    for chunk in chunks:
        chunk["hybrid_score"] = hybrid_scores.get(chunk["id"], 0.0)

    sorted_chunks = sorted(chunks, key=lambda x: x.get("hybrid_score", 0), reverse=True)

    # Stage 2: Cross-encoder on top candidates
    if cross_encoder_model is not None and len(sorted_chunks) > 0:
        top_candidates = sorted_chunks[:top_k]
        print(f"[PHASE-4][HYBRID] Stage 2: Cross-encoder reranking on top {len(top_candidates)} candidates...")

        for chunk in top_candidates:
            try:
                ce_score = compute_cross_encoder_score(query, chunk.get("text", ""), cross_encoder_model)
                # Combine: 60% cross-encoder + 40% hybrid
                chunk["final_score"] = 0.6 * ((ce_score + 8.0) / 16.0) + 0.4 * chunk["hybrid_score"]
            except Exception:
                chunk["final_score"] = chunk["hybrid_score"]

        # Re-sort top candidates by final score
        top_candidates = sorted(top_candidates, key=lambda x: x.get("final_score", 0), reverse=True)

        # Combine: reranked top + rest
        rest = sorted_chunks[top_k:]
        for chunk in rest:
            chunk["final_score"] = chunk["hybrid_score"] * 0.4  # Lower weight for non-reranked

        return top_candidates + rest

    # No cross-encoder: just return hybrid-sorted
    for chunk in sorted_chunks:
        chunk["final_score"] = chunk["hybrid_score"]

    return sorted_chunks


# =============================================================================
# CROSS-ENCODER RERANKER (SOTA UPGRADE)
# =============================================================================

_cross_encoder = None
_cross_encoder_available = None


def load_cross_encoder():
    """
    Load the cross-encoder model for neural reranking.

    Uses ms-marco-MiniLM-L-6-v2 for efficiency (~80MB).
    """
    global _cross_encoder, _cross_encoder_available

    if _cross_encoder_available is not None:
        return _cross_encoder

    try:
        from sentence_transformers import CrossEncoder
        print("[PHASE-4] Loading CrossEncoder: ms-marco-MiniLM-L-6-v2")
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        _cross_encoder_available = True
        print("[PHASE-4] CrossEncoder loaded successfully")
        return _cross_encoder
    except ImportError as e:
        # LOW-061: Use logger instead of print
        logger.warning(f"[PHASE-4][WARN] sentence-transformers not available: {e}")
        _cross_encoder_available = False
        return None
    except Exception as e:
        # LOW-062: Use logger instead of print
        logger.warning(f"[PHASE-4][WARN] Failed to load CrossEncoder: {e}")
        _cross_encoder_available = False
        return None


def compute_cross_encoder_score(
    query: str,
    chunk: str,
    model=None,
) -> float:
    """
    Compute neural relevance score using cross-encoder.

    Args:
        query: Research question
        chunk: Text chunk to score
        model: Pre-loaded CrossEncoder model

    Returns:
        Score (higher = more relevant)
    """
    if model is None:
        model = load_cross_encoder()

    if model is None:
        return 0.0

    try:
        # CrossEncoder expects [(query, document)] pairs
        # Truncate chunk to model limits (512 tokens ~ 2000 chars for safety)
        chunk_truncated = chunk[:2000]
        scores = model.predict([(query, chunk_truncated)])
        return float(scores[0])
    except Exception as e:
        # LOW-063: Use logger instead of print
        logger.warning(f"[PHASE-4][WARN] CrossEncoder scoring failed: {e}")
        return 0.0


def compute_soft_score(
    query: str,
    chunk: str,
    model=None,
    debug: bool = False,
) -> float:
    """
    Soft-gate scoring using cross-encoder.

    Args:
        query: Research question
        chunk: Text chunk
        model: Pre-loaded model
        debug: Print debug info

    Returns:
        Normalized score 0-1
    """
    raw_score = compute_cross_encoder_score(query, chunk, model)

    # MS-MARCO cross-encoder outputs logits typically in range [-12, +12]
    # Use wider range for research content: map [-8, +8] to [0, 1]
    # This gives more granularity for somewhat-relevant content
    normalized = (raw_score + 8.0) / 16.0
    normalized = max(0.0, min(1.0, normalized))  # Clamp to [0, 1]

    if debug:
        print(f"[DEBUG] raw_score={raw_score:.3f}, normalized={normalized:.3f}")

    return normalized


# IRON LOOP: Whitelisted .com domains (legitimate news/science)
WHITELISTED_COM_DOMAINS = {
    "nytimes.com", "wsj.com", "bloomberg.com", "reuters.com",
    "sciencedaily.com", "nature.com", "sciencemag.org", "scientificamerican.com",
    "mayoclinic.org", "webmd.com", "healthline.com",
    "bbc.com", "theguardian.com", "washingtonpost.com",
}

# IRON LOOP: Academic/authoritative domain patterns (STRONG BOOST)
ACADEMIC_DOMAIN_PATTERNS = [".gov", ".edu", "ncbi.nlm.nih.gov", "pubmed", "arxiv.org", "semanticscholar", "cdc.gov", "epa.gov", "who.int"]

# IRON LOOP v2: Commercial vendor domain BLACKLIST (HARD REJECT -0.5)
COMMERCIAL_VENDOR_PATTERNS = [
    "marketresearch", "grandviewresearch", "researchnester", "polarismarketresearch",
    "expertmarketresearch", "mordorintelligence", "arizton", "statista",
    "filter", "purifier", "aquasana", "multipure", "springwell", "berkey",
    "store.", "shop.", "/buy", "/product", "/cart", "amazon.com",
    "alibaba", "ebay", "walmart", "homedepot", "lowes",
]

# IRON LOOP v2: SEO spam URL patterns (INSTANT REJECT)
SEO_URL_PATTERNS = [
    "best-", "-reviews", "top-10", "buying-guide", "-vs-",
    "/compare/", "/deals/", "/discount", "/coupon", "/promo",
]

# IRON LOOP: SEO spam blacklist phrases (instant reject)
SEO_BLACKLIST_PHRASES = [
    "buying guide",
    "best reviews",
    "top 10",
    "affiliate",
    "sponsored post",
    "as an amazon associate",
    "buy now",
    "limited time offer",
    "discount code",
    "promo code",
    "shop now",
    "free shipping",
    "order now",
    "add to cart",
    "compare prices",
    "cheapest",
    "best deal",
    "market size",
    "cagr",
    "market forecast",
    "request a free sample",
    "download report",
]


def compute_domain_score_adjustment(url: str) -> float:
    """
    IRON LOOP v2: Source Hygiene - Compute domain-based score adjustment.

    HARD penalties for commercial/vendor domains.
    STRONG boost for academic/government domains.

    NOTE: Primary blacklist filtering now happens at P3 (ingestion).
    This function provides graduated scoring for edge cases and legacy support.

    Args:
        url: Source URL

    Returns:
        Score adjustment (-0.5 to +0.25)
    """
    if not url:
        return 0.0

    url_lower = url.lower()

    # FAILSAFE: Check centralized blacklist first (in case URL bypassed P3)
    # This catches URLs from cached results or manual additions
    is_blacklisted, _ = is_url_blacklisted(url, include_news=False)
    if is_blacklisted:
        return -0.5  # Hard penalty for blacklisted URLs

    # IRON LOOP v2: Check for commercial vendor domains (HARD PENALTY -0.5)
    for pattern in COMMERCIAL_VENDOR_PATTERNS:
        if pattern in url_lower:
            return -0.5

    # IRON LOOP v2: Check for SEO spam URL patterns (HARD PENALTY -0.4)
    for pattern in SEO_URL_PATTERNS:
        if pattern in url_lower:
            return -0.4

    # FIX BUG 8: Check for news/media/social sites (PENALTY -0.35 to -0.5)
    # News sites should not be primary sources for scientific research
    NEWS_SITE_PATTERNS = [
        "news-medical.net",  # News aggregator
        "medicalnewstoday.com",
        "healthline.com",
        "webmd.com",
        "mayoclinic.org/healthy-lifestyle",  # Not the research side
        "cnn.com/health",
        "bbc.com/news",
        "reuters.com",
        "apnews.com",
        "huffpost.com",
        "buzzfeed.com",
        "dailymail.co.uk",
        "theguardian.com",
        "nytimes.com",
        "washingtonpost.com",
        "forbes.com",
        "businessinsider.com",
        "medium.com",
        "blog.",  # Blog subdomains
        "/blog/",  # Blog paths
        # Social media - HARD REJECT
        "linkedin.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "tiktok.com",
        "reddit.com",
        "quora.com",
        "pinterest.com",
        "youtube.com",
    ]
    for pattern in NEWS_SITE_PATTERNS:
        if pattern in url_lower:
            return -0.35

    # Check for academic/authoritative domains (STRONG BOOST +0.25)
    for pattern in ACADEMIC_DOMAIN_PATTERNS:
        if pattern in url_lower:
            return 0.25

    # Check for .org domains (moderate boost +0.10)
    if ".org" in url_lower:
        return 0.10

    # Check for whitelisted .com domains (no penalty)
    for domain in WHITELISTED_COM_DOMAINS:
        if domain in url_lower:
            return 0.0

    # Generic .com domains get penalized (-0.3)
    if ".com" in url_lower:
        return -0.3

    # Neutral for other TLDs
    return 0.0


def is_seo_spam(text: str) -> bool:
    """
    IRON LOOP: Check if chunk contains SEO spam phrases.

    Uses centralized blacklist from src/utils/url_blacklist.py.

    Args:
        text: Chunk text to check

    Returns:
        True if chunk is SEO spam and should be rejected
    """
    # Use centralized module for consistency
    return is_content_seo_spam(text)


def compute_geographic_score_adjustment(
    content_region: str,
    target_region: str,
    geo_confidence: float = 0.5,
) -> float:
    """
    SOTA: Compute score adjustment based on geographic relevance.

    Content from the target region gets a boost.
    Content from other regions gets a penalty (unless GLOBAL).

    Args:
        content_region: Detected region of the content
        target_region: Target region for the research vector
        geo_confidence: Confidence of geographic detection

    Returns:
        Score adjustment (-0.2 to +0.15)
    """
    # GLOBAL content is always acceptable
    if content_region == "GLOBAL":
        return 0.0

    # GLOBAL target accepts all regions
    if target_region == "GLOBAL":
        return 0.0

    # Exact region match - boost
    if content_region == target_region:
        return 0.15 * geo_confidence  # Max +0.15 for high-confidence match

    # Region mismatch - penalty
    # Stronger penalty for high-confidence mismatches
    return -0.20 * geo_confidence  # Max -0.20 for high-confidence mismatch


def fuse_scores(
    hard_score: float,
    soft_score: float,
    hard_weight: float = 0.4,
    soft_weight: float = 0.6,
) -> float:
    """
    Fuse hard-gate (keyword) and soft-gate (neural) scores.

    Args:
        hard_score: Keyword-based score
        soft_score: Neural cross-encoder score
        hard_weight: Weight for hard score (default 0.4)
        soft_weight: Weight for soft score (default 0.6)

    Returns:
        Fused relevance score
    """
    return hard_weight * hard_score + soft_weight * soft_score


# =============================================================================
# RELEVANCE SCORING
# =============================================================================

# Global embedding model cache
_embedding_model = None


def load_embedding_model():
    """Load embedding model for hard gate scoring."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("[PHASE-4] Embedding model loaded: all-MiniLM-L6-v2")
        except ImportError:
            # LOW-064: Use logger instead of print
            logger.warning("[PHASE-4][WARN] sentence-transformers not available")
            _embedding_model = None
    return _embedding_model


def compute_embedding_similarity(
    query: str,
    chunk: str,
    model=None,
) -> float:
    """
    Compute embedding-based similarity score (hard gate).

    Uses sentence-transformers for semantic similarity.

    Args:
        query: Research question
        chunk: Text chunk
        model: Pre-loaded embedding model

    Returns:
        Cosine similarity score between 0 and 1
    """
    if model is None:
        model = load_embedding_model()

    if model is None:
        # Fallback to keyword matching if model unavailable
        return compute_keyword_relevance(chunk, extract_keywords(query))

    try:
        import numpy as np
        # Encode query and chunk
        embeddings = model.encode([query, chunk[:1000]])  # Truncate chunk
        # Compute cosine similarity
        query_emb = embeddings[0]
        chunk_emb = embeddings[1]
        similarity = np.dot(query_emb, chunk_emb) / (
            np.linalg.norm(query_emb) * np.linalg.norm(chunk_emb)
        )
        # Convert to 0-1 range (similarity is already -1 to 1)
        return float(max(0.0, (similarity + 1) / 2))
    except Exception as e:
        # LOW-065: Use logger instead of print
        logger.warning(f"[PHASE-4][WARN] Embedding similarity failed: {e}")
        return 0.0


def compute_keyword_relevance(
    chunk: str,
    query_keywords: List[str],
) -> float:
    """
    Compute keyword-based relevance score (fallback for hard gate).

    Args:
        chunk: Text chunk
        query_keywords: Keywords from research question

    Returns:
        Score between 0 and 1
    """
    if not chunk or not query_keywords:
        return 0.0

    chunk_lower = chunk.lower()
    matches = sum(1 for kw in query_keywords if kw.lower() in chunk_lower)
    return min(1.0, matches / len(query_keywords))


def extract_keywords(question: str) -> List[str]:
    """Extract keywords from research question."""
    # Remove common words
    stop_words = {
        'what', 'where', 'when', 'which', 'who', 'how', 'why',
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did',
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
        'to', 'for', 'of', 'with', 'by', 'from', 'as', 'into',
        'through', 'during', 'before', 'after', 'above', 'below',
        'between', 'under', 'again', 'further', 'then', 'once',
        'here', 'there', 'all', 'each', 'few', 'more', 'most',
        'other', 'some', 'such', 'no', 'nor', 'not', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'can',
        'will', 'just', 'should', 'now', 'exist', 'rates', 'patterns',
    }

    words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
    keywords = [w for w in words if w not in stop_words]

    return list(set(keywords))


def assign_relevance_tier(score: float) -> RelevanceTier:
    """
    Assign relevance tier based on score.

    Thresholds:
    - GOLD: >= 0.70
    - SILVER: 0.55-0.69
    - BRONZE: 0.40-0.54
    - REJECTED: < 0.40
    """
    config = get_config()

    gold_threshold = config.thresholds.relevance.gold_threshold
    silver_threshold = config.thresholds.relevance.silver_threshold
    bronze_threshold = config.thresholds.relevance.bronze_threshold

    if score >= gold_threshold:
        return RelevanceTier.GOLD
    elif score >= silver_threshold:
        return RelevanceTier.SILVER
    elif score >= bronze_threshold:
        return RelevanceTier.BRONZE
    else:
        return RelevanceTier.REJECTED


def check_geographic_relevance(
    chunk_text: str,
    target_region: str,
    title: str = "",
    url: str = "",
    geo_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, float]:
    """
    Check if chunk content is geographically relevant to target region.

    SOTA FIX: Now uses pre-computed geographic metadata from ingestion when available.
    Falls back to text-based detection if metadata not provided.

    Args:
        chunk_text: Text content of the chunk
        target_region: Target region from vector_id (e.g., "NORTH_AMERICA")
        title: Title of the source (optional)
        url: Source URL (optional)
        geo_metadata: Pre-computed geographic metadata from citation_metadata (optional)

    Returns:
        Tuple of (is_relevant, penalty_factor)
        - is_relevant: True if chunk is geographically compatible
        - penalty_factor: Multiplier to apply to relevance score (0.0-1.0)
    """
    import re

    # SOTA: Use pre-computed geographic metadata if available
    if geo_metadata and "geo_region" in geo_metadata:
        content_region = geo_metadata.get("geo_region", "GLOBAL")
        geo_confidence = geo_metadata.get("geo_confidence", 0.5)

        # GLOBAL content is always relevant
        if content_region == "GLOBAL":
            return True, 1.0

        # GLOBAL target accepts all content
        if target_region == "GLOBAL":
            return True, 1.0

        # Exact region match
        if content_region == target_region:
            return True, 1.0

        # SOTA: Strict geographic filtering - reject high-confidence mismatches
        # If we're confident content is from a different region, reject it
        if geo_confidence >= 0.70:
            # High-confidence mismatch = hard reject
            return False, 0.0

        # Region mismatch with moderate confidence - heavy penalty
        # Higher confidence = stronger penalty (0.0 to 0.35)
        penalty = 0.35 - (0.35 * geo_confidence)  # Range: 0.0 to 0.35
        return False, penalty

    # FALLBACK: Text-based geographic detection (original logic)
    target_lower = target_region.lower().replace("_", " ")
    chunk_lower = chunk_text.lower()
    title_lower = title.lower() if title else ""
    url_lower = url.lower() if url else ""

    # Combine text, title, and url for comprehensive checking
    combined_text = f"{chunk_lower} {title_lower} {url_lower}"

    # BUG-008 FIX: Load geographic terms from config (NO HARDCODING - LAW VI)
    # Terms loaded from config/settings/geographic_regions.yaml
    config = get_config()
    geo_config = getattr(config, 'geographic_regions', None) if config else None

    def _get_exclusion_keywords(region_key: str) -> List[str]:
        """Load exclusion region keywords from config."""
        if geo_config and hasattr(geo_config, 'exclusion_regions'):
            exclusion = getattr(geo_config.exclusion_regions, region_key, None)
            if exclusion and hasattr(exclusion, 'keywords'):
                return [kw.lower() for kw in exclusion.keywords]
        return []

    def _get_region_keywords(region_key: str) -> List[str]:
        """Load target region keywords from config."""
        if geo_config and hasattr(geo_config, 'regions'):
            region = getattr(geo_config.regions, region_key, None)
            if region and hasattr(region, 'keywords'):
                return [kw.lower() for kw in region.keywords]
        return []

    # Load from config - empty list if not configured (fails safe)
    AFRICA_TERMS = _get_exclusion_keywords('AFRICA')
    MIDDLE_EAST_TERMS = _get_exclusion_keywords('MIDDLE_EAST')
    SOUTH_AMERICA_TERMS = _get_exclusion_keywords('SOUTH_AMERICA')
    DEVELOPING_TERMS = _get_exclusion_keywords('DEVELOPING')

    # Target region terms from config
    NORTH_AMERICA_TERMS = _get_region_keywords('NORTH_AMERICA')
    EUROPE_TERMS = _get_region_keywords('EUROPE')
    ASIA_TERMS = _get_region_keywords('ASIA_PACIFIC')
    OCEANIA_TERMS = _get_region_keywords('OCEANIA') or ["australia", "new zealand", "oceania"]

    # Check for target region mentions (positive signal)
    target_mentioned = False
    if "north" in target_lower and "america" in target_lower:
        target_mentioned = any(term in combined_text for term in NORTH_AMERICA_TERMS)
    elif "europe" in target_lower:
        target_mentioned = any(term in combined_text for term in EUROPE_TERMS)
    elif "asia" in target_lower:
        target_mentioned = any(term in combined_text for term in ASIA_TERMS)

    # Check for incompatible region mentions (negative signal)
    incompatible_mentioned = False
    penalty = 1.0

    if "north" in target_lower and "america" in target_lower:
        # SOTA: For North America target, reject content from other regions
        # Check Middle East (HARD REJECT) - terms from config
        if any(term in combined_text for term in MIDDLE_EAST_TERMS):
            incompatible_mentioned = True
            # Hard reject if Middle East location in title (use config terms)
            if any(term in title_lower for term in MIDDLE_EAST_TERMS):
                penalty = 0.0  # REJECT - Middle East study in title
            elif any(term in chunk_lower for term in MIDDLE_EAST_TERMS):
                penalty = 0.0  # REJECT - Middle East mentioned prominently
            else:
                penalty = 0.1  # Heavy penalty for other Middle East content

        # Check Africa (HARD REJECT for region-specific studies)
        # BUG-008 FIX: All terms from config (NO HARDCODING)
        if any(term in combined_text for term in AFRICA_TERMS):
            incompatible_mentioned = True
            # Hard reject if ANY African location is in the title (use config terms)
            if any(term in title_lower for term in AFRICA_TERMS):
                penalty = min(penalty, 0.0)  # REJECT - Africa study in title
            # Hard reject if African location appears prominently in text (use config terms)
            elif any(term in chunk_lower for term in AFRICA_TERMS):
                penalty = min(penalty, 0.0)  # REJECT - African location prominent in text
            else:
                penalty = min(penalty, 0.15)

        # Check South America (REJECT for region-specific studies) - terms from config
        if any(term in combined_text for term in SOUTH_AMERICA_TERMS):
            incompatible_mentioned = True
            if any(term in title_lower for term in SOUTH_AMERICA_TERMS):
                penalty = min(penalty, 0.0)  # REJECT - South America study in title
            else:
                penalty = min(penalty, 0.2)

        # Check Asia (REJECT for region-specific studies) - terms from config
        if any(term in combined_text for term in ASIA_TERMS):
            incompatible_mentioned = True
            if any(term in title_lower for term in ASIA_TERMS):
                penalty = min(penalty, 0.0)  # REJECT - Asia study in title
            else:
                penalty = min(penalty, 0.2)

        # Check developing countries (REJECT)
        if any(term in combined_text for term in DEVELOPING_TERMS):
            if "developing countr" in title_lower or "low-income" in title_lower:
                penalty = min(penalty, 0.0)  # REJECT - developing countries study
            elif "compared to" in chunk_lower or "versus" in chunk_lower:
                penalty = min(penalty, 0.5)  # Context of comparison
            else:
                incompatible_mentioned = True
                penalty = min(penalty, 0.2)

    # If ONLY target region is mentioned (not incompatible), no penalty
    if target_mentioned and not incompatible_mentioned:
        penalty = 1.0
    # If target region is mentioned along with incompatible, still heavy penalty
    elif target_mentioned and incompatible_mentioned:
        penalty = min(penalty + 0.1, 0.5)  # Small restoration but still penalized

    # If neither target nor incompatible mentioned, chunk might be generic/global
    if not target_mentioned and not incompatible_mentioned:
        penalty = 0.8  # Slight penalty for non-specific content

    is_relevant = penalty >= 0.4
    return is_relevant, penalty


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

async def run_phase4(
    vector_id: str,
    input_path: Path,
    output_dir: Path,
) -> Phase4Output:
    """
    Execute Phase 4: Relevance Filtering.

    Args:
        vector_id: Vector ID to process
        input_path: Path to Phase 3 output
        output_dir: Directory to write output

    Returns:
        Phase4Output model
    """
    timestamps = {"start": datetime.now(timezone.utc).isoformat()}
    audit = get_audit()

    # Load config
    config = get_config()

    # 1. Load Phase 3 output
    with open(input_path, "r", encoding="utf-8") as f:
        p3_data = json.load(f)

    p3_output = Phase3Output(**p3_data)

    # Verify vector ID matches
    if p3_output.vector_id != vector_id:
        raise ValueError(f"Vector ID mismatch: {vector_id} != {p3_output.vector_id}")

    # 2. Extract URLs to fetch and build metadata index
    urls = [r.url for r in p3_output.search_results if r.url]
    print(f"[PHASE-4][{vector_id}][INFO] URLs to fetch: {len(urls)}")

    # SOTA: Build mapping from URL to SearchResult metadata for source-level filtering
    # This preserves API-provided metadata (author_countries, citation_count) through the pipeline
    search_result_metadata: Dict[str, Dict[str, Any]] = {}
    for r in p3_output.search_results:
        if r.url:
            search_result_metadata[r.url] = {
                "author_countries": r.author_countries,
                "publication_year": r.publication_year,
                "citation_count": r.citation_count,
                "authors": r.authors,
                "doi": r.doi,
            }

    # SOTA: Fetch all URLs for comprehensive coverage
    # Use config-driven limit for scalability
    config = get_config()
    max_urls = getattr(config.thresholds.search, 'max_urls_to_fetch', 200)
    if len(urls) > max_urls:
        print(f"[PHASE-4][{vector_id}][INFO] Limiting to {max_urls} URLs (found {len(urls)})")
        urls = urls[:max_urls]

    # 3. Fetch content (with academic paper support)
    print(f"[PHASE-4][{vector_id}][INFO] Fetching content from {len(urls)} URLs...")
    content_map, fetch_methods = await fetch_content_batch(urls, max_concurrent=10)

    # Count successes
    successful_fetches = sum(1 for url, result in content_map.items() if result.content and result.status == 200)

    print(f"[PHASE-4][{vector_id}][INFO] Successful fetches: {successful_fetches}/{len(urls)}")
    print(f"[PHASE-4][{vector_id}][INFO] Fetch methods: {fetch_methods}")

    # 4. Extract keywords and stage from vector_id
    # Vector ID format: S{stage}V{vector}_{application}_{region}
    # FIX BUG 1: Handle multi-word regions like NORTH_AMERICA, SOUTH_EAST_ASIA
    KNOWN_REGIONS = [
        "NORTH_AMERICA", "SOUTH_AMERICA", "LATIN_AMERICA", "CENTRAL_AMERICA",
        "EUROPE", "WESTERN_EUROPE", "EASTERN_EUROPE", "NORTHERN_EUROPE",
        "ASIA", "SOUTH_ASIA", "EAST_ASIA", "SOUTH_EAST_ASIA", "CENTRAL_ASIA",
        "AFRICA", "NORTH_AFRICA", "SUB_SAHARAN_AFRICA", "WEST_AFRICA", "EAST_AFRICA",
        "OCEANIA", "AUSTRALIA", "MIDDLE_EAST", "GLOBAL", "WORLDWIDE",
        "UNITED_STATES", "USA", "CANADA", "MEXICO", "UK", "CHINA", "INDIA",
    ]

    # Extract region by matching known regions at end of vector_id
    parts = vector_id.split("_")
    region = "GLOBAL"
    vector_upper = vector_id.upper()

    for known_region in sorted(KNOWN_REGIONS, key=len, reverse=True):  # Check longer regions first
        if vector_upper.endswith(known_region):
            region = known_region
            # Remove region parts from end to get application
            region_parts = known_region.split("_")
            num_region_parts = len(region_parts)
            application = "_".join(parts[1:-num_region_parts]) if len(parts) > num_region_parts + 1 else "Unknown"
            break
    else:
        # Fallback: last part is region (single word)
        application = "_".join(parts[1:-1]) if len(parts) > 2 else "Unknown"
        region = parts[-1] if parts else "GLOBAL"

    print(f"[PHASE-4][{vector_id}][INFO] Extracted region: {region}")
    question = f"What pathogen contamination rates and patterns exist in {application.replace('_', ' ')} for {region.replace('_', ' ')}?"
    keywords = extract_keywords(question)
    print(f"[PHASE-4][{vector_id}][INFO] Keywords: {keywords[:10]}...")

    # Parse stage from vector_id (S1V1 -> stage 1)
    stage = 1
    try:
        stage_str = parts[0]  # "S1V1" or similar
        stage = int(stage_str[1])  # Extract the digit after 'S'
    except (IndexError, ValueError):
        stage = 1

    # Initialize semantic chunker with stage-specific template
    semantic_chunker = get_chunker_for_stage(stage)
    print(f"[PHASE-4][{vector_id}][INFO] Semantic chunking: stage={stage}, template={semantic_chunker.template_name}, size={semantic_chunker.chunk_size}")

    # 5. Chunk content and score relevance
    # OPERATION GLASS HOUSE: Clean HTML before chunking
    # OPERATION DEEP DIVE: Use CrossEncoder for neural reranking
    all_chunks = []
    chunk_id_counter = 0
    off_topic_rejected_count = 0  # SOTA: Track chunks rejected by minimum relevance threshold
    titles_extracted = {}  # URL -> formatted citation title
    citation_metadata = {}  # URL -> {authors, year, doi}

    # Load embedding model for hard gate scoring
    embedding_model = load_embedding_model()
    if embedding_model:
        print(f"[PHASE-4][{vector_id}][INFO] Embedding hard gate ENABLED")
    else:
        print(f"[PHASE-4][{vector_id}][INFO] Embedding hard gate DISABLED (fallback to keywords)")

    # Load cross-encoder model for soft gate scoring
    cross_encoder_model = load_cross_encoder()
    use_neural_scoring = cross_encoder_model is not None
    if use_neural_scoring:
        print(f"[PHASE-4][{vector_id}][INFO] Neural reranking ENABLED (CrossEncoder)")
    else:
        print(f"[PHASE-4][{vector_id}][INFO] Neural reranking DISABLED (fallback to keywords)")

    # SOTA: Initialize spaCy for NER location extraction
    ner_enabled = load_spacy_model() is not None
    if ner_enabled:
        print(f"[PHASE-4][{vector_id}][INFO] SOTA: NER location extraction ENABLED")
    else:
        print(f"[PHASE-4][{vector_id}][INFO] SOTA: NER location extraction DISABLED")

    # SOTA: Initialize adaptive stopping rule
    stopping_rule = AdaptiveStoppingRule(
        min_gold_chunks=15,
        min_silver_chunks=30,
        min_total_chunks=50,
        max_chunks_total=500,
    )
    adaptive_stop_triggered = False

    for url, fetch_result in content_map.items():
        # SOTA: Check adaptive stopping rule
        if stopping_rule.should_stop():
            if not adaptive_stop_triggered:
                stop_status = stopping_rule.get_status()
                print(f"[PHASE-4][{vector_id}][SOTA] Adaptive stopping triggered: {stop_status['stop_reason']}")
                print(f"[PHASE-4][{vector_id}][SOTA] Current: gold={stop_status['gold_count']}, silver={stop_status['silver_count']}, total={stop_status['total_count']}")
                adaptive_stop_triggered = True
            break  # Stop processing more URLs

        if not fetch_result.content or fetch_result.status != 200:
            continue

        # Parse URL for fallback domain extraction
        from urllib.parse import urlparse
        parsed_url = urlparse(url)

        # CRITICAL: Strip HTML to get clean text
        clean_text, extracted_title = clean_html(fetch_result.content)

        # FIX: Use enhanced metadata extraction for HTML content
        # This properly handles PubMed/PMC pages and extracts authors, dates, DOIs
        html_metadata = extract_metadata_from_html(fetch_result.content, url)

        # SOTA: Source-level geographic filtering using API metadata
        # Priority: 1) author_countries from P3 (OpenAlex), 2) text-based tagging
        p3_metadata = search_result_metadata.get(url, {})
        api_author_countries = p3_metadata.get("author_countries")

        if api_author_countries:
            # SOTA: Use API-provided author country data (more accurate than text matching)
            geo_region, geo_confidence = derive_geo_region_from_countries(api_author_countries, region)
            geo_meta = {
                "region": geo_region,
                "countries": api_author_countries,
                "confidence": geo_confidence,
                "source": "api",  # Track that this came from API
            }
        else:
            # Fallback: Text-based geographic tagging
            geo_meta = tag_content_geography(
                url=url,
                text=clean_text[:3000],  # Sample for performance
                title=extracted_title or "",
            )
            geo_meta["source"] = "text"

        # Store citation metadata - prefer academic API data, fall back to HTML extraction
        # SOTA: Merge P3 metadata with fetch results and HTML extraction
        citation_metadata[url] = {
            "authors": fetch_result.authors or p3_metadata.get("authors") or ([html_metadata.author] if html_metadata.author and html_metadata.author != "Unknown" else None),
            "year": fetch_result.year or p3_metadata.get("publication_year") or (int(html_metadata.publication_date[:4]) if html_metadata.publication_date and html_metadata.publication_date[:4].isdigit() else None),
            "doi": fetch_result.doi or p3_metadata.get("doi") or html_metadata.doi or None,
            "citation_count": p3_metadata.get("citation_count"),  # SOTA: Citation count from API
            # SOTA: Geographic metadata (API-based or text-based)
            "geo_region": geo_meta.get("region", "GLOBAL"),
            "geo_countries": geo_meta.get("countries", []),
            "geo_confidence": geo_meta.get("confidence", 0.0),
            "geo_source": geo_meta.get("source", "unknown"),
        }

        # Format proper citation title
        # Priority: academic metadata > HTML metadata > HTML title > URL
        # FIX BUG 2: Check fetch_result.title for garbage before using
        if fetch_result.title and not _is_garbage_title(fetch_result.title):
            # Use academic paper title with authors/year if available
            titles_extracted[url] = format_citation_title(
                title=fetch_result.title,
                authors=fetch_result.authors,
                year=fetch_result.year,
                url=url,
            )
        elif html_metadata.title and html_metadata.title not in ["", "Unknown", "Untitled"]:
            # FIX: Use enhanced HTML metadata extraction
            # Skip bad titles like "References", "Author contributions", PMC IDs
            if not _is_garbage_title(html_metadata.title):
                titles_extracted[url] = html_metadata.title
            elif extracted_title and not _is_garbage_title(extracted_title):
                titles_extracted[url] = extracted_title
            else:
                # FIX: Also check URL-extracted title for garbage before using
                url_title = extract_title_from_url(url)
                if url_title and not _is_garbage_title(url_title):
                    titles_extracted[url] = url_title
                else:
                    # Use descriptive fallback with domain
                    titles_extracted[url] = f"Article from {parsed_url.netloc}"
        elif extracted_title and not _is_garbage_title(extracted_title):
            titles_extracted[url] = extracted_title
        else:
            # FIX: Also check URL-extracted title for garbage before using
            url_title = extract_title_from_url(url)
            if url_title and not _is_garbage_title(url_title):
                titles_extracted[url] = url_title
            else:
                # Use descriptive fallback with domain
                titles_extracted[url] = f"Article from {parsed_url.netloc}"

        # Skip if content is garbage after cleaning
        if is_garbage_content(clean_text):
            print(f"[PHASE-4][{vector_id}][WARN] Skipping garbage content from {url[:50]}...")
            continue

        # Use semantic chunking with stage-specific template
        chunks = semantic_chunker.chunk(clean_text)

        for chunk_text in chunks:
            # Additional garbage check per chunk
            if is_garbage_content(chunk_text):
                continue

            # IRON LOOP: SEO spam blacklist check (instant reject)
            if is_seo_spam(chunk_text):
                continue

            # Compute HARD gate score (embedding-based)
            hard_score = compute_embedding_similarity(question, chunk_text, embedding_model)

            # Compute SOFT gate score (neural cross-encoder)
            if use_neural_scoring:
                soft_score = compute_soft_score(question, chunk_text, cross_encoder_model)
                # Fuse scores: 0.4 * hard + 0.6 * soft
                fused_score = fuse_scores(hard_score, soft_score)
            else:
                # Fallback: use keyword score with boost
                fused_score = hard_score
                # Boost for certain indicators
                if any(indicator in chunk_text.lower() for indicator in ['contamination', 'pathogen', 'bacteria', 'filter']):
                    fused_score = min(1.0, fused_score + 0.15)

            # IRON LOOP: Apply domain-based score adjustment
            domain_adjustment = compute_domain_score_adjustment(url)
            fused_score = max(0.0, min(1.0, fused_score + domain_adjustment))

            # SOTA FIX: Hard minimum relevance threshold - reject clearly off-topic content
            # This catches content that scored above REJECTED tier but is semantically unrelated
            # (e.g., ophthalmology papers, cardiology papers for water filter question)
            MIN_RELEVANCE_THRESHOLD = 0.40
            if fused_score < MIN_RELEVANCE_THRESHOLD:
                off_topic_rejected_count += 1
                continue  # Skip this chunk entirely - it's off-topic

            # SOTA: Apply geographic relevance penalty
            # Uses pre-computed geographic metadata from ingestion
            chunk_title = titles_extracted.get(url, "")
            chunk_geo_meta = citation_metadata.get(url, {})
            geo_relevant, geo_penalty = check_geographic_relevance(
                chunk_text,
                region,
                title=chunk_title,
                url=url,
                geo_metadata=chunk_geo_meta,  # SOTA: Pass pre-computed metadata
            )
            if geo_penalty < 1.0:
                original_score = fused_score
                fused_score = fused_score * geo_penalty
                # BUG-008 FIX: HARD REJECT - skip chunk entirely for geographic mismatch
                # Previously only applied penalty but still included chunk
                if geo_penalty <= 0.0:
                    print(f"      [GEO-FILTER] HARD REJECT: {url[:50]}... (geographic mismatch, region={region})")
                    off_topic_rejected_count += 1  # Track as rejected
                    continue  # SKIP THIS CHUNK ENTIRELY
                elif geo_penalty < 0.5:
                    print(f"      [GEO-FILTER] Penalizing chunk from {url[:50]}... (penalty={geo_penalty:.2f})")

            tier = assign_relevance_tier(fused_score)

            # FIX: Get citation metadata early (needed for source quality scoring)
            chunk_meta = citation_metadata.get(url, {})

            # SOTA: Source quality scoring (PaperQA2 RCS Map)
            # Uses domain tier for fast sync scoring (async S2 API deferred to batch)
            source_quality_score = score_source_quality_sync(url=url, doi=chunk_meta.get("doi"))

            # Apply source quality weight to final score (20% weight)
            # High-quality sources get boost, low-quality get penalty
            quality_adjusted_score = fused_score * 0.80 + source_quality_score * 0.20
            quality_adjusted_score = max(0.0, min(1.0, quality_adjusted_score))

            # Re-evaluate tier with quality adjustment
            tier = assign_relevance_tier(quality_adjusted_score)

            # SOTA: RCS Map - Generate contextual summary (extractive, no LLM)
            chunk_id_str = f"chunk_{chunk_id_counter:05d}"
            ctx_summary = _extractive_contextual_summary(chunk_text, question, chunk_id_str)

            # SOTA: NER-based study location extraction
            ner_location = {}
            if ner_enabled:
                ner_location = extract_study_location_ner(chunk_text)

            chunk_data = {
                "chunk_id": chunk_id_str,
                "source_url": url,
                "title": titles_extracted.get(url, ""),  # OPERATION GLASS HOUSE: Include title
                "author": _format_authors(chunk_meta.get("authors")),  # FIX: Add author
                "publication_date": str(chunk_meta.get("year", "")) if chunk_meta.get("year") else "",  # FIX: Add date
                "doi": chunk_meta.get("doi", ""),  # FIX: Add DOI
                # SOTA: Geographic metadata from ingestion
                "geo_region": chunk_meta.get("geo_region", "GLOBAL"),
                "geo_countries": chunk_meta.get("geo_countries", []),
                "geo_confidence": chunk_meta.get("geo_confidence", 0.0),
                "text": chunk_text[:2000],  # Truncate very long chunks
                "relevance_score": round(quality_adjusted_score, 4),  # SOTA: Use quality-adjusted score
                "hard_score": round(hard_score, 4),
                "soft_score": round(soft_score if use_neural_scoring else 0.0, 4),
                "relevance_tier": tier.value,
                "content_hash": hashlib.md5(chunk_text.encode()).hexdigest()[:16],
                # SOTA: New fields for RCS Map
                "source_quality_score": round(source_quality_score, 4),
                "contextual_summary": ctx_summary.contextual_summary[:300] if ctx_summary.contextual_summary else "",
                "key_claims": ctx_summary.key_claims[:3],  # Top 3 claims
                # SOTA: NER-based study location (from upgrade plan)
                "study_locations": ner_location.get("locations", []),
                "study_countries": ner_location.get("countries", []),
                "ner_confidence": ner_location.get("confidence", 0.0),
            }

            all_chunks.append(chunk_data)
            chunk_id_counter += 1

            # SOTA: Track chunk in adaptive stopping rule
            stopping_rule.record_chunk(tier.value)

    print(f"[PHASE-4][{vector_id}][INFO] Total chunks: {len(all_chunks)}")
    print(f"[PHASE-4][{vector_id}][INFO] Off-topic rejected (corpus pollution): {off_topic_rejected_count}")

    # SOTA: Log adaptive stopping status
    stop_status = stopping_rule.get_status()
    print(f"[PHASE-4][{vector_id}][SOTA] Adaptive stopping: triggered={stop_status['stopped']}, reason={stop_status['stop_reason'] or 'N/A'}")
    print(f"[PHASE-4][{vector_id}][SOTA] Quality tiers: gold={stop_status['gold_count']}, silver={stop_status['silver_count']}")

    # 6. Filter chunks (keep bronze and above)
    filtered_chunks = [c for c in all_chunks if c["relevance_tier"] != RelevanceTier.REJECTED.value]
    rejected_count = len(all_chunks) - len(filtered_chunks)

    # 7. Calculate tier distribution
    tier_distribution = defaultdict(int)
    relevance_scores = []

    for chunk in all_chunks:
        tier_distribution[chunk["relevance_tier"]] += 1
        relevance_scores.append(chunk["relevance_score"])

    print(f"[PHASE-4][{vector_id}][INFO] Tier distribution: {dict(tier_distribution)}")

    # Audit: Log URL fetches and chunks
    if audit:
        # Log URL fetches
        for url, result in content_map.items():
            if result:
                audit.log_url_fetch(
                    url=url,
                    method=result.method,
                    status_code=result.status,
                    success=result.status == 200,
                    content_size=len(result.content) if result.content else 0,
                )

        # Log chunks
        for chunk in all_chunks:
            audit.log_chunk(
                chunk_id=chunk["chunk_id"],
                source_url=chunk["source_url"],
                text_preview=chunk["text"][:200] if chunk.get("text") else "",
                relevance_score=chunk.get("relevance_score", 0.0),
                relevance_tier=chunk.get("relevance_tier", "unknown"),
            )

    timestamps["end"] = datetime.now(timezone.utc).isoformat()

    # 8. Calculate fetch statistics
    urls_attempted = len(urls)
    urls_successful = successful_fetches
    urls_failed = urls_attempted - urls_successful
    fetch_success_rate = urls_successful / urls_attempted if urls_attempted > 0 else 0.0

    print(f"[PHASE-4][{vector_id}][INFO] Fetch stats: {urls_successful}/{urls_attempted} ({fetch_success_rate:.1%})")
    print(f"[PHASE-4][{vector_id}][INFO] Chunks passed: {len(filtered_chunks)}")

    # SOTA: Calculate corpus relevance score (percentage of chunks that passed minimum threshold)
    # High score = clean corpus, low score = significant pollution
    total_chunks_considered = len(all_chunks) + off_topic_rejected_count
    corpus_relevance = 1.0 - (off_topic_rejected_count / total_chunks_considered) if total_chunks_considered > 0 else 1.0
    print(f"[PHASE-4][{vector_id}][INFO] Corpus relevance score: {corpus_relevance:.2%}")

    # 9. Build output
    output = Phase4Output(
        vector_id=vector_id,
        urls_attempted=urls_attempted,
        urls_successful=urls_successful,
        urls_failed=urls_failed,
        fetch_success_rate=round(fetch_success_rate, 4),
        fetch_methods=dict(fetch_methods),
        chunks_input=len(all_chunks),
        chunks_passed=len(filtered_chunks),
        chunks_rejected=rejected_count,
        off_topic_rejected=off_topic_rejected_count,
        corpus_relevance_score=round(corpus_relevance, 4),
        tier_distribution=dict(tier_distribution),
        relevance_scores=relevance_scores,
        filtered_chunks=filtered_chunks,
        timestamps=timestamps,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 4 self-tests.

    Tests:
    1. Chunking logic
    2. Keyword extraction
    3. Relevance scoring
    4. Tier assignment
    """
    print("Running Phase 4 self-tests...")

    # Test 1: Chunking
    try:
        content = "This is the first sentence. This is the second sentence. This is the third sentence. " * 50
        chunks = chunk_content(content, chunk_size=200, chunk_overlap=50)
        assert len(chunks) > 1
        print(f"  Chunks created: {len(chunks)}")
        print("  [PASS] Chunking logic")
    except Exception as e:
        print(f"  [FAIL] Chunking logic: {e}")
        return False

    # Test 2: Keyword extraction
    try:
        question = "What pathogen contamination rates exist in household water filters for North America?"
        keywords = extract_keywords(question)
        assert "pathogen" in keywords
        assert "contamination" in keywords
        assert "water" in keywords
        assert "filters" in keywords
        print(f"  Keywords: {keywords}")
        print("  [PASS] Keyword extraction")
    except Exception as e:
        print(f"  [FAIL] Keyword extraction: {e}")
        return False

    # Test 3: Relevance scoring
    try:
        chunk = "Studies show pathogen contamination in household water filters increases with age."
        keywords = ["pathogen", "contamination", "water", "filters", "household"]
        score = compute_keyword_relevance(chunk, keywords)
        assert 0.6 <= score <= 1.0  # Should have high score
        print(f"  Relevance score: {score}")
        print("  [PASS] Relevance scoring")
    except Exception as e:
        print(f"  [FAIL] Relevance scoring: {e}")
        return False

    # Test 4: Tier assignment (using config-driven thresholds)
    # SOTA FIX: Updated thresholds - gold >= 0.55, silver >= 0.40, bronze >= 0.25
    try:
        assert assign_relevance_tier(0.75) == RelevanceTier.GOLD
        assert assign_relevance_tier(0.60) == RelevanceTier.GOLD  # >= 0.55
        assert assign_relevance_tier(0.45) == RelevanceTier.SILVER  # >= 0.40
        assert assign_relevance_tier(0.30) == RelevanceTier.BRONZE  # >= 0.25
        assert assign_relevance_tier(0.20) == RelevanceTier.REJECTED  # < 0.25
        print("  [PASS] Tier assignment")
    except Exception as e:
        print(f"  [FAIL] Tier assignment: {e}")
        return False

    print("\nAll Phase 4 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def find_latest_p3_output(vector_id: str) -> Optional[Path]:
    """Find the most recent Phase 3 output for a vector."""
    p3_dir = OUTPUTS_DIR / "P3"
    if not p3_dir.exists():
        return None

    pattern = f"{vector_id}__P3__*.json"
    matches = sorted(p3_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 4: Relevance Filtering"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to Phase 3 output JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P4"),
        help="Output directory"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode"
    )

    args = parser.parse_args()

    # Self-test mode
    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    # Normal execution requires vector-id
    if not args.vector_id:
        parser.error("--vector-id is required (unless using --self-test)")

    # Find input file
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_latest_p3_output(args.vector_id)
        if not input_path:
            print(f"[PHASE-4][{args.vector_id}][ERROR] No Phase 3 output found")
            sys.exit(1)

    if not input_path.exists():
        print(f"[PHASE-4][{args.vector_id}][ERROR] Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=4,
        status="running",
        attempt=1,
        input_paths=[str(input_path)]
    )

    try:
        # Execute phase
        print(f"[PHASE-4][{args.vector_id}][INFO] Starting relevance filtering...")
        print(f"[PHASE-4][{args.vector_id}][INFO] Input: {input_path}")

        output = asyncio.run(run_phase4(args.vector_id, input_path, output_dir))

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P4__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-4][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-4][{args.vector_id}][INFO] Chunks input: {output.chunks_input}")
        print(f"[PHASE-4][{args.vector_id}][INFO] Chunks passed: {output.chunks_passed}")
        print(f"[PHASE-4][{args.vector_id}][INFO] Tier distribution: {output.tier_distribution}")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=4,
            status="completed",
            attempt=1,
            input_paths=[str(input_path)],
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-4][{args.vector_id}][ERROR] {e}")
        import traceback
        traceback.print_exc()

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=4,
            status="failed",
            attempt=1,
            input_paths=[str(input_path)],
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
