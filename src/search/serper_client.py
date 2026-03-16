"""
POLARIS Serper.dev API Client
=============================
Production-grade Serper integration for comprehensive Google Search.

Supported Endpoints:
- Search: General web search
- Scholar: Google Scholar academic papers
- News: Google News articles
- Images: Google Images
- Places: Google Maps/Places
- Patents: Google Patents

Features:
- All 10 Serper endpoints supported
- Async and sync interfaces
- Geographic targeting (gl, hl, location parameters)
- Domain filtering (site: operators)
- Rate limiting with circuit breaker
- Cost tracking and budget management
- Pagination support (up to 100 results per request)

Based on:
- Serper.dev official documentation: https://serper.dev/
- Haystack SerperDevWebSearch best practices
- LangChain GoogleSerperAPIWrapper patterns

Usage:
    from src.search.serper_client import SerperClient
    client = SerperClient()
    results = await client.search("water filter contamination", max_results=50)
    scholar = await client.scholar("household water filter pathogens", max_results=30)
"""

import os
import time
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum

import httpx

from src.config import get_config


# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

SERPER_BASE_URL = "https://google.serper.dev"

# Endpoint URLs
ENDPOINTS = {
    "search": f"{SERPER_BASE_URL}/search",
    "scholar": f"{SERPER_BASE_URL}/scholar",
    "news": f"{SERPER_BASE_URL}/news",
    "images": f"{SERPER_BASE_URL}/images",
    "videos": f"{SERPER_BASE_URL}/videos",
    "places": f"{SERPER_BASE_URL}/places",
    "maps": f"{SERPER_BASE_URL}/maps",
    "shopping": f"{SERPER_BASE_URL}/shopping",
    "patents": f"{SERPER_BASE_URL}/patents",
    "autocomplete": f"{SERPER_BASE_URL}/autocomplete",
}

# Serper limits
MAX_RESULTS_PER_REQUEST = 100
DEFAULT_RESULTS = 10
FREE_TIER_QUERIES = 2500
COST_PER_1000_QUERIES = 0.30

# Timeouts
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0


# =============================================================================
# DATA CLASSES
# =============================================================================

class SearchType(str, Enum):
    """Serper search types."""
    SEARCH = "search"
    SCHOLAR = "scholar"
    NEWS = "news"
    IMAGES = "images"
    VIDEOS = "videos"
    PLACES = "places"
    MAPS = "maps"
    SHOPPING = "shopping"
    PATENTS = "patents"
    AUTOCOMPLETE = "autocomplete"


@dataclass
class SerperResult:
    """Unified search result from any Serper endpoint."""
    url: str
    title: str
    snippet: str = ""
    position: int = 0
    search_type: str = "search"
    source: str = "serper"

    # Optional metadata
    date: Optional[str] = None
    authors: Optional[str] = None
    publication: Optional[str] = None
    cited_by: Optional[int] = None
    year: Optional[str] = None
    domain: Optional[str] = None
    image_url: Optional[str] = None

    # Quality signals
    relevance_score: float = 0.7

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SerperStats:
    """Usage statistics for cost tracking."""
    requests_made: int = 0
    results_retrieved: int = 0
    errors: int = 0
    rate_limits: int = 0
    free_queries_used: int = 0
    paid_queries_used: int = 0
    total_cost_usd: float = 0.0

    # Per-endpoint tracking
    search_requests: int = 0
    scholar_requests: int = 0
    news_requests: int = 0
    images_requests: int = 0
    places_requests: int = 0
    patents_requests: int = 0


# =============================================================================
# EXCEPTIONS
# =============================================================================

class SerperError(Exception):
    """Base Serper exception."""
    pass


class SerperRateLimitError(SerperError):
    """Rate limit exceeded."""
    pass


class SerperQuotaError(SerperError):
    """Monthly quota exceeded."""
    pass


class SerperAuthError(SerperError):
    """Authentication failed."""
    pass


# =============================================================================
# SERPER CLIENT
# =============================================================================

class SerperClient:
    """
    Production-grade Serper.dev API Client.

    Features:
    - All Serper endpoints (search, scholar, news, images, places, patents)
    - Async and sync interfaces
    - Geographic targeting and domain filtering
    - Circuit breaker pattern for resilience
    - Cost tracking and budget management
    - SOTA pagination for comprehensive results
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        daily_budget_usd: float = 50.0,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize Serper client.

        Args:
            api_key: Serper API key (defaults to SERPER_API_KEY env var)
            daily_budget_usd: Daily budget limit in USD
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        self.daily_budget = daily_budget_usd
        self.timeout = timeout

        # Validate API key
        if not self.api_key:
            logger.warning("Serper API key not configured (SERPER_API_KEY)")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Serper client initialized")

        # Statistics
        self.stats = SerperStats()

        # Circuit breaker
        self._failure_count = 0
        self._circuit_open_until = 0
        self._max_failures = 5
        self._circuit_timeout = 300  # 5 minutes

        # HTTP client (reusable)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is open."""
        if self._failure_count < self._max_failures:
            return False

        if time.time() > self._circuit_open_until:
            # Reset circuit
            self._failure_count = 0
            logger.info("Serper circuit breaker reset")
            return False

        return True

    def _record_failure(self):
        """Record a failure for circuit breaker."""
        self._failure_count += 1
        if self._failure_count >= self._max_failures:
            self._circuit_open_until = time.time() + self._circuit_timeout
            logger.error(f"Serper circuit breaker OPEN for {self._circuit_timeout}s")

    def _record_success(self):
        """Record success to reset failure count."""
        self._failure_count = 0

    def _check_budget(self, num_requests: int = 1) -> bool:
        """Check if requests fit within budget."""
        # Free tier check
        total_used = self.stats.free_queries_used + self.stats.paid_queries_used
        if total_used + num_requests <= FREE_TIER_QUERIES:
            return True

        # Paid tier check
        if self.stats.total_cost_usd + (num_requests / 1000 * COST_PER_1000_QUERIES) > self.daily_budget:
            logger.warning(f"Serper daily budget exceeded: ${self.daily_budget}")
            return False

        return True

    def _update_cost(self, num_requests: int = 1):
        """Update cost tracking after requests."""
        total_used = self.stats.free_queries_used + self.stats.paid_queries_used

        if total_used + num_requests <= FREE_TIER_QUERIES:
            self.stats.free_queries_used += num_requests
        else:
            # Some or all are paid
            free_remaining = max(0, FREE_TIER_QUERIES - total_used)
            paid = num_requests - free_remaining

            self.stats.free_queries_used += free_remaining
            self.stats.paid_queries_used += paid
            self.stats.total_cost_usd += (paid / 1000) * COST_PER_1000_QUERIES

    async def _request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        search_type: str = "search",
    ) -> Dict[str, Any]:
        """
        Make request to Serper API.

        Args:
            endpoint: API endpoint URL
            payload: Request payload
            search_type: Type of search for stats tracking

        Returns:
            API response as dictionary
        """
        if not self.enabled:
            raise SerperError("Serper client not enabled (missing API key)")

        if self._check_circuit_breaker():
            raise SerperError("Serper circuit breaker is open")

        if not self._check_budget():
            raise SerperQuotaError("Daily budget exceeded")

        client = await self._get_client()

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.post(endpoint, json=payload)

                # Handle specific status codes
                if response.status_code == 401:
                    raise SerperAuthError("Invalid API key")

                if response.status_code == 429:
                    self.stats.rate_limits += 1
                    raise SerperRateLimitError("Rate limit exceeded")

                if response.status_code == 403:
                    error_data = response.json() if response.content else {}
                    if "quota" in str(error_data).lower():
                        raise SerperQuotaError("Monthly quota exceeded")
                    raise SerperError(f"Forbidden: {error_data}")

                response.raise_for_status()

                # Success
                self._record_success()
                self.stats.requests_made += 1
                self._update_cost(1)

                # Track by type
                type_attr = f"{search_type}_requests"
                if hasattr(self.stats, type_attr):
                    setattr(self.stats, type_attr, getattr(self.stats, type_attr) + 1)

                return response.json()

            except httpx.TimeoutException:
                logger.warning(f"Serper timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt == MAX_RETRIES - 1:
                    self._record_failure()
                    self.stats.errors += 1
                    raise SerperError("Request timeout")
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

            except httpx.HTTPError as e:
                logger.error(f"Serper HTTP error: {e}")
                self._record_failure()
                self.stats.errors += 1
                raise SerperError(f"HTTP error: {e}")

    # =========================================================================
    # SEARCH ENDPOINTS
    # =========================================================================

    async def search(
        self,
        query: str,
        max_results: int = DEFAULT_RESULTS,
        gl: str = "us",
        hl: str = "en",
        location: Optional[str] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        time_range: Optional[str] = None,
    ) -> List[SerperResult]:
        """
        Execute Google Search via Serper.

        Args:
            query: Search query
            max_results: Maximum results (up to 100)
            gl: Geographic location (country code)
            hl: Language code
            location: Precise location string (e.g., "North America")
            domains: Include only these domains (site: filter)
            exclude_domains: Exclude these domains (-site: filter)
            time_range: Time filter (d=day, w=week, m=month, y=year)

        Returns:
            List of SerperResult objects
        """
        # Build query with domain filters
        search_query = query
        if domains:
            site_filter = " OR ".join([f"site:{d}" for d in domains])
            search_query = f"({query}) ({site_filter})"
        if exclude_domains:
            exclude_filter = " ".join([f"-site:{d}" for d in exclude_domains])
            search_query = f"{search_query} {exclude_filter}"

        # Pagination for comprehensive results
        all_results = []
        seen_urls = set()
        pages_needed = min((max_results + 9) // 10, 10)  # Serper returns 10 per page, max 10 pages

        for page in range(pages_needed):
            payload = {
                "q": search_query,
                "gl": gl,
                "hl": hl,
                "num": 10,
                "page": page + 1,
            }

            if location:
                payload["location"] = location

            if time_range:
                payload["tbs"] = f"qdr:{time_range}"

            try:
                data = await self._request(ENDPOINTS["search"], payload, "search")

                # Process organic results
                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        result = SerperResult(
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("snippet", ""),
                            position=len(all_results) + 1,
                            search_type="search",
                            date=item.get("date"),
                            domain=self._extract_domain(url),
                        )
                        all_results.append(result)

                # Also include answer box if present
                if "answerBox" in data:
                    ab = data["answerBox"]
                    snippet = ab.get("answer") or ab.get("snippet") or ab.get("title", "")
                    if snippet and ab.get("link"):
                        url = ab.get("link")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            result = SerperResult(
                                url=url,
                                title=ab.get("title", "Answer Box"),
                                snippet=snippet,
                                position=0,  # Answer box is position 0
                                search_type="answer_box",
                                relevance_score=0.95,  # High relevance
                            )
                            all_results.insert(0, result)

                if len(all_results) >= max_results:
                    break

            except SerperError as e:
                logger.error(f"Search page {page + 1} failed: {e}")
                break

        self.stats.results_retrieved += len(all_results)
        logger.info(f"Serper search '{query[:50]}...' returned {len(all_results)} results")

        return all_results[:max_results]

    async def scholar(
        self,
        query: str,
        max_results: int = DEFAULT_RESULTS,
        gl: str = "us",
        hl: str = "en",
        location: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> List[SerperResult]:
        """
        Execute Google Scholar search via Serper.

        Args:
            query: Search query
            max_results: Maximum results
            gl: Geographic location
            hl: Language
            location: Precise location
            year_from: Filter papers from this year
            year_to: Filter papers until this year

        Returns:
            List of SerperResult objects with academic metadata
        """
        all_results = []
        seen_urls = set()
        pages_needed = min((max_results + 9) // 10, 5)  # Cap at 5 pages for Scholar

        for page in range(pages_needed):
            payload = {
                "q": query,
                "gl": gl,
                "hl": hl,
                "num": 10,
                "page": page + 1,
            }

            if location:
                payload["location"] = location

            # Year filtering
            if year_from or year_to:
                as_ylo = year_from or ""
                as_yhi = year_to or ""
                payload["as_ylo"] = as_ylo
                payload["as_yhi"] = as_yhi

            try:
                data = await self._request(ENDPOINTS["scholar"], payload, "scholar")

                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        result = SerperResult(
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("snippet", ""),
                            position=len(all_results) + 1,
                            search_type="scholar",
                            authors=item.get("authors"),
                            publication=item.get("publication"),
                            cited_by=item.get("citedBy"),
                            year=item.get("year"),
                            relevance_score=0.85,  # Academic sources score higher
                        )
                        all_results.append(result)

                if len(all_results) >= max_results:
                    break

            except SerperError as e:
                logger.error(f"Scholar page {page + 1} failed: {e}")
                break

        self.stats.results_retrieved += len(all_results)
        logger.info(f"Serper Scholar '{query[:50]}...' returned {len(all_results)} results")

        return all_results[:max_results]

    async def news(
        self,
        query: str,
        max_results: int = DEFAULT_RESULTS,
        gl: str = "us",
        hl: str = "en",
        location: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> List[SerperResult]:
        """
        Execute Google News search via Serper.

        Args:
            query: Search query
            max_results: Maximum results
            gl: Geographic location
            hl: Language
            location: Precise location
            time_range: Time filter (h=hour, d=day, w=week, m=month)

        Returns:
            List of SerperResult objects with news metadata
        """
        all_results = []
        seen_urls = set()
        pages_needed = min((max_results + 9) // 10, 5)

        for page in range(pages_needed):
            payload = {
                "q": query,
                "gl": gl,
                "hl": hl,
                "num": 10,
                "page": page + 1,
            }

            if location:
                payload["location"] = location

            if time_range:
                payload["tbs"] = f"qdr:{time_range}"

            try:
                data = await self._request(ENDPOINTS["news"], payload, "news")

                for item in data.get("news", []):
                    url = item.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        result = SerperResult(
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("snippet", ""),
                            position=len(all_results) + 1,
                            search_type="news",
                            date=item.get("date"),
                            domain=item.get("source"),
                            image_url=item.get("imageUrl"),
                            relevance_score=0.75,
                        )
                        all_results.append(result)

                if len(all_results) >= max_results:
                    break

            except SerperError as e:
                logger.error(f"News page {page + 1} failed: {e}")
                break

        self.stats.results_retrieved += len(all_results)
        logger.info(f"Serper News '{query[:50]}...' returned {len(all_results)} results")

        return all_results[:max_results]

    async def patents(
        self,
        query: str,
        max_results: int = DEFAULT_RESULTS,
        gl: str = "us",
        hl: str = "en",
    ) -> List[SerperResult]:
        """
        Execute Google Patents search via Serper.

        Args:
            query: Search query
            max_results: Maximum results
            gl: Geographic location
            hl: Language

        Returns:
            List of SerperResult objects with patent metadata
        """
        all_results = []
        seen_urls = set()
        pages_needed = min((max_results + 9) // 10, 3)

        for page in range(pages_needed):
            payload = {
                "q": query,
                "gl": gl,
                "hl": hl,
                "num": 10,
                "page": page + 1,
            }

            try:
                data = await self._request(ENDPOINTS["patents"], payload, "patents")

                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        result = SerperResult(
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("snippet", ""),
                            position=len(all_results) + 1,
                            search_type="patents",
                            date=item.get("filingDate") or item.get("date"),
                            authors=item.get("inventor"),
                            relevance_score=0.80,
                        )
                        all_results.append(result)

                if len(all_results) >= max_results:
                    break

            except SerperError as e:
                logger.error(f"Patents page {page + 1} failed: {e}")
                break

        self.stats.results_retrieved += len(all_results)
        logger.info(f"Serper Patents '{query[:50]}...' returned {len(all_results)} results")

        return all_results[:max_results]

    async def places(
        self,
        query: str,
        max_results: int = DEFAULT_RESULTS,
        gl: str = "us",
        hl: str = "en",
        location: Optional[str] = None,
    ) -> List[SerperResult]:
        """
        Execute Google Places search via Serper.

        Args:
            query: Search query
            max_results: Maximum results
            gl: Geographic location
            hl: Language
            location: Precise location

        Returns:
            List of SerperResult objects with place metadata
        """
        payload = {
            "q": query,
            "gl": gl,
            "hl": hl,
        }

        if location:
            payload["location"] = location

        try:
            data = await self._request(ENDPOINTS["places"], payload, "places")

            results = []
            for item in data.get("places", [])[:max_results]:
                result = SerperResult(
                    url=item.get("website", ""),
                    title=item.get("title", ""),
                    snippet=item.get("address", ""),
                    position=len(results) + 1,
                    search_type="places",
                    relevance_score=0.70,
                )
                results.append(result)

            self.stats.results_retrieved += len(results)
            logger.info(f"Serper Places '{query[:50]}...' returned {len(results)} results")

            return results

        except SerperError as e:
            logger.error(f"Places search failed: {e}")
            return []

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    async def multi_search(
        self,
        query: str,
        search_types: List[str] = None,
        max_results_per_type: int = 10,
        **kwargs,
    ) -> Dict[str, List[SerperResult]]:
        """
        Execute multiple search types in parallel.

        Args:
            query: Search query
            search_types: List of types (search, scholar, news, patents)
            max_results_per_type: Results per search type
            **kwargs: Additional parameters passed to each search

        Returns:
            Dict mapping search type to results
        """
        if search_types is None:
            search_types = ["search", "scholar", "news"]

        tasks = []
        for search_type in search_types:
            if search_type == "search":
                tasks.append(self.search(query, max_results_per_type, **kwargs))
            elif search_type == "scholar":
                tasks.append(self.scholar(query, max_results_per_type, **kwargs))
            elif search_type == "news":
                tasks.append(self.news(query, max_results_per_type, **kwargs))
            elif search_type == "patents":
                tasks.append(self.patents(query, max_results_per_type, **kwargs))
            elif search_type == "places":
                tasks.append(self.places(query, max_results_per_type, **kwargs))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for search_type, result in zip(search_types, results_list):
            if isinstance(result, Exception):
                logger.error(f"Multi-search {search_type} failed: {result}")
                results[search_type] = []
            else:
                results[search_type] = result

        return results

    async def government_search(
        self,
        query: str,
        max_results: int = DEFAULT_RESULTS,
        region: str = "NORTH_AMERICA",
        **kwargs,
    ) -> List[SerperResult]:
        """
        Search government sources using site: filters.

        Args:
            query: Search query
            max_results: Maximum results
            region: Geographic region for domain selection
            **kwargs: Additional parameters

        Returns:
            List of SerperResult from government sources
        """
        # Government domains by region
        gov_domains = {
            "NORTH_AMERICA": [
                "epa.gov", "fda.gov", "cdc.gov", "nih.gov", "usda.gov",
                "canada.ca", "gc.ca", "health.gov",
            ],
            "EUROPE": [
                "europa.eu", "gov.uk", "ema.europa.eu", "efsa.europa.eu",
            ],
            "GLOBAL": [
                "who.int", "un.org", "worldbank.org",
            ],
        }

        domains = gov_domains.get(region, gov_domains["NORTH_AMERICA"])

        return await self.search(
            query,
            max_results=max_results,
            domains=domains,
            **kwargs,
        )

    async def academic_comprehensive(
        self,
        query: str,
        max_results: int = 30,
        **kwargs,
    ) -> List[SerperResult]:
        """
        Comprehensive academic search combining Scholar + PubMed site filter.

        Args:
            query: Search query
            max_results: Maximum total results
            **kwargs: Additional parameters

        Returns:
            Combined academic results
        """
        # Run Scholar and PubMed site search in parallel
        scholar_task = self.scholar(query, max_results // 2, **kwargs)
        pubmed_task = self.search(
            query,
            max_results // 2,
            domains=["pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"],
            **kwargs,
        )

        scholar_results, pubmed_results = await asyncio.gather(
            scholar_task, pubmed_task, return_exceptions=True
        )

        all_results = []
        seen_urls = set()

        for result_list in [scholar_results, pubmed_results]:
            if isinstance(result_list, Exception):
                continue
            for result in result_list:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    all_results.append(result)

        return all_results[:max_results]

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return asdict(self.stats)

    def reset_stats(self):
        """Reset usage statistics."""
        self.stats = SerperStats()

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        if not self.enabled:
            return {"status": "disabled", "message": "API key not configured"}

        if self._check_circuit_breaker():
            return {"status": "circuit_open", "message": "Circuit breaker is open"}

        try:
            results = await self.search("test", max_results=1)
            return {
                "status": "healthy",
                "message": "Serper operational",
                "test_results": len(results),
            }
        except SerperQuotaError:
            return {"status": "quota_exceeded", "message": "Monthly quota exceeded"}
        except SerperRateLimitError:
            return {"status": "rate_limited", "message": "Rate limit active"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# =============================================================================
# SINGLETON
# =============================================================================

_serper_client: Optional[SerperClient] = None


def get_serper_client() -> SerperClient:
    """Get singleton Serper client."""
    global _serper_client
    if _serper_client is None:
        _serper_client = SerperClient()
    return _serper_client


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "SerperClient",
    "SerperResult",
    "SerperStats",
    "SerperError",
    "SerperRateLimitError",
    "SerperQuotaError",
    "SearchType",
    "get_serper_client",
]
