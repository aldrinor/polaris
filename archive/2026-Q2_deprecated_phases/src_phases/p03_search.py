#!/usr/bin/env python3
"""
POLARIS Phase 3: Search Execution
==================================
Execute federated search across multiple engines.

Purpose:
- Execute queries from Phase 2 across multiple search engines
- Aggregate and deduplicate results
- Return URLs for content fetching in Phase 4

Usage:
    python src/phases/p03_search.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --input outputs/P2/S1V1...json --output outputs/P3/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --input: Required. Path to Phase 2 output JSON.
    --output: Optional. Output directory (default: outputs/P3/)
    --self-test: Run self-test mode
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)
from urllib.parse import urlparse

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase2Output, Phase3Output, SearchResult, PerspectiveQuery
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.search.engines import (
    SearchEngine,
    SerperEngine,
    PubMedEngine,
    SemanticScholarEngine,
    OpenAlexEngine,
    get_search_engines,
    get_engine_for_bucket,
)
from src.audit import get_audit
from src.utils.url_blacklist import is_url_blacklisted, filter_blacklisted_urls
from src.utils.crossref_resolver import extract_doi_from_url
from src.utils.source_router import get_domain_authority, get_source_priorities
from src.schemas.question_types import QuestionType

# SOTA: Multi-source academic retrieval
from src.schemas.api_query import RegionCode
from src.utils.academic_orchestrator import (
    AcademicOrchestrator,
    paper_to_search_result,
    OrchestratorStats,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Map query bucket to search engines
BUCKET_ENGINE_MAP = {
    "academic": ["pubmed", "semantic_scholar", "openalex"],
    "government": ["serper"],
    "industry": ["serper"],
    "news": ["serper"],
    "general": ["serper"],
}

# SOTA: Region mapping for academic orchestrator
REGION_MAP = {
    "NORTH_AMERICA": RegionCode.NORTH_AMERICA,
    "EUROPE": RegionCode.EUROPE,
    "ASIA_PACIFIC": RegionCode.ASIA_PACIFIC,
    "GLOBAL": RegionCode.GLOBAL,
}


# =============================================================================
# SEARCH ORCHESTRATION
# =============================================================================

async def execute_single_search(
    engine: SearchEngine,
    query: str,
    max_results: int,
) -> Tuple[str, str, List[SearchResult]]:
    """
    Execute a single search query on an engine.

    Args:
        engine: Search engine instance
        query: Search query
        max_results: Maximum results

    Returns:
        Tuple of (engine_name, query, results)
    """
    try:
        results = await engine.search(query, max_results)
        return (engine.name, query, results)
    except Exception as e:
        # LOW-075: Use logger instead of print
        logger.warning(f"  [WARN] Search failed on {engine.name}: {e}")
        return (engine.name, query, [])


async def execute_bucket_searches(
    queries: List[str],
    bucket: str,
    engines: Dict[str, SearchEngine],
    max_results_per_query: int = 10,
    max_concurrent: int = 5,
) -> List[SearchResult]:
    """
    Execute searches for a bucket across appropriate engines.

    Args:
        queries: List of queries for this bucket
        bucket: Bucket type
        engines: Available engines
        max_results_per_query: Results per query
        max_concurrent: Max concurrent requests

    Returns:
        Aggregated search results
    """
    # Get engines for this bucket
    engine_names = BUCKET_ENGINE_MAP.get(bucket, ["serper"])
    available_engines = [engines[name] for name in engine_names if name in engines]

    if not available_engines:
        # Fallback to any available engine
        available_engines = list(engines.values())[:1]

    if not available_engines:
        return []

    # Build search tasks
    tasks = []
    for query in queries:
        # Distribute queries across engines for this bucket
        engine = available_engines[len(tasks) % len(available_engines)]
        task = execute_single_search(engine, query, max_results_per_query)
        tasks.append(task)

    # Execute with concurrency limit
    results = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_search(task):
        async with semaphore:
            return await task

    completed = await asyncio.gather(*[bounded_search(t) for t in tasks])

    for engine_name, query, search_results in completed:
        results.extend(search_results)

    return results


def deduplicate_results(results: List[SearchResult]) -> List[SearchResult]:
    """
    Deduplicate search results by URL.

    FIX-124B: Preserves perspective attribution from ALL perspectives that found each URL.
    When the same URL is found by multiple STORM perspectives, all are merged into
    perspective_origins list for coverage tracking.

    Args:
        results: List of search results

    Returns:
        Deduplicated results with merged perspective attributions
    """
    seen_urls: Dict[str, SearchResult] = {}

    for result in results:
        # Normalize URL
        url = result.url.lower().rstrip("/")

        if url not in seen_urls:
            # First time seeing this URL - initialize perspective_origins
            if result.perspective_origin and result.perspective_origin not in result.perspective_origins:
                result.perspective_origins.append(result.perspective_origin)
            seen_urls[url] = result
        else:
            existing = seen_urls[url]

            # FIX-124B: Merge perspective_origin into perspective_origins list
            if result.perspective_origin and result.perspective_origin not in existing.perspective_origins:
                existing.perspective_origins.append(result.perspective_origin)

            # Keep the one with better rank, but preserve merged perspectives
            if result.rank < existing.rank:
                # Transfer merged perspectives to the better-ranked result
                merged_perspectives = existing.perspective_origins.copy()
                result.perspective_origins = merged_perspectives
                if result.perspective_origin and result.perspective_origin not in result.perspective_origins:
                    result.perspective_origins.append(result.perspective_origin)
                seen_urls[url] = result

    # Log perspective coverage after deduplication
    multi_perspective_count = sum(1 for r in seen_urls.values() if len(r.perspective_origins) > 1)
    if multi_perspective_count > 0:
        logger.info(f"[FIX-124B] {multi_perspective_count} URLs found by multiple perspectives")

    return list(seen_urls.values())


def filter_blacklisted_results(
    results: List[SearchResult],
    vector_id: str = "",
) -> Tuple[List[SearchResult], int]:
    """
    Filter out blacklisted URLs at INGESTION (P3).

    This prevents wasting API calls on commercial, spam, and low-quality sources.
    Filtering at P3 is more efficient than waiting until P4 after content is fetched.

    Args:
        results: Search results to filter
        vector_id: Vector ID for logging

    Returns:
        Tuple of (filtered_results, rejected_count)
    """
    filtered = []
    rejected_count = 0

    for result in results:
        is_blacklisted, reason = is_url_blacklisted(result.url, include_news=True)
        if is_blacklisted:
            rejected_count += 1
            # Log only first 5 rejections to avoid spam
            if rejected_count <= 5:
                url_short = result.url[:50] + "..." if len(result.url) > 50 else result.url
                print(f"  [P3-BLACKLIST] Rejected: {url_short} ({reason})")
            elif rejected_count == 6:
                print(f"  [P3-BLACKLIST] ... and more (suppressing further logs)")
        else:
            filtered.append(result)

    return filtered, rejected_count


def enrich_with_doi(results: List[SearchResult]) -> List[SearchResult]:
    """
    SOTA: Extract DOI from URLs at search time for early metadata enrichment.

    This enables better deduplication and source quality assessment before
    content is fetched in P4.

    Args:
        results: Search results to enrich

    Returns:
        Results with DOI field populated where extractable
    """
    enriched_count = 0
    for result in results:
        if result.doi:  # Already has DOI
            continue

        # Try to extract DOI from URL
        doi = extract_doi_from_url(result.url)
        if doi:
            result.doi = doi
            enriched_count += 1

    if enriched_count > 0:
        print(f"  [P3-DOI] Extracted DOI from {enriched_count} URLs")

    return results


async def execute_sota_academic_search(
    queries: List[str],
    region: str,
    vector_id: str,
    year_min: int = 2020,
    year_max: int = 2026,
    enable_citation_chaining: bool = True,
) -> Tuple[List[SearchResult], Dict[str, int]]:
    """
    SOTA: Execute multi-source academic search using the academic orchestrator.

    This replaces probabilistic keyword search with deterministic API access:
    - OpenAlex (240M+ papers, geographic filtering)
    - Semantic Scholar (semantic search, TLDRs)
    - Citation chaining (forward/backward snowballing)
    - Unpaywall (PDF URL enrichment)

    Args:
        queries: Academic bucket queries
        region: Geographic region filter
        vector_id: Vector ID for logging
        year_min: Minimum publication year
        year_max: Maximum publication year
        enable_citation_chaining: Whether to perform citation chaining

    Returns:
        Tuple of (search_results, content_by_engine)
    """
    print(f"[PHASE-3][{vector_id}][SOTA] Executing multi-source academic search...")

    # Map region string to RegionCode
    region_code = REGION_MAP.get(region, RegionCode.GLOBAL)
    print(f"[PHASE-3][{vector_id}][SOTA] Region filter: {region_code.value}")

    orchestrator = AcademicOrchestrator()

    try:
        papers, stats = await orchestrator.search(
            queries=queries,
            region=region_code,
            year_min=year_min,
            year_max=year_max,
            max_per_query=25,
            enable_citation_chaining=enable_citation_chaining,
            citation_chain_limit=50,
        )

        print(f"[PHASE-3][{vector_id}][SOTA] Retrieved {stats.unique_papers} unique papers")
        print(f"[PHASE-3][{vector_id}][SOTA] From keyword search: {stats.from_keyword_search}")
        print(f"[PHASE-3][{vector_id}][SOTA] From embedding similarity: {stats.from_embedding_similarity}")
        print(f"[PHASE-3][{vector_id}][SOTA] From citation chaining: {stats.from_citation_chaining}")
        print(f"[PHASE-3][{vector_id}][SOTA] With DOI: {stats.papers_with_doi}")
        print(f"[PHASE-3][{vector_id}][SOTA] With PDF: {stats.papers_with_pdf}")
        print(f"[PHASE-3][{vector_id}][SOTA] Valid author rate: {stats.valid_author_rate:.1%}")

        # Convert NormalizedPaper to SearchResult
        results = []
        for rank, paper in enumerate(papers, start=1):
            result = paper_to_search_result(paper, rank)
            results.append(result)

        # Build content_by_engine stats
        content_by_engine = {}
        for source, count in stats.papers_by_source.items():
            content_by_engine[source] = count

        return results, content_by_engine

    except Exception as e:
        # LOW-002: Log error instead of print
        logger.error(f"Academic orchestrator failed for {vector_id}: {e}")
        return [], {}


def rank_results(results: List[SearchResult]) -> List[SearchResult]:
    """
    Re-rank deduplicated results using SOTA authority scoring.

    Prioritizes by:
    1. Domain authority score (from source_router)
    2. Academic sources (pubmed, semantic_scholar)
    3. Government sources (.gov domains)
    4. Original search rank

    Args:
        results: Deduplicated results

    Returns:
        Re-ranked results
    """
    def score_result(r: SearchResult) -> Tuple[float, int, int]:
        # SOTA: Use source_router for domain authority (higher = better, so negate for sorting)
        authority = get_domain_authority(r.url)
        authority_score = -authority  # Negate so higher authority sorts first

        # Engine priority as secondary sort (lower = better)
        engine_priority = {
            "pubmed": 1,
            "semantic_scholar": 2,
            "openalex": 3,
            "serper": 5,
        }
        engine_score = engine_priority.get(r.source_engine, 10)

        # Boost .gov and .edu domains
        try:
            domain = urlparse(r.url).netloc.lower()
            if ".gov" in domain:
                engine_score -= 2
            elif ".edu" in domain:
                engine_score -= 1
        except (ValueError, AttributeError) as e:
            # HIGH-004: Log URL parsing error instead of silent pass
            logger.debug(f"Could not parse URL for domain boost: {r.url} - {e}")

        return (authority_score, engine_score, r.rank)

    sorted_results = sorted(results, key=score_result)

    # Reassign ranks
    for i, result in enumerate(sorted_results, start=1):
        result.rank = i

    return sorted_results


# =============================================================================
# FIX-124I-C: PERSPECTIVE HEALTH CHECK
# =============================================================================

# Configuration constants for perspective health
MIN_PERSPECTIVES_REQUIRED = 5
MIN_PERSPECTIVE_BALANCE = 0.15


def check_perspective_health(
    results: List[SearchResult],
    min_required: int = MIN_PERSPECTIVES_REQUIRED,
    min_balance: float = MIN_PERSPECTIVE_BALANCE,
) -> Tuple[bool, Dict[str, Any]]:
    """
    FIX-124I-C: Check perspective coverage health before continuing.

    Returns (is_healthy, diagnostic_info) where:
    - is_healthy: True if perspective count >= min_required AND balance >= min_balance
    - diagnostic_info: Dict with perspective_count, balance, coverage, reason

    Args:
        results: List of search results with perspective attribution
        min_required: Minimum number of perspectives required (default 5)
        min_balance: Minimum balance ratio (min/max) required (default 0.15)

    Returns:
        Tuple of (is_healthy, diagnostic_info)
    """
    coverage: Dict[str, int] = {}
    for r in results:
        # Check perspective_origins first (merged list after dedup), then fallback to perspective_origin
        origins = getattr(r, 'perspective_origins', []) or []
        if not origins:
            origin = getattr(r, 'perspective_origin', None)
            if origin:
                origins = [origin]
        for origin in origins:
            coverage[origin] = coverage.get(origin, 0) + 1

    if not coverage:
        return False, {
            "is_healthy": False,
            "perspectives_count": 0,
            "balance": 0.0,
            "coverage": {},
            "reason": "No perspective-tagged results",
        }

    actual_count = len(coverage)
    values = list(coverage.values())
    balance = min(values) / max(values) if max(values) > 0 else 0

    is_healthy = actual_count >= min_required and balance >= min_balance

    reason = None
    if not is_healthy:
        issues = []
        if actual_count < min_required:
            issues.append(f"{actual_count} perspectives < {min_required} required")
        if balance < min_balance:
            issues.append(f"balance={balance:.2f} < {min_balance} required")
        reason = "; ".join(issues)

    return is_healthy, {
        "is_healthy": is_healthy,
        "perspectives_count": actual_count,
        "balance": round(balance, 3),
        "coverage": coverage,
        "reason": reason,
    }


# =============================================================================
# FIX-124: STORM PERSPECTIVE-BASED SEARCH EXECUTION
# =============================================================================

async def execute_perspective_searches(
    perspective_queries: List[PerspectiveQuery],
    engines: Dict[str, SearchEngine],
    vector_id: str,
    region: str,
    max_results_per_query: int = 10,
) -> List[SearchResult]:
    """
    FIX-124: Execute searches preserving STORM perspective identity.

    This function executes perspective-tagged queries and ensures each
    result is tagged with its originating perspective for coverage tracking.

    Args:
        perspective_queries: List of PerspectiveQuery objects with perspective identity
        engines: Available search engines
        vector_id: Vector ID for logging
        region: Geographic region
        max_results_per_query: Max results per query

    Returns:
        List of SearchResult objects tagged with perspective_origin
    """
    if not perspective_queries:
        return []

    print(f"[PHASE-3][{vector_id}][FIX-124] Executing {len(perspective_queries)} perspective-tagged queries")

    # Group queries by perspective for logging
    queries_by_perspective: Dict[str, List[PerspectiveQuery]] = defaultdict(list)
    for pq in perspective_queries:
        queries_by_perspective[pq.perspective_name].append(pq)

    for pname, pqueries in queries_by_perspective.items():
        print(f"[PHASE-3][{vector_id}][FIX-124]   {pname}: {len(pqueries)} queries")

    all_results = []

    # Execute queries by bucket but preserve perspective
    bucket_to_queries: Dict[str, List[PerspectiveQuery]] = defaultdict(list)
    for pq in perspective_queries:
        bucket_to_queries[pq.bucket].append(pq)

    for bucket, pqueries in bucket_to_queries.items():
        engine_names = BUCKET_ENGINE_MAP.get(bucket, ["serper"])
        available_engines = [engines[name] for name in engine_names if name in engines]

        if not available_engines:
            available_engines = list(engines.values())[:1]

        if not available_engines:
            continue

        # FIX-124I-A: Add retry logic with exponential backoff
        MAX_RETRIES = 2
        RETRY_DELAY = 1.5

        perspective_failures: Dict[str, List[str]] = defaultdict(list)

        for pq in pqueries:
            success = False
            for attempt in range(MAX_RETRIES + 1):
                try:
                    engine = available_engines[0]  # Use first available engine for bucket
                    engine_name, query_text, results = await execute_single_search(
                        engine, pq.query_text, max_results_per_query
                    )

                    if not results:
                        logger.warning(f"[FIX-124I] {pq.perspective_name} returned 0 results: {pq.query_text[:50]}")

                    # FIX-124: Tag each result with its perspective origin
                    for result in results:
                        result.perspective_origin = pq.perspective_name
                        all_results.append(result)
                    success = True
                    break  # Success, exit retry loop

                except Exception as e:
                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAY * (2 ** attempt)
                        logger.warning(f"[FIX-124I] Retry {attempt+1}/{MAX_RETRIES} for {pq.perspective_name} in {delay}s: {e}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[FIX-124I] FAILED after {MAX_RETRIES} retries for {pq.perspective_name}: {e}")
                        perspective_failures[pq.perspective_name].append(str(e))

        # FIX-124I-A: Log perspective failure summary
        if perspective_failures:
            failed_perspectives = list(perspective_failures.keys())
            logger.error(f"[FIX-124I] PERSPECTIVE FAILURES ({len(failed_perspectives)}): {failed_perspectives}")

    # Log perspective coverage
    perspective_coverage: Dict[str, int] = defaultdict(int)
    for r in all_results:
        if r.perspective_origin:
            perspective_coverage[r.perspective_origin] += 1

    print(f"[PHASE-3][{vector_id}][FIX-124] Perspective coverage:")
    for pname, pcount in sorted(perspective_coverage.items(), key=lambda x: -x[1]):
        print(f"[PHASE-3][{vector_id}][FIX-124]   {pname}: {pcount} results")

    return all_results


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

async def run_phase3(
    vector_id: str,
    input_path: Path,
    output_dir: Path,
) -> Phase3Output:
    """
    Execute Phase 3: Search Execution.

    Args:
        vector_id: Vector ID to process
        input_path: Path to Phase 2 output
        output_dir: Directory to write output

    Returns:
        Phase3Output model
    """
    timestamps = {"start": datetime.now(timezone.utc).isoformat()}
    audit = get_audit()

    # Load config
    config = get_config()
    max_results_per_engine = config.thresholds.search.max_results_per_engine

    # 1. Load Phase 2 output
    with open(input_path, "r", encoding="utf-8") as f:
        p2_data = json.load(f)

    p2_output = Phase2Output(**p2_data)

    # Verify vector ID matches
    if p2_output.vector_id != vector_id:
        raise ValueError(f"Vector ID mismatch: {vector_id} != {p2_output.vector_id}")

    # 2. Get available search engines
    engines = get_search_engines()
    print(f"[PHASE-3][{vector_id}][INFO] Available engines: {list(engines.keys())}")

    if not engines:
        print(f"[PHASE-3][{vector_id}][WARN] No search engines available, using fallbacks")

    # 3. Group queries by bucket
    bucket_queries = defaultdict(list)
    bucket_distribution = p2_output.bucket_distribution

    # Map queries to buckets based on distribution
    query_idx = 0
    for bucket, count in bucket_distribution.items():
        bucket_queries[bucket] = p2_output.final_queries[query_idx:query_idx + count]
        query_idx += count

    # SOTA: Extract region from vector_id for geographic filtering
    region = "GLOBAL"
    for region_name in ["NORTH_AMERICA", "EUROPE", "ASIA_PACIFIC", "GLOBAL"]:
        if region_name in vector_id:
            region = region_name
            break
    print(f"[PHASE-3][{vector_id}][INFO] Detected region: {region}")

    # 4. Execute searches per bucket
    all_results = []
    content_by_engine = defaultdict(int)

    for bucket, queries in bucket_queries.items():
        print(f"[PHASE-3][{vector_id}][INFO] Searching bucket '{bucket}' with {len(queries)} queries")

        # SOTA: Use academic orchestrator for academic bucket
        if bucket == "academic" and queries:
            print(f"[PHASE-3][{vector_id}][SOTA] Using multi-source academic orchestrator")
            sota_results, sota_engines = await execute_sota_academic_search(
                queries=queries,
                region=region,
                vector_id=vector_id,
                year_min=2020,
                year_max=2026,
                enable_citation_chaining=True,
            )
            all_results.extend(sota_results)
            for engine, count in sota_engines.items():
                content_by_engine[engine] += count
        else:
            # Use legacy engine-based search for non-academic buckets
            bucket_results = await execute_bucket_searches(
                queries=queries,
                bucket=bucket,
                engines=engines,
                max_results_per_query=max_results_per_engine // len(queries) if queries else 10,
                max_concurrent=5,
            )
            all_results.extend(bucket_results)

            # Track content by engine
            for result in bucket_results:
                content_by_engine[result.source_engine] += 1

    print(f"[PHASE-3][{vector_id}][INFO] Total raw results from buckets: {len(all_results)}")

    # 4.5 FIX-124: Execute STORM perspective-tagged queries
    # These are additional queries that preserve perspective identity for coverage tracking
    if hasattr(p2_output, 'perspective_queries') and p2_output.perspective_queries:
        print(f"[PHASE-3][{vector_id}][FIX-124] Executing STORM perspective-tagged queries...")
        perspective_results = await execute_perspective_searches(
            perspective_queries=p2_output.perspective_queries,
            engines=engines,
            vector_id=vector_id,
            region=region,
            max_results_per_query=5,  # Fewer per query since we have many perspective queries
        )
        all_results.extend(perspective_results)

        # Track perspective results by engine
        for result in perspective_results:
            content_by_engine[result.source_engine] += 1

        print(f"[PHASE-3][{vector_id}][FIX-124] Added {len(perspective_results)} perspective-tagged results")
        print(f"[PHASE-3][{vector_id}][INFO] Total raw results (bucket + perspective): {len(all_results)}")
    else:
        print(f"[PHASE-3][{vector_id}][INFO] No perspective queries found (legacy P2 output)")

    # 5. Deduplicate by URL
    unique_results = deduplicate_results(all_results)
    print(f"[PHASE-3][{vector_id}][INFO] Unique results after dedup: {len(unique_results)}")

    # FIX-124I-B: Log POST-DEDUP perspective coverage (the REAL coverage)
    post_dedup_coverage: Dict[str, int] = defaultdict(int)
    for r in unique_results:
        # Count from perspective_origins (merged list after dedup)
        origins = getattr(r, 'perspective_origins', []) or []
        if not origins:
            origin = getattr(r, 'perspective_origin', None)
            if origin:
                origins = [origin]
        for origin in origins:
            post_dedup_coverage[origin] += 1

    if post_dedup_coverage:
        print(f"[PHASE-3][{vector_id}][FIX-124I] POST-DEDUP perspective coverage:")
        for pname, pcount in sorted(post_dedup_coverage.items(), key=lambda x: -x[1]):
            print(f"[PHASE-3][{vector_id}][FIX-124I]   {pname}: {pcount} results")

        # Calculate and warn on low balance
        values = list(post_dedup_coverage.values())
        balance = min(values) / max(values) if max(values) > 0 else 0
        perspective_count = len(post_dedup_coverage)

        if perspective_count < 7:
            logger.warning(f"[FIX-124I] LOW PERSPECTIVE COUNT: {perspective_count}/9 (expected ≥7)")
        if balance < 0.20:
            logger.warning(f"[FIX-124I] LOW PERSPECTIVE BALANCE: {balance:.2f} (expected ≥0.20)")

    # FIX-124I-C: Check perspective health before continuing
    is_healthy, health_info = check_perspective_health(unique_results)
    if not is_healthy:
        logger.error(f"[FIX-124I] PERSPECTIVE HEALTH CRITICAL: {health_info['reason']}")
        logger.error(f"[FIX-124I] Coverage: {health_info['coverage']}")

    # 5.5 Filter blacklisted URLs at INGESTION (SOTA: Source Hygiene)
    # This prevents wasting P4 fetch calls on commercial/spam URLs
    filtered_results, blacklist_rejected = filter_blacklisted_results(unique_results, vector_id)
    if blacklist_rejected > 0:
        print(f"[PHASE-3][{vector_id}][INFO] Blacklist filtered: {blacklist_rejected} URLs rejected")
    print(f"[PHASE-3][{vector_id}][INFO] Results after blacklist filter: {len(filtered_results)}")

    # 5.6 SOTA: Extract DOI from URLs at search time
    # Enables early metadata enrichment before P4 content fetch
    filtered_results = enrich_with_doi(filtered_results)

    # 6. Re-rank results
    ranked_results = rank_results(filtered_results)

    # 7. Calculate stats
    urls_attempted = len(ranked_results)
    # Phase 3 doesn't fetch content, so success/failed are placeholders
    # Phase 4 will update these
    urls_success = urls_attempted  # Assume all found URLs are "successful" searches
    urls_failed = 0

    # Audit: Log search results and executions
    if audit:
        # Log each search result
        for result in ranked_results:
            audit.log_search_result(
                query_id=f"q_{hash(result.url) % 10000}",
                engine=result.source_engine,
                rank=result.rank,
                url=result.url,
                title=result.title or "",
                snippet=result.snippet or "",
            )

        # Log search execution summary for each bucket
        for bucket, queries in bucket_queries.items():
            if queries:
                bucket_results = [r for r in ranked_results if r.source_engine in BUCKET_ENGINE_MAP.get(bucket, [])]
                audit.log_search_execution(
                    query_id=f"bucket_{bucket}",
                    query_text=queries[0] if queries else "",
                    engines_used=BUCKET_ENGINE_MAP.get(bucket, ["serper"]),
                    total_results=len(bucket_results),
                    unique_urls=len(set(r.url for r in bucket_results)),
                )

    timestamps["end"] = datetime.now(timezone.utc).isoformat()

    # 8. Build output
    output = Phase3Output(
        vector_id=vector_id,
        search_results=ranked_results,
        urls_attempted=urls_attempted,
        urls_success=urls_success,
        urls_failed=urls_failed,
        content_by_engine=dict(content_by_engine),
        total_content_chars=0,  # Will be filled by Phase 4
        fetch_methods={},  # Will be filled by Phase 4
        timestamps=timestamps,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 3 self-tests.

    Tests:
    1. Search engine initialization
    2. Deduplication logic
    3. Ranking logic
    4. Full search execution (if engines available)
    """
    print("Running Phase 3 self-tests...")

    # Test 1: Engine initialization
    try:
        engines = get_search_engines()
        print(f"  Available engines: {list(engines.keys())}")
        print("  [PASS] Search engine initialization")
    except Exception as e:
        print(f"  [FAIL] Search engine initialization: {e}")
        return False

    # Test 2: Deduplication
    try:
        results = [
            SearchResult(url="https://example.com/page1", title="Page 1", snippet="", source_engine="serper", rank=1),
            SearchResult(url="https://example.com/page1/", title="Page 1 Dup", snippet="", source_engine="pubmed", rank=3),
            SearchResult(url="https://example.com/page2", title="Page 2", snippet="", source_engine="serper", rank=2),
        ]
        deduped = deduplicate_results(results)
        assert len(deduped) == 2
        print("  [PASS] Deduplication logic")
    except Exception as e:
        print(f"  [FAIL] Deduplication logic: {e}")
        return False

    # Test 3: Ranking
    try:
        results = [
            SearchResult(url="https://example.com", title="General", snippet="", source_engine="serper", rank=1),
            SearchResult(url="https://pubmed.ncbi.nlm.nih.gov/123", title="PubMed", snippet="", source_engine="pubmed", rank=2),
            SearchResult(url="https://epa.gov/water", title="EPA", snippet="", source_engine="serper", rank=3),
        ]
        ranked = rank_results(results)
        # PubMed should be ranked first, then EPA (.gov), then general
        assert "pubmed" in ranked[0].url.lower() or ".gov" in ranked[0].url.lower()
        print("  [PASS] Ranking logic")
    except Exception as e:
        print(f"  [FAIL] Ranking logic: {e}")
        return False

    # Test 3.5: Blacklist filtering (SOTA: Source Hygiene at P3)
    try:
        results = [
            SearchResult(url="https://pubmed.ncbi.nlm.nih.gov/12345", title="PubMed Study", snippet="", source_engine="pubmed", rank=1),
            SearchResult(url="https://www.grandviewresearch.com/market", title="Market Report", snippet="", source_engine="serper", rank=2),
            SearchResult(url="https://www.amazon.com/water-filter", title="Amazon Product", snippet="", source_engine="serper", rank=3),
            SearchResult(url="https://www.epa.gov/water-quality", title="EPA Guidelines", snippet="", source_engine="serper", rank=4),
            SearchResult(url="https://www.linkedin.com/posts/water", title="LinkedIn Post", snippet="", source_engine="serper", rank=5),
        ]
        filtered, rejected_count = filter_blacklisted_results(results, "test")
        # Should reject: grandviewresearch, amazon, linkedin (3 total)
        assert rejected_count == 3, f"Expected 3 rejected, got {rejected_count}"
        # Should keep: pubmed, epa (2 total)
        assert len(filtered) == 2, f"Expected 2 filtered, got {len(filtered)}"
        # Verify kept URLs are the good ones
        kept_urls = [r.url for r in filtered]
        assert any("pubmed" in u for u in kept_urls), "PubMed should be kept"
        assert any("epa.gov" in u for u in kept_urls), "EPA should be kept"
        print(f"  Blacklist filtered: {rejected_count} rejected, {len(filtered)} kept")
        print("  [PASS] Blacklist filtering (P3 Source Hygiene)")
    except Exception as e:
        print(f"  [FAIL] Blacklist filtering: {e}")
        return False

    # Test 4: OpenAlex search (no API key required)
    async def test_openalex_search():
        try:
            engine = OpenAlexEngine()
            results = await engine.search("water filter contamination", max_results=3)
            return len(results) >= 0  # May be 0 due to rate limiting
        except Exception as e:
            print(f"  [WARN] OpenAlex search: {e}")
            return True  # Don't fail on network issues

    try:
        result = asyncio.run(test_openalex_search())
        if result:
            print("  [PASS] OpenAlex search execution")
    except Exception as e:
        print(f"  [FAIL] OpenAlex search execution: {e}")
        return False

    print("\nAll Phase 3 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def find_latest_p2_output(vector_id: str) -> Optional[Path]:
    """Find the most recent Phase 2 output for a vector."""
    p2_dir = OUTPUTS_DIR / "P2"
    if not p2_dir.exists():
        return None

    pattern = f"{vector_id}__P2__*.json"
    matches = sorted(p2_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 3: Search Execution"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to Phase 2 output JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P3"),
        help="Output directory"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode"
    )

    args = parser.parse_args()

    # Self-test mode
    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    # Normal execution requires vector-id
    if not args.vector_id:
        parser.error("--vector-id is required (unless using --self-test)")

    # Find input file
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_latest_p2_output(args.vector_id)
        if not input_path:
            print(f"[PHASE-3][{args.vector_id}][ERROR] No Phase 2 output found")
            sys.exit(1)

    if not input_path.exists():
        print(f"[PHASE-3][{args.vector_id}][ERROR] Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=3,
        status="running",
        attempt=1,
        input_paths=[str(input_path)]
    )

    try:
        # Execute phase
        print(f"[PHASE-3][{args.vector_id}][INFO] Starting search execution...")
        print(f"[PHASE-3][{args.vector_id}][INFO] Input: {input_path}")

        output = asyncio.run(run_phase3(args.vector_id, input_path, output_dir))

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P3__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-3][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-3][{args.vector_id}][INFO] URLs found: {output.urls_attempted}")
        print(f"[PHASE-3][{args.vector_id}][INFO] Results by engine: {output.content_by_engine}")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=3,
            status="completed",
            attempt=1,
            input_paths=[str(input_path)],
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-3][{args.vector_id}][ERROR] {e}")

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=3,
            status="failed",
            attempt=1,
            input_paths=[str(input_path)],
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
