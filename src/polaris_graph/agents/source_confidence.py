"""
Source confidence rating module for polaris graph.

Computes composite confidence scores for evidence sources using three signals:
1. Open PageRank API (domain authority, 0-10 normalized to 0.0-1.0)
2. Source type hierarchy (static scores by publication type)
3. Citation count (logarithmic scaling, capped at 100)

Composite formula: 0.4 * pagerank_norm + 0.4 * type_score + 0.2 * citation_factor

Controlled by env var PG_SOURCE_CONFIDENCE_ENABLED (default "0" - disabled).
PageRank API key from env var OPEN_PAGERANK_API_KEY.
"""

import logging
import os
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature gate
# ---------------------------------------------------------------------------
# Legacy module-level constant (kept for backward compatibility in tests)
PG_SOURCE_CONFIDENCE_ENABLED = os.getenv("PG_SOURCE_CONFIDENCE_ENABLED", "0") == "1"


def _is_enabled() -> bool:
    """Runtime check for source confidence feature gate.

    FIX-RUNTIME-GATE: Module-level constants bind at import time.
    If .env is loaded after import, the constant is stale.
    Use this function instead of PG_SOURCE_CONFIDENCE_ENABLED at call sites.
    """
    return os.getenv("PG_SOURCE_CONFIDENCE_ENABLED", "0") == "1"

# ---------------------------------------------------------------------------
# Open PageRank API configuration
# ---------------------------------------------------------------------------
PAGERANK_API_URL = "https://openpagerank.com/api/v1.0/getPageRank"
PAGERANK_MAX_BATCH_SIZE = 100
PAGERANK_MAX_SCORE = 10.0

# ---------------------------------------------------------------------------
# Composite score weights
# ---------------------------------------------------------------------------
WEIGHT_PAGERANK = 0.4
WEIGHT_TYPE = 0.4
WEIGHT_CITATION = 0.2
CITATION_CAP = 100

# ---------------------------------------------------------------------------
# Source type hierarchy (static scores)
# ---------------------------------------------------------------------------
_SOURCE_TYPE_SCORES: dict[str, float] = {
    "journal_article": 0.95,
    "government_report": 0.90,
    "standard": 0.90,
    "book": 0.85,
    "industry_report": 0.70,
    "news": 0.60,
    "blog": 0.40,
    "unknown": 0.30,
}

# ---------------------------------------------------------------------------
# Module-level domain -> pagerank cache (avoids duplicate API lookups)
# ---------------------------------------------------------------------------
_pagerank_cache: dict[str, float] = {}


def _extract_domain(url: str) -> str:
    """Extract the root domain from a URL.

    Strips 'www.' prefix to normalize domains.
    Returns empty string if the URL cannot be parsed.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception:
        logger.debug("Failed to parse URL for domain extraction: %s", url)
        return ""


def get_type_confidence(source_type: str) -> float:
    """Return the static confidence score for a source type.

    Args:
        source_type: One of the keys in the source type hierarchy
                     (e.g. "journal_article", "news", "blog").
                     Case-insensitive; unknown types return 0.30.

    Returns:
        Confidence score between 0.0 and 1.0.
    """
    normalized = source_type.strip().lower().replace("-", "_").replace(" ", "_")
    score = _SOURCE_TYPE_SCORES.get(normalized, _SOURCE_TYPE_SCORES["unknown"])
    return score


def compute_composite_confidence(
    pagerank: float,
    type_score: float,
    citation_count: int = 0,
) -> float:
    """Compute the composite confidence score from three signals.

    Formula: 0.4 * pagerank_norm + 0.4 * type_score + 0.2 * min(citation_count/100, 1.0)

    Args:
        pagerank: Normalized PageRank score (0.0-1.0).
        type_score: Source type confidence score (0.0-1.0).
        citation_count: Number of citations for the source (>= 0).

    Returns:
        Composite confidence score between 0.0 and 1.0.
    """
    pagerank_clamped = max(0.0, min(1.0, pagerank))
    type_clamped = max(0.0, min(1.0, type_score))
    citation_factor = min(max(0, citation_count) / CITATION_CAP, 1.0)

    composite = (
        WEIGHT_PAGERANK * pagerank_clamped
        + WEIGHT_TYPE * type_clamped
        + WEIGHT_CITATION * citation_factor
    )
    return round(composite, 4)


async def get_source_confidence(urls: list[str]) -> dict[str, float]:
    """Batch-lookup PageRank scores for a list of URLs.

    Extracts the domain from each URL, deduplicates, checks the module-level
    cache, and queries the Open PageRank API for any uncached domains (batched
    up to 100 per API call).

    Args:
        urls: List of source URLs to score.

    Returns:
        Dict mapping each input URL to its normalized PageRank score (0.0-1.0).
        URLs whose domains fail lookup receive a score of 0.0.
    """
    import aiohttp

    api_key = os.getenv("OPEN_PAGERANK_API_KEY", "")
    if not api_key:
        logger.warning(
            "[polaris graph] OPEN_PAGERANK_API_KEY not set; "
            "returning 0.0 for all URLs"
        )
        return {url: 0.0 for url in urls}

    # Map URL -> domain, track unique domains needing lookup
    url_to_domain: dict[str, str] = {}
    domains_to_lookup: list[str] = []

    for url in urls:
        domain = _extract_domain(url)
        url_to_domain[url] = domain
        if not domain:
            continue
        if domain not in _pagerank_cache and domain not in domains_to_lookup:
            domains_to_lookup.append(domain)

    # Query the API in batches of PAGERANK_MAX_BATCH_SIZE
    if domains_to_lookup:
        headers = {"API-OPR": api_key}
        timeout = aiohttp.ClientTimeout(total=30)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for batch_start in range(
                    0, len(domains_to_lookup), PAGERANK_MAX_BATCH_SIZE
                ):
                    batch = domains_to_lookup[
                        batch_start : batch_start + PAGERANK_MAX_BATCH_SIZE
                    ]
                    params: list[tuple[str, str]] = [
                        ("domains[]", domain) for domain in batch
                    ]

                    try:
                        async with session.get(
                            PAGERANK_API_URL,
                            headers=headers,
                            params=params,
                        ) as response:
                            if response.status != 200:
                                logger.warning(
                                    "[polaris graph] PageRank API returned "
                                    "status %d for batch of %d domains",
                                    response.status,
                                    len(batch),
                                )
                                # Cache failures as 0.0 so we don't retry
                                for domain in batch:
                                    _pagerank_cache.setdefault(domain, 0.0)
                                continue

                            data: dict[str, Any] = await response.json()
                            _parse_pagerank_response(data, batch)

                    except aiohttp.ClientError as exc:
                        logger.warning(
                            "[polaris graph] PageRank API network error "
                            "for batch of %d domains: %s",
                            len(batch),
                            exc,
                        )
                        for domain in batch:
                            _pagerank_cache.setdefault(domain, 0.0)

        except Exception as exc:
            logger.error(
                "[polaris graph] PageRank API session error: %s", exc
            )
            for domain in domains_to_lookup:
                _pagerank_cache.setdefault(domain, 0.0)

    # Build result mapping
    result: dict[str, float] = {}
    for url in urls:
        domain = url_to_domain.get(url, "")
        raw_score = _pagerank_cache.get(domain, 0.0)
        result[url] = round(raw_score / PAGERANK_MAX_SCORE, 4)

    logger.info(
        "[polaris graph] PageRank lookup: %d URLs, %d unique domains, "
        "%d cache hits, %d API lookups",
        len(urls),
        len(set(url_to_domain.values()) - {""}),
        len(set(url_to_domain.values()) - {""}) - len(domains_to_lookup),
        len(domains_to_lookup),
    )

    return result


def _parse_pagerank_response(
    data: dict[str, Any], batch: list[str]
) -> None:
    """Parse the Open PageRank API response and populate the cache.

    The API returns a response shaped like:
    {
        "status_code": 200,
        "response": [
            {
                "status_code": 200,
                "domain": "example.com",
                "page_rank_integer": 7,
                "page_rank_decimal": 7.23,
                "rank": "12345"
            },
            ...
        ]
    }

    Args:
        data: Parsed JSON response from the API.
        batch: List of domains in this batch (used for fallback on missing).
    """
    seen_domains: set[str] = set()
    response_items = data.get("response", [])

    for item in response_items:
        if not isinstance(item, dict):
            continue

        domain = item.get("domain", "")
        if not domain:
            continue

        seen_domains.add(domain.lower())

        # Prefer the decimal score for precision
        score = item.get("page_rank_decimal")
        if score is None:
            score = item.get("page_rank_integer", 0)

        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0

        # Clamp to valid range
        score = max(0.0, min(PAGERANK_MAX_SCORE, score))
        _pagerank_cache[domain.lower()] = score

    # Any domains not in the response get cached as 0.0
    for domain in batch:
        if domain.lower() not in seen_domains:
            _pagerank_cache.setdefault(domain.lower(), 0.0)
