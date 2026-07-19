"""Rate-Limited Fetch Helper (Fix R4-#4).

In v1, the pipeline was slow enough to naturally rate-limit itself. In v2,
asyncio.to_thread + concurrent fetching can fire 150 requests simultaneously,
instantly hitting HTTP 429 (Too Many Requests) on Jina Reader, Serper, or S2.

The existing analyzer.py uses asyncio.Semaphore(PG_FETCH_CONCURRENCY=5) for
content fetching. This module provides a reusable rate-limited wrapper that
the v2 CRAG graph node should use for any URL fetching.

Integration point: The CRAG graph node should use `rate_limited_fetch()`
instead of raw httpx/requests calls.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any, Callable, Optional
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph")

# Concurrency cap — matches existing PG_FETCH_CONCURRENCY default
FETCH_CONCURRENCY = int(os.getenv("PG_FETCH_CONCURRENCY", "10"))

# Retry config for 429/5xx responses
MAX_RETRIES = int(resolve("PG_FETCH_MAX_RETRIES"))
RETRY_BASE_SECONDS = float(resolve("PG_FETCH_RETRY_BASE"))
RETRY_MAX_SECONDS = float(resolve("PG_FETCH_RETRY_MAX"))

# Per-fetch timeout
FETCH_TIMEOUT_SECONDS = int(os.getenv("PG_FETCH_TIMEOUT", "30"))

# Module-level semaphore (shared across all callers)
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (must be created inside an event loop)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    return _semaphore


async def rate_limited_fetch(
    url: str,
    fetch_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute a fetch function with semaphore throttling and retry.

    Fix R4-#4: Prevents 429 burst limit errors by:
    1. Semaphore: max PG_FETCH_CONCURRENCY concurrent requests
    2. Retry: exponential backoff with jitter on 429/5xx
    3. Timeout: per-fetch timeout via asyncio.wait_for

    Args:
        url: URL being fetched (for logging).
        fetch_fn: The actual fetch function (sync or async).
                  If sync, it will be wrapped in asyncio.to_thread.
        *args, **kwargs: Passed through to fetch_fn.

    Returns:
        Whatever fetch_fn returns.

    Raises:
        Exception: After MAX_RETRIES exhausted.
    """
    sem = _get_semaphore()

    for attempt in range(1, MAX_RETRIES + 1):
        async with sem:
            try:
                # Run the fetch (with timeout)
                if asyncio.iscoroutinefunction(fetch_fn):
                    result = await asyncio.wait_for(
                        fetch_fn(url, *args, **kwargs),
                        timeout=FETCH_TIMEOUT_SECONDS,
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(fetch_fn, url, *args, **kwargs),
                        timeout=FETCH_TIMEOUT_SECONDS,
                    )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    "Fetch timeout (%ds) for %s (attempt %d/%d)",
                    FETCH_TIMEOUT_SECONDS, url[:80], attempt, MAX_RETRIES,
                )
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "rate limit" in error_str
                is_server_error = any(
                    code in error_str for code in ("500", "502", "503", "504")
                )

                if (is_rate_limit or is_server_error) and attempt < MAX_RETRIES:
                    # Exponential backoff with jitter
                    delay = min(
                        RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                        RETRY_MAX_SECONDS,
                    )
                    jitter = random.uniform(0, delay * 0.5)
                    total_delay = delay + jitter
                    logger.info(
                        "Fetch %s: %s, retrying in %.1fs (attempt %d/%d)",
                        "429" if is_rate_limit else "5xx",
                        url[:60], total_delay, attempt, MAX_RETRIES,
                    )
                    await asyncio.sleep(total_delay)
                else:
                    if attempt >= MAX_RETRIES:
                        logger.warning(
                            "Fetch failed after %d attempts: %s — %s",
                            MAX_RETRIES, url[:80], str(e)[:200],
                        )
                    raise

    return None


async def rate_limited_fetch_batch(
    urls: list[str],
    fetch_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Fetch multiple URLs with rate limiting.

    Returns dict of url -> result. Failed fetches map to None.
    """
    tasks = {
        url: asyncio.create_task(
            rate_limited_fetch(url, fetch_fn, *args, **kwargs)
        )
        for url in urls
    }

    results: dict[str, Any] = {}
    for url, task in tasks.items():
        try:
            results[url] = await task
        except Exception:
            results[url] = None

    succeeded = sum(1 for v in results.values() if v is not None)
    logger.info(
        "Batch fetch: %d/%d succeeded (concurrency=%d)",
        succeeded, len(urls), FETCH_CONCURRENCY,
    )
    return results
