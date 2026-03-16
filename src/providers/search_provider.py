"""Search Provider Abstraction — Cloud APIs (Serper/Exa/Tavily) or SearxNG (sovereign)."""

import os
import logging
from typing import Optional

logger = logging.getLogger("polaris.providers.search")

# Provider configuration from environment (LAW VI)
SEARCH_PROVIDER = os.getenv("POLARIS_SEARCH_PROVIDER", "cloud")  # cloud | searxng | internal
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
SEARXNG_FORMAT = os.getenv("SEARXNG_FORMAT", "json")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Internal corpus configuration (for air-gapped with pre-loaded documents)
INTERNAL_CORPUS_PATH = os.getenv("POLARIS_INTERNAL_CORPUS_PATH", "data/corpus")
INTERNAL_CORPUS_COLLECTION = os.getenv("POLARIS_INTERNAL_CORPUS_COLLECTION", "polaris_corpus")


class SearchProviderConfig:
    """Configuration for search provider."""

    def __init__(self):
        self.provider = SEARCH_PROVIDER.lower()
        self._validate()

    def _validate(self):
        """Validate provider configuration."""
        if self.provider == "cloud":
            if not SERPER_API_KEY:
                logger.warning("SERPER_API_KEY not set — web search will fail")
        elif self.provider == "searxng":
            logger.info(f"Search Provider: SearxNG at {SEARXNG_BASE_URL}")
        elif self.provider == "internal":
            if not os.path.isdir(INTERNAL_CORPUS_PATH):
                logger.warning(f"Internal corpus path does not exist: {INTERNAL_CORPUS_PATH}")
            logger.info(f"Search Provider: Internal corpus at {INTERNAL_CORPUS_PATH}")
        else:
            raise ValueError(
                f"Unknown search provider: '{self.provider}'. "
                f"Must be one of: cloud, searxng, internal. "
                f"Set POLARIS_SEARCH_PROVIDER in .env"
            )

    @property
    def is_cloud(self) -> bool:
        return self.provider == "cloud"

    @property
    def is_searxng(self) -> bool:
        return self.provider == "searxng"

    @property
    def is_internal(self) -> bool:
        return self.provider == "internal"

    def get_searxng_url(self, query: str, num_results: int = 10) -> str:
        """Build SearxNG search URL."""
        import urllib.parse
        params = urllib.parse.urlencode({
            "q": query,
            "format": SEARXNG_FORMAT,
            "pageno": 1,
            "categories": "general",
        })
        return f"{SEARXNG_BASE_URL}/search?{params}"


async def search_searxng(query: str, num_results: int = 10) -> list[dict]:
    """Execute search via SearxNG instance.

    Returns list of dicts with: title, url, snippet, source
    Compatible with Serper result format for easy swapping.
    """
    import aiohttp

    config = SearchProviderConfig()
    url = config.get_searxng_url(query, num_results)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"SearxNG search failed: HTTP {resp.status}")
                    return []
                data = await resp.json()
    except Exception as e:
        logger.error(f"SearxNG search error: {e}")
        return []

    results = []
    for item in data.get("results", [])[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
            "source": "searxng",
            "position": len(results) + 1,
        })

    logger.info(f"SearxNG returned {len(results)} results for: {query[:80]}")
    return results


def validate_search_provider() -> dict:
    """Validate search provider configuration. Returns status dict."""
    try:
        config = SearchProviderConfig()
        available_engines = []
        if config.is_cloud:
            if SERPER_API_KEY:
                available_engines.append("serper")
            if EXA_API_KEY:
                available_engines.append("exa")
            if TAVILY_API_KEY:
                available_engines.append("tavily")
            available_engines.append("duckduckgo")  # Always available, no key needed
            available_engines.append("semantic_scholar")
        elif config.is_searxng:
            available_engines.append("searxng")
        elif config.is_internal:
            available_engines.append("internal_corpus")

        return {
            "provider": config.provider,
            "engines": available_engines,
            "status": "configured" if available_engines else "warning",
            "error": None if available_engines else "No search engines available",
        }
    except ValueError as e:
        return {
            "provider": SEARCH_PROVIDER,
            "engines": [],
            "status": "error",
            "error": str(e),
        }
