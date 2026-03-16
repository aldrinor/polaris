"""
POLARIS Result Cache

SOTA FIX: Issues #51-54 - Performance optimizations.

Provides caching for:
- Search results
- LLM responses
- Evidence extraction results
- Quality assessments
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached entry with metadata."""
    key: str
    value: Any
    created_at: float
    expires_at: float
    hit_count: int = 0


class ResultCache:
    """
    In-memory result cache with TTL support.

    SOTA FIX: Issue #52 - Result caching.
    """

    def __init__(
        self,
        default_ttl_seconds: int = 3600,
        max_entries: int = 10000,
    ):
        """
        Initialize cache.

        Args:
            default_ttl_seconds: Default time-to-live in seconds
            max_entries: Maximum number of entries
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]

        # Check expiration
        if time.time() > entry.expires_at:
            del self._cache[key]
            self._misses += 1
            return None

        entry.hit_count += 1
        self._hits += 1
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set value in cache."""
        # Evict old entries if at capacity
        if len(self._cache) >= self._max_entries:
            self._evict_oldest()

        ttl = ttl_seconds or self._default_ttl
        now = time.time()

        self._cache[key] = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + ttl,
        )

    def _evict_oldest(self, count: int = 100) -> None:
        """Evict oldest entries."""
        if not self._cache:
            return

        # Sort by created_at and remove oldest
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at
        )

        for key in sorted_keys[:count]:
            del self._cache[key]

    def invalidate(self, key: str) -> bool:
        """Remove entry from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


def cached(
    cache: ResultCache,
    ttl_seconds: Optional[int] = None,
    key_prefix: str = "",
):
    """
    Decorator for caching function results.

    SOTA FIX: Issue #52 - Result caching decorator.

    Args:
        cache: ResultCache instance
        ttl_seconds: Optional TTL override
        key_prefix: Prefix for cache keys

    Usage:
        cache = ResultCache()

        @cached(cache, ttl_seconds=300)
        def expensive_function(arg1, arg2):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key_data = json.dumps({
                "prefix": key_prefix,
                "func": func.__name__,
                "args": args,
                "kwargs": kwargs
            }, sort_keys=True, default=str)
            key = hashlib.md5(key_data.encode()).hexdigest()

            # Check cache
            cached_value = cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_value

            # Execute function
            result = func(*args, **kwargs)

            # Store in cache
            cache.set(key, result, ttl_seconds)
            logger.debug(f"Cached result for {func.__name__}")

            return result

        return wrapper
    return decorator


class SearchResultCache(ResultCache):
    """
    Specialized cache for search results.

    SOTA FIX: Issue #51 - Search result caching.
    """

    def __init__(self, ttl_seconds: int = 1800):  # 30 min default
        super().__init__(
            default_ttl_seconds=ttl_seconds,
            max_entries=5000,
        )

    def get_search_results(
        self,
        query: str,
        source: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached search results."""
        key = self._generate_key(query=query, source=source)
        return self.get(key)

    def cache_search_results(
        self,
        query: str,
        source: str,
        results: List[Dict[str, Any]],
    ) -> None:
        """Cache search results."""
        key = self._generate_key(query=query, source=source)
        self.set(key, results)


class LLMResponseCache(ResultCache):
    """
    Specialized cache for LLM responses.

    SOTA FIX: Issue #53 - LLM response caching.
    """

    def __init__(self, ttl_seconds: int = 7200):  # 2 hour default
        super().__init__(
            default_ttl_seconds=ttl_seconds,
            max_entries=2000,
        )

    def get_response(
        self,
        prompt_hash: str,
        model: str,
    ) -> Optional[str]:
        """Get cached LLM response."""
        key = f"{model}:{prompt_hash}"
        return self.get(key)

    def cache_response(
        self,
        prompt_hash: str,
        model: str,
        response: str,
    ) -> None:
        """Cache LLM response."""
        key = f"{model}:{prompt_hash}"
        self.set(key, response)

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """Generate hash for prompt."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]


# =============================================================================
# Parallel Execution Utilities
# =============================================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed


async def parallel_async(
    tasks: List[Callable],
    max_concurrent: int = 10,
) -> List[Any]:
    """
    Execute async tasks in parallel with concurrency limit.

    SOTA FIX: Issue #54 - Parallel execution.

    Args:
        tasks: List of async coroutines
        max_concurrent: Maximum concurrent tasks

    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def limited_task(task):
        async with semaphore:
            return await task

    results = await asyncio.gather(
        *[limited_task(t) for t in tasks],
        return_exceptions=True
    )

    # Filter out exceptions
    valid_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"Parallel task failed: {r}")
        else:
            valid_results.append(r)

    return valid_results


def parallel_sync(
    func: Callable,
    args_list: List[tuple],
    max_workers: int = 10,
) -> List[Any]:
    """
    Execute function calls in parallel using thread pool.

    SOTA FIX: Issue #54 - Parallel execution.

    Args:
        func: Function to execute
        args_list: List of argument tuples
        max_workers: Maximum worker threads

    Returns:
        List of results
    """
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(func, *args): i
            for i, args in enumerate(args_list)
        }

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.warning(f"Parallel task failed: {e}")

    return results


# =============================================================================
# Global Cache Instances
# =============================================================================

_search_cache: Optional[SearchResultCache] = None
_llm_cache: Optional[LLMResponseCache] = None


def get_search_cache() -> SearchResultCache:
    """Get global search result cache."""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchResultCache()
    return _search_cache


def get_llm_cache() -> LLMResponseCache:
    """Get global LLM response cache."""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMResponseCache()
    return _llm_cache
