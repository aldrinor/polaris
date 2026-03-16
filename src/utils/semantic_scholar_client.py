"""
Semantic Scholar API Client for POLARIS SOTA Retrieval.

Semantic Scholar provides:
- Semantic search (finds papers even without keyword overlap)
- TLDR summaries (AI-generated paper summaries)
- Citation graph with "highly influential" citations
- Paper embeddings for similarity search

API Documentation: https://api.semanticscholar.org/api-docs/
Rate Limit: 100 requests/5 minutes (free), 1000 requests/5 minutes (partner)

References:
- GPT Blueprint: Phase 2 Multi-Source Ingestion, Phase 3 Semantic Search
- Gemini Diagnostic: Section 1 Semantic Ranking and Recall
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Semantic Scholar API configuration
S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"
S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
REQUEST_DELAY_SECONDS = 0.5  # Conservative rate limiting for free tier


@dataclass
class S2Author:
    """Author information from Semantic Scholar."""

    author_id: str
    name: str
    affiliations: list[str] = field(default_factory=list)


@dataclass
class S2Paper:
    """Normalized paper object from Semantic Scholar."""

    paper_id: str
    corpus_id: Optional[int] = None
    doi: Optional[str] = None
    title: str = ""
    abstract: Optional[str] = None
    tldr: Optional[str] = None  # AI-generated summary
    venue: Optional[str] = None
    year: Optional[int] = None
    publication_date: Optional[str] = None
    authors: list[S2Author] = field(default_factory=list)
    citation_count: int = 0
    influential_citation_count: int = 0
    reference_count: int = 0
    is_open_access: bool = False
    open_access_pdf_url: Optional[str] = None
    fields_of_study: list[str] = field(default_factory=list)
    s2_url: Optional[str] = None
    external_ids: dict = field(default_factory=dict)

    @property
    def author_names(self) -> list[str]:
        """Return list of author names."""
        return [a.name for a in self.authors]


class SemanticScholarClient:
    """
    Async client for Semantic Scholar API.

    Features:
    - Semantic search (relevance-based, not just keyword)
    - Paper lookup by ID, DOI, or title
    - Citation and reference traversal
    - TLDR summaries for quick screening
    """

    # Fields to request from API
    PAPER_FIELDS = [
        "paperId", "corpusId", "externalIds", "url",
        "title", "abstract", "venue", "year", "publicationDate",
        "referenceCount", "citationCount", "influentialCitationCount",
        "isOpenAccess", "openAccessPdf", "fieldsOfStudy",
        "authors", "tldr",
    ]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Semantic Scholar client.

        Args:
            api_key: API key for higher rate limits (optional)
        """
        self.api_key = api_key or S2_API_KEY
        self.base_url = S2_BASE_URL
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
            if self.api_key:
                headers["x-api-key"] = self.api_key
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
        params: Optional[dict] = None,
        method: str = "GET",
        json_data: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict:
        """
        Make a rate-limited request to Semantic Scholar API.

        Args:
            endpoint: API endpoint
            params: Query parameters
            method: HTTP method
            json_data: JSON body for POST requests
            max_retries: Maximum retry attempts

        Returns:
            JSON response as dict
        """
        await self._ensure_session()
        await self._rate_limit()

        url = f"{self.base_url}{endpoint}"

        for attempt in range(max_retries):
            try:
                if method == "GET":
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            wait_time = (2 ** attempt) * 2.0
                            logger.warning(f"S2 rate limited, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                        elif response.status == 404:
                            return {}
                        else:
                            logger.error(f"S2 API error: {response.status}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                else:  # POST
                    async with self.session.post(url, params=params, json=json_data) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            wait_time = (2 ** attempt) * 2.0
                            logger.warning(f"S2 rate limited, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"S2 API error: {response.status}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                logger.error(f"S2 request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

        return {}

    def _parse_paper(self, raw: dict) -> S2Paper:
        """
        Parse raw Semantic Scholar paper response into normalized object.

        Args:
            raw: Raw paper dict from API

        Returns:
            Normalized S2Paper object
        """
        # Extract authors
        authors = []
        for author_data in raw.get("authors", []):
            authors.append(S2Author(
                author_id=author_data.get("authorId", ""),
                name=author_data.get("name", "Unknown"),
                affiliations=author_data.get("affiliations", []),
            ))

        # Extract external IDs
        external_ids = raw.get("externalIds", {}) or {}

        # Extract open access PDF URL
        oa_pdf = raw.get("openAccessPdf", {}) or {}
        oa_url = oa_pdf.get("url") if oa_pdf else None

        # Extract TLDR
        tldr_data = raw.get("tldr", {}) or {}
        tldr = tldr_data.get("text") if tldr_data else None

        return S2Paper(
            paper_id=raw.get("paperId", ""),
            corpus_id=raw.get("corpusId"),
            doi=external_ids.get("DOI"),
            title=raw.get("title", ""),
            abstract=raw.get("abstract"),
            tldr=tldr,
            venue=raw.get("venue"),
            year=raw.get("year"),
            publication_date=raw.get("publicationDate"),
            authors=authors,
            citation_count=raw.get("citationCount", 0),
            influential_citation_count=raw.get("influentialCitationCount", 0),
            reference_count=raw.get("referenceCount", 0),
            is_open_access=raw.get("isOpenAccess", False),
            open_access_pdf_url=oa_url,
            fields_of_study=raw.get("fieldsOfStudy", []) or [],
            s2_url=raw.get("url"),
            external_ids=external_ids,
        )

    async def search_papers(
        self,
        query: str,
        year_range: Optional[tuple[int, int]] = None,
        fields_of_study: Optional[list[str]] = None,
        open_access_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[S2Paper]:
        """
        Search for papers using Semantic Scholar's relevance search.

        This finds semantically similar papers even without keyword overlap.

        Args:
            query: Search query
            year_range: (min_year, max_year) tuple
            fields_of_study: Filter by field (e.g., ["Environmental Science"])
            open_access_only: Only return open access papers
            limit: Maximum results (max 100 per request)
            offset: Pagination offset

        Returns:
            List of matching papers
        """
        params = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "fields": ",".join(self.PAPER_FIELDS),
        }

        if year_range:
            params["year"] = f"{year_range[0]}-{year_range[1]}"

        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        if open_access_only:
            params["openAccessPdf"] = ""

        response = await self._request("/paper/search", params)
        data = response.get("data", [])

        papers = [self._parse_paper(raw) for raw in data]
        logger.info(f"S2 search '{query[:50]}...' returned {len(papers)} papers")
        return papers

    async def get_paper_by_id(
        self,
        paper_id: str,
        id_type: str = "auto",
    ) -> Optional[S2Paper]:
        """
        Fetch a specific paper by ID.

        Args:
            paper_id: Paper identifier
            id_type: ID type - "s2" (Semantic Scholar), "doi", "arxiv", "pmid", "auto"

        Returns:
            Paper object or None if not found
        """
        # Build the identifier based on type
        if id_type == "doi" or (id_type == "auto" and "/" in paper_id):
            identifier = f"DOI:{paper_id}"
        elif id_type == "arxiv":
            identifier = f"ARXIV:{paper_id}"
        elif id_type == "pmid":
            identifier = f"PMID:{paper_id}"
        else:
            identifier = paper_id

        params = {"fields": ",".join(self.PAPER_FIELDS)}

        try:
            response = await self._request(f"/paper/{identifier}", params)
            if response and "paperId" in response:
                return self._parse_paper(response)
        except Exception as e:
            logger.error(f"Failed to fetch paper {paper_id}: {e}")

        return None

    async def get_paper_citations(
        self,
        paper_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[S2Paper]:
        """
        Get papers that cite the given paper (forward snowballing).

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum citations to return
            offset: Pagination offset

        Returns:
            List of citing papers
        """
        params = {
            "fields": ",".join(self.PAPER_FIELDS),
            "limit": min(limit, 1000),
            "offset": offset,
        }

        response = await self._request(f"/paper/{paper_id}/citations", params)
        data = response.get("data", [])

        papers = []
        for item in data:
            citing_paper = item.get("citingPaper", {})
            if citing_paper:
                papers.append(self._parse_paper(citing_paper))

        logger.info(f"Found {len(papers)} citations for paper {paper_id}")
        return papers

    async def get_paper_references(
        self,
        paper_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[S2Paper]:
        """
        Get papers referenced by the given paper (backward snowballing).

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum references to return
            offset: Pagination offset

        Returns:
            List of referenced papers
        """
        params = {
            "fields": ",".join(self.PAPER_FIELDS),
            "limit": min(limit, 1000),
            "offset": offset,
        }

        response = await self._request(f"/paper/{paper_id}/references", params)
        data = response.get("data", [])

        papers = []
        for item in data:
            cited_paper = item.get("citedPaper", {})
            if cited_paper:
                papers.append(self._parse_paper(cited_paper))

        logger.info(f"Found {len(papers)} references for paper {paper_id}")
        return papers

    async def bulk_search(
        self,
        queries: list[str],
        year_range: Optional[tuple[int, int]] = None,
        per_query_limit: int = 20,
    ) -> list[S2Paper]:
        """
        Search multiple queries and deduplicate results.

        Args:
            queries: List of search queries
            year_range: Optional year filter
            per_query_limit: Results per query

        Returns:
            Deduplicated list of papers
        """
        all_papers = []
        seen_ids = set()

        for query in queries:
            papers = await self.search_papers(
                query=query,
                year_range=year_range,
                limit=per_query_limit,
            )

            for paper in papers:
                if paper.paper_id not in seen_ids:
                    seen_ids.add(paper.paper_id)
                    all_papers.append(paper)

        logger.info(f"Bulk search returned {len(all_papers)} unique papers from {len(queries)} queries")
        return all_papers

    async def search_recent_high_impact(
        self,
        topic: str,
        min_year: int = 2024,
        min_citations: int = 0,
        limit: int = 50,
    ) -> list[S2Paper]:
        """
        Search for recent high-impact papers on a topic.

        Sorts by citation count to find influential papers.

        Args:
            topic: Research topic
            min_year: Minimum publication year
            min_citations: Minimum citation count
            limit: Maximum results

        Returns:
            List of papers sorted by citations
        """
        papers = await self.search_papers(
            query=topic,
            year_range=(min_year, 2026),
            limit=limit,
        )

        # Filter by citation count and sort
        filtered = [p for p in papers if p.citation_count >= min_citations]
        filtered.sort(key=lambda x: x.citation_count, reverse=True)

        return filtered

    # =========================================================================
    # SOTA: EMBEDDING-BASED SEMANTIC SIMILARITY (from upgrade plan)
    # Uses S2 Recommendations API for paper similarity via embeddings
    # =========================================================================

    async def get_similar_papers(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> list[S2Paper]:
        """
        SOTA: Get semantically similar papers using S2 embeddings.

        Uses the Semantic Scholar Recommendations API which returns papers
        similar to the given paper based on SPECTER2 embeddings.

        API: POST /recommendations/v1/papers/
        Docs: https://api.semanticscholar.org/api-docs/recommendations

        Args:
            paper_id: Seed paper ID (S2 paper ID)
            limit: Maximum similar papers to return

        Returns:
            List of semantically similar papers
        """
        # The recommendations API uses a different base URL
        reco_url = "https://api.semanticscholar.org/recommendations/v1/papers/"

        params = {
            "fields": ",".join(self.PAPER_FIELDS),
            "limit": min(limit, 500),
        }

        # POST with seed paper in body
        json_data = {
            "positivePaperIds": [paper_id],
            "negativePaperIds": [],
        }

        await self._ensure_session()
        await self._rate_limit()

        try:
            async with self.session.post(
                reco_url,
                params=params,
                json=json_data,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    papers = [self._parse_paper(p) for p in data.get("recommendedPapers", [])]
                    logger.info(f"S2 recommendations for {paper_id}: {len(papers)} similar papers")
                    return papers
                else:
                    logger.warning(f"S2 recommendations API returned {response.status}")
                    return []

        except Exception as e:
            logger.error(f"S2 recommendations failed: {e}")
            return []

    async def get_similar_papers_multi(
        self,
        paper_ids: list[str],
        limit: int = 50,
    ) -> list[S2Paper]:
        """
        SOTA: Get papers similar to multiple seed papers.

        This is useful for finding papers that are similar to a set of
        high-quality papers already retrieved.

        Args:
            paper_ids: List of seed paper IDs (max 5)
            limit: Maximum similar papers to return

        Returns:
            List of semantically similar papers
        """
        reco_url = "https://api.semanticscholar.org/recommendations/v1/papers/"

        # S2 API accepts up to 5 positive paper IDs
        seed_ids = paper_ids[:5]

        params = {
            "fields": ",".join(self.PAPER_FIELDS),
            "limit": min(limit, 500),
        }

        json_data = {
            "positivePaperIds": seed_ids,
            "negativePaperIds": [],
        }

        await self._ensure_session()
        await self._rate_limit()

        try:
            async with self.session.post(
                reco_url,
                params=params,
                json=json_data,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    papers = [self._parse_paper(p) for p in data.get("recommendedPapers", [])]
                    logger.info(f"S2 multi-seed recommendations: {len(papers)} papers from {len(seed_ids)} seeds")
                    return papers
                else:
                    logger.warning(f"S2 recommendations API returned {response.status}")
                    return []

        except Exception as e:
            logger.error(f"S2 multi-seed recommendations failed: {e}")
            return []

    async def semantic_similarity_search(
        self,
        query: str,
        year_range: Optional[tuple[int, int]] = None,
        limit: int = 50,
        similarity_expansion: bool = True,
    ) -> list[S2Paper]:
        """
        SOTA: Two-stage semantic search with embedding expansion.

        Stage 1: Standard semantic search to find seed papers
        Stage 2: Use top seeds to find similar papers via embeddings

        This dramatically improves recall by finding papers that are
        semantically related but may not share keywords with the query.

        Args:
            query: Search query
            year_range: Optional year filter
            limit: Maximum total results
            similarity_expansion: Whether to expand via embeddings

        Returns:
            Combined list of papers from both stages
        """
        # Stage 1: Standard semantic search
        seed_papers = await self.search_papers(
            query=query,
            year_range=year_range,
            limit=min(limit // 2, 25),
        )

        if not seed_papers or not similarity_expansion:
            return seed_papers

        # Stage 2: Embedding expansion using top 3-5 papers as seeds
        seed_ids = [p.paper_id for p in seed_papers[:5] if p.paper_id]
        if not seed_ids:
            return seed_papers

        logger.info(f"SOTA: Expanding search via embeddings using {len(seed_ids)} seed papers")
        similar_papers = await self.get_similar_papers_multi(seed_ids, limit=limit)

        # Combine and deduplicate
        seen_ids = {p.paper_id for p in seed_papers}
        combined = list(seed_papers)

        for paper in similar_papers:
            if paper.paper_id not in seen_ids:
                seen_ids.add(paper.paper_id)
                combined.append(paper)

        # Apply year filter to expanded results
        if year_range:
            combined = [
                p for p in combined
                if p.year and year_range[0] <= p.year <= year_range[1]
            ]

        logger.info(f"SOTA: Semantic similarity search returned {len(combined)} papers ({len(seed_papers)} direct + {len(combined) - len(seed_papers)} via embeddings)")
        return combined[:limit]


# Convenience function for quick searches
async def search_semantic_scholar(
    query: str,
    year_min: int = 2020,
    year_max: int = 2026,
    limit: int = 50,
) -> list[S2Paper]:
    """
    Convenience function for quick Semantic Scholar searches.

    Args:
        query: Search query
        year_min: Minimum year
        year_max: Maximum year
        limit: Maximum results

    Returns:
        List of matching papers
    """
    async with SemanticScholarClient() as client:
        return await client.search_papers(
            query=query,
            year_range=(year_min, year_max),
            limit=limit,
        )


# Self-test
if __name__ == "__main__":
    async def test_client():
        """Test Semantic Scholar client functionality."""
        print("Testing Semantic Scholar Client...")

        async with SemanticScholarClient() as client:
            # Test 1: Basic search
            print("\n1. Basic search for 'water contamination'...")
            papers = await client.search_papers(
                "water contamination private wells",
                year_range=(2023, 2026),
                limit=5,
            )
            print(f"   Found {len(papers)} papers")
            for p in papers[:3]:
                print(f"   - {p.title[:60]}... ({p.year})")
                print(f"     Citations: {p.citation_count}, TLDR: {p.tldr[:80] if p.tldr else 'N/A'}...")

            # Test 2: Paper by DOI
            print("\n2. Testing DOI lookup...")
            # Using a known DOI
            paper = await client.get_paper_by_id("10.1371/journal.pone.0000000", id_type="doi")
            if paper:
                print(f"   Found: {paper.title}")
            else:
                print("   Paper not found (expected for test DOI)")

            # Test 3: Recent high-impact papers
            print("\n3. Recent high-impact papers...")
            high_impact = await client.search_recent_high_impact(
                topic="drinking water quality contamination",
                min_year=2024,
                limit=10,
            )
            print(f"   Found {len(high_impact)} papers")
            for p in high_impact[:3]:
                print(f"   - {p.title[:50]}... (Citations: {p.citation_count})")

        print("\n[PASS] Semantic Scholar client tests completed")

    asyncio.run(test_client())
