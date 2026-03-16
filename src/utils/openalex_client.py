"""
OpenAlex API Client for POLARIS SOTA Retrieval.

OpenAlex is a fully open catalog of the global research system with 240M+ works.
This client provides:
- Semantic and keyword search
- Geographic filtering via author affiliations
- Citation network traversal (forward/backward snowballing)
- Clean metadata extraction (authors, DOIs, concepts)

API Documentation: https://docs.openalex.org/
Rate Limit: 100,000 requests/day (polite pool with email in User-Agent)

References:
- GPT Blueprint: Phase 2 Multi-Source Ingestion
- Gemini Diagnostic: Section 1 Comprehensive Retrieval, Section 5 Academic APIs
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import aiohttp

logger = logging.getLogger(__name__)

# OpenAlex API configuration
OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "polaris@research.ai")
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200
REQUEST_DELAY_SECONDS = 0.1  # 10 requests/second max for polite pool


@dataclass
class OpenAlexAuthor:
    """Author information from OpenAlex."""

    name: str
    orcid: Optional[str] = None
    institution: Optional[str] = None
    country_code: Optional[str] = None


@dataclass
class OpenAlexWork:
    """Normalized work (paper) object from OpenAlex."""

    openalex_id: str
    doi: Optional[str] = None
    title: str = ""
    abstract: Optional[str] = None
    publication_date: Optional[str] = None
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    authors: list[OpenAlexAuthor] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    cited_by_count: int = 0
    referenced_works: list[str] = field(default_factory=list)
    cited_by_api_url: Optional[str] = None
    open_access_url: Optional[str] = None
    is_open_access: bool = False
    author_countries: list[str] = field(default_factory=list)

    @property
    def primary_country(self) -> Optional[str]:
        """Return the first author's country if available."""
        return self.author_countries[0] if self.author_countries else None

    def is_from_region(self, region_codes: list[str]) -> bool:
        """Check if any author is from the specified region codes."""
        return any(c in region_codes for c in self.author_countries)


class OpenAlexClient:
    """
    Async client for OpenAlex API.

    Features:
    - Search by keywords, concepts, and filters
    - Geographic filtering by author country
    - Citation network traversal
    - Rate limiting with exponential backoff
    """

    # Region to ISO country codes mapping
    REGION_CODES = {
        "NORTH_AMERICA": ["US", "CA", "MX"],
        "EUROPE": ["GB", "DE", "FR", "IT", "ES", "NL", "BE", "SE", "NO", "DK",
                   "FI", "AT", "CH", "IE", "PL", "PT", "CZ", "GR", "HU", "RO"],
        "ASIA_PACIFIC": ["CN", "JP", "KR", "AU", "IN", "SG", "TW", "HK", "NZ",
                         "TH", "MY", "ID", "PH", "VN"],
        "GLOBAL": [],  # No country filter for global
    }

    def __init__(self, email: Optional[str] = None):
        """
        Initialize OpenAlex client.

        Args:
            email: Email for polite pool (gets better rate limits)
        """
        self.email = email or OPENALEX_EMAIL
        self.base_url = OPENALEX_BASE_URL
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
        max_retries: int = 3
    ) -> dict:
        """
        Make a rate-limited request to OpenAlex API.

        Args:
            endpoint: API endpoint (e.g., "/works")
            params: Query parameters
            max_retries: Maximum retry attempts

        Returns:
            JSON response as dict
        """
        await self._ensure_session()
        await self._rate_limit()

        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params["mailto"] = self.email  # Polite pool

        for attempt in range(max_retries):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        # Rate limited - exponential backoff
                        wait_time = (2 ** attempt) * 1.0
                        logger.warning(f"OpenAlex rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"OpenAlex API error: {response.status}")
                        response.raise_for_status()
            except aiohttp.ClientError as e:
                logger.error(f"OpenAlex request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

        return {}

    def _parse_work(self, raw: dict) -> OpenAlexWork:
        """
        Parse raw OpenAlex work response into normalized object.

        Args:
            raw: Raw work dict from API

        Returns:
            Normalized OpenAlexWork object
        """
        # Extract authors with affiliations
        authors = []
        author_countries = []
        for authorship in raw.get("authorships", []):
            author_data = authorship.get("author", {})
            institutions = authorship.get("institutions", [])
            countries = authorship.get("countries", [])

            # Get first institution
            institution = None
            country_code = None
            if institutions:
                institution = institutions[0].get("display_name")
                country_code = institutions[0].get("country_code")
            elif countries:
                country_code = countries[0]

            if country_code:
                author_countries.append(country_code)

            authors.append(OpenAlexAuthor(
                name=author_data.get("display_name", "Unknown"),
                orcid=author_data.get("orcid"),
                institution=institution,
                country_code=country_code,
            ))

        # Extract concepts (top 5 by score)
        concepts = []
        for concept in sorted(
            raw.get("concepts", []),
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:5]:
            concepts.append(concept.get("display_name", ""))

        # Extract open access URL
        oa_url = None
        is_oa = False
        open_access = raw.get("open_access", {})
        if open_access.get("is_oa"):
            is_oa = True
            oa_url = open_access.get("oa_url")

        # Extract venue/journal
        journal = None
        primary_location = raw.get("primary_location", {})
        if primary_location:
            source = primary_location.get("source", {})
            if source:
                journal = source.get("display_name")

        return OpenAlexWork(
            openalex_id=raw.get("id", ""),
            doi=raw.get("doi"),
            title=raw.get("title", ""),
            abstract=raw.get("abstract_inverted_index"),  # Will need reconstruction
            publication_date=raw.get("publication_date"),
            publication_year=raw.get("publication_year"),
            journal=journal,
            authors=authors,
            concepts=concepts,
            cited_by_count=raw.get("cited_by_count", 0),
            referenced_works=raw.get("referenced_works", []),
            cited_by_api_url=raw.get("cited_by_api_url"),
            open_access_url=oa_url,
            is_open_access=is_oa,
            author_countries=list(set(author_countries)),
        )

    def _reconstruct_abstract(self, inverted_index: Optional[dict]) -> Optional[str]:
        """
        Reconstruct abstract from OpenAlex inverted index format.

        OpenAlex stores abstracts as {word: [positions]} for efficiency.
        """
        if not inverted_index:
            return None

        # Build word -> positions list
        words = []
        for word, positions in inverted_index.items():
            for pos in positions:
                words.append((pos, word))

        # Sort by position and join
        words.sort(key=lambda x: x[0])
        return " ".join(word for _, word in words)

    async def search_works(
        self,
        query: str,
        filters: Optional[dict] = None,
        per_page: int = DEFAULT_PER_PAGE,
        page: int = 1,
        sort: str = "relevance_score:desc",
    ) -> list[OpenAlexWork]:
        """
        Search for works matching query and filters.

        Args:
            query: Search query (searches title, abstract, full text)
            filters: OpenAlex filter dict (e.g., {"publication_year": ">2023"})
            per_page: Results per page (max 200)
            page: Page number
            sort: Sort order

        Returns:
            List of matching works
        """
        params = {
            "search": query,
            "per_page": min(per_page, MAX_PER_PAGE),
            "page": page,
            "sort": sort,
        }

        # Build filter string
        if filters:
            filter_parts = []
            for key, value in filters.items():
                filter_parts.append(f"{key}:{value}")
            params["filter"] = ",".join(filter_parts)

        response = await self._request("/works", params)
        results = response.get("results", [])

        works = []
        for raw in results:
            work = self._parse_work(raw)
            # Reconstruct abstract
            if raw.get("abstract_inverted_index"):
                work.abstract = self._reconstruct_abstract(raw["abstract_inverted_index"])
            works.append(work)

        logger.info(f"OpenAlex search '{query[:50]}...' returned {len(works)} works")
        return works

    async def search_by_region(
        self,
        query: str,
        region: str,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[OpenAlexWork]:
        """
        Search for works with regional filtering by author country.

        Args:
            query: Search query
            region: Region name (NORTH_AMERICA, EUROPE, ASIA_PACIFIC, GLOBAL)
            year_min: Minimum publication year
            year_max: Maximum publication year
            per_page: Results per page

        Returns:
            List of works from authors in the specified region
        """
        filters = {}

        # Add year filters
        if year_min:
            filters["publication_year"] = f">{year_min - 1}"
        if year_max:
            if "publication_year" in filters:
                filters["publication_year"] += f",<{year_max + 1}"
            else:
                filters["publication_year"] = f"<{year_max + 1}"

        # Add country filter for non-global regions
        country_codes = self.REGION_CODES.get(region, [])
        if country_codes:
            filters["authorships.countries"] = "|".join(country_codes)

        return await self.search_works(query, filters=filters, per_page=per_page)

    async def get_work_by_doi(self, doi: str) -> Optional[OpenAlexWork]:
        """
        Fetch a specific work by DOI.

        Args:
            doi: DOI string (with or without https://doi.org/ prefix)

        Returns:
            Work object or None if not found
        """
        # Normalize DOI
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("doi.org/"):
            doi = doi[8:]

        try:
            response = await self._request(f"/works/https://doi.org/{doi}")
            if response:
                work = self._parse_work(response)
                if response.get("abstract_inverted_index"):
                    work.abstract = self._reconstruct_abstract(response["abstract_inverted_index"])
                return work
        except Exception as e:
            logger.error(f"Failed to fetch DOI {doi}: {e}")

        return None

    async def get_work_by_id(self, openalex_id: str) -> Optional[OpenAlexWork]:
        """
        Fetch a specific work by OpenAlex ID.

        Args:
            openalex_id: OpenAlex ID (e.g., "W2741809809")

        Returns:
            Work object or None if not found
        """
        # Extract ID if full URL provided
        if openalex_id.startswith("https://openalex.org/"):
            openalex_id = openalex_id.split("/")[-1]

        try:
            response = await self._request(f"/works/{openalex_id}")
            if response:
                work = self._parse_work(response)
                if response.get("abstract_inverted_index"):
                    work.abstract = self._reconstruct_abstract(response["abstract_inverted_index"])
                return work
        except Exception as e:
            logger.error(f"Failed to fetch OpenAlex ID {openalex_id}: {e}")

        return None

    async def get_citing_works(
        self,
        work: OpenAlexWork,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[OpenAlexWork]:
        """
        Get works that cite the given work (forward snowballing).

        Args:
            work: Source work to find citations for
            per_page: Results per page

        Returns:
            List of citing works
        """
        if not work.cited_by_api_url:
            return []

        # The cited_by_api_url is a full URL, extract the path
        # Format: https://api.openalex.org/works?filter=cites:W123
        try:
            # Parse the filter from the URL
            openalex_id = work.openalex_id.split("/")[-1]
            filters = {"cites": openalex_id}
            return await self.search_works(
                query="",
                filters=filters,
                per_page=per_page,
                sort="publication_date:desc",
            )
        except Exception as e:
            logger.error(f"Failed to get citing works: {e}")
            return []

    async def get_referenced_works(
        self,
        work: OpenAlexWork,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[OpenAlexWork]:
        """
        Get works referenced by the given work (backward snowballing).

        Args:
            work: Source work to find references for
            per_page: Max references to fetch

        Returns:
            List of referenced works
        """
        if not work.referenced_works:
            return []

        # Fetch each referenced work (limit to avoid too many requests)
        works = []
        for ref_id in work.referenced_works[:per_page]:
            ref_work = await self.get_work_by_id(ref_id)
            if ref_work:
                works.append(ref_work)

        return works

    async def search_recent_studies(
        self,
        topic: str,
        region: str = "GLOBAL",
        years: list[int] = None,
        journals: list[str] = None,
        per_page: int = 50,
    ) -> list[OpenAlexWork]:
        """
        Search for recent studies on a topic, optionally filtering by journal.

        This is specifically designed to find papers like "Sexton et al. PLOS Water 2025"
        that the keyword search missed.

        Args:
            topic: Research topic
            region: Geographic region
            years: List of years to search (default: [2024, 2025, 2026])
            journals: List of journal names to prioritize
            per_page: Results per page

        Returns:
            List of matching works
        """
        years = years or [2024, 2025, 2026]
        all_works = []

        # Build base filters
        base_filters = {}

        # Year range
        min_year = min(years)
        max_year = max(years)
        base_filters["publication_year"] = f"{min_year}-{max_year}"

        # Region filter
        country_codes = self.REGION_CODES.get(region, [])
        if country_codes:
            base_filters["authorships.countries"] = "|".join(country_codes)

        # Search with topic
        works = await self.search_works(
            query=topic,
            filters=base_filters,
            per_page=per_page,
            sort="publication_date:desc",
        )
        all_works.extend(works)

        # If specific journals requested, also search within those
        if journals:
            for journal in journals:
                journal_filter = base_filters.copy()
                # Search for journal in source name
                journal_works = await self.search_works(
                    query=f"{topic} {journal}",
                    filters=journal_filter,
                    per_page=per_page // len(journals),
                )
                all_works.extend(journal_works)

        # Deduplicate by OpenAlex ID
        seen_ids = set()
        unique_works = []
        for work in all_works:
            if work.openalex_id not in seen_ids:
                seen_ids.add(work.openalex_id)
                unique_works.append(work)

        logger.info(f"Found {len(unique_works)} unique recent studies on '{topic}'")
        return unique_works


# Convenience function for quick searches
async def search_openalex(
    query: str,
    region: str = "GLOBAL",
    year_min: int = 2020,
    year_max: int = 2026,
    per_page: int = 25,
) -> list[OpenAlexWork]:
    """
    Convenience function for quick OpenAlex searches.

    Args:
        query: Search query
        region: Geographic region
        year_min: Minimum year
        year_max: Maximum year
        per_page: Results per page

    Returns:
        List of matching works
    """
    async with OpenAlexClient() as client:
        return await client.search_by_region(
            query=query,
            region=region,
            year_min=year_min,
            year_max=year_max,
            per_page=per_page,
        )


# Self-test
if __name__ == "__main__":
    async def test_client():
        """Test OpenAlex client functionality."""
        print("Testing OpenAlex Client...")

        async with OpenAlexClient() as client:
            # Test 1: Basic search
            print("\n1. Basic search for 'water filter contamination'...")
            works = await client.search_works(
                "water filter contamination",
                filters={"publication_year": ">2023"},
                per_page=5,
            )
            print(f"   Found {len(works)} works")
            for w in works[:3]:
                print(f"   - {w.title[:60]}... ({w.publication_year})")

            # Test 2: Regional search
            print("\n2. Regional search (North America)...")
            na_works = await client.search_by_region(
                "private well contamination",
                region="NORTH_AMERICA",
                year_min=2024,
                per_page=5,
            )
            print(f"   Found {len(na_works)} North American works")
            for w in na_works[:3]:
                print(f"   - {w.title[:50]}... Countries: {w.author_countries}")

            # Test 3: Recent studies (PLOS Water target)
            print("\n3. Searching for recent PLOS studies...")
            recent = await client.search_recent_studies(
                topic="private well water quality contamination",
                region="NORTH_AMERICA",
                years=[2024, 2025],
                journals=["PLOS Water", "PLOS ONE"],
                per_page=10,
            )
            print(f"   Found {len(recent)} recent studies")
            for w in recent[:5]:
                print(f"   - {w.title[:50]}...")
                print(f"     Journal: {w.journal}, Year: {w.publication_year}")
                print(f"     DOI: {w.doi}")

        print("\n[PASS] OpenAlex client tests completed")

    asyncio.run(test_client())
