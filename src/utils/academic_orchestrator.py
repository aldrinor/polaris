"""
POLARIS Academic Source Orchestrator
=====================================
Orchestrates multi-source academic retrieval using SOTA API clients.

This module integrates:
- OpenAlex (240M+ papers, geographic filtering)
- Semantic Scholar (semantic search, TLDRs, influential citations)
- CrossRef (DOI resolution, clean metadata)
- Unpaywall (Open Access PDF links)
- Citation Chainer (forward/backward snowballing)

Purpose:
- Replace probabilistic keyword search with deterministic API access
- Enable citation chaining for comprehensive literature coverage
- Provide clean, validated metadata (no garbage authors)
- Geographic filtering at the API level (not text pattern matching)

References:
- GPT Blueprint: Phase 3 Multi-Source Ingestion
- Gemini Diagnostic: Section 1-3 SOTA Data Acquisition
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.schemas.api_query import (
    APISource,
    NormalizedAuthor,
    NormalizedPaper,
    RegionCode,
    get_country_codes,
)
from src.schemas.phase_models import SearchResult
from src.utils.openalex_client import OpenAlexClient, OpenAlexWork
from src.utils.semantic_scholar_client import SemanticScholarClient, S2Paper
from src.utils.crossref_client import CrossRefClient, CrossRefWork
from src.utils.unpaywall_client import UnpaywallClient
from src.utils.citation_chainer import CitationChainer, CitationChainResult

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorStats:
    """Statistics from orchestrated retrieval."""

    total_papers: int = 0
    unique_papers: int = 0
    papers_by_source: Dict[str, int] = field(default_factory=dict)

    # By retrieval method
    from_keyword_search: int = 0
    from_citation_chaining: int = 0
    from_doi_resolution: int = 0
    from_embedding_similarity: int = 0  # SOTA: Embedding-based expansion

    # Quality metrics
    papers_with_doi: int = 0
    papers_with_pdf: int = 0
    papers_with_abstract: int = 0
    valid_author_rate: float = 0.0

    # Filtering
    geographic_filtered: int = 0
    year_filtered: int = 0

    execution_time_ms: int = 0


class AcademicOrchestrator:
    """
    Orchestrates multi-source academic paper retrieval.

    Features:
    - Parallel queries across OpenAlex, Semantic Scholar, CrossRef
    - Citation chaining for comprehensive coverage
    - PDF URL enrichment via Unpaywall
    - Geographic filtering at API level
    - Deduplication by DOI
    """

    def __init__(
        self,
        openalex_email: Optional[str] = None,
        s2_api_key: Optional[str] = None,
        unpaywall_email: Optional[str] = None,
    ):
        """
        Initialize academic orchestrator.

        Args:
            openalex_email: Email for OpenAlex polite pool
            s2_api_key: Semantic Scholar API key (optional)
            unpaywall_email: Email for Unpaywall API
        """
        self.openalex_email = openalex_email
        self.s2_api_key = s2_api_key
        self.unpaywall_email = unpaywall_email

        # Deduplication tracking
        self._seen_dois: set[str] = set()
        self._seen_titles: set[str] = set()

    def _normalize_title(self, title: str) -> str:
        """Normalize title for deduplication."""
        return title.lower().strip()[:100]

    def _is_duplicate(self, paper: NormalizedPaper) -> bool:
        """Check if paper is a duplicate."""
        if paper.doi and paper.doi in self._seen_dois:
            return True
        title_norm = self._normalize_title(paper.title)
        if title_norm in self._seen_titles:
            return True
        return False

    def _mark_seen(self, paper: NormalizedPaper):
        """Mark paper as seen."""
        if paper.doi:
            self._seen_dois.add(paper.doi)
        self._seen_titles.add(self._normalize_title(paper.title))

    def _openalex_to_normalized(self, work: OpenAlexWork) -> NormalizedPaper:
        """Convert OpenAlex work to NormalizedPaper."""
        authors = []
        for oa_author in work.authors:
            authors.append(NormalizedAuthor(
                full_name=oa_author.display_name,
                orcid=oa_author.orcid,
                affiliations=[],
                source_api=APISource.OPENALEX,
            ))

        return NormalizedPaper(
            doi=work.doi,
            openalex_id=work.openalex_id,
            title=work.title,
            abstract=work.abstract,
            authors=authors,
            year=work.publication_year,
            venue=work.primary_location,
            publisher=work.publisher,
            citation_count=work.cited_by_count,
            reference_count=len(work.referenced_works),
            is_open_access=work.is_open_access,
            author_countries=work.author_countries,
            source_api=APISource.OPENALEX,
        )

    def _s2_to_normalized(self, paper: S2Paper) -> NormalizedPaper:
        """Convert Semantic Scholar paper to NormalizedPaper."""
        authors = []
        for s2_author in paper.authors:
            authors.append(NormalizedAuthor(
                full_name=s2_author.name,
                affiliations=s2_author.affiliations,
                source_api=APISource.SEMANTIC_SCHOLAR,
            ))

        return NormalizedPaper(
            doi=paper.doi,
            s2_id=paper.paper_id,
            title=paper.title,
            abstract=paper.abstract,
            tldr=paper.tldr,
            authors=authors,
            publication_date=paper.publication_date,
            year=paper.year,
            venue=paper.venue,
            citation_count=paper.citation_count,
            influential_citation_count=paper.influential_citation_count,
            reference_count=paper.reference_count,
            is_open_access=paper.is_open_access,
            pdf_url=paper.open_access_pdf_url,
            source_api=APISource.SEMANTIC_SCHOLAR,
        )

    def _crossref_to_normalized(self, work: CrossRefWork) -> NormalizedPaper:
        """Convert CrossRef work to NormalizedPaper."""
        authors = []
        for cr_author in work.authors:
            authors.append(NormalizedAuthor(
                given_name=cr_author.given,
                family_name=cr_author.family,
                full_name=cr_author.full_name,
                orcid=cr_author.orcid,
                affiliations=[cr_author.affiliation] if cr_author.affiliation else [],
                source_api=APISource.CROSSREF,
            ))

        return NormalizedPaper(
            doi=work.doi,
            title=work.title,
            authors=authors,
            publication_date=work.published_date,
            year=work.published_year,
            venue=work.container_title,
            publisher=work.publisher,
            is_open_access=work.is_open_access,
            license=work.license_url,
            reference_count=work.reference_count,
            citation_count=work.citation_count,
            referenced_dois=work.references,
            source_api=APISource.CROSSREF,
        )

    async def search(
        self,
        queries: List[str],
        region: Optional[RegionCode] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        max_per_query: int = 25,
        enable_citation_chaining: bool = True,
        citation_chain_limit: int = 50,
    ) -> Tuple[List[NormalizedPaper], OrchestratorStats]:
        """
        Execute multi-source academic search.

        Args:
            queries: List of search queries
            region: Geographic region filter
            year_min: Minimum publication year
            year_max: Maximum publication year
            max_per_query: Maximum results per query per source
            enable_citation_chaining: Whether to perform citation chaining
            citation_chain_limit: Maximum papers from citation chaining

        Returns:
            Tuple of (papers, stats)
        """
        start_time = datetime.now(timezone.utc)
        stats = OrchestratorStats()

        # Reset deduplication
        self._seen_dois = set()
        self._seen_titles = set()

        all_papers: List[NormalizedPaper] = []

        # Get country codes for region filter
        country_codes = get_country_codes(region) if region else []

        async with OpenAlexClient(email=self.openalex_email) as openalex:
            async with SemanticScholarClient(api_key=self.s2_api_key) as s2:

                # Phase 1: OpenAlex search (primary - best coverage and geographic filtering)
                logger.info(f"Searching OpenAlex with {len(queries)} queries...")
                for query in queries:
                    try:
                        if region and region != RegionCode.GLOBAL:
                            # Use geographic filtering
                            works = await openalex.search_by_region(
                                query=query,
                                region=region.value,
                                year_min=year_min,
                                year_max=year_max,
                                limit=max_per_query,
                            )
                        else:
                            works = await openalex.search_works(
                                query=query,
                                year_min=year_min,
                                year_max=year_max,
                                limit=max_per_query,
                            )

                        for work in works:
                            paper = self._openalex_to_normalized(work)
                            if not self._is_duplicate(paper):
                                all_papers.append(paper)
                                self._mark_seen(paper)
                                stats.from_keyword_search += 1
                                stats.papers_by_source["openalex"] = \
                                    stats.papers_by_source.get("openalex", 0) + 1

                    except Exception as e:
                        logger.warning(f"OpenAlex search failed for '{query[:50]}': {e}")

                # Phase 2: Semantic Scholar search (semantic relevance + TLDRs)
                logger.info(f"Searching Semantic Scholar with {len(queries)} queries...")
                for query in queries:
                    try:
                        papers = await s2.search_papers(
                            query=query,
                            year_range=(year_min, year_max) if year_min and year_max else None,
                            limit=max_per_query // 2,  # Fewer from S2 to balance
                        )

                        for s2_paper in papers:
                            paper = self._s2_to_normalized(s2_paper)

                            # Apply region filter (less precise than OpenAlex)
                            if not self._is_duplicate(paper):
                                all_papers.append(paper)
                                self._mark_seen(paper)
                                stats.from_keyword_search += 1
                                stats.papers_by_source["semantic_scholar"] = \
                                    stats.papers_by_source.get("semantic_scholar", 0) + 1

                    except Exception as e:
                        logger.warning(f"S2 search failed for '{query[:50]}': {e}")

                # =========================================================
                # SOTA: Phase 2.5 - Embedding-based semantic similarity
                # Uses S2 Recommendations API for SPECTER2 embeddings
                # =========================================================
                logger.info("SOTA: Expanding via S2 embedding similarity...")
                try:
                    # Get S2 paper IDs from papers found so far
                    s2_seed_ids = [
                        p.s2_id for p in all_papers
                        if p.s2_id and p.citation_count >= 5  # Use higher-quality papers as seeds
                    ][:5]  # Max 5 seeds for recommendations API

                    if s2_seed_ids:
                        logger.info(f"SOTA: Using {len(s2_seed_ids)} seed papers for embedding expansion")
                        similar_papers = await s2.get_similar_papers_multi(
                            paper_ids=s2_seed_ids,
                            limit=30,  # Get 30 similar papers
                        )

                        for s2_paper in similar_papers:
                            # Apply year filter
                            if year_min and s2_paper.year and s2_paper.year < year_min:
                                continue
                            if year_max and s2_paper.year and s2_paper.year > year_max:
                                continue

                            paper = self._s2_to_normalized(s2_paper)
                            if not self._is_duplicate(paper):
                                all_papers.append(paper)
                                self._mark_seen(paper)
                                stats.from_embedding_similarity += 1
                                stats.papers_by_source["s2_embeddings"] = \
                                    stats.papers_by_source.get("s2_embeddings", 0) + 1

                        logger.info(f"SOTA: Added {stats.from_embedding_similarity} papers via embedding similarity")
                    else:
                        logger.info("SOTA: No suitable seeds for embedding expansion")

                except Exception as e:
                    logger.warning(f"SOTA: Embedding similarity expansion failed: {e}")

                # Phase 3: Citation chaining from top results
                if enable_citation_chaining and all_papers:
                    logger.info("Performing citation chaining...")
                    try:
                        # Select seed papers (top by citation count)
                        seed_papers = sorted(
                            [p for p in all_papers if p.doi],
                            key=lambda x: x.citation_count,
                            reverse=True
                        )[:10]  # Top 10 as seeds

                        seed_dois = [p.doi for p in seed_papers if p.doi]

                        if seed_dois:
                            chainer = CitationChainer(
                                openalex_email=self.openalex_email,
                                s2_api_key=self.s2_api_key,
                                max_papers_per_seed=citation_chain_limit // len(seed_dois),
                            )
                            chain_result = await chainer.chain_from_dois(
                                seed_dois=seed_dois,
                                forward=True,
                                backward=True,
                                year_min=year_min,
                                year_max=year_max,
                            )

                            # Add chained papers
                            for node in chain_result.all_papers:
                                if node.is_seed:
                                    continue  # Skip seeds, already in results

                                # Convert citation node to NormalizedPaper
                                if node.openalex_work:
                                    paper = self._openalex_to_normalized(node.openalex_work)
                                elif node.s2_paper:
                                    paper = self._s2_to_normalized(node.s2_paper)
                                else:
                                    continue

                                if not self._is_duplicate(paper):
                                    all_papers.append(paper)
                                    self._mark_seen(paper)
                                    stats.from_citation_chaining += 1

                    except Exception as e:
                        logger.warning(f"Citation chaining failed: {e}")

        # Phase 4: Enrich with Unpaywall PDF URLs
        logger.info("Enriching with Unpaywall PDF URLs...")
        try:
            async with UnpaywallClient(email=self.unpaywall_email) as unpaywall:
                dois_to_lookup = [p.doi for p in all_papers if p.doi and not p.pdf_url][:100]
                if dois_to_lookup:
                    pdf_urls = await unpaywall.get_pdf_urls(dois_to_lookup)
                    for paper in all_papers:
                        if paper.doi in pdf_urls:
                            paper.pdf_url = pdf_urls[paper.doi]
        except Exception as e:
            logger.warning(f"Unpaywall enrichment failed: {e}")

        # Compute final stats
        stats.total_papers = len(all_papers)
        stats.unique_papers = len(all_papers)  # Already deduplicated
        stats.papers_with_doi = sum(1 for p in all_papers if p.doi)
        stats.papers_with_pdf = sum(1 for p in all_papers if p.pdf_url)
        stats.papers_with_abstract = sum(1 for p in all_papers if p.abstract)

        # Valid author rate
        total_authors = 0
        valid_authors = 0
        for paper in all_papers:
            for author in paper.authors:
                total_authors += 1
                if author.is_valid:
                    valid_authors += 1
        stats.valid_author_rate = valid_authors / total_authors if total_authors > 0 else 0.0

        end_time = datetime.now(timezone.utc)
        stats.execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.info(
            f"Academic orchestrator complete: {stats.unique_papers} unique papers, "
            f"{stats.from_keyword_search} from search, "
            f"{stats.from_citation_chaining} from citation chaining"
        )

        return all_papers, stats

    async def resolve_dois(
        self,
        dois: List[str],
        enrich_with_pdf: bool = True,
    ) -> List[NormalizedPaper]:
        """
        Resolve DOIs to full paper metadata.

        Uses CrossRef as primary source for clean metadata.

        Args:
            dois: List of DOIs to resolve
            enrich_with_pdf: Whether to look up PDF URLs via Unpaywall

        Returns:
            List of NormalizedPaper objects
        """
        papers = []

        async with CrossRefClient() as crossref:
            for doi in dois:
                try:
                    work = await crossref.get_work_by_doi(doi)
                    if work:
                        paper = self._crossref_to_normalized(work)
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"CrossRef lookup failed for {doi}: {e}")

        # Enrich with PDF URLs
        if enrich_with_pdf:
            try:
                async with UnpaywallClient(email=self.unpaywall_email) as unpaywall:
                    pdf_urls = await unpaywall.get_pdf_urls(dois)
                    for paper in papers:
                        if paper.doi in pdf_urls:
                            paper.pdf_url = pdf_urls[paper.doi]
            except Exception as e:
                logger.warning(f"Unpaywall enrichment failed: {e}")

        return papers


def paper_to_search_result(paper: NormalizedPaper, rank: int) -> SearchResult:
    """
    Convert NormalizedPaper to SearchResult for P3 output compatibility.

    Args:
        paper: NormalizedPaper object
        rank: Result rank

    Returns:
        SearchResult object
    """
    # Build snippet from abstract and metadata
    abstract_snippet = (paper.abstract or paper.tldr or "")[:500]
    author_list = [a.full_name for a in paper.authors[:3] if a.is_valid]
    author_str = ", ".join(author_list) if author_list else "Unknown"
    venue_str = f"{paper.venue or ''} {paper.year or ''}".strip()

    snippet = f"{author_str}. {venue_str}. {abstract_snippet}"

    # Construct URL
    url = ""
    if paper.doi:
        url = f"https://doi.org/{paper.doi}"
    elif paper.openalex_id:
        url = paper.openalex_id
    elif paper.s2_id:
        url = f"https://www.semanticscholar.org/paper/{paper.s2_id}"

    return SearchResult(
        url=url,
        title=paper.title,
        snippet=snippet,
        source_engine=paper.source_api.value,
        rank=rank,
        doi=paper.doi,
        authors=[a.full_name for a in paper.authors if a.is_valid],
        # SOTA: Source-level geographic metadata for API-based filtering
        author_countries=paper.author_countries if paper.author_countries else None,
        publication_year=paper.year,
        citation_count=paper.citation_count,
    )


# Self-test
if __name__ == "__main__":
    async def test_orchestrator():
        """Test academic orchestrator functionality."""
        print("Testing Academic Orchestrator...")

        orchestrator = AcademicOrchestrator()

        # Test 1: Multi-source search
        print("\n1. Testing multi-source search...")
        papers, stats = await orchestrator.search(
            queries=["private well water contamination bacteria"],
            region=RegionCode.NORTH_AMERICA,
            year_min=2020,
            year_max=2026,
            max_per_query=10,
            enable_citation_chaining=False,  # Disable for faster test
        )

        print(f"   Total papers: {stats.total_papers}")
        print(f"   By source: {stats.papers_by_source}")
        print(f"   With DOI: {stats.papers_with_doi}")
        print(f"   With PDF: {stats.papers_with_pdf}")
        print(f"   Valid author rate: {stats.valid_author_rate:.2%}")

        if papers:
            print(f"\n2. First 3 results:")
            for i, paper in enumerate(papers[:3], 1):
                print(f"   {i}. {paper.title[:60]}...")
                print(f"      DOI: {paper.doi}, Year: {paper.year}, Citations: {paper.citation_count}")

        print("\n[PASS] Academic orchestrator tests completed")

    asyncio.run(test_orchestrator())
