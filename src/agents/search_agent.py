"""
POLARIS v3 Search Agent

Executes searches based on sub-queries from the Planner.
Supports multiple search backends:
- Web search (Serper Google Search, DuckDuckGo fallback)
- Academic search (Serper Scholar, Semantic Scholar, PubMed, arXiv)
- Domain-specific search (EPA, FDA, CDC via Serper site: filters)

SOTA Deep Research multi-source approach with Serper.dev integration.
"""

import os
import logging
import hashlib
import threading
import time
from typing import List, Optional, Literal, Set
from datetime import datetime, timezone
from pathlib import Path

# FIX-121: Explicit path for environment loading
# This ensures .env is loaded correctly regardless of CWD during pipeline execution
# LOOPBACK-FIX: override=False so pre-set os.environ values (test harnesses,
# loopback scripts) win over .env defaults. Was override=True which clobbered
# programmatic overrides set BEFORE import at module-load time.
from dotenv import load_dotenv
_SEARCH_AGENT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_SEARCH_AGENT_ENV, override=False)

import yaml
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, SubQuery, SearchResult
try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived; polaris_graph does not use depth_config
from src.search.query_amplifier import QueryAmplifier, amplify_query


# =============================================================================
# FIX 105C: POLITE THROTTLING - Semaphore-based concurrency control
# =============================================================================
# Gemini Deep Audit identified 429 rate limit errors as a "Supply Chain" blocker
# that prevents evidence retrieval. The fix uses semaphores to limit concurrent
# requests to academic APIs:
# - Semantic Scholar: max 3 concurrent (their rate limit is generous)
# - PubMed: max 1 concurrent (very strict rate limits)
# - arXiv: max 2 concurrent (moderate)
#
# This prevents the "supply chain" failure where rate limits block evidence
# retrieval, causing the Death Spiral.
# =============================================================================

# Semaphores for rate limiting (thread-safe)
_SEMANTIC_SCHOLAR_SEMAPHORE = threading.Semaphore(
    int(os.environ.get("POLARIS_SEMANTIC_SCHOLAR_CONCURRENCY", "1"))  # FIX: Reduced from 3 to 1 (429 errors)
)
_PUBMED_SEMAPHORE = threading.Semaphore(
    int(os.environ.get("POLARIS_PUBMED_CONCURRENCY", "1"))
)
_ARXIV_SEMAPHORE = threading.Semaphore(
    int(os.environ.get("POLARIS_ARXIV_CONCURRENCY", "2"))
)
_WEB_SEARCH_SEMAPHORE = threading.Semaphore(
    int(os.environ.get("POLARIS_WEB_SEARCH_CONCURRENCY", "5"))
)

# Track last request time for additional rate limiting
_LAST_REQUEST_TIME = {
    "semantic_scholar": 0.0,
    "pubmed": 0.0,
    "arxiv": 0.0,
    "serper": 0.0,  # FIX: Add Serper rate limiting
}
_MIN_REQUEST_INTERVAL = {
    "semantic_scholar": 1.2,  # FIX: 1.2s between requests (1 RPS limit with API key)
    "pubmed": 1.0,           # 1 second between requests (strict)
    "arxiv": 0.3,            # 300ms between requests
    "serper": 0.3,           # FIX: 300ms between Serper requests
}
_REQUEST_LOCK = threading.Lock()


def _wait_for_rate_limit(api_name: str):
    """FIX 105C: Ensure minimum interval between requests to the same API.

    This provides additional protection beyond semaphores by enforcing
    a minimum time gap between consecutive requests.
    """
    with _REQUEST_LOCK:
        min_interval = _MIN_REQUEST_INTERVAL.get(api_name, 0.2)
        last_time = _LAST_REQUEST_TIME.get(api_name, 0.0)
        elapsed = time.time() - last_time

        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            logger.debug(f"[FIX 105C] Rate limit: sleeping {sleep_time:.2f}s before {api_name} request")
            time.sleep(sleep_time)

        _LAST_REQUEST_TIME[api_name] = time.time()


# =============================================================================
# Search Configuration (P1.2 domain blocklist removed 2026-04-13)
#
# The domain blocklist (fandom, youtube, tiktok, reddit, netflix, etc.) was
# removed on 2026-04-13. Reason: blocklists don't scale (infinite tail of
# garbage domains), and they limit source diversity. The PageRank/tier
# authority gate in src/polaris_graph/agents/analyzer.py + the pre-fetch
# authority gate (PG_AUTHORITY_GATE, default 0.3) handle filtering by
# SCORING sources, not by maintaining a manual list of names.
#
# Mirrors commits 74e1bf6 (wiki path) and 9ee62ff (polaris_graph analyzer path).
# =============================================================================

def load_search_config() -> dict:
    """Load search configuration (preferred domains, diversity, rate limits)."""
    config_path = Path(__file__).parent.parent.parent / "config" / "settings" / "search.yaml"
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {"preferred_domains": []}


# Load config at module level
_SEARCH_CONFIG = load_search_config()
_PREFERRED_DOMAINS: List[str] = _SEARCH_CONFIG.get("preferred_domains", [])
_DIVERSITY_CONFIG = _SEARCH_CONFIG.get("domain_diversity", {
    "max_results_per_domain": 10,
    "min_unique_domains": 15,
    "enabled": True,
    "warn_on_low_diversity": True,
    "low_diversity_threshold": 0.25,
})


def extract_domain_from_url(url: str) -> str:
    """
    Extract domain from URL for diversity tracking.

    Args:
        url: Full URL

    Returns:
        Domain string (e.g., 'example.com')
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove 'www.' prefix for consistency
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def enforce_domain_diversity(results: List[dict]) -> List[dict]:
    """
    Enforce domain diversity by capping results per domain.

    SOTA FIX W1.2: Prevents single domain dominance (was 38% from one domain).

    Args:
        results: List of search results with 'url' field

    Returns:
        Filtered list with domain caps applied
    """
    if not _DIVERSITY_CONFIG.get("enabled", True):
        return results

    max_per_domain = _DIVERSITY_CONFIG.get("max_results_per_domain", 10)

    # Count results per domain
    domain_counts: dict = {}
    filtered_results = []

    for r in results:
        url = r.get("url", "")
        domain = extract_domain_from_url(url)

        if not domain:
            # Keep results without valid URLs (e.g., graph results)
            filtered_results.append(r)
            continue

        current_count = domain_counts.get(domain, 0)

        if current_count < max_per_domain:
            filtered_results.append(r)
            domain_counts[domain] = current_count + 1
        else:
            logger.debug(f"[DIVERSITY-CAP] Skipped result from {domain} (cap={max_per_domain})")

    # Log diversity statistics
    unique_domains = len(domain_counts)
    total_results = len(results)
    kept_results = len(filtered_results)
    removed = total_results - kept_results

    if removed > 0:
        logger.info(
            f"[DIVERSITY-ENFORCEMENT] Kept {kept_results}/{total_results} results "
            f"({unique_domains} unique domains, removed {removed} over-cap)"
        )

    # Check for low diversity warning
    if _DIVERSITY_CONFIG.get("warn_on_low_diversity", True) and unique_domains > 0:
        max_domain_count = max(domain_counts.values()) if domain_counts else 0
        max_domain_pct = max_domain_count / kept_results if kept_results > 0 else 0
        low_diversity_threshold = _DIVERSITY_CONFIG.get("low_diversity_threshold", 0.25)

        if max_domain_pct > low_diversity_threshold:
            max_domain = max(domain_counts, key=domain_counts.get)
            logger.warning(
                f"[DIVERSITY-WARNING] Single domain {max_domain} has {max_domain_pct:.1%} "
                f"of results (threshold: {low_diversity_threshold:.0%})"
            )

    return filtered_results


def get_domain_statistics(results: List[dict]) -> dict:
    """
    Calculate domain diversity statistics for search results.

    Args:
        results: List of search results

    Returns:
        Dictionary with diversity metrics
    """
    domain_counts: dict = {}

    for r in results:
        url = r.get("url", "")
        domain = extract_domain_from_url(url)
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    total = len(results)
    unique = len(domain_counts)
    max_count = max(domain_counts.values()) if domain_counts else 0
    max_domain = max(domain_counts, key=domain_counts.get) if domain_counts else ""
    diversity_score = unique / total if total > 0 else 0

    return {
        "total_results": total,
        "unique_domains": unique,
        "max_single_domain_count": max_count,
        "max_single_domain": max_domain,
        "max_single_domain_pct": max_count / total if total > 0 else 0,
        "diversity_score": diversity_score,
        "domain_distribution": domain_counts,
    }


logger = logging.getLogger(__name__)


# =============================================================================
# FIX-124B: Perspective-Aware Deduplication
# =============================================================================

def deduplicate_results_with_perspective_merge(results: List["SearchResult"]) -> List["SearchResult"]:
    """
    Deduplicate search results by URL, merging perspective attributions.

    FIX-124B: When same URL found by multiple STORM perspectives,
    merge all perspectives into perspective_origins list instead of
    overwriting (which loses perspective attribution).

    Args:
        results: List of SearchResult objects to deduplicate

    Returns:
        List of unique SearchResult objects with merged perspective_origins
    """
    seen_urls: dict = {}

    for result in results:
        url = result.url.lower().rstrip("/")

        if url not in seen_urls:
            # First time seeing URL - ensure perspective_origins is initialized
            if result.perspective_origin and result.perspective_origin not in result.perspective_origins:
                result.perspective_origins = [result.perspective_origin] + list(result.perspective_origins)
            seen_urls[url] = result
        else:
            existing = seen_urls[url]
            # Merge perspective_origin into perspective_origins
            if result.perspective_origin and result.perspective_origin not in existing.perspective_origins:
                existing.perspective_origins.append(result.perspective_origin)

            # Keep higher-scored result but preserve merged perspectives
            existing_score = existing.metadata.get("score", 0.0) if existing.metadata else 0.0
            new_score = result.metadata.get("score", 0.0) if result.metadata else 0.0

            if new_score > existing_score:
                # Transfer merged perspectives to higher-scored result
                merged_perspectives = list(set(existing.perspective_origins))
                result.perspective_origins = merged_perspectives
                seen_urls[url] = result

    # Log multi-perspective URLs
    multi_count = sum(1 for r in seen_urls.values() if len(r.perspective_origins) > 1)
    if multi_count > 0:
        logger.info(f"[FIX-124B] {multi_count} URLs found by multiple perspectives")

    return list(seen_urls.values())


def get_perspective_coverage_stats(results: List["SearchResult"]) -> dict:
    """
    Calculate perspective coverage statistics for STORM tracking.

    FIX-124: Logs which STORM perspectives have results for coverage verification.

    Args:
        results: List of SearchResult objects

    Returns:
        Dictionary with perspective coverage stats
    """
    perspective_counts: dict = {}
    multi_perspective_urls = 0

    for r in results:
        # Count primary perspective
        if r.perspective_origin:
            perspective_counts[r.perspective_origin] = perspective_counts.get(r.perspective_origin, 0) + 1

        # Count multi-perspective URLs
        if len(r.perspective_origins) > 1:
            multi_perspective_urls += 1

    return {
        "total_results": len(results),
        "perspective_distribution": perspective_counts,
        "perspectives_covered": len(perspective_counts),
        "multi_perspective_urls": multi_perspective_urls,
    }


# =============================================================================
# Graph Search Tool
# =============================================================================

@tool
def graph_search(query: str, strategy: str = "hybrid", max_results: int = 20) -> List[dict]:
    """
    Search the knowledge graph for relevant entities and relationships.

    Args:
        query: Search query
        strategy: Retrieval strategy (entity_hop, path_based, subgraph, hybrid)
        max_results: Maximum results to return

    Returns:
        List of graph-based search results
    """
    try:
        from src.graph import get_graph_retriever, RetrievalStrategy

        retriever = get_graph_retriever(max_contexts=max_results)

        # Map string to enum
        strategy_map = {
            "entity_hop": RetrievalStrategy.ENTITY_HOP,
            "path_based": RetrievalStrategy.PATH_BASED,
            "subgraph": RetrievalStrategy.SUBGRAPH,
            "hybrid": RetrievalStrategy.HYBRID,
        }
        strategy_enum = strategy_map.get(strategy, RetrievalStrategy.HYBRID)

        result = retriever.retrieve(query=query, strategy=strategy_enum)

        results = []
        for ctx in result.contexts:
            results.append({
                "url": f"graph://{ctx.source_id}",
                "title": f"[Graph] {ctx.source_type.upper()}: {ctx.source_id}",
                "snippet": ctx.content,
                "score": ctx.relevance_score,
                "source_type": "graph",
                "metadata": ctx.metadata,
            })

        # Add entity information
        for entity in result.entities_found[:5]:
            entity_snippet = f"{entity.entity_type}: {entity.name}"
            if entity.properties:
                props = [f"{k}: {v}" for k, v in list(entity.properties.items())[:3]]
                entity_snippet += f" ({'; '.join(props)})"

            results.append({
                "url": f"graph://entity/{entity.entity_id}",
                "title": f"[Graph Entity] {entity.name}",
                "snippet": entity_snippet,
                "score": entity.confidence,
                "source_type": "graph_entity",
                "metadata": {
                    "entity_type": entity.entity_type,
                    "source_chunks": entity.source_chunks,
                }
            })

        logger.info(f"Graph search for '{query}' returned {len(results)} results")
        return results

    except ImportError as e:
        logger.warning(f"Graph module not available: {e}")
        return []
    except Exception as e:
        logger.error(f"Graph search failed: {e}")
        return []


# =============================================================================
# SERPER CLIENT INTEGRATION
# =============================================================================

import asyncio
import requests
import time
import random

# Import Serper client (kept for reference, but we use sync requests now)
try:
    from src.search.serper_client import SerperClient, get_serper_client, SerperResult
    SERPER_CLIENT_AVAILABLE = True
except ImportError:
    SERPER_CLIENT_AVAILABLE = False
    logger.warning("SerperClient not available, using fallback implementations")


# P0.3 FIX: Replace broken _run_async with synchronous Serper API calls
# The original _run_async caused "Event loop is closed" errors 100% of the time
# because asyncio.run() in a thread closes the event loop, breaking Serper.
# See: deployment_plan_20260126.md for full analysis

def _serper_search_sync(
    query: str,
    search_type: str = "search",
    max_results: int = 10,
    gl: str = "us",
    location: Optional[str] = None,
    domains: Optional[List[str]] = None,
    **kwargs
) -> List[dict]:
    """
    P0.3 FIX: Synchronous Serper API call using requests.

    Replaces async SerperClient to avoid event loop conflicts.

    Args:
        query: Search query
        search_type: Type of search (search, scholar, news, patents)
        max_results: Maximum results to return
        gl: Geographic location code
        location: Location string
        domains: List of domains to filter

    Returns:
        List of search result dicts
    """
    # FIX-121 DIAGNOSTIC: File-based logging to bypass stdout buffering in ThreadPoolExecutor
    import traceback
    diag_path = Path(__file__).parent.parent.parent / "logs" / "serper_diag.log"
    diag_path.parent.mkdir(exist_ok=True)

    try:
        api_key = os.getenv("SERPER_API_KEY")

        # FIX-121: Write to file to bypass stdout buffering
        with open(diag_path, "a") as f:
            f.write(f"\n[{datetime.now()}] _serper_search_sync ENTERED\n")
            f.write(f"  Query: {query[:100]}\n")
            f.write(f"  API Key: present={bool(api_key)}, len={len(api_key) if api_key else 0}\n")
            f.write(f"  CWD: {os.getcwd()}\n")
            f.write(f"  .env path: {_SEARCH_AGENT_ENV}\n")
            f.write(f"  .env exists: {_SEARCH_AGENT_ENV.exists()}\n")

        # FIX-121: Critical-level logging that always displays
        logger.debug(f"[FIX-121] _serper_search_sync ENTERED, API key present: {bool(api_key)}")

        # FIX: Rate limit Serper requests to avoid 429 errors
        _wait_for_rate_limit("serper")

        if not api_key:
            logger.warning("SERPER_API_KEY not set, falling back to DuckDuckGo")
            with open(diag_path, "a") as f:
                f.write(f"[{datetime.now()}] RETURNING EARLY: No API key\n")
            return []

        url = f"https://google.serper.dev/{search_type}"

        payload = {
            "q": query,
            "num": min(max_results, 100),
            "gl": gl,
        }

        if location:
            payload["location"] = location
        if domains:
            # Add site: operators to query
            domain_query = " OR ".join([f"site:{d}" for d in domains])
            payload["q"] = f"({payload['q']}) ({domain_query})"

        # Add any additional kwargs
        payload.update(kwargs)

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }

        # FIX-121: Log the request details
        with open(diag_path, "a") as f:
            f.write(f"[{datetime.now()}] Making request to {url}\n")
            f.write(f"  Payload: {payload}\n")

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        # FIX-121: Log the response
        with open(diag_path, "a") as f:
            f.write(f"[{datetime.now()}] Response received, status={response.status_code}\n")
            f.write(f"  Keys in response: {list(data.keys())}\n")

        # Parse results based on search type
        if search_type == "search":
            results = data.get("organic", [])
        elif search_type == "scholar":
            results = data.get("organic", [])
        elif search_type == "news":
            results = data.get("news", [])
        elif search_type == "patents":
            results = data.get("organic", [])
        else:
            results = data.get("organic", [])

        # Normalize result format
        # Map Serper search_type to valid SearchResult source_type
        source_type_map = {
            "search": "web",
            "scholar": "academic",
            "news": "news",
            "patents": "web",
        }
        normalized_source_type = source_type_map.get(search_type, "web")

        normalized = []
        for r in results:
            normalized.append({
                "url": r.get("link", ""),
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "position": r.get("position", 0),
                "source_type": normalized_source_type,
            })

        logger.info(f"Serper {search_type} returned {len(normalized)} results for: {query[:50]}...")

        # FIX-121: Log success
        with open(diag_path, "a") as f:
            f.write(f"[{datetime.now()}] SUCCESS: Returning {len(normalized)} results\n")

        # Domain blocklist filter removed 2026-04-13 — authority gate in
        # src/polaris_graph/agents/analyzer.py scores these downstream.
        return normalized

    except requests.exceptions.Timeout:
        logger.error(f"Serper API timeout for query: {query[:50]}...")
        with open(diag_path, "a") as f:
            f.write(f"[{datetime.now()}] TIMEOUT for query: {query[:50]}\n")
        return []
    except requests.exceptions.HTTPError as e:
        # FIX 119: Debug logging for Serper 400 errors
        logger.error(f"Serper API HTTP error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"[FIX 119] Serper response body: {e.response.text[:500] if e.response.text else 'empty'}")
            logger.error(f"[FIX 119] Failing query (first 200 chars): {payload.get('q', 'N/A')[:200]}")
            logger.error(f"[FIX 119] Query length: {len(payload.get('q', ''))}")
        with open(diag_path, "a") as f:
            f.write(f"[{datetime.now()}] HTTP ERROR: {e}\n")
            if hasattr(e, 'response') and e.response is not None:
                f.write(f"  Response body: {e.response.text[:500] if e.response.text else 'empty'}\n")
        return []
    except Exception as e:
        # FIX-121: Comprehensive exception logging
        logger.debug(f"[FIX-121] UNHANDLED EXCEPTION in _serper_search_sync: {e}")
        logger.debug(f"[FIX-121] Traceback: {traceback.format_exc()}")
        with open(diag_path, "a") as f:
            f.write(f"[{datetime.now()}] EXCEPTION: {e}\n")
            f.write(f"  Traceback: {traceback.format_exc()}\n")
        return []


def _run_async(coro):
    """
    DEPRECATED: This function caused 100% Serper failures.

    P0.3 FIX: Kept for backwards compatibility but logs deprecation warning.
    Use _serper_search_sync() instead.
    """
    logger.warning("DEPRECATED: _run_async() is broken and should not be used. "
                   "Use _serper_search_sync() instead.")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # This path causes "Event loop is closed" errors
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# =============================================================================
# Search Tools
# =============================================================================

class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(description="Search query")
    max_results: int = Field(default=10, description="Maximum results to return")
    domains: Optional[List[str]] = Field(default=None, description="Limit to specific domains")
    region: Optional[str] = Field(default=None, description="Geographic region (NORTH_AMERICA, EUROPE, ASIA_PACIFIC, GLOBAL)")


class AcademicSearchInput(BaseModel):
    """Input for academic search tool."""
    query: str = Field(description="Search query")
    max_results: int = Field(default=10, description="Maximum results to return")
    year_from: Optional[int] = Field(default=None, description="Filter by publication year (from)")
    year_to: Optional[int] = Field(default=None, description="Filter by publication year (to)")


@tool
def web_search(
    query: str,
    max_results: int = 20,
    domains: Optional[List[str]] = None,
    region: Optional[str] = None,
) -> List[dict]:
    """
    Execute web search using Serper.dev API (Google Search) - SOTA Integration.

    P0.3 FIX: Now uses synchronous requests instead of broken _run_async.

    Args:
        query: Search query
        max_results: Maximum results to return (up to 100)
        domains: Optional list of domains to restrict search
        region: Geographic region for targeting (NORTH_AMERICA, EUROPE, ASIA_PACIFIC, GLOBAL)

    Returns:
        List of search results with url, title, snippet, score
    """
    # FIX-121: Always ensure dotenv is loaded with explicit path
    # LOOPBACK-FIX: override=False so programmatic env overrides win.
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path, override=False)

    # FIX-121: Clear config cache after reloading dotenv to ensure fresh API keys
    from src.config.core import clear_config_cache
    clear_config_cache()

    # FIX-121: Critical logging that always displays
    logger.debug(f"[FIX-121] web_search CALLED with query: {query[:50]}")

    # Geographic targeting
    location = None
    gl = "us"  # Default to US
    if region:
        region_map = {
            "NORTH_AMERICA": ("North America", "us"),
            "EUROPE": ("Europe", "uk"),
            "ASIA_PACIFIC": ("Asia Pacific", "au"),
            "GLOBAL": (None, "us"),
        }
        location, gl = region_map.get(region, (None, "us"))

    # P0.3 FIX: Use sync Serper API directly
    results = _serper_search_sync(
        query=query,
        search_type="search",
        max_results=max_results,
        gl=gl,
        location=location,
        domains=domains,
    )

    if results:
        return results
    else:
        # Fallback to DuckDuckGo if Serper fails
        logger.warning("Serper returned no results, falling back to DuckDuckGo")
        return _duckduckgo_search(query, max_results)


@tool
def serper_scholar_search(
    query: str,
    max_results: int = 20,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[dict]:
    """
    Execute Google Scholar search using Serper.dev API - SOTA Integration.

    P0.3 FIX: Now uses synchronous requests instead of broken _run_async.

    Args:
        query: Search query
        max_results: Maximum results to return
        year_from: Filter papers from this year
        year_to: Filter papers until this year

    Returns:
        List of academic paper results with url, title, snippet, authors, citations
    """
    # Build query with year filters if provided
    search_query = query
    if year_from or year_to:
        # Serper scholar doesn't have direct year params, add to query
        if year_from and year_to:
            search_query = f"{query} {year_from}..{year_to}"
        elif year_from:
            search_query = f"{query} after:{year_from}"
        elif year_to:
            search_query = f"{query} before:{year_to}"

    # P0.3 FIX: Use sync Serper API directly
    results = _serper_search_sync(
        query=search_query,
        search_type="scholar",
        max_results=max_results,
    )

    if results:
        return results
    else:
        return _fallback_scholar_search(query, max_results)


@tool
def serper_news_search(
    query: str,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> List[dict]:
    """
    Execute Google News search using Serper.dev API.

    P0.3 FIX: Now uses synchronous requests instead of broken _run_async.

    Args:
        query: Search query
        max_results: Maximum results to return
        time_range: Time filter (h=hour, d=day, w=week, m=month)

    Returns:
        List of news results with url, title, snippet, date
    """
    # P0.3 FIX: Use sync Serper API directly
    kwargs = {}
    if time_range:
        kwargs["tbs"] = f"qdr:{time_range}"

    return _serper_search_sync(
        query=query,
        search_type="news",
        max_results=max_results,
        **kwargs
    )


@tool
def serper_patents_search(query: str, max_results: int = 10) -> List[dict]:
    """
    Execute Google Patents search using Serper.dev API.

    P0.3 FIX: Now uses synchronous requests instead of broken _run_async.

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of patent results with url, title, snippet, inventor
    """
    # P0.3 FIX: Use sync Serper API directly
    return _serper_search_sync(
        query=query,
        search_type="patents",
        max_results=max_results,
    )


@tool
def serper_comprehensive_search(
    query: str,
    max_results_per_type: int = 10,
    search_types: Optional[List[str]] = None,
    region: Optional[str] = None,
) -> List[dict]:
    """
    Execute comprehensive multi-source search using Serper.dev API.
    Searches web, scholar, news, and patents sequentially for maximum coverage.

    P0.3 FIX: Now uses synchronous requests instead of broken _run_async.

    Args:
        query: Search query
        max_results_per_type: Maximum results per search type
        search_types: Types to search (search, scholar, news, patents)
        region: Geographic region targeting

    Returns:
        List of combined results from all search types
    """
    if search_types is None:
        search_types = ["search", "scholar", "news"]

    # Geographic targeting
    location = None
    gl = "us"
    if region:
        region_map = {
            "NORTH_AMERICA": ("North America", "us"),
            "EUROPE": ("Europe", "uk"),
            "ASIA_PACIFIC": ("Asia Pacific", "au"),
            "GLOBAL": (None, "us"),
        }
        location, gl = region_map.get(region, (None, "us"))

    # P0.3 FIX: Use sync Serper API for each search type
    all_results = []
    seen_urls = set()

    for search_type in search_types:
        try:
            results = _serper_search_sync(
                query=query,
                search_type=search_type,
                max_results=max_results_per_type,
                gl=gl,
                location=location,
            )

            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    r["search_type"] = search_type
                    all_results.append(r)

        except Exception as e:
            logger.error(f"Comprehensive search failed for {search_type}: {e}")
            continue

    logger.info(f"Comprehensive search returned {len(all_results)} unique results")
    return all_results


def _fallback_web_search(query: str, max_results: int = 10, domains: Optional[List[str]] = None) -> List[dict]:
    """Fallback web search using direct Serper API call."""
    import os
    import requests

    serper_api_key = os.getenv("SERPER_API_KEY")

    if not serper_api_key:
        logger.warning("Serper API key not configured, using DuckDuckGo fallback")
        return _duckduckgo_search(query, max_results)

    try:
        search_query = query
        if domains:
            domain_filter = " OR ".join([f"site:{d}" for d in domains])
            search_query = f"({query}) ({domain_filter})"

        headers = {
            "X-API-KEY": serper_api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "q": search_query,
            "num": min(max_results, 100),
        }

        response = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic", []):
            results.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "score": 0.7,
                "source_type": "web",
            })

        logger.info(f"Fallback Serper web search for '{query}' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Fallback web search failed: {e}")
        return _duckduckgo_search(query, max_results)


def _fallback_scholar_search(query: str, max_results: int = 10) -> List[dict]:
    """Fallback scholar search using direct Serper API call."""
    import os
    import requests

    serper_api_key = os.getenv("SERPER_API_KEY")

    if not serper_api_key:
        logger.warning("Serper API key not configured for Scholar search")
        return []

    try:
        headers = {
            "X-API-KEY": serper_api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "q": query,
            "num": min(max_results, 100),
        }

        response = requests.post(
            "https://google.serper.dev/scholar",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic", []):
            results.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "authors": [a.strip() for a in item.get("authors", "").split(",") if a.strip()] if isinstance(item.get("authors", ""), str) else item.get("authors", []),  # FIX-227A: Convert string to list
                "publication": item.get("publication", ""),
                "cited_by": item.get("citedBy", 0),
                "year": item.get("year", ""),
                "score": 0.8,
                "source_type": "academic",
            })

        logger.info(f"Fallback Serper Scholar search for '{query}' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Fallback Scholar search failed: {e}")
        return []


def _optimize_ddg_query(query: str) -> str:
    """
    FIX-125/FIX-221A: Optimize query for DuckDuckGo with topic anchoring.

    DDG optimizations:
    - Shorter queries work better (max 6-8 key terms)
    - Remove filler words that don't help ranking
    - FIX-221A: ALWAYS preserve topic anchor words (application + region)

    Args:
        query: Original search query

    Returns:
        Optimized query for DuckDuckGo
    """
    query_words = query.replace('"', '').split()

    if len(query_words) <= 8:
        return query

    stop_words = {
        'the', 'a', 'an', 'in', 'on', 'at', 'for', 'to', 'of', 'and', 'or',
        'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
        'how', 'when', 'where', 'why', 'all', 'each', 'every', 'both', 'few',
        'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'just', 'but', 'if',
        'exist', 'rates', 'patterns', 'applications',
    }

    # FIX-221A: Extract topic anchor words (capitalized nouns + region)
    topic_anchor_enabled = os.environ.get("POLARIS_QUERY_TOPIC_ANCHOR", "1") == "1"
    if topic_anchor_enabled:
        topic_anchor = []
        region_words = []
        for w in query_words:
            if w.isupper() and len(w) > 2:
                region_words.append(w.title())
            elif w[0:1].isupper() and w.lower() not in stop_words:
                topic_anchor.append(w)
        anchor = topic_anchor[:4] + region_words[:2]
        anchor_lower = {w.lower() for w in anchor}
        significant = [w for w in query_words if w.lower() not in stop_words and w.lower() not in anchor_lower]
        optimized = ' '.join(anchor + significant[:3])
    else:
        significant = [w for w in query_words if w.lower() not in stop_words]
        optimized = ' '.join(significant[:6])

    logger.debug(f"[FIX-221A] DDG query optimized: '{query[:40]}...' -> '{optimized}'")
    return optimized


def _duckduckgo_search(query: str, max_results: int = 10, region: str = "us-en") -> List[dict]:
    """
    FIX-125: Enhanced fallback search using DuckDuckGo with optimization.

    Improvements:
    - Query simplification for better DDG ranking
    - Region parameter for geographic targeting
    - Safe search disabled for research mode

    Args:
        query: Search query
        max_results: Maximum results to return
        region: DDG region code (e.g., 'us-en', 'uk-en', 'de-de')

    Returns:
        List of search results
    """
    try:
        from duckduckgo_search import DDGS

        # FIX-125: Optimize query for DDG
        optimized_query = _optimize_ddg_query(query)

        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(
                optimized_query,
                max_results=max_results,
                region=region,
                safesearch="off",  # Research mode - no filtering
            ):
                results.append({
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "score": 0.5,  # DuckDuckGo doesn't provide scores
                    "source_type": "web",
                })

            logger.info(f"[FIX-125] DuckDuckGo search: '{optimized_query[:50]}' -> {len(results)} results")
            return results

    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []


@tool
def academic_search(
    query: str,
    max_results: int = 10,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None
) -> List[dict]:
    """
    Execute academic search using Semantic Scholar API.

    P1.6 FIX: Added exponential backoff for rate limiting (429 errors).
    FIX 105C: Added semaphore-based concurrency control (Polite Throttling).

    See deployment_plan_20260126.md

    Args:
        query: Search query
        max_results: Maximum results to return
        year_from: Filter by publication year (from)
        year_to: Filter by publication year (to)

    Returns:
        List of academic papers with url, title, abstract
    """
    # P1.6 FIX: Rate limiting config
    max_retries = 3
    base_delay = 1.0
    max_delay = 10.0

    # FIX-122: Use bulk search endpoint (10M results vs 1K for relevance search)
    # Per Semantic Scholar docs: "paper bulk search should be used in most cases
    # because paper relevance search is more resource intensive"
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

    # FIX: Add Semantic Scholar API key for higher rate limits (1 RPS vs shared pool)
    # Without API key: unauthenticated users share a global rate limit pool
    # With API key: dedicated 1 request/second rate limit
    s2_api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
    headers = {}
    if s2_api_key:
        headers["x-api-key"] = s2_api_key
        logger.debug("[FIX-122] Using Semantic Scholar API key for authenticated access")
    else:
        logger.warning(
            "[FIX-122] No SEMANTIC_SCHOLAR_API_KEY found - using unauthenticated access "
            "(shared global rate limit, expect 429 errors)"
        )

    # FIX-122: Optimized parameters for bulk search
    # - limit: 1000 max per request (vs 100 for relevance search)
    # - fields: Request all useful metadata
    # - fieldsOfStudy: Filter to relevant domains when applicable
    # FIX-122B/FIX-221A: Simplify query for Semantic Scholar with topic anchoring
    # Long compound queries return 0 results - extract key terms
    # FIX-221A: ALWAYS preserve topic anchor words to prevent drift
    # Example: "Legionella household water filter North America contamination rates"
    # Becomes: "Household Water Filter North America Legionella" (topic anchored)
    topic_anchor_enabled = os.environ.get("POLARIS_QUERY_TOPIC_ANCHOR", "1") == "1"
    query_words = query.replace('"', '').split()
    if len(query_words) > 6:
        stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'for', 'to', 'of', 'and', 'or', 'with', 'by',
                       'what', 'how', 'which', 'where', 'when', 'why', 'do', 'does', 'did',
                       'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                       'exist', 'rates', 'patterns', 'applications'}
        significant_words = [w for w in query_words if w.lower() not in stop_words]

        if topic_anchor_enabled:
            # FIX-221A: Extract topic anchor (capitalized multi-word noun phrases)
            # These are typically the application name + region that MUST be preserved
            topic_anchor_words = []
            region_words = []
            for w in query_words:
                # Region detection: ALL CAPS words like "NORTH", "AMERICA", "EUROPE"
                if w.isupper() and len(w) > 2:
                    region_words.append(w.title())
                # Title case words are typically topic nouns: "Household", "Water", "Filter"
                elif w[0:1].isupper() and w.lower() not in stop_words:
                    topic_anchor_words.append(w)

            # Build: topic_anchor + region + additional significant words (up to 3)
            anchor = topic_anchor_words[:4] + region_words[:2]
            anchor_lower = {w.lower() for w in anchor}
            remaining = [w for w in significant_words if w.lower() not in anchor_lower][:3]
            simplified_query = ' '.join(anchor + remaining)
        else:
            simplified_query = ' '.join(significant_words[:5])

        logger.debug(f"[FIX-221A] Simplified query for S2: '{query[:60]}...' -> '{simplified_query}'")
    else:
        simplified_query = query

    params = {
        "query": simplified_query,
        "limit": min(max_results, 1000),  # FIX-122: Bulk search allows up to 1000
        "fields": "paperId,title,abstract,url,year,authors,citationCount,influentialCitationCount,venue,openAccessPdf,publicationTypes",
    }

    # FIX-122B: Removed fieldsOfStudy filter - too restrictive, causes 0 results
    # The query itself provides domain filtering

    if year_from or year_to:
        year_filter = ""
        if year_from:
            year_filter += f"{year_from}-"
        else:
            year_filter += "1900-"
        if year_to:
            year_filter += str(year_to)
        else:
            year_filter += str(datetime.now().year)
        params["year"] = year_filter

    # FIX 105C: Acquire semaphore for rate limiting (max 3 concurrent requests)
    with _SEMANTIC_SCHOLAR_SEMAPHORE:
        # FIX 105C: Enforce minimum interval between requests
        _wait_for_rate_limit("semantic_scholar")

        logger.debug(f"[FIX 105C] Acquired Semantic Scholar semaphore for query: {query[:50]}...")

        # P1.6 FIX: Retry loop with exponential backoff
        last_error = None
        for attempt in range(max_retries):
            try:
                # P2.5 FIX: Use context manager for proper socket cleanup
                with requests.Session() as session:
                    # FIX: Include API key header if available
                    response = session.get(base_url, params=params, headers=headers, timeout=30)

                    # P1.6 FIX: Check for rate limiting
                    if response.status_code == 429:
                        wait_time = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                        logger.warning(
                            f"[FIX-122] Semantic Scholar 429 rate limit, waiting {wait_time:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue

                    response.raise_for_status()

                    data = response.json()
                    all_results = []

                    # FIX-122: Log total available results from bulk search
                    total_results = data.get("total", 0)
                    token = data.get("token")
                    page_count = 1
                    logger.debug(f"[FIX-122] Semantic Scholar bulk: {total_results} total, {len(data.get('data', []))} returned (page 1)")

                    # FIX-123: Pagination loop - fetch additional pages if available
                    # S2 bulk API returns up to 1000 results per page with continuation token
                    while True:
                        for paper in data.get("data", []):
                            # Build proper URL - prefer open access PDF if available
                            paper_id = paper.get("paperId", "")
                            open_access = paper.get("openAccessPdf", {})
                            if open_access and open_access.get("url"):
                                url = open_access.get("url")  # Direct PDF link
                            else:
                                url = paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}"

                            # FIX-122: Enhanced result with all useful metadata
                            all_results.append({
                                "url": url,
                                "title": paper.get("title", ""),
                                "snippet": paper.get("abstract", "")[:500] if paper.get("abstract") else "",
                                "year": paper.get("year"),
                                "authors": [a.get("name", "") for a in paper.get("authors", [])[:5]],
                                "citation_count": paper.get("citationCount", 0),
                                "venue": paper.get("venue", ""),
                                "publication_types": paper.get("publicationTypes", []),
                                "has_open_access": bool(open_access and open_access.get("url")),
                                "score": min(paper.get("citationCount", 0) / 100, 1.0),  # Normalize
                                "source_type": "academic",
                            })

                        # FIX-123: Check if we should fetch more pages
                        # Stop conditions: no token, reached max_results, or max 3 pages (3000 results)
                        if not token or len(all_results) >= max_results or page_count >= 3:
                            break

                        # FIX-123: Fetch next page with rate limit compliance
                        page_count += 1
                        logger.debug(f"[FIX-123] Fetching S2 page {page_count} with token...")
                        time.sleep(1.2)  # Rate limit: 1 RPS with API key

                        params["token"] = token
                        page_response = session.get(base_url, params=params, headers=headers, timeout=30)
                        if page_response.status_code == 429:
                            logger.warning(f"[FIX-123] Rate limited on page {page_count}, stopping pagination")
                            break
                        page_response.raise_for_status()
                        data = page_response.json()
                        token = data.get("token")
                        logger.debug(f"[FIX-123] S2 page {page_count}: {len(data.get('data', []))} results")

                    # Domain blocklist filter removed 2026-04-13 — authority gate
                    # in src/polaris_graph/agents/analyzer.py scores these downstream.
                    results = all_results

                    logger.info(f"[FIX-122/123] Semantic Scholar bulk: '{query[:60]}...' -> {len(results)} results (of {total_results} total, {page_count} pages)")
                    return results

            except requests.exceptions.HTTPError as e:
                # P1.6 FIX: Handle rate limiting with backoff
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                    wait_time = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    logger.warning(
                        f"[FIX 105C] Semantic Scholar HTTP 429, waiting {wait_time:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    last_error = e
                else:
                    logger.error(f"Academic search HTTP error: {e}")
                    return []
            except Exception as e:
                logger.error(f"Academic search failed: {e}")
                last_error = e
                # Don't retry on non-rate-limit errors
                break

        # All retries exhausted
        logger.error(f"Academic search failed after {max_retries} retries: {last_error}")
        return []


@tool
def pubmed_search(query: str, max_results: int = 10) -> List[dict]:
    """
    Execute PubMed search for medical/health research.

    FIX 105C: Added semaphore-based concurrency control (Polite Throttling).
    PubMed has strict rate limits, so we use max 1 concurrent request.

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of PubMed articles with url, title, abstract
    """
    # FIX 105C: Acquire semaphore for rate limiting (max 1 concurrent request to PubMed)
    with _PUBMED_SEMAPHORE:
        # FIX 105C: Enforce minimum interval between requests (1 second for PubMed)
        _wait_for_rate_limit("pubmed")

        logger.debug(f"[FIX 105C] Acquired PubMed semaphore for query: {query[:50]}...")

        try:
            import requests

            # Search for IDs
            search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
            }

            search_response = requests.get(search_url, params=search_params, timeout=30)

            # FIX 105C: Check for rate limiting
            if search_response.status_code == 429:
                logger.warning("[FIX 105C] PubMed 429 rate limit hit, backing off...")
                time.sleep(2.0)  # PubMed requires longer backoff
                search_response = requests.get(search_url, params=search_params, timeout=30)

            search_response.raise_for_status()
            search_data = search_response.json()

            id_list = search_data.get("esearchresult", {}).get("idlist", [])

            if not id_list:
                return []

            # FIX 105C: Wait before fetch request
            _wait_for_rate_limit("pubmed")

            # Fetch details
            fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
            }

            fetch_response = requests.get(fetch_url, params=fetch_params, timeout=30)

            # FIX 105C: Check for rate limiting on fetch
            if fetch_response.status_code == 429:
                logger.warning("[FIX 105C] PubMed fetch 429 rate limit hit, backing off...")
                time.sleep(2.0)
                fetch_response = requests.get(fetch_url, params=fetch_params, timeout=30)

            fetch_response.raise_for_status()

            # Parse XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(fetch_response.content)

            results = []
            for article in root.findall(".//PubmedArticle"):
                pmid = article.findtext(".//PMID", "")
                title = article.findtext(".//ArticleTitle", "")
                abstract_elem = article.find(".//Abstract/AbstractText")
                abstract = abstract_elem.text if abstract_elem is not None else ""

                results.append({
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "title": title,
                    "snippet": abstract[:500] if abstract else "",
                    "pmid": pmid,
                    "source_type": "academic",
                    "score": 0.7,  # PubMed articles generally high quality
                })

            logger.info(f"PubMed search for '{query}' returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return []


@tool
def government_search(query: str, agency: str = "all", max_results: int = 10) -> List[dict]:
    """
    Search government sources (FDA, EPA, CDC).

    Args:
        query: Search query
        agency: Specific agency or 'all'
        max_results: Maximum results to return

    Returns:
        List of government documents
    """
    # Use web search with domain filtering for government sites
    domains = []
    if agency == "all":
        domains = ["fda.gov", "epa.gov", "cdc.gov", "who.int", "nih.gov"]
    elif agency == "fda":
        domains = ["fda.gov"]
    elif agency == "epa":
        domains = ["epa.gov"]
    elif agency == "cdc":
        domains = ["cdc.gov"]
    elif agency == "who":
        domains = ["who.int"]

    return web_search.invoke({
        "query": query,
        "max_results": max_results,
        "domains": domains
    })


# =============================================================================
# Search Agent Output Schema
# =============================================================================

class SearchPlan(BaseModel):
    """Plan for executing searches."""
    sub_query_id: str = Field(description="ID of the sub-query being searched")
    search_strategy: Literal["web_first", "academic_first", "parallel", "domain_specific", "graph_augmented"] = Field(
        description="Strategy for this search"
    )
    keywords: List[str] = Field(description="Keywords to use in search")
    target_sources: List[Literal["web", "academic", "pubmed", "government", "graph"]] = Field(
        description="Types of sources to search"
    )
    domain_hints: List[str] = Field(default_factory=list, description="Specific domains to prioritize")
    use_graph_rag: bool = Field(default=True, description="Whether to use knowledge graph for retrieval")


class SearchExecution(BaseModel):
    """Record of search execution."""
    search_plans: List[SearchPlan] = Field(description="Plans for each sub-query")
    total_queries: int = Field(description="Total number of search queries to execute")
    reasoning: str = Field(description="Explanation of search approach")


# =============================================================================
# Search Agent
# =============================================================================

@register_agent("search")
class SearchAgent(BaseAgent):
    """
    Search Agent - Executes multi-source searches.

    Responsibilities:
    1. Interpret sub-queries from Planner
    2. Select appropriate search backends
    3. Execute searches in parallel
    4. Deduplicate and rank results
    5. Return structured SearchResult objects

    Uses multiple search APIs for comprehensive coverage.
    Depth configuration loaded from .env via DepthConfig (LAW VI: Zero hard-coding).
    """

    def __init__(self):
        # Load depth configuration from .env (LAW VI)
        self.depth_config = get_depth_config()

        # SOTA FIX: Initialize query amplifier for 10x search coverage
        self.query_amplifier = QueryAmplifier()

        config = AgentConfig(
            name="search",
            description="Executes web and academic searches for research queries",
            task_tier="simple",  # Fast search coordination task
            temperature=0.0,
            max_tokens=4096,
        )

        # Define tools available to this agent
        # Deep Serper integration with all endpoints
        tools = [
            # Primary Serper tools (SOTA)
            web_search,                    # Google Search via Serper
            serper_scholar_search,         # Google Scholar via Serper
            serper_news_search,            # Google News via Serper
            serper_patents_search,         # Google Patents via Serper
            serper_comprehensive_search,   # Multi-source parallel search
            # Additional academic sources
            academic_search,               # Semantic Scholar
            pubmed_search,                 # PubMed/NCBI
            # Government sources
            government_search,             # EPA, FDA, CDC via Serper site:
            # Knowledge graph
            graph_search,                  # Neo4j knowledge graph
        ]

        super().__init__(config, tools)

        logger.info(
            f"SearchAgent initialized with QueryAmplifier "
            f"(amplification={self.depth_config.query_amplification.enabled}, "
            f"variants_per_query={self.depth_config.query_amplification.variants_per_query})"
        )

    def get_system_prompt(self) -> str:
        return """You are a Research Search Specialist. Your job is to execute comprehensive searches across multiple sources to gather evidence for research questions.

SEARCH STRATEGY:
1. Analyze each sub-query's expected data type:
   - factual → government sources, encyclopedias, knowledge graph
   - statistical → academic papers, government reports
   - comparative → multiple sources for different perspectives
   - procedural → technical documentation, standards
   - entity-centric → knowledge graph first, then web

2. Select appropriate search backends:
   - Web search: General information, news, industry sources
   - Academic search: Peer-reviewed research, citations
   - PubMed: Health and medical research
   - Government: Regulatory documents, official reports
   - Graph search: Known entities, relationships, prior research context

3. Knowledge Graph (Graph RAG):
   - Use graph search for queries about known entities (chemicals, regulations, organizations)
   - Graph provides high-confidence structured information
   - Use graph_augmented strategy when entities are mentioned
   - Graph results include relationships between concepts

4. Use domain hints when provided:
   - Prioritize authoritative domains (gov, edu, org)
   - Include industry-specific sources

5. Optimize search queries:
   - Use specific keywords
   - Add domain-specific terminology
   - Include relevant synonyms

DEDUPLICATION:
- Track URLs to avoid duplicates
- Prioritize higher-quality sources
- Merge results from different backends

QUALITY INDICATORS:
- Knowledge graph: High confidence, structured data
- Government sources: High reliability
- Academic papers: Cite count matters
- News sources: Check recency
- Industry sources: Consider bias

Return structured search plans for each sub-query."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Execute searches for all pending sub-queries.

        Args:
            state: Current research state with sub_queries

        Returns:
            Updated state with search_results populated
        """
        sub_queries = state.get("sub_queries", [])

        if not sub_queries:
            logger.warning("No sub-queries to search")
            return state

        # Filter pending sub-queries
        pending = [sq for sq in sub_queries if sq.status == "pending"]

        if not pending:
            logger.info("No pending sub-queries")
            return state

        logger.info(f"Executing searches for {len(pending)} sub-queries")

        # Plan searches
        search_plans = self._plan_searches(pending, state)

        # Execute searches
        all_results = []
        urls_attempted = 0
        urls_success = 0
        urls_failed = 0

        for plan in search_plans:
            # Find the sub-query
            sub_query = next((sq for sq in sub_queries if sq.query_id == plan.sub_query_id), None)
            if not sub_query:
                continue

            # Mark as searching
            sub_query.status = "searching"

            # Execute searches based on plan
            query_results = self._execute_search_plan(plan, sub_query)

            # Update counters
            urls_attempted += len(query_results) + 5  # Estimate for failed
            urls_success += len(query_results)

            # Convert to SearchResult objects
            for i, result in enumerate(query_results):
                result_id = f"{sub_query.query_id}_r{i+1:03d}"

                # Generate content hash
                content_hash = hashlib.md5(
                    (result.get("url", "") + result.get("title", "")).encode()
                ).hexdigest()[:16]

                # FIX-124B: Don't skip duplicates here - let perspective-aware dedup merge them
                # This allows same URL from different perspectives to have their perspectives merged

                # FIX-124: Get perspective from sub_query for STORM tracking
                perspective_name = getattr(sub_query, 'perspective_name', None)

                search_result = SearchResult(
                    result_id=result_id,
                    url=result.get("url", ""),
                    title=result.get("title", ""),
                    snippet=result.get("snippet", ""),
                    source_type=result.get("source_type", "web"),
                    domain=self._extract_domain(result.get("url", "")),
                    fetch_status="success",
                    content=None,  # Will be fetched by Analyst
                    metadata={
                        "score": result.get("score", 0.0),
                        "sub_query_id": sub_query.query_id,
                        "search_keywords": plan.keywords,
                        "content_hash": content_hash,
                        "authors": result.get("authors", []),  # FIX-227: Pipe author metadata
                    },
                    perspective_origin=perspective_name,  # FIX-124: STORM perspective tracking
                    perspective_origins=[perspective_name] if perspective_name else [],  # FIX-124B: Multi-perspective list
                )
                all_results.append(search_result)

            # Mark sub-query complete
            sub_query.status = "complete"

        # FIX-124B: Apply perspective-aware deduplication to merge perspective_origins
        pre_dedup_count = len(all_results)
        all_results = deduplicate_results_with_perspective_merge(all_results)
        logger.info(
            f"[FIX-124B] Perspective-aware dedup: {pre_dedup_count} -> {len(all_results)} results"
        )

        # FIX-124: Calculate perspective coverage statistics
        perspective_stats = get_perspective_coverage_stats(all_results)
        if perspective_stats["perspective_distribution"]:
            dist_str = ", ".join(
                f"{k}={v}" for k, v in sorted(perspective_stats["perspective_distribution"].items())
            )
            logger.info(f"[FIX-124] Perspective coverage: {dist_str}")

        # FIX-124I-B: Post-dedup perspective health warnings
        # This is the REAL coverage after deduplication
        perspective_count = perspective_stats.get("perspectives_covered", 0)
        if perspective_stats["perspective_distribution"]:
            values = list(perspective_stats["perspective_distribution"].values())
            perspective_balance = min(values) / max(values) if max(values) > 0 else 0
        else:
            perspective_balance = 0

        # FIX-124I-C: Health check thresholds
        MIN_PERSPECTIVES_REQUIRED = 5
        MIN_PERSPECTIVE_BALANCE = 0.15

        if perspective_count < 7:
            logger.warning(
                f"[FIX-124I] LOW PERSPECTIVE COUNT: {perspective_count}/9 (expected ≥7)"
            )
        if perspective_balance < 0.20:
            logger.warning(
                f"[FIX-124I] LOW PERSPECTIVE BALANCE: {perspective_balance:.2f} (expected ≥0.20)"
            )

        # FIX-124I-C: Critical health check - fail loudly if catastrophic
        is_perspective_healthy = (
            perspective_count >= MIN_PERSPECTIVES_REQUIRED and
            perspective_balance >= MIN_PERSPECTIVE_BALANCE
        )
        if not is_perspective_healthy:
            logger.error(
                f"[FIX-124I] PERSPECTIVE HEALTH CRITICAL: "
                f"{perspective_count} perspectives, balance={perspective_balance:.2f} "
                f"(requires ≥{MIN_PERSPECTIVES_REQUIRED} perspectives, ≥{MIN_PERSPECTIVE_BALANCE} balance)"
            )

        # Add health status to stats
        perspective_stats["balance"] = round(perspective_balance, 3)
        perspective_stats["is_healthy"] = is_perspective_healthy

        # SOTA FIX W1.2: Calculate final diversity statistics
        final_diversity_stats = get_domain_statistics(
            [{"url": sr.url} for sr in all_results]
        )

        # Update state
        state["search_results"] = all_results
        state["urls_attempted"] = urls_attempted
        state["urls_success"] = urls_success
        state["urls_failed"] = urls_attempted - urls_success

        # SOTA FIX W1.2: Add diversity metrics to state
        state["search_unique_domains"] = final_diversity_stats["unique_domains"]
        state["search_max_domain_pct"] = final_diversity_stats["max_single_domain_pct"]
        state["search_diversity_score"] = final_diversity_stats["diversity_score"]

        # FIX-124: Add perspective coverage to state
        state["search_perspective_stats"] = perspective_stats

        logger.info(
            f"Search complete: {len(all_results)} results from {urls_attempted} URLs "
            f"({urls_success} success, {state['urls_failed']} failed, "
            f"diversity: {final_diversity_stats['unique_domains']} domains, "
            f"max_domain_pct={final_diversity_stats['max_single_domain_pct']:.1%}, "
            f"perspectives={perspective_stats['perspectives_covered']})"
        )

        return state

    def _plan_searches(self, sub_queries: List[SubQuery], state: ResearchState) -> List[SearchPlan]:
        """Plan searches for sub-queries using LLM."""
        # Build context for planning
        query_list = "\n".join([
            f"- {sq.query_id}: {sq.query_text} (type: {sq.expected_data_type}, "
            f"keywords: {sq.search_keywords}, domains: {sq.domain_hints})"
            for sq in sub_queries
        ])

        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=f"""Plan searches for these sub-queries:

{query_list}

Original question: {state.get('original_query', '')}
Region: {state.get('region', 'GLOBAL')}

For each sub-query, specify:
1. Search strategy (web_first, academic_first, parallel, domain_specific)
2. Keywords to use
3. Target sources (web, academic, pubmed, government)
4. Domain hints if applicable""")
        ]

        result: SearchExecution = self.call_llm_structured(messages, SearchExecution)

        return result.search_plans

    def _execute_search_plan(self, plan: SearchPlan, sub_query: SubQuery) -> List[dict]:
        """Execute a search plan and return results.

        Uses DepthConfig for search limits (LAW VI: Zero hard-coding).
        SOTA FIX: Uses QueryAmplifier for 10x search coverage.
        SOTA W2.2: Uses parallel execution for 3x speedup.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        all_results = []
        seen_urls = set()
        seen_urls_lock = threading.Lock()

        # Get depth configuration
        search_config = self.depth_config.search_execution
        max_results_per_source = search_config.top_k_per_query
        max_concurrency = search_config.max_concurrency  # SOTA W2.2: 20 concurrent

        # Build search query from keywords
        base_query = " ".join(plan.keywords[:5])

        # SOTA FIX: Amplify query into variants for comprehensive coverage
        region = sub_query.metadata.get("region", "GLOBAL") if hasattr(sub_query, 'metadata') and sub_query.metadata else "GLOBAL"
        amplification_result = self.query_amplifier.amplify(
            query=base_query,
            region=region,
        )

        # Use amplified variants (limit to avoid API rate limits)
        search_queries = amplification_result.variants[:10]
        logger.info(
            f"Query amplification: '{base_query[:40]}...' -> {len(search_queries)} variants"
        )

        # FIX-124I-A: Retry configuration for search resilience
        MAX_SEARCH_RETRIES = 2
        SEARCH_RETRY_DELAY = 1.5  # Base delay in seconds (exponential backoff)

        def execute_single_search(args):
            """Execute a single search with retry logic (for parallel execution).

            FIX-124I-A: Added retry logic with exponential backoff to prevent
            silent perspective failures due to rate limits (429) or transient errors.
            """
            search_query, source, max_results, domain_hints = args

            for attempt in range(MAX_SEARCH_RETRIES + 1):
                try:
                    if source == "web":
                        # FIX-221E: Pass region for geographic targeting in Serper
                        result = web_search.invoke({
                            "query": search_query,
                            "max_results": max_results,
                            "domains": domain_hints if domain_hints else None,
                            "region": region,
                        })
                    elif source == "academic":
                        result = academic_search.invoke({
                            "query": search_query,
                            "max_results": max_results
                        })
                    elif source == "pubmed":
                        result = pubmed_search.invoke({
                            "query": search_query,
                            "max_results": max_results
                        })
                    elif source == "government":
                        result = government_search.invoke({
                            "query": search_query,
                            "agency": "all",
                            "max_results": max_results
                        })
                    elif source == "graph":
                        result = graph_search.invoke({
                            "query": search_query,
                            "strategy": "hybrid",
                            "max_results": max_results
                        })
                    else:
                        return []

                    # FIX-124I-A: Log if we got 0 results (potential issue)
                    if not result:
                        logger.warning(f"[FIX-124I] {source} returned 0 results for: {search_query[:50]}...")

                    return result

                except Exception as e:
                    error_str = str(e).lower()
                    is_rate_limit = "429" in error_str or "rate" in error_str or "too many" in error_str

                    if attempt < MAX_SEARCH_RETRIES:
                        delay = SEARCH_RETRY_DELAY * (2 ** attempt)
                        if is_rate_limit:
                            logger.warning(
                                f"[FIX-124I] Rate limit on {source}, retry {attempt+1}/{MAX_SEARCH_RETRIES} in {delay:.1f}s"
                            )
                        else:
                            logger.warning(
                                f"[FIX-124I] {source} failed, retry {attempt+1}/{MAX_SEARCH_RETRIES} in {delay:.1f}s: {e}"
                            )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[FIX-124I] {source} FAILED after {MAX_SEARCH_RETRIES} retries: {e}"
                        )
                        return []

            return []  # Should not reach here, but safety fallback

        # SOTA W2.2: Build list of search tasks for parallel execution
        # FIX 95: Separate academic from web searches for different concurrency
        academic_sources = {"academic", "pubmed"}
        web_tasks = []
        academic_tasks = []

        for search_query in search_queries:
            for source in plan.target_sources:
                task = (search_query, source, max_results_per_source, plan.domain_hints)
                if source in academic_sources:
                    academic_tasks.append(task)
                else:
                    web_tasks.append(task)

        # FIX 95: Academic APIs need much lower concurrency to avoid 429 blocks
        # PubMed: 3 requests/second, Semantic Scholar: 1 request/second (with API key)
        # NOTE: Semantic Scholar is 1 RPS with API key, shared pool without key
        academic_concurrency = 1  # FIX: Set to 1 (Semantic Scholar rate limit)
        web_concurrency = max_concurrency  # Full concurrency for web

        logger.info(
            f"[PARALLEL-SEARCH] Starting {len(web_tasks)} web + {len(academic_tasks)} academic searches "
            f"(web_concurrency={web_concurrency}, academic_concurrency={academic_concurrency})"
        )

        # FIX 95: Execute web searches first with full concurrency
        completed_count = 0
        total_tasks = len(web_tasks) + len(academic_tasks)

        if web_tasks:
            with ThreadPoolExecutor(max_workers=web_concurrency) as executor:
                future_to_task = {
                    executor.submit(execute_single_search, task): task
                    for task in web_tasks
                }

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        results = future.result(timeout=60)  # 60s timeout per search

                        # Thread-safe deduplication
                        with seen_urls_lock:
                            for r in results:
                                url = r.get("url", "")
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    all_results.append(r)

                        completed_count += 1
                        if completed_count % 10 == 0:
                            logger.debug(
                                f"[PARALLEL-SEARCH] Web progress: {completed_count}/{len(web_tasks)} "
                                f"tasks, {len(all_results)} results"
                            )

                    except Exception as e:
                        logger.error(f"Web search task failed: {task[1]} - {e}")

        # FIX 95: Execute academic searches with LOWER concurrency to avoid 429 rate limits
        if academic_tasks:
            import time as _time
            logger.info(f"[FIX 95] Starting {len(academic_tasks)} academic searches with concurrency={academic_concurrency}")

            with ThreadPoolExecutor(max_workers=academic_concurrency) as executor:
                future_to_task = {
                    executor.submit(execute_single_search, task): task
                    for task in academic_tasks
                }

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        results = future.result(timeout=90)  # Academic APIs can be slower

                        # Thread-safe deduplication
                        with seen_urls_lock:
                            for r in results:
                                url = r.get("url", "")
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    all_results.append(r)

                        completed_count += 1

                        # FIX 95: Add small delay between academic API completions
                        _time.sleep(0.5)

                    except Exception as e:
                        logger.error(f"Academic search task failed: {task[1]} - {e}")

        logger.info(
            f"[PARALLEL-SEARCH] Completed {completed_count}/{total_tasks} searches, "
            f"{len(all_results)} unique results"
        )

        # SOTA FIX W1.2: Enforce domain diversity to prevent single-domain dominance
        pre_diversity_count = len(all_results)
        all_results = enforce_domain_diversity(all_results)
        diversity_stats = get_domain_statistics(all_results)

        logger.info(
            f"Search plan executed: {len(all_results)} results from {len(plan.target_sources)} sources "
            f"x {len(search_queries)} query variants (max_per_source={max_results_per_source}, "
            f"diversity: {diversity_stats['unique_domains']} domains, "
            f"pre-filter={pre_diversity_count})"
        )
        return all_results

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""


# =============================================================================
# Standalone function
# =============================================================================

def execute_search(
    query: str,
    sources: List[str] = None,
    max_results_per_source: int = None,
    include_graph: bool = True
) -> List[dict]:
    """
    Standalone function to execute a search.

    Args:
        query: Search query
        sources: List of source types (web, academic, pubmed, government, graph)
        max_results_per_source: Maximum results per source (defaults to DepthConfig)
        include_graph: Whether to include graph search (default True)

    Returns:
        List of search results
    """
    # Use DepthConfig if not specified (LAW VI: Zero hard-coding)
    if max_results_per_source is None:
        depth_config = get_depth_config()
        max_results_per_source = depth_config.search_execution.top_k_per_query

    if sources is None:
        # Include Serper Scholar for academic coverage
        sources = ["graph", "web", "scholar", "academic", "pubmed"] if include_graph else ["web", "scholar", "academic", "pubmed"]

    all_results = []
    seen_urls = set()

    for source in sources:
        try:
            if source == "web":
                results = web_search.invoke({"query": query, "max_results": max_results_per_source})
            elif source == "scholar":
                # Google Scholar via Serper for broader academic coverage
                results = serper_scholar_search.invoke({"query": query, "max_results": max_results_per_source})
            elif source == "academic":
                results = academic_search.invoke({"query": query, "max_results": max_results_per_source})
            elif source == "pubmed":
                results = pubmed_search.invoke({"query": query, "max_results": max_results_per_source})
            elif source == "government":
                results = government_search.invoke({"query": query, "max_results": max_results_per_source})
            elif source == "graph":
                results = graph_search.invoke({
                    "query": query,
                    "strategy": "hybrid",
                    "max_results": max_results_per_source
                })
            else:
                continue

            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

        except Exception as e:
            logger.error(f"Search failed for {source}: {e}")

    return all_results
