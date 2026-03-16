#!/usr/bin/env python3
"""
POLARIS CrossRef API Integration Module
=======================================
Provides deterministic citation resolution via CrossRef API.

CrossRef is the official DOI registration agency that provides metadata
for scholarly publications. Using CrossRef ensures consistent, authoritative
citation metadata rather than scraping HTML.

API Documentation: https://api.crossref.org/swagger-ui/index.html

Usage:
    from src.utils.crossref_resolver import CrossRefResolver, resolve_doi

    resolver = CrossRefResolver()
    metadata = await resolver.resolve_doi("10.1021/acs.est.5b00716")
    # Returns: {"title": "...", "authors": [...], "year": 2015, ...}
"""

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp
import logging

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

CROSSREF_API_BASE = "https://api.crossref.org"
CROSSREF_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds

# User-Agent for polite pool (faster rate limit)
# Format: "AppName/Version (URL; mailto:email)"
USER_AGENT = "POLARIS-ResearchPipeline/1.0 (https://github.com/polaris; mailto:research@example.com)"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CrossRefCitation:
    """Structured citation metadata from CrossRef."""
    doi: str
    title: str
    authors: List[str] = field(default_factory=list)
    publication_date: Optional[str] = None  # ISO format
    year: Optional[int] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    type: Optional[str] = None  # journal-article, book-chapter, etc.
    url: Optional[str] = None
    abstract: Optional[str] = None
    subject_areas: List[str] = field(default_factory=list)
    references_count: int = 0
    cited_by_count: int = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "publication_date": self.publication_date,
            "year": self.year,
            "journal": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "publisher": self.publisher,
            "type": self.type,
            "url": self.url,
            "abstract": self.abstract,
            "subject_areas": self.subject_areas,
            "references_count": self.references_count,
            "cited_by_count": self.cited_by_count,
        }

    def format_citation(self, style: str = "apa") -> str:
        """
        Format citation in specified style.

        Args:
            style: Citation style ("apa", "mla", "chicago")

        Returns:
            Formatted citation string
        """
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."

        year_str = f"({self.year})" if self.year else "(n.d.)"

        if style == "apa":
            # APA: Author(s) (Year). Title. Journal, Volume(Issue), Pages. DOI
            parts = [authors_str, year_str, self.title]
            if self.journal:
                journal_part = self.journal
                if self.volume:
                    journal_part += f", {self.volume}"
                    if self.issue:
                        journal_part += f"({self.issue})"
                if self.pages:
                    journal_part += f", {self.pages}"
                parts.append(journal_part)
            parts.append(f"https://doi.org/{self.doi}")
            return ". ".join(parts)

        elif style == "mla":
            # MLA: Author(s). "Title." Journal, vol. X, no. Y, Year, pp. Z.
            parts = [authors_str, f'"{self.title}."']
            if self.journal:
                parts.append(f"{self.journal},")
                if self.volume:
                    parts.append(f"vol. {self.volume},")
                if self.issue:
                    parts.append(f"no. {self.issue},")
            if self.year:
                parts.append(f"{self.year},")
            if self.pages:
                parts.append(f"pp. {self.pages}.")
            return " ".join(parts)

        else:  # chicago
            # Chicago: Author(s). "Title." Journal Volume, no. Issue (Year): Pages.
            parts = [authors_str, f'"{self.title}."']
            if self.journal:
                parts.append(self.journal)
                if self.volume:
                    parts.append(str(self.volume))
                if self.issue:
                    parts.append(f", no. {self.issue}")
                if self.year:
                    parts.append(f" ({self.year})")
                if self.pages:
                    parts.append(f": {self.pages}")
            return " ".join(parts) + "."


# =============================================================================
# CROSSREF RESOLVER CLASS
# =============================================================================

class CrossRefResolver:
    """
    Resolves citations via CrossRef API.

    Provides deterministic, authoritative citation metadata for DOIs.
    """

    def __init__(self, email: Optional[str] = None):
        """
        Initialize CrossRef resolver.

        Args:
            email: Contact email for polite pool (faster rate limits)
        """
        self.email = email or os.environ.get("CROSSREF_EMAIL", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, CrossRefCitation] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {"User-Agent": USER_AGENT}
            if self.email:
                headers["User-Agent"] += f" mailto:{self.email}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def resolve_doi(self, doi: str) -> Optional[CrossRefCitation]:
        """
        Resolve DOI to citation metadata via CrossRef.

        Args:
            doi: DOI string (e.g., "10.1021/acs.est.5b00716")

        Returns:
            CrossRefCitation object or None if not found
        """
        # Normalize DOI
        doi = self._normalize_doi(doi)
        if not doi:
            return None

        # Check cache
        if doi in self._cache:
            return self._cache[doi]

        # Call CrossRef API
        session = await self._get_session()
        url = f"{CROSSREF_API_BASE}/works/{quote(doi, safe='')}"

        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url, timeout=CROSSREF_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        citation = self._parse_response(doi, data)
                        self._cache[doi] = citation
                        return citation
                    elif response.status == 404:
                        return None  # DOI not found
                    elif response.status == 429:
                        # Rate limited
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        # LOW-015: Log error instead of print
                        logger.debug(f"CrossRef unexpected status {response.status} for {doi}")
                        return None

            except asyncio.TimeoutError:
                # LOW-016: Log error instead of print
                logger.debug(f"CrossRef timeout for {doi} (attempt {attempt + 1})")
                await asyncio.sleep(RETRY_DELAY)
            except aiohttp.ClientError as e:
                # LOW-017: Log error instead of print
                logger.debug(f"CrossRef client error for {doi}: {e}")
                return None

        return None

    async def resolve_many(
        self,
        dois: List[str],
        max_concurrent: int = 5,
    ) -> Dict[str, Optional[CrossRefCitation]]:
        """
        Resolve multiple DOIs concurrently.

        Args:
            dois: List of DOIs to resolve
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict mapping DOI -> CrossRefCitation (or None if not found)
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results: Dict[str, Optional[CrossRefCitation]] = {}

        async def resolve_with_semaphore(doi: str) -> tuple[str, Optional[CrossRefCitation]]:
            async with semaphore:
                result = await self.resolve_doi(doi)
                return doi, result

        tasks = [resolve_with_semaphore(doi) for doi in dois]
        for doi, citation in await asyncio.gather(*tasks):
            results[doi] = citation

        return results

    async def search(
        self,
        query: str,
        rows: int = 10,
        filter_type: Optional[str] = None,
    ) -> List[CrossRefCitation]:
        """
        Search CrossRef for works matching query.

        Args:
            query: Search query
            rows: Maximum results to return
            filter_type: Filter by type (e.g., "journal-article")

        Returns:
            List of CrossRefCitation objects
        """
        session = await self._get_session()
        url = f"{CROSSREF_API_BASE}/works"

        params = {
            "query": query,
            "rows": str(rows),
        }
        if filter_type:
            params["filter"] = f"type:{filter_type}"

        try:
            async with session.get(url, params=params, timeout=CROSSREF_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("message", {}).get("items", [])
                    citations = []
                    for item in items:
                        doi = item.get("DOI", "")
                        if doi:
                            citation = self._parse_work_item(doi, item)
                            citations.append(citation)
                    return citations
                else:
                    return []

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            # LOW-018: Log error instead of print
            logger.debug(f"CrossRef search error: {e}")
            return []

    def _normalize_doi(self, doi: str) -> Optional[str]:
        """Normalize DOI string."""
        if not doi:
            return None

        # Remove common prefixes
        doi = doi.strip()
        doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
        doi = re.sub(r'^doi:\s*', '', doi, flags=re.I)

        # Validate DOI format
        if not re.match(r'^10\.\d{4,}/[^\s]+$', doi):
            return None

        return doi

    def _parse_response(self, doi: str, data: Dict[str, Any]) -> CrossRefCitation:
        """Parse CrossRef API response."""
        message = data.get("message", {})
        return self._parse_work_item(doi, message)

    def _parse_work_item(self, doi: str, item: Dict[str, Any]) -> CrossRefCitation:
        """Parse a single work item from CrossRef."""
        # Extract authors
        authors = []
        for author in item.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)
            elif author.get("name"):
                authors.append(author["name"])

        # Extract publication date
        pub_date = None
        year = None
        date_parts = item.get("published-print", {}).get("date-parts", [[]])
        if not date_parts or not date_parts[0]:
            date_parts = item.get("published-online", {}).get("date-parts", [[]])
        if not date_parts or not date_parts[0]:
            date_parts = item.get("created", {}).get("date-parts", [[]])

        if date_parts and date_parts[0]:
            parts = date_parts[0]
            year = parts[0] if len(parts) > 0 else None
            month = parts[1] if len(parts) > 1 else 1
            day = parts[2] if len(parts) > 2 else 1
            try:
                pub_date = datetime(year, month, day).isoformat()[:10]
            except (ValueError, TypeError):
                pub_date = None

        # Extract title
        title_list = item.get("title", [])
        title = title_list[0] if title_list else "Untitled"

        # Extract journal
        journal_list = item.get("container-title", [])
        journal = journal_list[0] if journal_list else None

        # Extract subject areas
        subjects = item.get("subject", [])

        return CrossRefCitation(
            doi=doi,
            title=title,
            authors=authors,
            publication_date=pub_date,
            year=year,
            journal=journal,
            volume=item.get("volume"),
            issue=item.get("issue"),
            pages=item.get("page"),
            publisher=item.get("publisher"),
            type=item.get("type"),
            url=item.get("URL"),
            abstract=item.get("abstract", "")[:500] if item.get("abstract") else None,
            subject_areas=subjects,
            references_count=item.get("references-count", 0),
            cited_by_count=item.get("is-referenced-by-count", 0),
            raw_response=item,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def resolve_doi(doi: str) -> Optional[CrossRefCitation]:
    """
    Resolve a single DOI via CrossRef.

    Convenience function for one-off resolution.

    Args:
        doi: DOI string

    Returns:
        CrossRefCitation or None
    """
    resolver = CrossRefResolver()
    try:
        return await resolver.resolve_doi(doi)
    finally:
        await resolver.close()


def resolve_doi_sync(doi: str) -> Optional[CrossRefCitation]:
    """
    Synchronous wrapper for resolve_doi.

    Args:
        doi: DOI string

    Returns:
        CrossRefCitation or None
    """
    return asyncio.run(resolve_doi(doi))


def extract_doi_from_url(url: str) -> Optional[str]:
    """
    Extract DOI from a URL.

    Args:
        url: URL that may contain a DOI

    Returns:
        Extracted DOI or None
    """
    # Pattern for DOI in URL
    patterns = [
        r'doi\.org/(10\.\d{4,}/[^\s?#]+)',
        r'/doi/(10\.\d{4,}/[^\s?#]+)',
        r'doi[=/](10\.\d{4,}/[^\s?#]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.I)
        if match:
            return match.group(1)

    return None


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("CROSSREF RESOLVER MODULE SELF-TEST")
    print("=" * 60)

    async def run_tests():
        resolver = CrossRefResolver()

        # Test 1: Resolve a known DOI
        print("\n[TEST 1] Resolving known DOI...")
        test_doi = "10.1038/nature12373"  # Famous Higgs boson paper
        citation = await resolver.resolve_doi(test_doi)

        if citation:
            print(f"  [PASS] Resolved DOI: {test_doi}")
            print(f"    Title: {citation.title[:60]}...")
            print(f"    Authors: {', '.join(citation.authors[:3])}...")
            print(f"    Year: {citation.year}")
            print(f"    Journal: {citation.journal}")
            print(f"    Cited by: {citation.cited_by_count}")
        else:
            print(f"  [FAIL] Could not resolve DOI: {test_doi}")

        # Test 2: DOI extraction from URL
        print("\n[TEST 2] DOI extraction from URLs...")
        test_urls = [
            ("https://doi.org/10.1021/acs.est.5b00716", "10.1021/acs.est.5b00716"),
            ("https://www.nature.com/articles/10.1038/nature12373", None),  # Not in path
            ("https://dx.doi.org/10.1016/j.watres.2020.115551", "10.1016/j.watres.2020.115551"),
        ]

        for url, expected in test_urls:
            extracted = extract_doi_from_url(url)
            status = "PASS" if extracted == expected else "FAIL"
            print(f"  [{status}] {url[:40]}... -> {extracted}")

        # Test 3: Invalid DOI
        print("\n[TEST 3] Invalid DOI handling...")
        invalid_result = await resolver.resolve_doi("invalid-doi")
        status = "PASS" if invalid_result is None else "FAIL"
        print(f"  [{status}] Invalid DOI returns None: {invalid_result is None}")

        # Test 4: Citation formatting
        print("\n[TEST 4] Citation formatting...")
        if citation:
            apa = citation.format_citation("apa")
            print(f"  APA: {apa[:100]}...")

        await resolver.close()

    asyncio.run(run_tests())

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
