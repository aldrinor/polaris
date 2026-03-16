#!/usr/bin/env python3
"""
POLARIS Search Engines
======================
Search engine implementations for federated search.

Supported Engines:
- Serper: Google Search API (general, news, industry)
- PubMed: NCBI biomedical literature (with free full text filter)
- Semantic Scholar: Academic papers
- OpenAlex: Open access academic content
- ArXiv: Technical/scientific preprints

Usage:
    from src.search.engines import get_search_engines
    engines = get_search_engines()
    results = await engines["serper"].search("query")
"""

import asyncio
import hashlib
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlencode

import httpx

# Academic search libraries
try:
    import arxiv
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False

try:
    from pymed import PubMed
    PYMED_AVAILABLE = True
except ImportError:
    PYMED_AVAILABLE = False

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config
from src.utils.rate_limiter import get_rate_limiter
from src.schemas.phase_models import SearchResult


# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# BASE ENGINE
# =============================================================================

class SearchEngine(ABC):
    """Base class for search engines."""

    name: str = "base"
    buckets: List[str] = []

    def __init__(self):
        self.config = get_config()
        self.rate_limiter = get_rate_limiter()

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        """
        Execute a search query.

        Args:
            query: Search query string
            max_results: Maximum results to return

        Returns:
            List of SearchResult objects
        """
        pass

    async def _wait_for_rate_limit(self, domain: str) -> None:
        """Wait for rate limit clearance."""
        await self.rate_limiter.acquire_async(domain, timeout=60.0)


# =============================================================================
# SERPER ENGINE (Google Search API)
# =============================================================================

class SerperEngine(SearchEngine):
    """Serper.dev Google Search API integration."""

    name: str = "serper"
    buckets: List[str] = ["general", "news", "industry"]

    def __init__(self):
        super().__init__()
        self.api_key = self.config.env.serper_api_key
        self.base_url = "https://google.serper.dev/search"

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        """Execute Google search via Serper API."""
        if not self.api_key:
            logger.warning("Serper API key not configured, skipping search")
            return []

        await self._wait_for_rate_limit("google.serper.dev")

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "q": query,
            "num": min(max_results, 100),
        }

        results = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Process organic results
                organic = data.get("organic", [])
                for rank, item in enumerate(organic[:max_results], start=1):
                    result = SearchResult(
                        url=item.get("link", ""),
                        title=item.get("title", ""),
                        snippet=item.get("snippet", ""),
                        source_engine=self.name,
                        rank=rank,
                    )
                    results.append(result)

        except httpx.HTTPError as e:
            logger.error(f"Serper search error: {e}")
        except Exception as e:
            logger.error(f"Serper unexpected error: {e}")

        return results


# =============================================================================
# PUBMED ENGINE (Enhanced with Free Full Text + Abstracts)
# =============================================================================

class PubMedEngine(SearchEngine):
    """
    NCBI PubMed literature search - SOTA Enhanced.

    Features:
    - Filters for free full text articles when possible
    - Retrieves abstracts for NLI verification
    - Uses pymed library for richer metadata when available
    """

    name: str = "pubmed"
    buckets: List[str] = ["academic", "medical", "health"]

    def __init__(self):
        super().__init__()
        self.api_key = self.config.env.ncbi_api_key
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        # Initialize pymed if available
        self.pymed_client = None
        if PYMED_AVAILABLE:
            self.pymed_client = PubMed(tool="POLARIS", email="polaris@research.ai")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        free_full_text: bool = True,
    ) -> List[SearchResult]:
        """
        Execute PubMed search via NCBI E-utilities.

        Args:
            query: Search query
            max_results: Maximum results to return
            free_full_text: If True, append filter for free full text articles
        """
        await self._wait_for_rate_limit("eutils.ncbi.nlm.nih.gov")

        results = []

        # Enhance query with free full text filter for better content access
        enhanced_query = query
        if free_full_text:
            enhanced_query = f"({query}) AND (free full text[sb])"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: Search for PMIDs
                search_params = {
                    "db": "pubmed",
                    "term": enhanced_query,
                    "retmax": max_results * 2,  # Request more to filter
                    "retmode": "json",
                    "sort": "relevance",
                }
                if self.api_key:
                    search_params["api_key"] = self.api_key

                search_url = f"{self.base_url}esearch.fcgi"
                search_response = await client.get(search_url, params=search_params)
                search_response.raise_for_status()
                search_data = search_response.json()

                pmids = search_data.get("esearchresult", {}).get("idlist", [])

                # If no free full text results, try without filter
                if not pmids and free_full_text:
                    search_params["term"] = query
                    search_response = await client.get(search_url, params=search_params)
                    search_data = search_response.json()
                    pmids = search_data.get("esearchresult", {}).get("idlist", [])

                if not pmids:
                    return results

                # Step 2: Fetch abstracts via efetch (richer than esummary)
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(pmids[:max_results]),
                    "retmode": "xml",
                    "rettype": "abstract",
                }
                if self.api_key:
                    fetch_params["api_key"] = self.api_key

                fetch_url = f"{self.base_url}efetch.fcgi"
                fetch_response = await client.get(fetch_url, params=fetch_params)
                fetch_response.raise_for_status()

                # Parse XML for abstracts
                abstract_map = self._parse_pubmed_xml(fetch_response.text)

                # Step 3: Fetch summaries for metadata
                summary_params = {
                    "db": "pubmed",
                    "id": ",".join(pmids[:max_results]),
                    "retmode": "json",
                }
                if self.api_key:
                    summary_params["api_key"] = self.api_key

                summary_url = f"{self.base_url}esummary.fcgi"
                summary_response = await client.get(summary_url, params=summary_params)
                summary_response.raise_for_status()
                summary_data = summary_response.json()

                summaries = summary_data.get("result", {})
                for rank, pmid in enumerate(pmids[:max_results], start=1):
                    if pmid in summaries:
                        article = summaries[pmid]
                        title = article.get("title", "")

                        # Get abstract from fetch results
                        abstract = abstract_map.get(pmid, "")

                        # Build rich snippet with abstract
                        authors = article.get("authors", [])
                        author_str = ", ".join([a.get("name", "") for a in authors[:3]])
                        source = article.get("source", "")
                        pubdate = article.get("pubdate", "")

                        # Include abstract in snippet for NLI verification
                        if abstract:
                            snippet = f"{author_str}. {source}. {pubdate}.\n\nABSTRACT: {abstract}"
                        else:
                            snippet = f"{author_str}. {source}. {pubdate}"

                        result = SearchResult(
                            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                            title=title,
                            snippet=snippet,
                            source_engine=self.name,
                            rank=rank,
                        )
                        results.append(result)

        except httpx.HTTPError as e:
            logger.error(f"PubMed search error: {e}")
        except Exception as e:
            logger.error(f"PubMed unexpected error: {e}")

        return results

    def _parse_pubmed_xml(self, xml_text: str) -> Dict[str, str]:
        """Parse PubMed XML to extract abstracts."""
        import re
        abstract_map = {}

        # Simple regex extraction (avoid heavy XML parsing)
        # Find all PMID and AbstractText pairs
        articles = re.findall(
            r'<PMID[^>]*>(\d+)</PMID>.*?<Abstract>(.*?)</Abstract>',
            xml_text,
            re.DOTALL
        )

        for pmid, abstract_block in articles:
            # Clean abstract text
            abstract_text = re.sub(r'<[^>]+>', ' ', abstract_block)
            abstract_text = re.sub(r'\s+', ' ', abstract_text).strip()
            abstract_map[pmid] = abstract_text[:2000]  # Limit length

        return abstract_map


# =============================================================================
# ARXIV ENGINE (Technical/Scientific Preprints)
# =============================================================================

class ArxivEngine(SearchEngine):
    """
    ArXiv preprint search for technical/scientific papers.

    Covers: physics, mathematics, computer science, quantitative biology,
    quantitative finance, statistics, electrical engineering, economics.
    """

    name: str = "arxiv"
    buckets: List[str] = ["academic", "technical", "scientific"]

    def __init__(self):
        super().__init__()
        self.client = None
        if ARXIV_AVAILABLE:
            self.client = arxiv.Client()

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        """Execute ArXiv search."""
        if not ARXIV_AVAILABLE or not self.client:
            logger.warning("ArXiv library not available, skipping search")
            return []

        await self._wait_for_rate_limit("arxiv.org")

        results = []

        try:
            # Run synchronous arxiv search in thread pool
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None,
                self._sync_search,
                query,
                max_results
            )
            results = search_results

        except Exception as e:
            logger.error(f"ArXiv search error: {e}")

        return results

    def _sync_search(self, query: str, max_results: int) -> List[SearchResult]:
        """Synchronous ArXiv search (run in executor)."""
        results = []

        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            for rank, paper in enumerate(self.client.results(search), start=1):
                # Get authors
                authors = [a.name for a in paper.authors[:3]]
                author_str = ", ".join(authors)

                # Build rich snippet with abstract
                abstract = paper.summary or ""
                categories = ", ".join(paper.categories[:3]) if paper.categories else ""
                published = paper.published.strftime("%Y-%m-%d") if paper.published else ""

                snippet = f"{author_str}. {categories}. {published}.\n\nABSTRACT: {abstract[:1500]}"

                # Prefer PDF URL for full text access
                url = paper.pdf_url or paper.entry_id or ""

                result = SearchResult(
                    url=url,
                    title=paper.title or "",
                    snippet=snippet,
                    source_engine=self.name,
                    rank=rank,
                )
                results.append(result)

        except Exception as e:
            logger.error(f"ArXiv sync search error: {e}")

        return results


# =============================================================================
# SEMANTIC SCHOLAR ENGINE
# =============================================================================

class SemanticScholarEngine(SearchEngine):
    """Semantic Scholar academic paper search."""

    name: str = "semantic_scholar"
    buckets: List[str] = ["academic"]

    def __init__(self):
        super().__init__()
        self.api_key = self.config.env.semantic_scholar_api_key
        self.base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        """Execute Semantic Scholar paper search."""
        await self._wait_for_rate_limit("api.semanticscholar.org")

        results = []
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        params = {
            "query": query,
            "limit": max_results,
            "fields": "paperId,title,abstract,url,authors,year,venue",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.base_url,
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                papers = data.get("data", [])
                for rank, paper in enumerate(papers, start=1):
                    title = paper.get("title", "")
                    abstract = paper.get("abstract", "") or ""
                    url = paper.get("url", "")
                    authors = paper.get("authors", [])
                    year = paper.get("year", "")
                    venue = paper.get("venue", "")

                    # Build snippet
                    author_str = ", ".join([a.get("name", "") for a in authors[:3]])
                    snippet = f"{author_str}. {venue} {year}. {abstract[:200]}..."

                    # Use Semantic Scholar URL or construct one
                    paper_id = paper.get("paperId", "")
                    if not url and paper_id:
                        url = f"https://www.semanticscholar.org/paper/{paper_id}"

                    result = SearchResult(
                        url=url,
                        title=title,
                        snippet=snippet,
                        source_engine=self.name,
                        rank=rank,
                    )
                    results.append(result)

        except httpx.HTTPError as e:
            logger.error(f"Semantic Scholar search error: {e}")
        except Exception as e:
            logger.error(f"Semantic Scholar unexpected error: {e}")

        return results


# =============================================================================
# OPENALEX ENGINE
# =============================================================================

class OpenAlexEngine(SearchEngine):
    """OpenAlex open access academic content search."""

    name: str = "openalex"
    buckets: List[str] = ["academic"]

    def __init__(self):
        super().__init__()
        self.base_url = "https://api.openalex.org/works"

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        """Execute OpenAlex works search."""
        await self._wait_for_rate_limit("api.openalex.org")

        results = []

        params = {
            "search": query,
            "per_page": max_results,
            "mailto": "polaris-research@example.com",  # Polite pool
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.base_url,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                works = data.get("results", [])
                for rank, work in enumerate(works, start=1):
                    title = work.get("title", "") or ""
                    doi = work.get("doi", "")
                    url = work.get("id", "") or doi or ""

                    # Build snippet from abstract and authorship
                    abstract_obj = work.get("abstract_inverted_index", {})
                    # OpenAlex uses inverted index for abstract
                    abstract_words = []
                    if abstract_obj:
                        # Reconstruct first 200 chars of abstract
                        word_positions = [(word, min(positions)) for word, positions in abstract_obj.items()]
                        word_positions.sort(key=lambda x: x[1])
                        abstract_words = [w[0] for w in word_positions[:30]]
                    abstract = " ".join(abstract_words)

                    authorships = work.get("authorships", [])
                    authors = [a.get("author", {}).get("display_name", "") for a in authorships[:3]]
                    author_str = ", ".join(authors)

                    year = work.get("publication_year", "")
                    venue = work.get("host_venue", {}).get("display_name", "") or ""

                    snippet = f"{author_str}. {venue} {year}. {abstract}..."

                    result = SearchResult(
                        url=url,
                        title=title,
                        snippet=snippet,
                        source_engine=self.name,
                        rank=rank,
                    )
                    results.append(result)

        except httpx.HTTPError as e:
            logger.error(f"OpenAlex search error: {e}")
        except Exception as e:
            logger.error(f"OpenAlex unexpected error: {e}")

        return results


# =============================================================================
# ENGINE FACTORY
# =============================================================================

def get_search_engines() -> Dict[str, SearchEngine]:
    """
    Get all configured search engines.

    Returns:
        Dict mapping engine name to engine instance
    """
    config = get_config()

    engines = {}

    # Serper (if configured)
    if config.search.engines.get("serper", {}).enabled:
        engines["serper"] = SerperEngine()

    # PubMed (always available - enhanced with free full text + abstracts)
    if config.search.engines.get("pubmed", {}).enabled:
        engines["pubmed"] = PubMedEngine()

    # Semantic Scholar (if configured)
    if config.search.engines.get("semantic_scholar", {}).enabled:
        engines["semantic_scholar"] = SemanticScholarEngine()

    # OpenAlex (always available, no API key needed)
    if config.search.engines.get("openalex", {}).enabled:
        engines["openalex"] = OpenAlexEngine()

    # ArXiv (always available, no API key needed) - SOTA addition
    arxiv_config = config.search.engines.get("arxiv", {})
    if arxiv_config.enabled if hasattr(arxiv_config, 'enabled') else True:
        if ARXIV_AVAILABLE:
            engines["arxiv"] = ArxivEngine()

    return engines


def get_engine_for_bucket(bucket: str) -> List[SearchEngine]:
    """
    Get search engines appropriate for a query bucket.

    Args:
        bucket: Query bucket (academic, government, industry, news, general)

    Returns:
        List of engines that handle this bucket
    """
    all_engines = get_search_engines()

    matching = []
    for engine in all_engines.values():
        if bucket in engine.buckets:
            matching.append(engine)

    return matching


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def run_tests():
        print("=" * 60)
        print("SEARCH ENGINES SELF-TEST")
        print("=" * 60)

        # Test 1: Engine initialization
        print("\n[TEST 1] Engine initialization...")
        try:
            engines = get_search_engines()
            print(f"  Engines available: {list(engines.keys())}")
            print("  [PASS] Engine initialization")
        except Exception as e:
            # LOW-107: Use logger instead of print
            logger.warning(f"Engine initialization failed: {e}")
            return

        # Test 2: OpenAlex search (no API key required)
        print("\n[TEST 2] OpenAlex search...")
        try:
            openalex = OpenAlexEngine()
            results = await openalex.search("water filter contamination pathogens", max_results=3)
            print(f"  Results: {len(results)}")
            if results:
                print(f"  First result: {results[0].title[:60]}...")
                print("  [PASS] OpenAlex search")
            else:
                print("  [WARN] No results (may be rate limited)")
        except Exception as e:
            # LOW-108: Use logger instead of print
            logger.warning(f"OpenAlex search failed: {e}")

        # Test 3: PubMed search (no API key required, but rate limited)
        print("\n[TEST 3] PubMed search...")
        try:
            pubmed = PubMedEngine()
            results = await pubmed.search("household water filter bacteria", max_results=3)
            print(f"  Results: {len(results)}")
            if results:
                print(f"  First result: {results[0].title[:60]}...")
                print("  [PASS] PubMed search")
            else:
                print("  [WARN] No results (may be rate limited)")
        except Exception as e:
            # LOW-109: Use logger instead of print
            logger.warning(f"PubMed search failed: {e}")

        # Test 4: Engine bucket mapping
        print("\n[TEST 4] Engine bucket mapping...")
        try:
            academic_engines = get_engine_for_bucket("academic")
            general_engines = get_engine_for_bucket("general")
            print(f"  Academic engines: {[e.name for e in academic_engines]}")
            print(f"  General engines: {[e.name for e in general_engines]}")
            print("  [PASS] Engine bucket mapping")
        except Exception as e:
            # LOW-110: Use logger instead of print
            logger.warning(f"Engine bucket mapping failed: {e}")

        print("\n" + "=" * 60)
        print("SEARCH ENGINES SELF-TEST COMPLETE")
        print("=" * 60)

    asyncio.run(run_tests())
