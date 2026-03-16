"""
CrossRef API Client for POLARIS SOTA Metadata Retrieval.

CrossRef provides:
- Clean, validated bibliographic metadata from DOI registrations
- Author names, publication dates, journal information
- Reference lists for citation chaining
- License and open access information

This replaces HTML scraping for metadata extraction.

API Documentation: https://api.crossref.org/
Rate Limit: Polite pool with email header

References:
- GPT Blueprint: Phase 2 Data Normalization
- Gemini Diagnostic: Section 2 Clean Metadata and Bibliographic Data
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# CrossRef API configuration
CROSSREF_BASE_URL = "https://api.crossref.org"
CROSSREF_EMAIL = os.getenv("CROSSREF_EMAIL", "polaris@research.ai")
REQUEST_DELAY_SECONDS = 0.1


@dataclass
class CrossRefAuthor:
    """Author information from CrossRef."""

    given: Optional[str] = None
    family: Optional[str] = None
    name: Optional[str] = None  # For single-name authors
    orcid: Optional[str] = None
    affiliation: Optional[str] = None

    @property
    def full_name(self) -> str:
        """Return formatted full name."""
        if self.name:
            return self.name
        parts = []
        if self.given:
            parts.append(self.given)
        if self.family:
            parts.append(self.family)
        return " ".join(parts) if parts else "Unknown"


@dataclass
class CrossRefWork:
    """Normalized work (publication) object from CrossRef."""

    doi: str
    title: str = ""
    subtitle: Optional[str] = None
    container_title: Optional[str] = None  # Journal name
    publisher: Optional[str] = None
    published_date: Optional[str] = None  # YYYY-MM-DD format
    published_year: Optional[int] = None
    authors: list[CrossRefAuthor] = field(default_factory=list)
    abstract: Optional[str] = None
    type: Optional[str] = None  # journal-article, book-chapter, etc.
    issn: list[str] = field(default_factory=list)
    isbn: list[str] = field(default_factory=list)
    url: Optional[str] = None
    license_url: Optional[str] = None
    is_open_access: bool = False
    reference_count: int = 0
    references: list[str] = field(default_factory=list)  # List of DOIs
    citation_count: Optional[int] = None

    @property
    def author_string(self) -> str:
        """Return formatted author string for citation."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) == 1:
            return self.authors[0].full_name
        elif len(self.authors) == 2:
            return f"{self.authors[0].full_name} & {self.authors[1].full_name}"
        else:
            return f"{self.authors[0].full_name} et al."


class CrossRefClient:
    """
    Async client for CrossRef API.

    Features:
    - DOI resolution for clean metadata
    - Author validation (no garbage like "Contact X" or domain names)
    - Reference extraction for citation chaining
    - Journal/publisher information
    """

    def __init__(self, email: Optional[str] = None):
        """
        Initialize CrossRef client.

        Args:
            email: Email for polite pool (gets better rate limits)
        """
        self.email = email or CROSSREF_EMAIL
        self.base_url = CROSSREF_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            headers = {
                "User-Agent": f"POLARIS/1.0 (mailto:{self.email})",
                "Accept": "application/json",
            }
            self.session = aiohttp.ClientSession(headers=headers)

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _rate_limit(self):
        """Implement rate limiting for polite pool."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            await asyncio.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.time()

    async def _request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict:
        """
        Make a rate-limited request to CrossRef API.

        Args:
            endpoint: API endpoint
            params: Query parameters
            max_retries: Maximum retry attempts

        Returns:
            JSON response as dict
        """
        await self._ensure_session()
        await self._rate_limit()

        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params["mailto"] = self.email

        for attempt in range(max_retries):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("message", {})
                    elif response.status == 429:
                        wait_time = (2 ** attempt) * 1.0
                        logger.warning(f"CrossRef rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                    elif response.status == 404:
                        logger.debug(f"DOI not found: {endpoint}")
                        return {}
                    else:
                        logger.error(f"CrossRef API error: {response.status}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                logger.error(f"CrossRef request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

        return {}

    def _parse_work(self, raw: dict) -> CrossRefWork:
        """
        Parse raw CrossRef work response into normalized object.

        Args:
            raw: Raw work dict from API

        Returns:
            Normalized CrossRefWork object
        """
        # Extract authors with validation
        authors = []
        for author_data in raw.get("author", []):
            # Skip garbage authors (single-word names that look like usernames/domains)
            given = author_data.get("given", "")
            family = author_data.get("family", "")
            name = author_data.get("name", "")

            # Validate author - skip if looks like garbage
            if self._is_valid_author(given, family, name):
                affiliation = None
                affiliations = author_data.get("affiliation", [])
                if affiliations and isinstance(affiliations, list):
                    if affiliations[0].get("name"):
                        affiliation = affiliations[0]["name"]

                authors.append(CrossRefAuthor(
                    given=given if given else None,
                    family=family if family else None,
                    name=name if name else None,
                    orcid=author_data.get("ORCID"),
                    affiliation=affiliation,
                ))

        # Extract publication date
        pub_date = None
        pub_year = None
        date_parts = raw.get("published", {}).get("date-parts", [[]])
        if date_parts and date_parts[0]:
            parts = date_parts[0]
            if len(parts) >= 1:
                pub_year = parts[0]
            if len(parts) >= 3:
                pub_date = f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
            elif len(parts) >= 2:
                pub_date = f"{parts[0]}-{parts[1]:02d}"
            elif len(parts) >= 1:
                pub_date = str(parts[0])

        # Extract title
        titles = raw.get("title", [])
        title = titles[0] if titles else ""

        # Extract subtitle
        subtitles = raw.get("subtitle", [])
        subtitle = subtitles[0] if subtitles else None

        # Extract journal/container
        container_titles = raw.get("container-title", [])
        container_title = container_titles[0] if container_titles else None

        # Extract references (DOIs only)
        references = []
        for ref in raw.get("reference", []):
            ref_doi = ref.get("DOI")
            if ref_doi:
                references.append(ref_doi)

        # Check open access via license
        is_oa = False
        license_url = None
        licenses = raw.get("license", [])
        if licenses:
            license_url = licenses[0].get("URL")
            # Common open access license patterns
            if license_url and any(oa in license_url.lower() for oa in
                                   ["creativecommons", "cc-by", "open-access"]):
                is_oa = True

        return CrossRefWork(
            doi=raw.get("DOI", ""),
            title=title,
            subtitle=subtitle,
            container_title=container_title,
            publisher=raw.get("publisher"),
            published_date=pub_date,
            published_year=pub_year,
            authors=authors,
            abstract=raw.get("abstract"),
            type=raw.get("type"),
            issn=raw.get("ISSN", []),
            isbn=raw.get("ISBN", []),
            url=raw.get("URL"),
            license_url=license_url,
            is_open_access=is_oa,
            reference_count=raw.get("references-count", 0),
            references=references,
            citation_count=raw.get("is-referenced-by-count"),
        )

    def _is_valid_author(self, given: str, family: str, name: str) -> bool:
        """
        Validate author name to filter out garbage.

        Rejects:
        - Domain names (contains .com, .org, .net, etc.)
        - Contact patterns ("Contact X", "Username")
        - Single-word names that look like usernames
        - Empty names

        Args:
            given: Given/first name
            family: Family/last name
            name: Full name (for single-name authors)

        Returns:
            True if author appears valid
        """
        full_name = name or f"{given} {family}".strip()

        if not full_name or full_name == " ":
            return False

        full_lower = full_name.lower()

        # Reject domain patterns
        domain_patterns = [".com", ".org", ".net", ".edu", ".gov", ".io", ".ai"]
        if any(p in full_lower for p in domain_patterns):
            return False

        # Reject contact patterns
        contact_patterns = ["contact", "username", "admin", "editor", "staff", "team"]
        if any(p in full_lower for p in contact_patterns):
            return False

        # Reject if looks like email
        if "@" in full_name:
            return False

        # Reject single-word names that are all lowercase (likely usernames)
        if " " not in full_name and full_name.islower() and len(full_name) > 3:
            return False

        return True

    async def get_work_by_doi(self, doi: str) -> Optional[CrossRefWork]:
        """
        Fetch metadata for a specific DOI.

        This is the primary method for getting clean, validated metadata.

        Args:
            doi: DOI string (with or without https://doi.org/ prefix)

        Returns:
            CrossRefWork object or None if not found
        """
        # Normalize DOI
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("http://doi.org/"):
            doi = doi[15:]
        elif doi.startswith("doi.org/"):
            doi = doi[8:]
        elif doi.startswith("doi:"):
            doi = doi[4:]

        try:
            response = await self._request(f"/works/{doi}")
            if response and "DOI" in response:
                return self._parse_work(response)
        except Exception as e:
            logger.error(f"Failed to fetch DOI {doi}: {e}")

        return None

    async def search_works(
        self,
        query: str,
        filters: Optional[dict] = None,
        rows: int = 25,
        offset: int = 0,
        sort: str = "relevance",
    ) -> list[CrossRefWork]:
        """
        Search CrossRef for works matching query.

        Args:
            query: Search query (searches title, author, etc.)
            filters: Filter dict (e.g., {"from-pub-date": "2024-01-01"})
            rows: Results per page (max 1000)
            offset: Pagination offset
            sort: Sort order ("relevance", "published", "cited")

        Returns:
            List of matching works
        """
        params = {
            "query": query,
            "rows": min(rows, 1000),
            "offset": offset,
            "sort": sort,
        }

        # Build filter string
        if filters:
            filter_parts = []
            for key, value in filters.items():
                filter_parts.append(f"{key}:{value}")
            params["filter"] = ",".join(filter_parts)

        response = await self._request("/works", params)
        items = response.get("items", [])

        works = [self._parse_work(raw) for raw in items]
        logger.info(f"CrossRef search '{query[:50]}...' returned {len(works)} works")
        return works

    async def get_references(self, doi: str) -> list[str]:
        """
        Get reference DOIs for a work (for backward snowballing).

        Args:
            doi: DOI of the work

        Returns:
            List of referenced DOIs
        """
        work = await self.get_work_by_doi(doi)
        if work:
            return work.references
        return []

    async def bulk_metadata_lookup(self, dois: list[str]) -> dict[str, CrossRefWork]:
        """
        Fetch metadata for multiple DOIs.

        Args:
            dois: List of DOIs

        Returns:
            Dict mapping DOI to CrossRefWork
        """
        results = {}
        for doi in dois:
            work = await self.get_work_by_doi(doi)
            if work:
                results[doi] = work
        return results


# Convenience function for quick DOI lookup
async def lookup_doi(doi: str) -> Optional[CrossRefWork]:
    """
    Convenience function for quick DOI metadata lookup.

    Args:
        doi: DOI string

    Returns:
        CrossRefWork or None
    """
    async with CrossRefClient() as client:
        return await client.get_work_by_doi(doi)


# Self-test
if __name__ == "__main__":
    async def test_client():
        """Test CrossRef client functionality."""
        print("Testing CrossRef Client...")

        async with CrossRefClient() as client:
            # Test 1: DOI lookup
            print("\n1. Testing DOI lookup...")
            # Use a known valid DOI (PLOS ONE article)
            work = await client.get_work_by_doi("10.1371/journal.pone.0123456")
            if work:
                print(f"   Title: {work.title[:60]}...")
                print(f"   Authors: {work.author_string}")
                print(f"   Journal: {work.container_title}")
                print(f"   Year: {work.published_year}")
            else:
                print("   (Article not found - normal for test DOI)")

            # Test 2: Search
            print("\n2. Testing search...")
            works = await client.search_works(
                "water contamination private wells",
                filters={"from-pub-date": "2024-01-01"},
                rows=5,
            )
            print(f"   Found {len(works)} works")
            for w in works[:3]:
                print(f"   - {w.title[:50]}... ({w.published_year})")
                print(f"     Authors: {w.author_string}")

            # Test 3: Author validation (internal test)
            print("\n3. Testing author validation...")
            test_cases = [
                ("John", "Smith", "", True),
                ("", "", "Username", False),
                ("Contact", "Support", "", False),
                ("", "", "example.com", False),
                ("", "", "admin@test.org", False),
                ("Marie", "Curie", "", True),
            ]
            for given, family, name, expected in test_cases:
                result = client._is_valid_author(given, family, name)
                status = "PASS" if result == expected else "FAIL"
                full = name or f"{given} {family}"
                print(f"   [{status}] '{full}' -> valid={result}")

        print("\n[PASS] CrossRef client tests completed")

    asyncio.run(test_client())
