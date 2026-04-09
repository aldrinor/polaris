"""
Wiki Deep Crawl — expands source pool via Jina Reader (free, 200 RPM).

Levels:
  L1: Follow DOIs/PMIDs mentioned in fetched content
  L2: S2 citation graph — references for key papers
  L3: S2 recommendations for seed papers

All fetching via Jina Reader ($0) with SQLite content cache dedup.
"""

import asyncio
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

CRAWL_CONCURRENCY = int(os.getenv("PG_CRAWL_CONCURRENCY", "10"))
CRAWL_BUDGET_MINUTES = int(os.getenv("PG_CRAWL_BUDGET_MINUTES", "15"))
CRAWL_MAX_SOURCES = int(os.getenv("PG_CRAWL_MAX_SOURCES", "500"))
CRAWL_L1_ENABLED = os.getenv("PG_CRAWL_L1_ENABLED", "1") == "1"
CRAWL_L2_ENABLED = os.getenv("PG_CRAWL_L2_ENABLED", "1") == "1"
CRAWL_L2_MAX_REFS = int(os.getenv("PG_CRAWL_L2_MAX_REFS", "10"))
S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

# DOI/PMID extraction patterns
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\])<>\"',;]+")
PMID_PATTERN = re.compile(r"(?:PMID|PubMed ID)[:\s]*(\d{7,8})")
PMC_PATTERN = re.compile(r"PMC\d{7,8}")


async def deep_crawl(
    fetched_content: list[dict],
    web_results: list[dict],
    academic_results: list[dict],
    query: str,
    vector_id: str,
) -> list[dict]:
    """
    Expand the source pool by following references and DOIs.

    Returns additional fetched content (list of {url, content, title, source_type}).
    """
    start_time = time.time()
    deadline = start_time + CRAWL_BUDGET_MINUTES * 60

    # Collect all already-fetched URLs for dedup
    known_urls = {fc.get("url", "") for fc in fetched_content}
    known_urls.update(r.get("url", "") for r in web_results)
    known_urls.update(r.get("url", "") for r in academic_results)
    known_urls.discard("")

    logger.info(
        "[deep-crawl] Starting: %d known URLs, budget=%d min, max=%d sources",
        len(known_urls), CRAWL_BUDGET_MINUTES, CRAWL_MAX_SOURCES,
    )

    new_content: list[dict] = []

    # ── L1: Follow DOIs/PMIDs from fetched content ──────────────
    if CRAWL_L1_ENABLED and time.time() < deadline:
        l1_urls = _extract_dois_from_content(fetched_content, known_urls)
        if l1_urls:
            logger.info("[deep-crawl] L1: Found %d new DOI/PMID URLs to follow", len(l1_urls))
            l1_fetched = await _fetch_batch(
                l1_urls[:CRAWL_MAX_SOURCES // 3],
                known_urls, deadline,
            )
            new_content.extend(l1_fetched)
            known_urls.update(fc.get("url", "") for fc in l1_fetched)
            logger.info("[deep-crawl] L1: Fetched %d new sources", len(l1_fetched))

    # ── L2: S2 citation graph ───────────────────────────────────
    if CRAWL_L2_ENABLED and time.time() < deadline:
        seed_papers = _get_seed_papers(academic_results)
        if seed_papers:
            l2_urls = await _get_s2_references(seed_papers, known_urls)
            if l2_urls:
                logger.info("[deep-crawl] L2: Found %d reference URLs to follow", len(l2_urls))
                l2_fetched = await _fetch_batch(
                    l2_urls[:CRAWL_MAX_SOURCES // 3],
                    known_urls, deadline,
                )
                new_content.extend(l2_fetched)
                known_urls.update(fc.get("url", "") for fc in l2_fetched)
                logger.info("[deep-crawl] L2: Fetched %d new sources", len(l2_fetched))

    elapsed = time.time() - start_time
    logger.info(
        "[deep-crawl] Complete: %d new sources in %.1fs (L1+L2)",
        len(new_content), elapsed,
    )

    return new_content


# ── L1: DOI/PMID Extraction ─────────────────────────────────────────


def _extract_dois_from_content(
    fetched_content: list[dict],
    known_urls: set[str],
) -> list[str]:
    """Extract DOIs and PMIDs from fetched content, return as URLs."""
    urls = []
    seen_dois: set[str] = set()

    for fc in fetched_content:
        content = fc.get("content", "")
        if not content:
            continue

        # Extract DOIs
        for doi_match in DOI_PATTERN.finditer(content):
            doi = doi_match.group(0).rstrip(".")
            if doi not in seen_dois:
                seen_dois.add(doi)
                url = f"https://doi.org/{doi}"
                if url not in known_urls:
                    urls.append(url)

        # Extract PMIDs
        for pmid_match in PMID_PATTERN.finditer(content):
            pmid = pmid_match.group(1)
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            if url not in known_urls:
                urls.append(url)

        # Extract PMC IDs
        for pmc_match in PMC_PATTERN.finditer(content):
            pmc_id = pmc_match.group(0)
            url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc_id}/"
            if url not in known_urls:
                urls.append(url)

    # Dedup
    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)

    return unique[:200]  # Cap at 200 L1 URLs


# ── L2: S2 Citation Graph ────────────────────────────────────────────


def _get_seed_papers(academic_results: list[dict]) -> list[dict]:
    """Get top-cited papers as seeds for citation chasing."""
    papers = [
        r for r in academic_results
        if r.get("citation_count", 0) > 5 or r.get("citationCount", 0) > 5
    ]
    papers.sort(
        key=lambda r: r.get("citation_count", r.get("citationCount", 0)),
        reverse=True,
    )
    return papers[:10]  # Top 10 most-cited


async def _get_s2_references(
    seed_papers: list[dict],
    known_urls: set[str],
) -> list[str]:
    """Fetch reference lists from S2 for seed papers."""
    import aiohttp

    urls = []
    headers = {}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    async with aiohttp.ClientSession() as session:
        for paper in seed_papers:
            # Get paper ID (S2 ID, DOI, or URL-derived)
            paper_id = (
                paper.get("paperId")
                or paper.get("semantic_scholar_id")
                or paper.get("doi")
            )
            if not paper_id:
                continue

            try:
                api_url = (
                    f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
                    f"/references?fields=title,url,openAccessPdf&limit={CRAWL_L2_MAX_REFS}"
                )
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for ref in data.get("data", []):
                            cited = ref.get("citedPaper", {})
                            # Prefer open access PDF URL
                            oa = cited.get("openAccessPdf", {})
                            url = (oa.get("url") if oa else None) or cited.get("url", "")
                            if url and url not in known_urls:
                                urls.append(url)

                    # Rate limit: 1 RPS for S2
                    await asyncio.sleep(1.0)

            except Exception as exc:
                logger.debug("[deep-crawl] S2 reference fetch failed for %s: %s", paper_id, str(exc)[:80])

    return urls[:100]  # Cap at 100 L2 URLs


# ── Batch Fetching ───────────────────────────────────────────────────


async def _fetch_batch(
    urls: list[str],
    known_urls: set[str],
    deadline: float,
) -> list[dict]:
    """Fetch URLs concurrently via the existing content fetch pipeline."""
    results: list[dict] = []
    semaphore = asyncio.Semaphore(CRAWL_CONCURRENCY)

    async def fetch_one(url: str) -> dict | None:
        if time.time() >= deadline:
            return None
        async with semaphore:
            return await _fetch_single_url(url)

    tasks = [fetch_one(url) for url in urls if url not in known_urls]
    if not tasks:
        return results

    completed = await asyncio.gather(*tasks, return_exceptions=True)
    for item in completed:
        if isinstance(item, dict) and item.get("content"):
            results.append(item)

    return results


async def _fetch_single_url(url: str) -> dict | None:
    """Fetch a single URL using the existing access bypass pipeline."""
    try:
        # Try to use existing content cache first
        try:
            from src.polaris_graph.memory.content_cache import get_cached_content
            cached = await get_cached_content(url)
            if cached:
                return {
                    "url": url,
                    "content": cached.get("content", ""),
                    "title": cached.get("title", ""),
                    "source_type": "deep_crawl_cached",
                }
        except Exception:
            pass

        # Fetch via Jina Reader (free, fast)
        import aiohttp
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "Accept": "text/markdown",
            "X-Return-Format": "markdown",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                jina_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    if content and len(content) > 100:
                        # Cache it
                        try:
                            from src.polaris_graph.memory.content_cache import cache_content
                            await cache_content(url, content, title="", fetch_method="jina_deep_crawl")
                        except Exception:
                            pass

                        return {
                            "url": url,
                            "content": content[:30000],  # Cap content length
                            "title": "",
                            "source_type": "deep_crawl",
                        }

    except Exception as exc:
        logger.debug("[deep-crawl] Failed to fetch %s: %s", url[:60], str(exc)[:80])

    return None
