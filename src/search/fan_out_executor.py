"""
POLARIS Fan-Out Search Executor
===============================
Parallel execution of 500+ searches across all sources for SOTA coverage.

Key features:
- Async parallel execution with rate limiting
- Circuit breaker per source
- URL deduplication (URL, content hash, title similarity)
- Progress tracking and logging
- Batch size optimization

Per CLAUDE.md LAW VI: Zero hard-coding. Uses DepthConfig for all parameters.
"""

import asyncio
import hashlib
import logging
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived


logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SearchResult:
    """A single search result."""
    url: str
    title: str
    snippet: str
    source: str
    query: str
    rank: int = 0
    content_hash: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FanOutStats:
    """Statistics from fan-out execution."""
    total_queries: int
    successful_queries: int
    failed_queries: int
    total_results: int
    unique_results: int
    duplicate_results: int
    execution_time_seconds: float
    results_per_source: Dict[str, int]
    errors: List[str]


# =============================================================================
# Circuit Breaker
# =============================================================================

class CircuitBreaker:
    """
    Circuit breaker for source resilience.

    Opens after consecutive failures, half-opens after cooldown,
    closes after successful request.
    """

    def __init__(
        self,
        source_name: str,
        failure_threshold: int = 5,
        cooldown_seconds: int = 60,
    ):
        self.source_name = source_name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open

    def record_success(self):
        """Record successful request."""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self):
        """Record failed request."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker OPEN for {self.source_name}")

    def is_available(self) -> bool:
        """Check if source is available."""
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if cooldown has passed
            if self.last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                if elapsed >= self.cooldown_seconds:
                    self.state = "half-open"
                    logger.info(f"Circuit breaker HALF-OPEN for {self.source_name}")
                    return True
            return False

        # half-open - allow one request
        return True


# =============================================================================
# Fan-Out Executor
# =============================================================================

class FanOutExecutor:
    """
    Parallel search executor for SOTA-level coverage.

    Features:
    - Async parallel execution across all sources
    - Per-source rate limiting
    - Circuit breaker for resilience
    - URL deduplication (URL, content hash, title)
    - Progress tracking and logging

    Usage:
        executor = FanOutExecutor()
        results = await executor.execute_parallel(
            queries=["query1", "query2", ...],
            sources=["web", "scholar", "pubmed"],
        )
    """

    def __init__(self):
        """Initialize with DepthConfig (LAW VI)."""
        self.depth_config = get_depth_config()
        self.fan_out_config = self.depth_config.fan_out

        # Circuit breakers per source
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Rate limiters per source (semaphores)
        self.rate_limiters: Dict[str, asyncio.Semaphore] = {}

        # Deduplication tracking
        self.seen_urls: Set[str] = set()
        self.seen_content_hashes: Set[str] = set()
        self.seen_titles: Set[str] = set()

    def _get_circuit_breaker(self, source: str) -> CircuitBreaker:
        """Get or create circuit breaker for source."""
        if source not in self.circuit_breakers:
            self.circuit_breakers[source] = CircuitBreaker(source)
        return self.circuit_breakers[source]

    def _get_rate_limiter(self, source: str) -> asyncio.Semaphore:
        """Get or create rate limiter for source."""
        if source not in self.rate_limiters:
            # Different limits per source
            limits = {
                "web": 10,
                "scholar": 5,
                "pubmed": 3,
                "news": 10,
                "patents": 5,
            }
            limit = limits.get(source, 5)
            self.rate_limiters[source] = asyncio.Semaphore(limit)
        return self.rate_limiters[source]

    async def execute_parallel(
        self,
        queries: List[str],
        sources: List[str],
        search_func: Callable,
        max_results_per_query: int = None,
    ) -> List[SearchResult]:
        """
        Execute searches in parallel across all sources.

        Args:
            queries: List of search queries
            sources: List of source types
            search_func: Async function to execute search
            max_results_per_query: Max results per query (defaults to DepthConfig)

        Returns:
            List of deduplicated SearchResult objects
        """
        start_time = datetime.now(timezone.utc)

        # Use DepthConfig if not specified
        if max_results_per_query is None:
            max_results_per_query = self.fan_out_config.results_per_source

        # Create tasks for all query-source combinations
        tasks = []
        for query in queries:
            for source in sources:
                # Check circuit breaker
                cb = self._get_circuit_breaker(source)
                if not cb.is_available():
                    continue

                task = self._execute_search(
                    query=query,
                    source=source,
                    search_func=search_func,
                    max_results=max_results_per_query,
                )
                tasks.append(task)

        logger.info(f"Fan-out: Executing {len(tasks)} searches ({len(queries)} queries x {len(sources)} sources)")

        # Execute in batches to respect rate limits
        all_results = []
        batch_size = self.fan_out_config.batch_size
        errors = []

        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                elif result:
                    all_results.extend(result)

        # Deduplicate
        unique_results = self._deduplicate_results(all_results)

        # Calculate stats
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        results_per_source = self._count_by_source(unique_results)

        logger.info(
            f"Fan-out complete: {len(unique_results)} unique results from {len(all_results)} total "
            f"({len(all_results) - len(unique_results)} duplicates removed) in {execution_time:.1f}s"
        )

        return unique_results

    async def _execute_search(
        self,
        query: str,
        source: str,
        search_func: Callable,
        max_results: int,
    ) -> List[SearchResult]:
        """Execute a single search with rate limiting and circuit breaker."""
        cb = self._get_circuit_breaker(source)
        rate_limiter = self._get_rate_limiter(source)

        async with rate_limiter:
            try:
                # Call the search function
                results = await search_func(
                    query=query,
                    source=source,
                    max_results=max_results,
                )

                cb.record_success()
                return results

            except Exception as e:
                cb.record_failure()
                logger.error(f"Search failed for {source}: {e}")
                return []

    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Deduplicate results by URL, content hash, and title similarity."""
        unique = []

        for result in results:
            # URL deduplication
            normalized_url = self._normalize_url(result.url)
            if normalized_url in self.seen_urls:
                continue

            # Content hash deduplication (if available)
            if result.content_hash and result.content_hash in self.seen_content_hashes:
                continue

            # Title deduplication (exact match)
            normalized_title = result.title.lower().strip()
            if normalized_title in self.seen_titles and len(normalized_title) > 20:
                continue

            # Mark as seen
            self.seen_urls.add(normalized_url)
            if result.content_hash:
                self.seen_content_hashes.add(result.content_hash)
            self.seen_titles.add(normalized_title)

            unique.append(result)

        return unique

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        try:
            parsed = urlparse(url)
            # Remove scheme, www, trailing slash
            normalized = f"{parsed.netloc.replace('www.', '')}{parsed.path.rstrip('/')}"
            return normalized.lower()
        except Exception:
            return url.lower()

    def _count_by_source(self, results: List[SearchResult]) -> Dict[str, int]:
        """Count results by source."""
        counts: Dict[str, int] = {}
        for result in results:
            source = result.source
            counts[source] = counts.get(source, 0) + 1
        return counts

    def get_stats(self) -> Dict[str, Any]:
        """Get current execution stats."""
        return {
            "circuit_breakers": {
                name: {
                    "state": cb.state,
                    "failures": cb.failure_count,
                }
                for name, cb in self.circuit_breakers.items()
            },
            "seen_urls": len(self.seen_urls),
            "seen_content_hashes": len(self.seen_content_hashes),
            "seen_titles": len(self.seen_titles),
        }

    def reset(self):
        """Reset deduplication state."""
        self.seen_urls.clear()
        self.seen_content_hashes.clear()
        self.seen_titles.clear()


# =============================================================================
# Standalone Functions
# =============================================================================

async def execute_fan_out(
    queries: List[str],
    sources: List[str],
    search_func: Callable,
) -> List[SearchResult]:
    """
    Standalone function for fan-out search execution.

    Args:
        queries: List of search queries
        sources: List of source types
        search_func: Async function to execute search

    Returns:
        List of deduplicated results
    """
    executor = FanOutExecutor()
    return await executor.execute_parallel(queries, sources, search_func)


def calculate_expected_results(
    query_count: int,
    source_count: int,
    results_per_query: int = None,
) -> int:
    """
    Calculate expected results from fan-out execution.

    Args:
        query_count: Number of queries
        source_count: Number of sources
        results_per_query: Results per query (defaults to DepthConfig)

    Returns:
        Expected result count (before deduplication)
    """
    if results_per_query is None:
        config = get_depth_config()
        results_per_query = config.fan_out.results_per_source

    return query_count * source_count * results_per_query


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "FanOutExecutor",
    "SearchResult",
    "FanOutStats",
    "CircuitBreaker",
    "execute_fan_out",
    "calculate_expected_results",
]
