"""
Unpaywall API Client for POLARIS Open Access PDF Retrieval.

Unpaywall provides:
- Open Access PDF links for DOIs
- License information (CC-BY, CC-BY-NC, etc.)
- Best available version (published, accepted, submitted)
- OA status classification (gold, green, hybrid, bronze)

API Documentation: https://unpaywall.org/products/api
Rate Limit: 100,000 requests/day with email parameter
No API key required - just need to include email in requests.

References:
- GPT Blueprint: Phase 3 Full-Text Retrieval
- Gemini Diagnostic: Section 3 Open Access Integration
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Unpaywall API configuration
UNPAYWALL_BASE_URL = "https://api.unpaywall.org/v2"
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "polaris@research.ai")
REQUEST_DELAY_SECONDS = 0.01  # Very generous rate limit


@dataclass
class OALocation:
    """Open Access location information."""

    url: Optional[str] = None
    url_for_pdf: Optional[str] = None
    url_for_landing_page: Optional[str] = None
    evidence: Optional[str] = None  # How OA status was determined
    license: Optional[str] = None
    version: Optional[str] = None  # publishedVersion, acceptedVersion, submittedVersion
    host_type: Optional[str] = None  # publisher, repository
    is_best: bool = False
    repository_institution: Optional[str] = None

    @property
    def pdf_url(self) -> Optional[str]:
        """Return the best PDF URL available."""
        return self.url_for_pdf or self.url

    @property
    def is_published_version(self) -> bool:
        """Check if this is the published (final) version."""
        return self.version == "publishedVersion"


@dataclass
class UnpaywallWork:
    """Work record from Unpaywall API."""

    doi: str
    title: Optional[str] = None
    year: Optional[int] = None
    journal_name: Optional[str] = None
    publisher: Optional[str] = None
    is_oa: bool = False
    oa_status: Optional[str] = None  # gold, green, hybrid, bronze, closed
    best_oa_location: Optional[OALocation] = None
    all_oa_locations: list[OALocation] = field(default_factory=list)
    data_standard: Optional[int] = None
    doi_url: Optional[str] = None

    @property
    def pdf_url(self) -> Optional[str]:
        """Return the best available PDF URL."""
        if self.best_oa_location:
            return self.best_oa_location.pdf_url
        return None

    @property
    def has_pdf(self) -> bool:
        """Check if a PDF is available."""
        return self.pdf_url is not None

    @property
    def license(self) -> Optional[str]:
        """Return the license of the best OA location."""
        if self.best_oa_location:
            return self.best_oa_location.license
        return None


class UnpaywallClient:
    """
    Async client for Unpaywall API.

    Features:
    - DOI-based Open Access lookup
    - PDF URL retrieval
    - License and version information
    - Bulk lookup with rate limiting
    """

    def __init__(self, email: Optional[str] = None):
        """
        Initialize Unpaywall client.

        Args:
            email: Email for API access (required by Unpaywall)
        """
        self.email = email or UNPAYWALL_EMAIL
        self.base_url = UNPAYWALL_BASE_URL
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
                "Accept": "application/json",
            }
            self.session = aiohttp.ClientSession(headers=headers)

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _rate_limit(self):
        """Implement rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            await asyncio.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.time()

    async def _request(
        self,
        endpoint: str,
        max_retries: int = 3,
    ) -> dict:
        """
        Make a rate-limited request to Unpaywall API.

        Args:
            endpoint: API endpoint (DOI)
            max_retries: Maximum retry attempts

        Returns:
            JSON response as dict
        """
        await self._ensure_session()
        await self._rate_limit()

        url = f"{self.base_url}/{endpoint}"
        params = {"email": self.email}

        for attempt in range(max_retries):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        logger.debug(f"DOI not found in Unpaywall: {endpoint}")
                        return {}
                    elif response.status == 429:
                        wait_time = (2 ** attempt) * 1.0
                        logger.warning(f"Unpaywall rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Unpaywall API error: {response.status}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                logger.error(f"Unpaywall request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

        return {}

    def _parse_location(self, raw: dict) -> OALocation:
        """
        Parse raw OA location dict into OALocation object.

        Args:
            raw: Raw location dict from API

        Returns:
            OALocation object
        """
        return OALocation(
            url=raw.get("url"),
            url_for_pdf=raw.get("url_for_pdf"),
            url_for_landing_page=raw.get("url_for_landing_page"),
            evidence=raw.get("evidence"),
            license=raw.get("license"),
            version=raw.get("version"),
            host_type=raw.get("host_type"),
            is_best=raw.get("is_best", False),
            repository_institution=raw.get("repository_institution"),
        )

    def _parse_work(self, raw: dict) -> UnpaywallWork:
        """
        Parse raw Unpaywall response into UnpaywallWork object.

        Args:
            raw: Raw work dict from API

        Returns:
            UnpaywallWork object
        """
        # Parse best OA location
        best_location = None
        best_oa_raw = raw.get("best_oa_location")
        if best_oa_raw:
            best_location = self._parse_location(best_oa_raw)

        # Parse all OA locations
        all_locations = []
        for loc_raw in raw.get("oa_locations", []):
            all_locations.append(self._parse_location(loc_raw))

        return UnpaywallWork(
            doi=raw.get("doi", ""),
            title=raw.get("title"),
            year=raw.get("year"),
            journal_name=raw.get("journal_name"),
            publisher=raw.get("publisher"),
            is_oa=raw.get("is_oa", False),
            oa_status=raw.get("oa_status"),
            best_oa_location=best_location,
            all_oa_locations=all_locations,
            data_standard=raw.get("data_standard"),
            doi_url=raw.get("doi_url"),
        )

    async def get_work_by_doi(self, doi: str) -> Optional[UnpaywallWork]:
        """
        Look up Open Access information for a DOI.

        Args:
            doi: DOI string (with or without https://doi.org/ prefix)

        Returns:
            UnpaywallWork object or None if not found
        """
        # Normalize DOI - remove common prefixes
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("http://doi.org/"):
            doi = doi[15:]
        elif doi.startswith("doi.org/"):
            doi = doi[8:]
        elif doi.startswith("doi:"):
            doi = doi[4:]

        try:
            response = await self._request(doi)
            if response and "doi" in response:
                return self._parse_work(response)
        except Exception as e:
            logger.error(f"Failed to fetch DOI {doi} from Unpaywall: {e}")

        return None

    async def get_pdf_url(self, doi: str) -> Optional[str]:
        """
        Get the best available PDF URL for a DOI.

        This is a convenience method for quick PDF lookup.

        Args:
            doi: DOI string

        Returns:
            PDF URL or None if not available
        """
        work = await self.get_work_by_doi(doi)
        if work:
            return work.pdf_url
        return None

    async def bulk_lookup(
        self,
        dois: list[str],
        return_pdf_only: bool = False,
    ) -> dict[str, UnpaywallWork]:
        """
        Look up Open Access information for multiple DOIs.

        Args:
            dois: List of DOIs
            return_pdf_only: If True, only return works with PDFs available

        Returns:
            Dict mapping DOI to UnpaywallWork
        """
        results = {}

        for doi in dois:
            work = await self.get_work_by_doi(doi)
            if work:
                if return_pdf_only and not work.has_pdf:
                    continue
                results[doi] = work

        logger.info(
            f"Unpaywall bulk lookup: {len(results)}/{len(dois)} DOIs with OA info"
        )
        return results

    async def get_pdf_urls(self, dois: list[str]) -> dict[str, str]:
        """
        Get PDF URLs for multiple DOIs.

        Convenience method for bulk PDF URL lookup.

        Args:
            dois: List of DOIs

        Returns:
            Dict mapping DOI to PDF URL (only includes DOIs with available PDFs)
        """
        results = {}

        for doi in dois:
            pdf_url = await self.get_pdf_url(doi)
            if pdf_url:
                results[doi] = pdf_url

        logger.info(
            f"Unpaywall PDF lookup: {len(results)}/{len(dois)} DOIs have PDFs"
        )
        return results

    async def filter_open_access(
        self,
        dois: list[str],
        oa_types: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Filter DOIs to only those with Open Access availability.

        Args:
            dois: List of DOIs to filter
            oa_types: Optional list of OA types to accept
                     (gold, green, hybrid, bronze). If None, accept all OA.

        Returns:
            List of DOIs that are Open Access
        """
        oa_dois = []

        for doi in dois:
            work = await self.get_work_by_doi(doi)
            if work and work.is_oa:
                if oa_types is None or work.oa_status in oa_types:
                    oa_dois.append(doi)

        logger.info(
            f"Unpaywall OA filter: {len(oa_dois)}/{len(dois)} DOIs are Open Access"
        )
        return oa_dois

    async def get_best_versions(
        self,
        dois: list[str],
        prefer_published: bool = True,
    ) -> dict[str, OALocation]:
        """
        Get the best available version for each DOI.

        Args:
            dois: List of DOIs
            prefer_published: If True, prefer published versions over preprints

        Returns:
            Dict mapping DOI to best OALocation
        """
        results = {}

        for doi in dois:
            work = await self.get_work_by_doi(doi)
            if work and work.all_oa_locations:
                if prefer_published:
                    # Try to find published version first
                    for loc in work.all_oa_locations:
                        if loc.is_published_version:
                            results[doi] = loc
                            break
                    else:
                        # Fall back to best location
                        if work.best_oa_location:
                            results[doi] = work.best_oa_location
                else:
                    if work.best_oa_location:
                        results[doi] = work.best_oa_location

        return results


# Convenience function for quick PDF lookup
async def get_open_access_pdf(doi: str) -> Optional[str]:
    """
    Convenience function to get Open Access PDF URL for a DOI.

    Args:
        doi: DOI string

    Returns:
        PDF URL or None
    """
    async with UnpaywallClient() as client:
        return await client.get_pdf_url(doi)


# Self-test
if __name__ == "__main__":
    async def test_client():
        """Test Unpaywall client functionality."""
        print("Testing Unpaywall Client...")

        async with UnpaywallClient() as client:
            # Test 1: DOI lookup (using a known OA article)
            print("\n1. Testing DOI lookup...")
            # PLOS ONE article (always open access)
            work = await client.get_work_by_doi("10.1371/journal.pone.0115069")
            if work:
                print(f"   Title: {work.title[:60] if work.title else 'N/A'}...")
                print(f"   Is OA: {work.is_oa}")
                print(f"   OA Status: {work.oa_status}")
                print(f"   PDF URL: {work.pdf_url}")
                print(f"   License: {work.license}")
            else:
                print("   (Article not found)")

            # Test 2: PDF URL lookup
            print("\n2. Testing PDF URL lookup...")
            pdf_url = await client.get_pdf_url("10.1371/journal.pone.0115069")
            if pdf_url:
                print(f"   PDF URL found: {pdf_url[:60]}...")
            else:
                print("   No PDF URL found")

            # Test 3: Bulk lookup
            print("\n3. Testing bulk lookup...")
            test_dois = [
                "10.1371/journal.pone.0115069",  # PLOS ONE (OA)
                "10.1038/nature12373",  # Nature (may be OA)
                "10.1126/science.1234567",  # Science (likely closed)
            ]
            results = await client.bulk_lookup(test_dois)
            print(f"   Found OA info for {len(results)}/{len(test_dois)} DOIs")
            for doi, w in results.items():
                print(f"   - {doi}: OA={w.is_oa}, Status={w.oa_status}")

        print("\n[PASS] Unpaywall client tests completed")

    asyncio.run(test_client())
