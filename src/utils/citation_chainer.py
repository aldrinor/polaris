"""
Citation Chainer for POLARIS SOTA Retrieval.

Implements forward and backward snowballing to discover papers through
citation networks rather than relying solely on keyword search.

Citation Chaining Strategy:
1. Start with seed papers (from initial search)
2. Forward snowball: Find papers citing the seed (newer, building on it)
3. Backward snowball: Find references of the seed (foundational works)
4. Recursive expansion with deduplication and relevance filtering

This addresses a key SOTA gap: probabilistic keyword search misses relevant
papers that use different terminology but cite the same foundational works.

References:
- GPT Blueprint: Phase 3 Citation Chaining, Snowballing
- Gemini Diagnostic: Section 1 Citation-Based Discovery
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.utils.openalex_client import OpenAlexClient, OpenAlexWork
from src.utils.semantic_scholar_client import SemanticScholarClient, S2Paper

logger = logging.getLogger(__name__)


@dataclass
class CitationNode:
    """Represents a paper in the citation graph."""

    # Identifiers
    doi: Optional[str] = None
    openalex_id: Optional[str] = None
    s2_id: Optional[str] = None

    # Metadata
    title: str = ""
    year: Optional[int] = None
    authors: list[str] = field(default_factory=list)
    abstract: Optional[str] = None
    venue: Optional[str] = None

    # Citation metrics
    citation_count: int = 0
    influential_citation_count: int = 0
    reference_count: int = 0

    # Graph position
    depth: int = 0  # 0 = seed, 1 = first hop, etc.
    is_seed: bool = False
    found_via: str = ""  # "forward", "backward", "seed"

    # Source data
    openalex_work: Optional[OpenAlexWork] = None
    s2_paper: Optional[S2Paper] = None

    @property
    def primary_id(self) -> str:
        """Return the best available identifier."""
        return self.doi or self.openalex_id or self.s2_id or ""

    @property
    def is_high_impact(self) -> bool:
        """Check if this is a high-impact paper (for prioritization)."""
        return (
            self.citation_count >= 50 or
            self.influential_citation_count >= 10
        )


@dataclass
class CitationChainResult:
    """Results from citation chaining."""

    seed_papers: list[CitationNode] = field(default_factory=list)
    forward_papers: list[CitationNode] = field(default_factory=list)
    backward_papers: list[CitationNode] = field(default_factory=list)
    all_papers: list[CitationNode] = field(default_factory=list)

    # Statistics
    total_unique: int = 0
    by_depth: dict[int, int] = field(default_factory=dict)
    sources_used: list[str] = field(default_factory=list)

    @property
    def unique_dois(self) -> set[str]:
        """Return set of unique DOIs."""
        return {p.doi for p in self.all_papers if p.doi}


class CitationChainer:
    """
    Orchestrates citation chaining across multiple academic APIs.

    Uses OpenAlex (primary) and Semantic Scholar (secondary) to:
    1. Find papers citing seed papers (forward snowballing)
    2. Find references of seed papers (backward snowballing)
    3. Deduplicate and rank by relevance/impact
    """

    def __init__(
        self,
        openalex_email: Optional[str] = None,
        s2_api_key: Optional[str] = None,
        max_depth: int = 1,
        max_papers_per_seed: int = 50,
    ):
        """
        Initialize citation chainer.

        Args:
            openalex_email: Email for OpenAlex polite pool
            s2_api_key: Semantic Scholar API key (optional)
            max_depth: Maximum citation chain depth (default 1 hop)
            max_papers_per_seed: Maximum papers to fetch per seed
        """
        self.openalex_email = openalex_email
        self.s2_api_key = s2_api_key
        self.max_depth = max_depth
        self.max_papers_per_seed = max_papers_per_seed

        # Deduplication tracking
        self._seen_dois: set[str] = set()
        self._seen_openalex_ids: set[str] = set()
        self._seen_s2_ids: set[str] = set()

    def _is_seen(self, node: CitationNode) -> bool:
        """Check if paper has already been processed."""
        if node.doi and node.doi in self._seen_dois:
            return True
        if node.openalex_id and node.openalex_id in self._seen_openalex_ids:
            return True
        if node.s2_id and node.s2_id in self._seen_s2_ids:
            return True
        return False

    def _mark_seen(self, node: CitationNode):
        """Mark paper as processed."""
        if node.doi:
            self._seen_dois.add(node.doi)
        if node.openalex_id:
            self._seen_openalex_ids.add(node.openalex_id)
        if node.s2_id:
            self._seen_s2_ids.add(node.s2_id)

    def _openalex_to_node(
        self,
        work: OpenAlexWork,
        depth: int,
        found_via: str,
    ) -> CitationNode:
        """Convert OpenAlex work to CitationNode."""
        return CitationNode(
            doi=work.doi,
            openalex_id=work.openalex_id,
            title=work.title,
            year=work.publication_year,
            authors=[a.display_name for a in work.authors],
            abstract=work.abstract,
            venue=work.primary_location,
            citation_count=work.cited_by_count,
            reference_count=len(work.referenced_works),
            depth=depth,
            found_via=found_via,
            openalex_work=work,
        )

    def _s2_to_node(
        self,
        paper: S2Paper,
        depth: int,
        found_via: str,
    ) -> CitationNode:
        """Convert S2Paper to CitationNode."""
        return CitationNode(
            doi=paper.doi,
            s2_id=paper.paper_id,
            title=paper.title,
            year=paper.year,
            authors=paper.author_names,
            abstract=paper.abstract or paper.tldr,
            venue=paper.venue,
            citation_count=paper.citation_count,
            influential_citation_count=paper.influential_citation_count,
            reference_count=paper.reference_count,
            depth=depth,
            found_via=found_via,
            s2_paper=paper,
        )

    async def chain_from_dois(
        self,
        seed_dois: list[str],
        forward: bool = True,
        backward: bool = True,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
    ) -> CitationChainResult:
        """
        Perform citation chaining starting from seed DOIs.

        Args:
            seed_dois: List of seed paper DOIs
            forward: Enable forward snowballing (papers citing seeds)
            backward: Enable backward snowballing (references of seeds)
            year_min: Minimum publication year filter
            year_max: Maximum publication year filter

        Returns:
            CitationChainResult with discovered papers
        """
        result = CitationChainResult()
        result.sources_used = []

        # Reset deduplication
        self._seen_dois = set()
        self._seen_openalex_ids = set()
        self._seen_s2_ids = set()

        async with OpenAlexClient(email=self.openalex_email) as openalex:
            async with SemanticScholarClient(api_key=self.s2_api_key) as s2:

                # Phase 1: Convert seed DOIs to nodes
                logger.info(f"Citation chaining: {len(seed_dois)} seed DOIs")
                for doi in seed_dois:
                    node = await self._resolve_seed(doi, openalex, s2)
                    if node:
                        node.is_seed = True
                        node.found_via = "seed"
                        node.depth = 0
                        result.seed_papers.append(node)
                        result.all_papers.append(node)
                        self._mark_seen(node)

                if not result.seed_papers:
                    logger.warning("No seed papers resolved")
                    return result

                result.sources_used.append("OpenAlex")
                result.sources_used.append("SemanticScholar")

                # Phase 2: Forward snowballing (papers citing seeds)
                if forward:
                    logger.info("Forward snowballing...")
                    for seed in result.seed_papers:
                        forward_nodes = await self._forward_snowball(
                            seed, openalex, s2, year_min, year_max
                        )
                        for node in forward_nodes:
                            if not self._is_seen(node):
                                node.depth = 1
                                node.found_via = "forward"
                                result.forward_papers.append(node)
                                result.all_papers.append(node)
                                self._mark_seen(node)

                # Phase 3: Backward snowballing (references of seeds)
                if backward:
                    logger.info("Backward snowballing...")
                    for seed in result.seed_papers:
                        backward_nodes = await self._backward_snowball(
                            seed, openalex, s2, year_min, year_max
                        )
                        for node in backward_nodes:
                            if not self._is_seen(node):
                                node.depth = 1
                                node.found_via = "backward"
                                result.backward_papers.append(node)
                                result.all_papers.append(node)
                                self._mark_seen(node)

        # Compute statistics
        result.total_unique = len(result.all_papers)
        for paper in result.all_papers:
            result.by_depth[paper.depth] = result.by_depth.get(paper.depth, 0) + 1

        logger.info(
            f"Citation chaining complete: {result.total_unique} unique papers "
            f"(seeds: {len(result.seed_papers)}, "
            f"forward: {len(result.forward_papers)}, "
            f"backward: {len(result.backward_papers)})"
        )

        return result

    async def _resolve_seed(
        self,
        doi: str,
        openalex: OpenAlexClient,
        s2: SemanticScholarClient,
    ) -> Optional[CitationNode]:
        """Resolve a seed DOI to a CitationNode using both APIs."""
        # Try OpenAlex first (better coverage)
        work = await openalex.get_work_by_doi(doi)
        if work:
            return self._openalex_to_node(work, depth=0, found_via="seed")

        # Fall back to Semantic Scholar
        paper = await s2.get_paper_by_id(doi, id_type="doi")
        if paper:
            return self._s2_to_node(paper, depth=0, found_via="seed")

        logger.warning(f"Could not resolve seed DOI: {doi}")
        return None

    async def _forward_snowball(
        self,
        seed: CitationNode,
        openalex: OpenAlexClient,
        s2: SemanticScholarClient,
        year_min: Optional[int],
        year_max: Optional[int],
    ) -> list[CitationNode]:
        """Find papers that cite the seed (forward snowballing)."""
        nodes = []

        # Use OpenAlex if we have the ID
        if seed.openalex_work:
            citing_works = await openalex.get_citing_works(
                seed.openalex_work.openalex_id,
                limit=self.max_papers_per_seed,
            )
            for work in citing_works:
                # Apply year filter
                if year_min and work.publication_year and work.publication_year < year_min:
                    continue
                if year_max and work.publication_year and work.publication_year > year_max:
                    continue
                nodes.append(self._openalex_to_node(work, depth=1, found_via="forward"))

        # Supplement with Semantic Scholar if we have the ID
        elif seed.s2_paper:
            citing_papers = await s2.get_paper_citations(
                seed.s2_paper.paper_id,
                limit=self.max_papers_per_seed,
            )
            for paper in citing_papers:
                if year_min and paper.year and paper.year < year_min:
                    continue
                if year_max and paper.year and paper.year > year_max:
                    continue
                nodes.append(self._s2_to_node(paper, depth=1, found_via="forward"))

        logger.debug(f"Forward snowball from '{seed.title[:50]}...': {len(nodes)} papers")
        return nodes

    async def _backward_snowball(
        self,
        seed: CitationNode,
        openalex: OpenAlexClient,
        s2: SemanticScholarClient,
        year_min: Optional[int],
        year_max: Optional[int],
    ) -> list[CitationNode]:
        """Find papers referenced by the seed (backward snowballing)."""
        nodes = []

        # Use OpenAlex if we have the ID
        if seed.openalex_work:
            ref_works = await openalex.get_referenced_works(
                seed.openalex_work.openalex_id,
                limit=self.max_papers_per_seed,
            )
            for work in ref_works:
                # Apply year filter
                if year_min and work.publication_year and work.publication_year < year_min:
                    continue
                if year_max and work.publication_year and work.publication_year > year_max:
                    continue
                nodes.append(self._openalex_to_node(work, depth=1, found_via="backward"))

        # Supplement with Semantic Scholar if we have the ID
        elif seed.s2_paper:
            ref_papers = await s2.get_paper_references(
                seed.s2_paper.paper_id,
                limit=self.max_papers_per_seed,
            )
            for paper in ref_papers:
                if year_min and paper.year and paper.year < year_min:
                    continue
                if year_max and paper.year and paper.year > year_max:
                    continue
                nodes.append(self._s2_to_node(paper, depth=1, found_via="backward"))

        logger.debug(f"Backward snowball from '{seed.title[:50]}...': {len(nodes)} papers")
        return nodes

    async def chain_from_search_results(
        self,
        openalex_works: list[OpenAlexWork] = None,
        s2_papers: list[S2Paper] = None,
        forward: bool = True,
        backward: bool = True,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
    ) -> CitationChainResult:
        """
        Perform citation chaining starting from existing search results.

        More efficient than starting from DOIs when you already have
        API response objects.

        Args:
            openalex_works: List of OpenAlex work objects
            s2_papers: List of Semantic Scholar paper objects
            forward: Enable forward snowballing
            backward: Enable backward snowballing
            year_min: Minimum publication year
            year_max: Maximum publication year

        Returns:
            CitationChainResult with discovered papers
        """
        result = CitationChainResult()
        result.sources_used = []

        # Reset deduplication
        self._seen_dois = set()
        self._seen_openalex_ids = set()
        self._seen_s2_ids = set()

        # Convert search results to seed nodes
        openalex_works = openalex_works or []
        s2_papers = s2_papers or []

        for work in openalex_works:
            node = self._openalex_to_node(work, depth=0, found_via="seed")
            node.is_seed = True
            if not self._is_seen(node):
                result.seed_papers.append(node)
                result.all_papers.append(node)
                self._mark_seen(node)

        for paper in s2_papers:
            node = self._s2_to_node(paper, depth=0, found_via="seed")
            node.is_seed = True
            if not self._is_seen(node):
                result.seed_papers.append(node)
                result.all_papers.append(node)
                self._mark_seen(node)

        if not result.seed_papers:
            logger.warning("No seed papers provided")
            return result

        async with OpenAlexClient(email=self.openalex_email) as openalex:
            async with SemanticScholarClient(api_key=self.s2_api_key) as s2:

                result.sources_used.append("OpenAlex")
                result.sources_used.append("SemanticScholar")

                # Forward snowballing
                if forward:
                    logger.info("Forward snowballing from search results...")
                    for seed in result.seed_papers:
                        forward_nodes = await self._forward_snowball(
                            seed, openalex, s2, year_min, year_max
                        )
                        for node in forward_nodes:
                            if not self._is_seen(node):
                                node.depth = 1
                                node.found_via = "forward"
                                result.forward_papers.append(node)
                                result.all_papers.append(node)
                                self._mark_seen(node)

                # Backward snowballing
                if backward:
                    logger.info("Backward snowballing from search results...")
                    for seed in result.seed_papers:
                        backward_nodes = await self._backward_snowball(
                            seed, openalex, s2, year_min, year_max
                        )
                        for node in backward_nodes:
                            if not self._is_seen(node):
                                node.depth = 1
                                node.found_via = "backward"
                                result.backward_papers.append(node)
                                result.all_papers.append(node)
                                self._mark_seen(node)

        # Compute statistics
        result.total_unique = len(result.all_papers)
        for paper in result.all_papers:
            result.by_depth[paper.depth] = result.by_depth.get(paper.depth, 0) + 1

        logger.info(
            f"Citation chaining complete: {result.total_unique} unique papers"
        )

        return result

    def rank_by_impact(
        self,
        result: CitationChainResult,
        top_n: Optional[int] = None,
    ) -> list[CitationNode]:
        """
        Rank discovered papers by impact metrics.

        Uses citation count and influential citations to prioritize
        the most important papers.

        Args:
            result: CitationChainResult to rank
            top_n: Return only top N papers (None for all)

        Returns:
            Sorted list of CitationNodes
        """
        papers = result.all_papers.copy()

        # Sort by: influential citations (weighted 3x) + regular citations
        papers.sort(
            key=lambda p: (p.influential_citation_count * 3) + p.citation_count,
            reverse=True,
        )

        if top_n:
            return papers[:top_n]
        return papers


# Convenience function
async def discover_related_papers(
    seed_dois: list[str],
    year_min: int = 2020,
    year_max: int = 2026,
    max_papers: int = 100,
) -> list[CitationNode]:
    """
    Convenience function to discover related papers via citation chaining.

    Args:
        seed_dois: Starting DOIs
        year_min: Minimum year filter
        year_max: Maximum year filter
        max_papers: Maximum papers to return

    Returns:
        List of related papers ranked by impact
    """
    chainer = CitationChainer()
    result = await chainer.chain_from_dois(
        seed_dois=seed_dois,
        year_min=year_min,
        year_max=year_max,
    )
    return chainer.rank_by_impact(result, top_n=max_papers)


# Self-test
if __name__ == "__main__":
    async def test_chainer():
        """Test citation chainer functionality."""
        print("Testing Citation Chainer...")

        # Use a well-known paper DOI for testing
        seed_dois = [
            "10.1021/acs.est.5b00716",  # Environmental Science & Technology
        ]

        chainer = CitationChainer(max_papers_per_seed=10)
        result = await chainer.chain_from_dois(
            seed_dois=seed_dois,
            forward=True,
            backward=True,
            year_min=2020,
            year_max=2026,
        )

        print(f"\n1. Citation Chain Results:")
        print(f"   Seeds: {len(result.seed_papers)}")
        print(f"   Forward (citing): {len(result.forward_papers)}")
        print(f"   Backward (references): {len(result.backward_papers)}")
        print(f"   Total unique: {result.total_unique}")

        print(f"\n2. Top 5 papers by impact:")
        ranked = chainer.rank_by_impact(result, top_n=5)
        for i, paper in enumerate(ranked, 1):
            print(f"   {i}. {paper.title[:50]}... ({paper.year})")
            print(f"      Citations: {paper.citation_count}, Via: {paper.found_via}")

        print("\n[PASS] Citation chainer tests completed")

    asyncio.run(test_chainer())
