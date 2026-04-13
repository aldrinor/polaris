"""
Search agent for polaris graph.

Executes web and academic searches using the battle-tested tools
from src/agents/search_agent.py. Includes query amplification (Change 2)
and DuckDuckGo fallback (Change 6) for maximum coverage.
FIX-A5: Exa neural search for semantic diversity.
FIX-D4: Prefer S2 openAccessPdf URL over landing page.
"""

import asyncio
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from dotenv import load_dotenv

from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.memory.search_cache import (
    get_cached_results,
    cache_results,
)
from src.polaris_graph.memory.content_cache import (
    cache_content,
    extract_readability_html,
)
from src.polaris_graph.state import (
    ResearchState,
    WEB_CONCURRENCY,
    ACADEMIC_CONCURRENCY,
    WEB_RESULTS_PER_QUERY,
    ACADEMIC_RESULTS_PER_QUERY,
    MAX_ACADEMIC_PAGES,
    PG_AMPLIFICATION_ENABLED,
    PG_AMPLIFICATION_VARIANTS,
    PG_ACADEMIC_QUERY_CAP,
    PG_MAX_TOTAL_ACADEMIC,
    PG_CITATION_CHASE_ENABLED,
    PG_CITATION_CHASE_MAX,
    PG_CITATION_CHASE_MIN_RELEVANCE,
    PG_EXA_ENABLED,
    PG_EXA_QUERIES_PER_VECTOR,
    PG_EXA_RESULTS_PER_QUERY,
    PG_EXA_SEARCH_TYPE,
    PG_EXA_CATEGORY,
    PG_EXA_EXCLUDE_DOMAINS,
    PG_EXA_HIGHLIGHTS_SENTENCES,
    PG_EXA_HIGHLIGHTS_PER_URL,
    PG_EXA_BUDGET_USD,
    PG_EXA_COST_PER_SEARCH,
    PG_EXA_COST_PER_CONTENT,
    PG_ADAPTIVE_SEARCH_ENABLED,
    PG_SEARCH_ROUNDS,
    PG_INITIAL_QUERY_PCT,
    PG_REFINEMENT_QUERIES,
    PG_REFINER_MAX_TOKENS,
    PG_AGENTIC_SEARCH_ENABLED,
    PG_AGENTIC_MAX_ROUNDS,
    PG_AGENTIC_MAX_QUERIES,
    PG_AGENTIC_MAX_TIME_SECONDS,
    PG_AGENTIC_QUERIES_PER_ROUND,
    PG_AGENTIC_WEB_PER_ROUND,
    PG_AGENTIC_ACADEMIC_PER_ROUND,
    PG_AGENTIC_EXA_PER_ROUND,
    PG_AGENTIC_CONVERGENCE_URL_OVERLAP,
    PG_AGENTIC_CONVERGENCE_THEME_SATURATION,
    PG_AGENTIC_CONVERGENCE_WINDOW,
    PG_AGENTIC_MIN_ROUNDS,
    PG_AGENTIC_REFINER_MAX_TOKENS,
    PG_AGENTIC_CONTENT_READING_ENABLED,
    PG_AGENTIC_PAGES_PER_ROUND,
    PG_AGENTIC_FETCH_TIMEOUT,
    PG_AGENTIC_PAGE_CONTENT_CAP,
    PG_AGENTIC_SUMMARY_MAX_TOKENS,
    PG_AGENTIC_MAX_NOTEBOOK_ENTRIES,
    PG_AGENTIC_KNOWLEDGE_SATURATION_PAGES,
    PG_AGENTIC_MIN_NEW_NOTES_PER_ROUND,
    PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT,
    PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS,
    STORM_PERSPECTIVES,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Thread pool for running sync search tools
_executor = ThreadPoolExecutor(max_workers=WEB_CONCURRENCY + ACADEMIC_CONCURRENCY)

# Module-level Exa budget tracker
# FIX-C7: Must be reset per-vector via reset_exa_budget() to prevent
# cost accumulation across vectors in the same process.
_exa_session_cost: float = 0.0
_exa_session_searches: int = 0


def reset_exa_budget() -> None:
    """FIX-C7: Reset Exa budget tracking for a new vector run."""
    global _exa_session_cost, _exa_session_searches
    _exa_session_cost = 0.0
    _exa_session_searches = 0


def _compute_perspective_distribution(
    evidence: list[dict],
) -> tuple[dict, list[str]]:
    """RC-7: Compute Shannon entropy and identify underrepresented perspectives.

    Returns:
        (distribution_info, underrepresented_perspectives) where:
        - distribution_info: {"entropy": float, "counts": {perspective: count}}
        - underrepresented_perspectives: perspectives with < min_pct coverage
    """
    import math
    from collections import Counter

    min_pct = float(os.getenv("PG_V3_MIN_PERSPECTIVE_PCT", "0.10"))

    perspectives = [e.get("perspective", "Unknown") for e in evidence]
    counts = Counter(perspectives)
    total = sum(counts.values())

    if total == 0:
        return {"entropy": 0.0, "counts": {}}, list(STORM_PERSPECTIVES)

    # Shannon entropy
    entropy = -sum(
        (c / total) * math.log2(c / total)
        for c in counts.values() if c > 0
    )
    max_entropy = math.log2(len(STORM_PERSPECTIVES)) if STORM_PERSPECTIVES else 1.0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

    # Underrepresented: below min_pct of total
    underrepresented = [
        p for p in STORM_PERSPECTIVES
        if counts.get(p, 0) / max(total, 1) < min_pct
    ]

    return {
        "entropy": round(normalized_entropy, 3),
        "counts": dict(counts),
    }, underrepresented



def _import_search_tools():
    """Import search tools from existing infrastructure."""
    from src.agents.search_agent import web_search, academic_search

    return web_search, academic_search


# FIX-047-K11: OpenAlex as primary academic search provider.
# T047 audit: S2 returned 0 academic results (broken API key or rate limit).
# OpenAlex has 474M+ works, 100 RPS rate limit, free API key.
PG_OPENALEX_ENABLED = os.getenv("PG_OPENALEX_ENABLED", "1") == "1"
PG_OPENALEX_EMAIL = os.getenv("PG_OPENALEX_EMAIL", "polaris@research.local")
PG_OPENALEX_MAX_PER_QUERY = int(os.getenv("PG_OPENALEX_MAX_PER_QUERY", "10"))


def _search_openalex(query: str, max_results: int = 10) -> list[dict]:
    """FIX-047-K11: Search OpenAlex for academic papers.

    OpenAlex is a free, open alternative to Semantic Scholar with 474M+ works.
    Uses the REST API directly (no pyalex dependency required).

    Returns list of dicts matching the polaris graph search result format:
    {url, title, snippet, source_type, year, authors, venue, doi, ...}
    """
    import urllib.parse
    import urllib.request
    import json as _json

    encoded_query = urllib.parse.quote(query)
    # Use polite pool (faster) by including email
    api_url = (
        f"https://api.openalex.org/works?"
        f"search={encoded_query}"
        f"&per_page={min(max_results, 25)}"
        f"&sort=relevance_score:desc"
        f"&select=id,doi,title,publication_year,authorships,"
        f"primary_location,abstract_inverted_index,cited_by_count,type,"
        f"is_retracted,open_access"
        f"&mailto={PG_OPENALEX_EMAIL}"
    )

    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "POLARIS/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning(
            "[polaris graph] FIX-047-K11: OpenAlex API failed: %s",
            str(exc)[:200],
        )
        return []

    results = []
    for work in data.get("results", []):
        # Reconstruct abstract from inverted index
        abstract = ""
        inv_idx = work.get("abstract_inverted_index")
        if inv_idx and isinstance(inv_idx, dict):
            # inverted_index: {"word": [pos1, pos2, ...]}
            word_positions: list[tuple[int, str]] = []
            for word, positions in inv_idx.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions)

        # Extract authors
        authors = []
        for authorship in (work.get("authorships") or [])[:5]:
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        # Extract venue (FIX-B14: use primary_location, host_venue deprecated)
        venue = ""
        _prim_loc = work.get("primary_location") or {}
        _source = _prim_loc.get("source") or {}
        venue = _source.get("display_name", "")

        # Extract URL (prefer DOI, then landing page)
        doi = work.get("doi", "")
        url = doi if doi else work.get("id", "")
        primary_loc = work.get("primary_location") or {}
        if primary_loc.get("pdf_url"):
            url = primary_loc["pdf_url"]
        elif primary_loc.get("landing_page_url"):
            url = primary_loc["landing_page_url"]

        title = work.get("title", "")
        if not title:
            continue

        results.append({
            "url": url,
            "title": title,
            "snippet": abstract[:500] if abstract else title,
            "source_type": "academic",
            "year": work.get("publication_year"),
            "authors": authors,
            "venue": venue,
            "doi": doi.replace("https://doi.org/", "") if doi else "",
            "citation_count": work.get("cited_by_count", 0),
            "openalex_id": work.get("id", ""),
        })

    return results[:max_results]


def _import_ddg_search():
    """Import DuckDuckGo fallback search."""
    from src.agents.search_agent import _duckduckgo_search

    return _duckduckgo_search


def _import_amplifier():
    """Import query amplifier from main pipeline."""
    from src.search.query_amplifier import amplify_queries

    return amplify_queries


async def execute_searches(
    state: ResearchState,
    client=None,
) -> dict:
    """
    Execute all web and academic searches in parallel.

    Returns state update with web_results and academic_results.
    """
    sub_queries = state["sub_queries"]
    region = state["region"]

    if not sub_queries:
        logger.warning("[polaris graph] No sub-queries to search")
        return {"web_results": [], "academic_results": []}

    # Agentic search loop: when enabled, replaces the static batch pipeline
    if PG_AGENTIC_SEARCH_ENABLED and client:
        return await execute_agentic_search(state, client)

    web_search_fn, academic_search_fn = _import_search_tools()

    # Change 2: Query amplification — expand queries for broader web coverage
    if PG_AMPLIFICATION_ENABLED:
        try:
            amplify_fn = _import_amplifier()
            original_count = len(sub_queries)
            amplified = amplify_fn(sub_queries, region=region)
            # Cap amplified queries to prevent explosion
            max_amplified = original_count * PG_AMPLIFICATION_VARIANTS
            web_queries = amplified[:max_amplified]
            logger.info(
                "[polaris graph] Query amplification: %d -> %d queries "
                "(cap=%d, variants=%d)",
                original_count,
                len(web_queries),
                max_amplified,
                PG_AMPLIFICATION_VARIANTS,
            )
            # OBS-3: Trace query amplification (WAVE-2.4: include full query strings)
            tracer = get_tracer()
            if tracer:
                tracer.query("search", "amplified", web_queries,
                    queries=[q for q in web_queries])
        except Exception as exc:
            logger.warning(
                "[polaris graph] Amplification failed: %s — using original queries",
                str(exc)[:200],
            )
            web_queries = sub_queries
    else:
        web_queries = sub_queries

    # Academic: use original queries (precise terminology), capped
    academic_queries = sub_queries[:PG_ACADEMIC_QUERY_CAP]

    logger.info(
        "[polaris graph] Searching: %d web queries (concurrency=%d), "
        "%d academic queries (concurrency=%d)",
        len(web_queries),
        WEB_CONCURRENCY,
        len(academic_queries),
        ACADEMIC_CONCURRENCY,
    )

    # FIX-PARALLEL: Run web, academic, and Exa searches in parallel.
    # They hit different APIs (Serper, S2, Exa) so no rate-limit conflict.
    # DDG fallback and citation chase remain sequential (conditional on results).
    logger.info(
        "[polaris graph] FIX-PARALLEL: Launching web + academic + exa "
        "searches in parallel"
    )

    web_task = asyncio.create_task(
        _adaptive_web_search(
            web_search_fn, web_queries, region,
            client=client,
            original_query=state["original_query"],
        )
    )
    academic_task = asyncio.create_task(
        _run_academic_searches(academic_search_fn, academic_queries)
    )
    exa_task = asyncio.create_task(
        _run_exa_searches(sub_queries)
    )

    # Gather all three — return_exceptions so one failure doesn't kill others
    web_result, academic_result, exa_result = await asyncio.gather(
        web_task, academic_task, exa_task, return_exceptions=True,
    )

    # Handle web results
    if isinstance(web_result, Exception):
        logger.error(
            "[polaris graph] FIX-PARALLEL: Web search failed: %s",
            str(web_result)[:200],
        )
        web_results = []
    else:
        web_results = web_result

    # Handle academic results
    if isinstance(academic_result, Exception):
        logger.error(
            "[polaris graph] FIX-PARALLEL: Academic search failed: %s",
            str(academic_result)[:200],
        )
        academic_results = []
    else:
        academic_results = academic_result

    # Handle Exa results
    if isinstance(exa_result, Exception):
        logger.warning(
            "[polaris graph] FIX-PARALLEL: Exa search failed: %s",
            str(exa_result)[:200],
        )
    elif exa_result:
        web_results.extend(exa_result)

    # Change 6: DuckDuckGo fallback for zero-result queries (sequential, conditional)
    web_results = await _run_ddg_fallback_for_zeros(
        web_queries, web_results, region
    )

    # FIX-306: Citation chasing — follow references from top academic papers
    # IMP-3: Pass query for embedding-based relevance filtering
    # Must run after academic search completes (needs paper IDs)
    if PG_CITATION_CHASE_ENABLED and academic_results:
        chased = await _chase_citations(
            academic_results, query=state["original_query"]
        )
        if chased:
            academic_results.extend(chased)

    # Deduplicate by URL
    web_results = _deduplicate_results(web_results, key="url")
    academic_results = _deduplicate_results(academic_results, key="url")

    logger.info(
        "[polaris graph] Search complete: %d web results, %d academic results",
        len(web_results),
        len(academic_results),
    )

    return {
        "web_results": web_results,
        "academic_results": academic_results,
        "status": "analyzing",
    }


async def _run_web_searches(
    search_fn,
    queries: list[str],
    region: str,
) -> list[dict]:
    """Run web searches with concurrency control."""
    semaphore = asyncio.Semaphore(WEB_CONCURRENCY)
    results: list[dict] = []
    loop = asyncio.get_event_loop()

    async def _search(query: str):
        async with semaphore:
            # AREA-5: Check search cache before API call
            cached = await get_cached_results(query, "serper")
            if cached is not None:
                for r in cached:
                    r["search_query"] = query
                    r["source_type"] = "web"
                logger.debug(
                    "[polaris graph] AREA-5: Search cache hit for '%s' (%d results)",
                    query[:50], len(cached),
                )
                # WAVE-2.2: Trace cache hit
                tracer = get_tracer()
                if tracer:
                    tracer.search_result("search", "serper", query, len(cached), cached=True)
                return cached

            try:
                # web_search is sync, run in thread pool
                batch = await loop.run_in_executor(
                    _executor,
                    lambda: search_fn.invoke({
                        "query": query,
                        "max_results": WEB_RESULTS_PER_QUERY,
                        "region": region,
                    }),
                )
                if isinstance(batch, list):
                    for r in batch:
                        r["search_query"] = query
                        r["source_type"] = "web"
                    # AREA-5: Cache successful search results
                    await cache_results(query, batch, "serper")
                    # OBS-3: Trace per-query web results (WAVE-2.2: full URLs/titles/snippets)
                    tracer = get_tracer()
                    if tracer:
                        tracer.search_result("search", "serper", query, len(batch),
                            urls=[r.get("url", "") for r in batch[:10]],
                            titles=[r.get("title", "") for r in batch[:10]],
                            snippets=[r.get("snippet", "") for r in batch[:10]])
                    return batch
            except Exception as exc:
                logger.warning(
                    "[polaris graph] Web search failed for '%s': %s",
                    query[:50],
                    str(exc)[:100],
                )
            return []

    tasks = [_search(q) for q in queries]
    batch_results = await asyncio.gather(*tasks)

    for batch in batch_results:
        results.extend(batch)

    return results



# FIX-CITE-3/S1: Synonym expansion for academic topic overlap.
# The stem-only approach rejected 926/926 papers because "time-restricted
# eating", "caloric restriction", "metabolic syndrome" have zero stem overlap
# with "intermittent fasting". These synonym sets ensure semantically
# equivalent research terms are recognized as matching.
_SYNONYM_SETS: list[frozenset[str]] = [
    frozenset(["fast", "eat", "diet", "feed", "nourish", "calor", "restrict"]),
    frozenset(["intermitt", "time-restrict", "period", "cycl", "alternat"]),
    frozenset(["metabol", "glycem", "insulin", "glucos", "lipid", "cholesterol"]),
    frozenset(["cardiovascular", "cardiac", "heart", "coronar", "vascular"]),
    frozenset(["obes", "overweight", "adipos", "weight", "body mass", "bmi"]),
    frozenset(["mortal", "death", "surviv", "longev"]),
    frozenset(["random", "clinical trial", "rct", "controlled trial"]),
    frozenset(["meta-analys", "systematic review", "umbrella review"]),
    frozenset(["inflammat", "cytokine", "crp", "il-6", "tnf"]),
    frozenset(["blood pressur", "hypertens", "systolic", "diastolic"]),
]


def _expand_with_synonyms(stems: set[str]) -> set[str]:
    """Expand a set of stems with synonyms from _SYNONYM_SETS.

    Uses minimum 5-char prefix matching to avoid false positives
    (e.g., "system" matching "systematic review" via 4-char prefix).
    """
    expanded = set(stems)
    _min_prefix = 5
    for syn_set in _SYNONYM_SETS:
        matched = False
        for stem in stems:
            if matched:
                break
            for syn in syn_set:
                # Skip multi-word synonyms for substring matching
                # (prevents "system" matching "systematic review")
                is_multi_word = " " in syn
                # Require longer prefix match to avoid false positives
                prefix_len = max(_min_prefix, min(len(stem), len(syn)))
                if not is_multi_word and stem[:prefix_len] == syn[:prefix_len]:
                    expanded.update(syn_set)
                    matched = True
                    break
                # Single-word: check containment (min 5 chars to avoid noise)
                if not is_multi_word and len(syn) >= 5 and (syn in stem or stem in syn):
                    expanded.update(syn_set)
                    matched = True
                    break
                # Multi-word: require exact match in the stems set
                if is_multi_word and syn in " ".join(sorted(stems)):
                    expanded.update(syn_set)
                    matched = True
                    break
    return expanded


def _prefilter_academic_results(papers: list[dict], query: str) -> list[dict]:
    """FIX-059-E: Pre-filter academic results before evidence extraction.

    Rejects papers where:
    1. No abstract or abstract too short (<50 chars) (H-12)
    2. Zero stemmed-word overlap between query and title+abstract (BUG-5)

    FIX-CITE-3/S1: Uses synonym expansion so "time-restricted eating",
    "caloric restriction", "metabolic syndrome" etc. match queries about
    "intermittent fasting". Previously rejected 926/926 relevant papers.
    """

    def _stem_words(text: str) -> set[str]:
        """Simple stemming: lowercase, strip common suffixes."""
        words = set(re.findall(r"\b[a-z]{3,}\b", text.lower()))
        stemmed: set[str] = set()
        for w in words:
            for suffix in (
                "tion", "sion", "ment", "ness", "ing",
                "ed", "ly", "er", "est", "ies", "es", "s",
            ):
                if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                    w = w[: -len(suffix)]
                    break
            stemmed.add(w)
        return stemmed

    min_abstract_len = int(os.getenv("PG_ACADEMIC_MIN_ABSTRACT_LEN", "50"))

    query_stems = _stem_words(query)
    # FIX-CITE-3/S1: Expand query stems with synonyms
    expanded_query_stems = _expand_with_synonyms(query_stems)

    filtered: list[dict] = []
    rejected_no_abstract = 0
    rejected_no_overlap = 0

    for paper in papers:
        # H-12: Skip papers without meaningful abstracts
        # FIX-CITE-3/S4: OpenAlex uses "snippet" not "abstract". S2 uses "abstract".
        abstract = paper.get("abstract", "") or paper.get("snippet", "") or ""
        if len(abstract.strip()) < min_abstract_len:
            rejected_no_abstract += 1
            continue

        # BUG-5: Check title/abstract has topic overlap with expanded query stems.
        # FIX-CITE-3/S1: Use synonym expansion for bidirectional matching.
        # FIX-074: Lowered from 2 to 1 synonym group. The 2-group requirement
        # blocked 80-100% of academic results across TEST_068-074 because
        # OpenAlex papers about "geographic variations of fasting" only match
        # the fasting group, not a second medical group. The original false
        # positive (UAV radar) has ZERO matching groups, so 1-group suffices.
        _min_overlap = 1
        title = paper.get("title", "") or ""
        title_stems = _stem_words(title)
        expanded_title = _expand_with_synonyms(title_stems)
        overlap = expanded_query_stems & expanded_title
        # Also count how many distinct synonym sets are represented
        _overlap_groups = sum(
            1 for syn_set in _SYNONYM_SETS
            if overlap & syn_set
        )
        if _overlap_groups < _min_overlap:
            # Fallback: check abstract for overlap
            abstract_stems = _stem_words(abstract[:300])
            expanded_abstract = _expand_with_synonyms(abstract_stems)
            abstract_overlap = expanded_query_stems & expanded_abstract
            _abs_groups = sum(
                1 for syn_set in _SYNONYM_SETS
                if abstract_overlap & syn_set
            )
            if _abs_groups < _min_overlap:
                rejected_no_overlap += 1
                continue

        filtered.append(paper)

    total_rejected = rejected_no_abstract + rejected_no_overlap
    if total_rejected > 0:
        logger.info(
            "[polaris graph] FIX-059-E: Pre-filtered %d/%d academic results "
            "(no_abstract=%d, no_overlap=%d)",
            total_rejected,
            len(papers),
            rejected_no_abstract,
            rejected_no_overlap,
        )

    return filtered


async def _run_academic_searches(
    search_fn,
    queries: list[str],
) -> list[dict]:
    """Run academic searches with OpenAlex primary + S2 fallback.

    FIX-047-K11: T047 audit found S2 returned 0 results (broken). OpenAlex
    is tried first (474M works, 100 RPS). S2 is fallback if OpenAlex returns 0.
    """
    results: list[dict] = []
    loop = asyncio.get_event_loop()
    openalex_total = 0
    s2_total = 0

    for i, query in enumerate(queries):
        if len(results) >= PG_MAX_TOTAL_ACADEMIC:
            logger.info(
                "[polaris graph] Academic cap reached (%d results), "
                "skipping remaining %d queries",
                len(results),
                len(queries) - i,
            )
            break

        # AREA-5: Check search cache before API call
        cached = await get_cached_results(query, "s2")
        if cached is not None:
            for r in cached:
                r["search_query"] = query
                r["source_type"] = "academic"
            results.extend(cached)
            logger.debug(
                "[polaris graph] AREA-5: Academic cache hit for '%s' (%d results)",
                query[:50], len(cached),
            )
            # WAVE-2.2: Trace academic cache hit
            tracer = get_tracer()
            if tracer:
                tracer.search_result("search", "s2", query, len(cached), cached=True)
            continue

        batch = []

        # FIX-047-K11: Try OpenAlex first (primary academic search)
        if PG_OPENALEX_ENABLED:
            try:
                oa_batch = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        lambda q=query: _search_openalex(q, PG_OPENALEX_MAX_PER_QUERY),
                    ),
                    timeout=30.0,
                )
                if isinstance(oa_batch, list) and oa_batch:
                    batch.extend(oa_batch)
                    openalex_total += len(oa_batch)
                    logger.info(
                        "[polaris graph] FIX-047-K11: OpenAlex %d/%d: '%s' -> %d results",
                        i + 1, len(queries), query[:50], len(oa_batch),
                    )
                    # WAVE-2.2: Per-query OpenAlex trace with URLs/titles
                    tracer = get_tracer()
                    if tracer:
                        tracer.search_result("search", "openalex", query, len(oa_batch),
                            urls=[r.get("url", "") for r in oa_batch[:10]],
                            titles=[r.get("title", "") for r in oa_batch[:10]],
                            years=[r.get("year", 0) for r in oa_batch[:10]],
                            citation_counts=[r.get("citationCount", 0) for r in oa_batch[:10]])
            except asyncio.TimeoutError:
                logger.warning(
                    "[polaris graph] FIX-047-K11: OpenAlex timed out for '%s'",
                    query[:50],
                )
            except Exception as exc:
                logger.warning(
                    "[polaris graph] FIX-047-K11: OpenAlex failed for '%s': %s",
                    query[:50], str(exc)[:100],
                )

        # PL: S2 runs ALONGSIDE OpenAlex, not as fallback.
        # S2 returns 51 results for IF queries (tested directly) but was silenced
        # because OpenAlex always returns "something" (even off-topic garbage).
        if os.getenv("PG_S2_PARALLEL", "1") == "1" or not batch:
            try:
                s2_batch = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        lambda q=query: search_fn.invoke({
                            "query": q,
                            "max_results": ACADEMIC_RESULTS_PER_QUERY,
                        }),
                    ),
                    timeout=45.0,
                )
                if isinstance(s2_batch, list):
                    batch.extend(s2_batch)
                    s2_total += len(s2_batch)
                    logger.info(
                        "[polaris graph] Academic S2 %d/%d: '%s' -> %d results",
                        i + 1, len(queries), query[:50], len(s2_batch),
                    )
                    # WAVE-2.2: Per-query S2 trace with URLs/titles
                    tracer = get_tracer()
                    if tracer:
                        tracer.search_result("search", "s2", query, len(s2_batch),
                            urls=[r.get("url", "") for r in s2_batch[:10]],
                            titles=[r.get("title", "") for r in s2_batch[:10]],
                            years=[r.get("year", 0) for r in s2_batch[:10]])
            except asyncio.TimeoutError:
                logger.warning(
                    "[polaris graph] Academic S2 timed out for '%s'",
                    query[:50],
                )
            except Exception as exc:
                logger.warning(
                    "[polaris graph] Academic S2 failed for '%s': %s",
                    query[:50], str(exc)[:100],
                )

        if batch:
            # FIX-059-E: Pre-filter academic results before processing
            batch = _prefilter_academic_results(batch, query)
            for r in batch:
                r["search_query"] = query
                r["source_type"] = "academic"
            if batch:
                # AREA-5: Cache successful academic search results
                await cache_results(query, batch, "s2")
                results.extend(batch)
            # (WAVE-2.2: Per-query traces already emitted above for openalex/s2)

        # Rate limit: 1 request per second (S2 requirement)
        await asyncio.sleep(1.0)

    if openalex_total > 0 or s2_total > 0:
        logger.info(
            "[polaris graph] FIX-047-K11: Academic search totals: OpenAlex=%d, S2=%d",
            openalex_total, s2_total,
        )

    return results


async def _run_ddg_fallback_for_zeros(
    web_queries: list[str],
    web_results: list[dict],
    region: str,
) -> list[dict]:
    """Run DuckDuckGo fallback for queries that returned zero web results.

    Identifies queries with no results in the web_results list and retries
    them through DDG. Capped at 20 fallback queries to avoid rate limiting.
    """
    # Build set of queries that produced at least one result
    queries_with_results: set[str] = set()
    for r in web_results:
        sq = r.get("search_query", "")
        if sq:
            queries_with_results.add(sq)

    zero_result_queries = [
        q for q in web_queries if q not in queries_with_results
    ]

    if not zero_result_queries:
        return web_results

    # Cap DDG fallback queries
    ddg_queries = zero_result_queries[:20]
    logger.info(
        "[polaris graph] DDG fallback: %d/%d queries had zero results, "
        "retrying %d via DuckDuckGo",
        len(zero_result_queries),
        len(web_queries),
        len(ddg_queries),
    )

    try:
        ddg_search_fn = _import_ddg_search()
    except (ImportError, AttributeError) as exc:
        logger.warning(
            "[polaris graph] DDG fallback unavailable: %s",
            str(exc)[:100],
        )
        return web_results

    loop = asyncio.get_event_loop()
    ddg_results: list[dict] = []

    for query in ddg_queries:
        try:
            batch = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    lambda q=query: ddg_search_fn(q, max_results=10, region="us-en"),
                ),
                timeout=30.0,
            )
            if isinstance(batch, list):
                for r in batch:
                    r["search_query"] = query
                    r["source_type"] = "web"
                    r["search_engine"] = "duckduckgo"
                ddg_results.extend(batch)
                # WAVE-2.3: Per-query DDG fallback trace with URLs/titles
                tracer = get_tracer()
                if tracer:
                    tracer.search_result("search", "duckduckgo", query, len(batch),
                        fallback=True,
                        urls=[r.get("url", "") for r in batch[:10]],
                        titles=[r.get("title", "") for r in batch[:10]])
            # Brief rate limit
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(
                "[polaris graph] DDG fallback failed for '%s': %s",
                query[:50],
                str(exc)[:100],
            )

    if ddg_results:
        logger.info(
            "[polaris graph] DDG fallback: recovered %d results from %d queries",
            len(ddg_results),
            len(ddg_queries),
        )
        # WAVE-2.3: DDG fallback summary
        tracer = get_tracer()
        if tracer:
            tracer.evidence("search", "ddg_fallback_summary", len(ddg_results),
                zero_result_queries=len(zero_result_queries), retried=len(ddg_queries))
        web_results.extend(ddg_results)

    return web_results


# ---------------------------------------------------------------------------
# FIX-A5 Overhaul: Exa production-grade neural search
# ---------------------------------------------------------------------------


def _exa_check_budget(num_queries: int, results_per_query: int) -> tuple[bool, str]:
    """Check if Exa budget allows the requested queries.

    Returns (allowed, reason).
    """
    global _exa_session_cost
    search_cost = num_queries * PG_EXA_COST_PER_SEARCH
    content_cost = num_queries * results_per_query * PG_EXA_COST_PER_CONTENT
    projected_total = _exa_session_cost + search_cost + content_cost

    if projected_total > PG_EXA_BUDGET_USD:
        return False, (
            f"Exa budget exceeded: projected ${projected_total:.2f} > "
            f"${PG_EXA_BUDGET_USD:.2f} (already spent ${_exa_session_cost:.2f})"
        )
    return True, f"Exa budget OK: ${projected_total:.2f} / ${PG_EXA_BUDGET_USD:.2f}"


async def _run_serper_scholar(
    queries: list[str],
) -> list[dict]:
    """PL: Run Google Scholar search via Serper API.

    Google Scholar returns ONLY peer-reviewed papers, theses, and conference
    proceedings. This is the primary fix for source quality — Google already
    solved academic source authority, we just weren't calling the endpoint.
    """
    results: list[dict] = []

    try:
        from src.agents.search_agent import _serper_search_sync
    except ImportError:
        logger.warning("[polaris graph] _serper_search_sync not available")
        return results

    loop = asyncio.get_event_loop()
    for query in queries:
        try:
            batch = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda q=query: _serper_search_sync(q, max_results=10, search_type="scholar"),
                ),
                timeout=30.0,
            )
            if isinstance(batch, list):
                for r in batch:
                    r["source_type"] = "academic"
                    r["search_engine"] = "serper_scholar"
                results.extend(batch)
                logger.info(
                    "Serper Scholar returned %d results for: %s",
                    len(batch), query[:60],
                )
        except asyncio.TimeoutError:
            logger.warning("[polaris graph] Serper Scholar timed out for '%s'", query[:50])
        except Exception as exc:
            logger.warning("[polaris graph] Serper Scholar failed for '%s': %s", query[:50], str(exc)[:100])

    return results


async def _run_exa_searches(
    queries: list[str],
) -> list[dict]:
    """FIX-A5 Overhaul: Production-grade Exa neural search.

    Changes from original:
    - x-api-key header (Exa recommended standard)
    - type: auto (SOTA auto-routing, not just neural)
    - category: research paper (academic noise filter)
    - excludeDomains (low-quality domain filter)
    - highlights with text fallback (10x token savings)
    - Full metadata capture (publishedDate, author, score, highlights)
    - Budget tracking with per-session cost gate
    - Differentiated error handling (429 backoff, 401 break, 400 warn, 5xx retry)
    - Query cap from PG_EXA_QUERIES_PER_VECTOR (default 5)
    """
    global _exa_session_cost, _exa_session_searches

    if not PG_EXA_ENABLED:
        return []

    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return []

    import aiohttp

    # Cap queries to budget-safe limit
    exa_queries = queries[:PG_EXA_QUERIES_PER_VECTOR]

    # Budget gate: check before starting
    allowed, reason = _exa_check_budget(len(exa_queries), PG_EXA_RESULTS_PER_QUERY)
    if not allowed:
        logger.warning("[polaris graph] %s — skipping Exa searches", reason)
        return []
    logger.info("[polaris graph] Exa budget check: %s", reason)

    results: list[dict] = []
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        # FIX-CITE-3/S2: Prevent brotli encoding (aiohttp can't decode br)
        "Accept-Encoding": "gzip, deflate",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for query in exa_queries:
                # AREA-5: Check Exa search cache first
                cached = await get_cached_results(query, "exa")
                if cached is not None:
                    for r in cached:
                        r["search_query"] = query
                        r["source_type"] = "web"
                    results.extend(cached)
                    logger.info(
                        "[polaris graph] Exa cache hit for '%s' → %d results",
                        query[:50], len(cached),
                    )
                    continue

                # Per-query budget check
                allowed, _ = _exa_check_budget(1, PG_EXA_RESULTS_PER_QUERY)
                if not allowed:
                    logger.warning(
                        "[polaris graph] Exa budget exhausted mid-batch "
                        "after %d/%d queries ($%.2f spent)",
                        _exa_session_searches,
                        len(exa_queries),
                        _exa_session_cost,
                    )
                    break

                try:
                    payload: dict = {
                        "query": query,
                        "numResults": PG_EXA_RESULTS_PER_QUERY,
                        "type": PG_EXA_SEARCH_TYPE,
                        "useAutoprompt": True,
                        "contents": {
                            "highlights": {
                                "numSentences": PG_EXA_HIGHLIGHTS_SENTENCES,
                                "highlightsPerUrl": PG_EXA_HIGHLIGHTS_PER_URL,
                            },
                            "text": {"maxCharacters": 500},
                        },
                    }

                    # Add category filter if set
                    if PG_EXA_CATEGORY:
                        payload["category"] = PG_EXA_CATEGORY

                    # Add domain exclusion if set
                    if PG_EXA_EXCLUDE_DOMAINS:
                        payload["excludeDomains"] = PG_EXA_EXCLUDE_DOMAINS

                    async with session.post(
                        "https://api.exa.ai/search",
                        json=payload,
                        headers=headers,
                    ) as resp:
                        status = resp.status

                        # Differentiated error handling
                        if status == 429:
                            retry_after = resp.headers.get("Retry-After", "10")
                            logger.warning(
                                "[polaris graph] Exa 429 rate limited — "
                                "Retry-After: %s, pausing",
                                retry_after,
                            )
                            try:
                                wait_seconds = float(retry_after)
                            except (ValueError, TypeError):
                                wait_seconds = 10.0
                            await asyncio.sleep(min(wait_seconds, 30.0))
                            continue

                        if status == 401:
                            logger.error(
                                "[polaris graph] Exa 401 unauthorized — "
                                "check EXA_API_KEY. Aborting Exa searches."
                            )
                            break

                        if status == 400:
                            body = await resp.text()
                            logger.warning(
                                "[polaris graph] Exa 400 bad request for '%s': %s",
                                query[:50],
                                body[:200],
                            )
                            continue

                        if status >= 500:
                            logger.warning(
                                "[polaris graph] Exa %d server error for '%s' — retrying once",
                                status,
                                query[:50],
                            )
                            await asyncio.sleep(2.0)
                            async with session.post(
                                "https://api.exa.ai/search",
                                json=payload,
                                headers=headers,
                            ) as retry_resp:
                                if retry_resp.status != 200:
                                    logger.warning(
                                        "[polaris graph] Exa retry also failed (%d)",
                                        retry_resp.status,
                                    )
                                    continue
                                data = await retry_resp.json()
                        elif status != 200:
                            logger.warning(
                                "[polaris graph] Exa unexpected status %d for '%s'",
                                status,
                                query[:50],
                            )
                            continue
                        else:
                            data = await resp.json()

                        # Track cost
                        result_count = len(data.get("results", []))
                        _exa_session_cost += PG_EXA_COST_PER_SEARCH
                        _exa_session_cost += result_count * PG_EXA_COST_PER_CONTENT
                        _exa_session_searches += 1

                        for item in data.get("results", []):
                            # Prefer highlights over raw text (10x token savings)
                            highlights = item.get("highlights", [])
                            highlight_scores = item.get("highlightScores", [])
                            snippet = ""
                            if highlights:
                                snippet = " ".join(highlights)
                            else:
                                snippet = (item.get("text", "") or "")[:500]

                            results.append({
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "snippet": snippet,
                                "score": item.get("score", 0.5),
                                "source_type": "web",
                                "search_engine": "exa",
                                "search_query": query,
                                "exa_id": item.get("id", ""),
                                "published_date": item.get("publishedDate", ""),
                                "author": item.get("author", ""),
                                "highlights": highlights,
                                "highlight_scores": highlight_scores,
                            })

                        # AREA-5: Cache Exa results for this query
                        query_results = [
                            r for r in results if r.get("search_query") == query
                        ]
                        if query_results:
                            await cache_results(query, query_results, "exa")
                            # WAVE-2.1: Per-query Exa trace with URLs/titles/snippets/scores
                            tracer = get_tracer()
                            if tracer:
                                tracer.search_result("search", "exa", query, len(query_results),
                                    urls=[r.get("url", "") for r in query_results[:10]],
                                    titles=[r.get("title", "") for r in query_results[:10]],
                                    snippets=[r.get("text", "")[:500] for r in query_results[:10]],
                                    scores=[r.get("score", 0) for r in query_results[:10]],
                                    exa_cost=_exa_session_cost)

                    # Brief rate limit between queries
                    await asyncio.sleep(0.2)

                except Exception as exc:
                    logger.warning(
                        "[polaris graph] Exa search failed for '%s': %s",
                        query[:50],
                        str(exc)[:100],
                    )

    except Exception as exc:
        logger.warning(
            "[polaris graph] Exa search session failed: %s",
            str(exc)[:100],
        )

    if results:
        logger.info(
            "[polaris graph] Exa search: %d results from %d queries "
            "(session cost: $%.3f, searches: %d)",
            len(results),
            len(exa_queries),
            _exa_session_cost,
            _exa_session_searches,
        )
        # WAVE-2.1: Exa summary (per-query traces already emitted above)
        tracer = get_tracer()
        if tracer:
            tracer.evidence("search", "exa_summary", len(results),
                queries=len(exa_queries),
                session_cost=round(_exa_session_cost, 4),
                session_searches=_exa_session_searches)

    return results


# ---------------------------------------------------------------------------
# Adaptive Search (Phase 4 — LLM-guided multi-round web search)
# ---------------------------------------------------------------------------

async def _generate_refinement_queries(
    client,
    original_query: str,
    current_results: list[dict],
    round_number: int,
) -> list[str]:
    """Generate refinement queries based on results from previous round.

    Uses LLM to analyze top results and identify gaps, then generates
    targeted follow-up queries. Falls back to empty list on failure.
    """
    from src.polaris_graph.schemas import SearchRefinement

    if not current_results:
        return []

    # Summarize top 50 results for context
    summaries = []
    for r in current_results[:50]:
        title = r.get("title", "")
        snippet = r.get("snippet", "")[:200]
        source = r.get("search_engine", "serper")
        if title:
            summaries.append(f"[{source}] {title}: {snippet}")

    results_context = "\n".join(summaries)

    prompt = (
        f"You are a research search strategist. Analyze the search results "
        f"from round {round_number} for the query:\n\n"
        f"RESEARCH QUESTION: {original_query}\n\n"
        f"RESULTS SO FAR ({len(current_results)} total):\n{results_context}\n\n"
        f"Based on these results:\n"
        f"1. What key findings have emerged?\n"
        f"2. What perspectives or aspects are MISSING?\n"
        f"3. Generate {PG_REFINEMENT_QUERIES} follow-up search queries that would "
        f"fill the gaps and deepen coverage.\n\n"
        f"Focus on queries that find NEW information not already covered. "
        f"Consider Scientific, Regulatory, Industry, Economic, Public_Health, "
        f"Historical, Regional, Methodological, and Emerging_Trends perspectives."
    )

    try:
        result = await client.generate_structured(
            prompt=prompt,
            schema=SearchRefinement,
            max_tokens=PG_REFINER_MAX_TOKENS,
        )

        if result and hasattr(result, "refinement_queries"):
            queries = result.refinement_queries[:PG_REFINEMENT_QUERIES]
            logger.info(
                "[polaris graph] Adaptive round %d: LLM generated %d "
                "refinement queries (perspectives: %s)",
                round_number,
                len(queries),
                ", ".join(result.perspective_gaps[:3]) if result.perspective_gaps else "none identified",
            )
            # OBS-3: Trace refinement
            tracer = get_tracer()
            if tracer:
                tracer.query(
                    "search",
                    f"refinement_round_{round_number}",
                    queries,
                )
            return queries

    except Exception as exc:
        logger.warning(
            "[polaris graph] Adaptive round %d: refinement LLM failed: %s "
            "— continuing with planned queries only",
            round_number,
            str(exc)[:200],
        )

    return []


async def _adaptive_web_search(
    search_fn,
    queries: list[str],
    region: str,
    client=None,
    original_query: str = "",
) -> list[dict]:
    """Execute web searches in adaptive rounds with LLM refinement.

    Splits queries into PG_SEARCH_ROUNDS rounds. After each round (except
    the last), calls LLM to generate refinement queries based on results.
    Falls back to standard sequential execution if refinement fails.

    Args:
        search_fn: The web search function to call.
        queries: All planned web queries.
        region: Search region.
        client: OpenRouter LLM client (needed for refinement).
        original_query: The original research question.

    Returns:
        Combined results from all rounds.
    """
    if not PG_ADAPTIVE_SEARCH_ENABLED or not client:
        logger.info(
            "[polaris graph] Adaptive search disabled or no client — "
            "using standard static search"
        )
        return await _run_web_searches(search_fn, queries, region)

    total_queries = len(queries)
    if total_queries < 10:
        # Too few queries to benefit from rounds
        return await _run_web_searches(search_fn, queries, region)

    rounds = PG_SEARCH_ROUNDS
    # Split queries: first round gets PG_INITIAL_QUERY_PCT, rest split evenly
    first_round_count = max(1, int(total_queries * PG_INITIAL_QUERY_PCT))
    remaining = total_queries - first_round_count
    per_later_round = max(1, remaining // max(1, rounds - 1))

    all_results: list[dict] = []
    query_offset = 0

    for round_num in range(1, rounds + 1):
        # Determine this round's planned queries
        if round_num == 1:
            round_count = first_round_count
        elif round_num == rounds:
            # Last round: take all remaining
            round_count = total_queries - query_offset
        else:
            round_count = per_later_round

        round_queries = queries[query_offset:query_offset + round_count]
        query_offset += round_count

        # Add refinement queries from previous round (except first round)
        refinement_queries: list[str] = []
        if round_num > 1 and all_results:
            refinement_queries = await _generate_refinement_queries(
                client=client,
                original_query=original_query,
                current_results=all_results,
                round_number=round_num - 1,
            )
            if refinement_queries:
                round_queries = round_queries + refinement_queries

        logger.info(
            "[polaris graph] Adaptive round %d/%d: %d planned + %d refined = %d queries",
            round_num,
            rounds,
            round_count,
            len(refinement_queries),
            len(round_queries),
        )

        # Execute this round's searches
        round_results = await _run_web_searches(search_fn, round_queries, region)
        all_results.extend(round_results)

        logger.info(
            "[polaris graph] Adaptive round %d/%d complete: %d new results "
            "(total: %d)",
            round_num,
            rounds,
            len(round_results),
            len(all_results),
        )

    logger.info(
        "[polaris graph] Adaptive search complete: %d total results from %d rounds "
        "(%d planned + refinement queries)",
        len(all_results),
        rounds,
        total_queries,
    )

    return all_results


# ---------------------------------------------------------------------------
# Agentic Phase 2: Content-aware in-loop reading
# ---------------------------------------------------------------------------


def _strip_html_for_summary(raw: str) -> str:
    """Lightweight HTML stripping for page content before LLM summarization.

    Strips HTML tags and collapses whitespace. Not a full HTML parser —
    just enough to make raw page content readable for the LLM.
    """
    import re

    # Remove script and style blocks
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def _fetch_top_pages(
    results: list[dict],
    already_fetched: set[str],
    max_pages: int,
    per_page_timeout: float,
) -> list[dict]:
    """Fetch top N pages from search results for in-loop comprehension.

    Selects top URLs not already fetched, skips blocked sources,
    fetches via AccessBypass with per-page timeout, truncates content.
    A1.1: Captures raw HTML and readability HTML, caches via content_cache.
    Returns list of {"url", "title", "content"} dicts.
    """
    from src.tools.access_bypass import AccessBypass
    from src.polaris_graph.agents.analyzer import _get_domain_authority

    # Authority gate threshold for pre-fetch filtering. Replaces the old
    # _is_blocked_source check (removed 2026-04-12). Sources scoring below
    # this are skipped before any fetch attempt. Set permissively (0.3) —
    # synthesis stage gates stricter downstream.
    _auth_gate = float(os.getenv("PG_AUTHORITY_GATE", "0.3"))

    # Select candidate URLs
    candidates = []
    for r in results:
        url = r.get("url", "")
        if not url or url in already_fetched:
            continue
        if _get_domain_authority(url) < _auth_gate:
            continue
        candidates.append({"url": url, "title": r.get("title", "")})
        if len(candidates) >= max_pages:
            break

    if not candidates:
        return []

    bypass = AccessBypass()

    async def _fetch_one(candidate: dict) -> dict:
        url = candidate["url"]
        try:
            result = await asyncio.wait_for(
                bypass.fetch_with_bypass(url),
                timeout=per_page_timeout,
            )
            if result.success and result.content:
                # A1.1: Capture raw HTML before stripping for cache storage
                raw_html = result.content
                readability_html = extract_readability_html(raw_html)

                content = _strip_html_for_summary(result.content)
                content = content[:PG_AGENTIC_PAGE_CONTENT_CAP]
                if len(content.strip()) > 100:
                    # A1.1: Cache content with raw HTML and readability HTML
                    await cache_content(
                        url,
                        content,
                        title=candidate["title"],
                        fetch_method="bypass_agentic",
                        raw_html=raw_html,
                        readability_html=readability_html,
                    )
                    return {
                        "url": url,
                        "title": candidate["title"],
                        "content": content,
                    }
        except asyncio.TimeoutError:
            logger.warning(
                "[polaris graph] Agentic page fetch timed out for %s",
                url[:60],
            )
        except Exception as exc:
            logger.warning(
                "[polaris graph] Agentic page fetch failed for %s: %s",
                url[:60], str(exc)[:100],
            )
        return {}

    # Fetch concurrently
    tasks = [_fetch_one(c) for c in candidates]
    results_raw = await asyncio.gather(*tasks)

    pages = [r for r in results_raw if r]

    if pages:
        logger.info(
            "[polaris graph] Agentic content fetch: %d/%d pages fetched",
            len(pages), len(candidates),
        )

    return pages


async def _summarize_pages(
    client,
    pages: list[dict],
    query: str,
    max_tokens: int,
) -> list[dict]:
    """Summarize fetched pages into research notes via a single batched LLM call.

    Returns list of PageResearchNote dicts with summary, perspectives, key_facts.
    Falls back to first-500-char truncation as summary if LLM fails.
    """
    from src.polaris_graph.schemas import PageSummaryBatch

    if not pages:
        return []

    # Build page content block (capped to avoid context overflow)
    page_blocks = []
    total_chars = 0
    for p in pages:
        content = p.get("content", "")
        block = (
            f"--- PAGE: {p.get('title', 'Untitled')} ---\n"
            f"URL: {p.get('url', '')}\n"
            f"CONTENT:\n{content}\n"  # Already capped in _fetch_top_pages()
        )
        total_chars += len(block)
        if total_chars > 120000:  # ~40K tokens (within model context window)
            break
        page_blocks.append(block)

    pages_context = "\n".join(page_blocks)

    prompt = (
        f"You are a research analyst reading web pages for a deep research project.\n\n"
        f"RESEARCH QUESTION: {query}\n\n"
        f"Read the following {len(page_blocks)} pages and create a research note for each.\n\n"
        f"{pages_context}\n\n"
        f"For each page, provide:\n"
        f"1. A 300-400 word deep analysis focused on findings relevant to the research question, including:\n"
        f"   - Key data points, statistics, and numerical findings\n"
        f"   - Methodology or approach described (if any)\n"
        f"   - Contradictions or tensions with commonly known information\n"
        f"   - Confidence assessment for each key finding: HIGH/MEDIUM/LOW\n"
        f"2. Which STORM perspectives are covered (from: Scientific, Regulatory, Industry, "
        f"Economic, Public_Health, Historical, Regional, Methodological, Emerging_Trends)\n"
        f"3. 3-5 specific facts with numbers, dates, or named entities\n"
        f"4. Any data tables, statistics, or quantitative results (preserve exact numbers)\n"
        f"5. What new understanding this page adds\n"
    )

    try:
        result = await client.generate_structured(
            prompt=prompt,
            schema=PageSummaryBatch,
            max_tokens=max_tokens,
        )

        if result and hasattr(result, "notes") and result.notes:
            notes = [note.model_dump() for note in result.notes]
            logger.info(
                "[polaris graph] Agentic page summarization: %d notes from %d pages",
                len(notes), len(page_blocks),
            )
            return notes

    except Exception as exc:
        logger.warning(
            "[polaris graph] Agentic page summarization failed: %s — "
            "using truncated content as fallback",
            str(exc)[:200],
        )

    # Fallback: use truncated content as summary
    fallback_notes = []
    for p in pages:
        content = p.get("content", "")
        fallback_notes.append({
            "url": p.get("url", ""),
            "title": p.get("title", ""),
            "summary": content[:500],
            "perspectives": [],
            "key_facts": [],
            "knowledge_contribution": "",
        })

    return fallback_notes


# ---------------------------------------------------------------------------
# Agentic Search Loop (Gemini-style deep research)
# ---------------------------------------------------------------------------


async def execute_agentic_search(
    state: ResearchState,
    client,
) -> dict:
    """Execute searches via an agentic loop: seed -> search -> reason -> repeat.

    Each round generates targeted follow-up queries informed by prior results.
    Converges when multiple signals indicate saturation or budget is exhausted.

    Returns state update compatible with the existing graph contract:
    web_results, academic_results, status, plus agentic metadata.
    """
    web_search_fn, academic_search_fn = _import_search_tools()
    region = state["region"]
    original_query = state["original_query"]
    sub_queries = state["sub_queries"]

    all_web: list[dict] = []
    all_academic: list[dict] = []
    seen_urls: set[str] = set()
    round_summaries: list[dict] = []
    perspective_hits: dict[str, int] = {p: 0 for p in STORM_PERSPECTIVES}
    total_queries = 0
    start_time = time.monotonic()
    research_notebook: list[dict] = []
    already_fetched: set[str] = set()
    last_analysis: Optional["AgenticRoundAnalysis"] = None
    consecutive_empty_rounds = 0  # FIX: Track empty rounds to prevent degenerate loops

    tracer = get_tracer()

    for round_num in range(1, PG_AGENTIC_MAX_ROUNDS + 1):
        # Budget checks
        elapsed = time.monotonic() - start_time
        if elapsed > PG_AGENTIC_MAX_TIME_SECONDS:
            logger.info(
                "[polaris graph] Agentic loop: time budget exhausted "
                "(%.0fs > %ds) after %d rounds",
                elapsed, PG_AGENTIC_MAX_TIME_SECONDS, round_num - 1,
            )
            break
        if total_queries >= PG_AGENTIC_MAX_QUERIES:
            logger.info(
                "[polaris graph] Agentic loop: query budget exhausted "
                "(%d >= %d) after %d rounds",
                total_queries, PG_AGENTIC_MAX_QUERIES, round_num - 1,
            )
            break

        if round_num == 1:
            # Use seed queries from planner, partitioned by source preference
            web_q, acad_q, exa_q = _partition_seeds(sub_queries)
        else:
            # FIX: Wrap LLM analysis in asyncio timeout to prevent hung HTTP calls
            try:
                analysis = await asyncio.wait_for(
                    _agentic_round_analysis(
                        client=client,
                        original_query=original_query,
                        latest_results=all_web[-50:] + all_academic[-20:],
                        round_summaries=round_summaries,
                        perspective_hits=perspective_hits,
                        round_number=round_num,
                        research_notebook=research_notebook,
                    ),
                    timeout=PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[polaris graph] Agentic analysis timed out after %ds "
                    "at round %d — stopping search loop",
                    PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS, round_num,
                )
                break
            last_analysis = analysis

            if not analysis.should_continue and round_num > PG_AGENTIC_MIN_ROUNDS:
                # Check multi-signal convergence
                converged, reason = _compute_convergence(
                    round_summaries, perspective_hits, analysis,
                    research_notebook=research_notebook,
                )
                if converged:
                    logger.info(
                        "[polaris graph] Agentic loop: converged after %d rounds — %s",
                        round_num - 1, reason,
                    )
                    break

            web_q = analysis.web_queries[:PG_AGENTIC_WEB_PER_ROUND]
            acad_q = analysis.academic_queries[:PG_AGENTIC_ACADEMIC_PER_ROUND]
            exa_q = analysis.exa_queries[:PG_AGENTIC_EXA_PER_ROUND]

            # FIX: Detect degenerate loop — LLM says "continue" but returns 0 queries
            round_query_total = len(web_q) + len(acad_q) + len(exa_q)
            if round_query_total == 0:
                consecutive_empty_rounds += 1
                if consecutive_empty_rounds >= 2:
                    logger.info(
                        "[polaris graph] Agentic loop: %d consecutive empty rounds "
                        "— forcing convergence at round %d",
                        consecutive_empty_rounds, round_num,
                    )
                    break
            else:
                consecutive_empty_rounds = 0

            # Update perspective tracking from analysis
            for gap in analysis.perspective_gaps:
                gap_normalized = gap.replace(" ", "_")
                if gap_normalized in perspective_hits:
                    # Perspective identified as a gap — don't increment
                    pass

        logger.info(
            "[polaris graph] Agentic round %d/%d: %d web + %d academic + %d exa queries",
            round_num, PG_AGENTIC_MAX_ROUNDS, len(web_q), len(acad_q), len(exa_q),
        )

        if tracer:
            tracer.node_start(
                "search",
                agentic_round=round_num,
                web_queries=len(web_q),
                academic_queries=len(acad_q),
                exa_queries=len(exa_q),
            )

        # Execute per-round searches (reuses existing low-level functions)
        round_web: list[dict] = []
        round_academic: list[dict] = []

        if web_q:
            round_web = await _run_web_searches(web_search_fn, web_q, region)

        # PL: Serper Google Scholar — returns ONLY peer-reviewed papers.
        # Runs on web queries (Scholar uses same natural language queries).
        # This is the primary fix for source quality: Google already solved
        # academic source authority. We just weren't calling the endpoint.
        if web_q and os.getenv("PG_SERPER_SCHOLAR_ENABLED", "1") == "1":
            scholar_results = await _run_serper_scholar(web_q[:3])
            if scholar_results:
                round_academic.extend(scholar_results)
                logger.info(
                    "[polaris graph] PL: Serper Scholar returned %d results from %d queries",
                    len(scholar_results), min(len(web_q), 3),
                )

        if acad_q:
            round_academic.extend(await _run_academic_searches(academic_search_fn, acad_q))

        if exa_q:
            exa_results = await _run_exa_searches(exa_q)
            if exa_results:
                round_web.extend(exa_results)

        # Track new URLs for convergence detection
        round_new_urls = 0
        for r in round_web + round_academic:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                round_new_urls += 1

        # Track perspective coverage from results (keyword-based, weight=1)
        for r in round_web + round_academic:
            snippet = (r.get("snippet", "") + " " + r.get("title", "")).lower()
            for perspective in STORM_PERSPECTIVES:
                keywords = perspective.lower().replace("_", " ")
                if keywords in snippet or perspective.lower() in snippet:
                    perspective_hits[perspective] = perspective_hits.get(perspective, 0) + 1

        # Phase 2: Content-aware search — fetch, comprehend, accumulate
        round_pages: list[dict] = []
        round_notes: list[dict] = []
        if PG_AGENTIC_CONTENT_READING_ENABLED:
            round_pages = await _fetch_top_pages(
                round_web + round_academic,
                already_fetched,
                PG_AGENTIC_PAGES_PER_ROUND,
                PG_AGENTIC_FETCH_TIMEOUT,
            )
            for p in round_pages:
                already_fetched.add(p["url"])

            if round_pages:
                round_notes = await _summarize_pages(
                    client, round_pages, original_query,
                    PG_AGENTIC_SUMMARY_MAX_TOKENS,
                )
                research_notebook.extend(round_notes)
                if len(research_notebook) > PG_AGENTIC_MAX_NOTEBOOK_ENTRIES:
                    research_notebook = research_notebook[-PG_AGENTIC_MAX_NOTEBOOK_ENTRIES:]

                # Content-derived perspective tags (higher weight than keyword matching)
                for note in round_notes:
                    for perspective in note.get("perspectives", []):
                        p_normalized = perspective.replace(" ", "_")
                        if p_normalized in perspective_hits:
                            perspective_hits[p_normalized] += PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT

        # Accumulate results
        all_web.extend(round_web)
        all_academic.extend(round_academic)

        # FIX-039/B.5: Cumulative academic cap to prevent S2 noise flood
        max_total_academic = int(os.getenv("PG_MAX_TOTAL_ACADEMIC", "100"))
        if len(all_academic) > max_total_academic:
            logger.info(
                "[polaris graph] Agentic S2 cap: truncating %d → %d academic results",
                len(all_academic), max_total_academic,
            )
            all_academic = all_academic[:max_total_academic]

        round_query_count = len(web_q) + len(acad_q) + len(exa_q)
        total_queries += round_query_count

        # Build round summary for convergence tracking
        round_summary = {
            "round": round_num,
            "queries": round_query_count,
            "total_queries": total_queries,
            "web_results": len(round_web),
            "academic_results": len(round_academic),
            "new_urls": round_new_urls,
            "total_urls": len(seen_urls),
            "elapsed_seconds": time.monotonic() - start_time,
            "pages_fetched": len(round_pages),
            "pages_summarized": len(round_notes),
            "notebook_size": len(research_notebook),
            "perspectives_from_content": [p for note in round_notes for p in note.get("perspectives", [])],
            "knowledge_gaps_remaining": len(last_analysis.knowledge_gaps) if last_analysis else -1,
        }
        round_summaries.append(round_summary)

        logger.info(
            "[polaris graph] Agentic round %d complete: %d web + %d academic results "
            "(%d new URLs, %d total, %d total queries)",
            round_num, len(round_web), len(round_academic),
            round_new_urls, len(seen_urls), total_queries,
        )

        if tracer:
            tracer.node_end(
                "search",
                agentic_round=round_num,
                web_results=len(round_web),
                academic_results=len(round_academic),
                new_urls=round_new_urls,
            )

        # Emission 15: Agentic round summary
        if tracer:
            tracer.evidence("search", "agentic_round_summary", round_num,
                queries=round_query_count,
                web_results=len(round_web),
                academic_results=len(round_academic),
                new_urls=round_new_urls,
                total_urls=len(seen_urls))

    # Post-loop: DDG fallback for zero-result queries from seed round
    all_web_queries = [r.get("search_query", "") for r in all_web if r.get("search_query")]
    all_web = await _run_ddg_fallback_for_zeros(
        sub_queries, all_web, region,
    )

    # Post-loop: Citation chasing on academic results
    if PG_CITATION_CHASE_ENABLED and all_academic:
        chased = await _chase_citations(
            all_academic, query=original_query,
        )
        if chased:
            all_academic.extend(chased)

    # Deduplicate
    all_web = _deduplicate_results(all_web, key="url")
    all_academic = _deduplicate_results(all_academic, key="url")

    elapsed_total = time.monotonic() - start_time
    logger.info(
        "[polaris graph] Agentic search complete: %d rounds, %d queries, "
        "%d web + %d academic results in %.0fs",
        len(round_summaries), total_queries,
        len(all_web), len(all_academic), elapsed_total,
    )


    # Emission 16: Agentic search complete
    if tracer:
        tracer.evidence("search", "agentic_search_complete", len(round_summaries),
            total_rounds=len(round_summaries),
            total_urls=len(seen_urls),
            convergence=[{"round": rs.get("round", i), "new_urls": rs.get("new_urls", 0)}
                         for i, rs in enumerate(round_summaries)])
    return {
        "web_results": all_web,
        "academic_results": all_academic,
        "status": "analyzing",
        "agentic_search_rounds": len(round_summaries),
        "agentic_total_queries": total_queries,
        "agentic_convergence_scores": round_summaries,
        "agentic_url_accumulator": list(seen_urls)[:500],
        "agentic_perspective_coverage": perspective_hits,
        "agentic_research_notebook": research_notebook,
        "agentic_pages_fetched_count": len(already_fetched),
        "agentic_knowledge_gaps": last_analysis.knowledge_gaps if last_analysis else [],
    }


async def _agentic_round_analysis(
    client,
    original_query: str,
    latest_results: list[dict],
    round_summaries: list[dict],
    perspective_hits: dict[str, int],
    round_number: int,
    research_notebook: Optional[list[dict]] = None,
) -> "AgenticRoundAnalysis":
    """Analyze results and generate targeted follow-up queries for the next round.

    When research_notebook is populated, reasons over accumulated page summaries
    instead of raw snippets (content-aware mode). Falls back to snippets when
    notebook is empty (round 1 or content reading disabled).
    """
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    notebook = research_notebook or []

    # Build round history summary
    history_lines = []
    for rs in round_summaries[-5:]:
        pages_info = ""
        if rs.get("pages_fetched", 0) > 0:
            pages_info = f", {rs['pages_fetched']} pages read"
        history_lines.append(
            f"Round {rs['round']}: {rs['queries']} queries -> "
            f"{rs['web_results']} web + {rs['academic_results']} academic, "
            f"{rs['new_urls']} new URLs{pages_info}"
        )
    history_context = "\n".join(history_lines)

    # Identify gap perspectives
    covered = [p for p, count in perspective_hits.items() if count > 0]
    uncovered = [p for p in STORM_PERSPECTIVES if perspective_hits.get(p, 0) == 0]
    low_coverage = [
        p for p in STORM_PERSPECTIVES
        if 0 < perspective_hits.get(p, 0) < 3
    ]

    # Build knowledge context: prefer notebook summaries over raw snippets
    if notebook:
        # Content-aware mode: use accumulated research notebook
        notebook_lines = []
        for i, note in enumerate(notebook[-30:], 1):
            summary = note.get("summary", "")[:500]
            perspectives = ", ".join(note.get("perspectives", [])[:3])
            facts = "; ".join(note.get("key_facts", [])[:3])
            notebook_lines.append(
                f"[Page {i}] {note.get('title', 'Untitled')[:80]}\n"
                f"  Summary: {summary}\n"
                f"  Perspectives: {perspectives or 'none tagged'}\n"
                f"  Key facts: {facts or 'none extracted'}"
            )
        knowledge_context = "\n".join(notebook_lines)

        # Titles of new (unread) results
        new_titles = []
        for r in latest_results[:20]:
            title = r.get("title", "")
            if title:
                new_titles.append(f"- {title[:100]}")
        new_results_context = "\n".join(new_titles) if new_titles else "(no new results)"

        prompt = (
            f"You are a research search strategist conducting an agentic deep research loop.\n\n"
            f"RESEARCH QUESTION: {original_query}\n\n"
            f"ROUND HISTORY:\n{history_context}\n\n"
            f"KNOWLEDGE ACQUIRED ({len(notebook)} pages read so far):\n{knowledge_context}\n\n"
            f"NEW SEARCH RESULTS (round {round_number - 1}, titles only — not yet read):\n"
            f"{new_results_context}\n\n"
            f"PERSPECTIVE COVERAGE:\n"
            f"  Covered ({len(covered)}/{len(STORM_PERSPECTIVES)}): {', '.join(covered)}\n"
            f"  Uncovered: {', '.join(uncovered) if uncovered else 'none'}\n"
            f"  Low coverage: {', '.join(low_coverage) if low_coverage else 'none'}\n\n"
            f"Based on what has been READ:\n"
            f"1. Decompose the research question into 5-8 sub-questions.\n"
            f"   Which sub-questions have ZERO or WEAK evidence?\n"
            f"   Which sub-questions are well-answered with strong evidence?\n"
            f"2. What CONTRADICTIONS exist between sources? Flag conflicting evidence.\n"
            f"3. What specific KNOWLEDGE GAPS remain? List them as specific factual questions\n"
            f"   we CANNOT yet answer. 'none' is almost never correct for a complex research question.\n"
            f"4. Rate overall confidence in accumulated knowledge: LOW/MEDIUM/HIGH with reasoning.\n"
            f"5. Which perspectives need more coverage?\n"
            f"6. Generate 3-6 targeted WEB queries to fill those gaps.\n"
            f"7. Generate 1-3 ACADEMIC queries using precise terminology.\n"
            f"8. Optionally generate 0-1 semantic EXA queries.\n"
            f"9. Assess ANSWER COMPLETENESS for the research question:\n"
            f"   - List specific sub-questions that remain UNANSWERED.\n"
            f"   - For each answered sub-question, rate evidence strength (weak/moderate/strong).\n"
            f"   - 'expanding': Major sub-questions still unanswered.\n"
            f"   - 'narrowing': Most sub-questions answered, seeking confirmation/depth.\n"
            f"   - 'saturated': All sub-questions answered with strong evidence.\n"
            f"10. Should we continue searching?\n\n"
            f"Focus on queries that address content-level gaps, not just missing URLs."
        )
    else:
        # Snippet-based mode (round 1 or content reading disabled)
        snippets = []
        for r in latest_results[:30]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")[:200]
            source = r.get("search_engine", r.get("source_type", "web"))
            if title:
                snippets.append(f"[{source}] {title}: {snippet}")

        snippet_context = "\n".join(snippets) if snippets else "(no results from previous round)"

        prompt = (
            f"You are a research search strategist conducting an agentic deep research loop.\n\n"
            f"RESEARCH QUESTION: {original_query}\n\n"
            f"ROUND HISTORY:\n{history_context}\n\n"
            f"LATEST RESULTS (round {round_number - 1}):\n{snippet_context}\n\n"
            f"PERSPECTIVE COVERAGE:\n"
            f"  Covered ({len(covered)}/{len(STORM_PERSPECTIVES)}): {', '.join(covered)}\n"
            f"  Uncovered: {', '.join(uncovered) if uncovered else 'none'}\n"
            f"  Low coverage: {', '.join(low_coverage) if low_coverage else 'none'}\n\n"
            f"Based on this analysis:\n"
            f"1. Decompose the research question into 5-8 sub-questions.\n"
            f"   Which sub-questions have ZERO or WEAK evidence?\n"
            f"   Which sub-questions are well-answered?\n"
            f"2. Which perspectives need more coverage?\n"
            f"3. Generate 3-6 targeted WEB queries that fill gaps.\n"
            f"4. Generate 1-3 ACADEMIC queries using precise terminology.\n"
            f"5. Optionally generate 0-1 semantic EXA queries.\n"
            f"6. Assess ANSWER COMPLETENESS for the research question:\n"
            f"   - List specific sub-questions that remain UNANSWERED.\n"
            f"   - For each answered sub-question, rate evidence strength (weak/moderate/strong).\n"
            f"   - 'expanding': Major sub-questions still unanswered.\n"
            f"   - 'narrowing': Most sub-questions answered, seeking confirmation/depth.\n"
            f"   - 'saturated': All sub-questions answered with strong evidence.\n"
            f"7. Knowledge gaps = specific factual questions we CANNOT yet answer.\n"
            f"   'none' is almost never correct for a complex research question.\n"
            f"8. Should we continue searching?\n\n"
            f"Focus on queries that find NEW information not already covered."
        )

    # FIX-055: Add timeout to generate_structured and try prose extraction
    # before falling back to templates. BUG-090: LLM sometimes returns prose.
    try:
        result = await client.generate_structured(
            prompt=prompt,
            schema=AgenticRoundAnalysis,
            max_tokens=PG_AGENTIC_REFINER_MAX_TOKENS,
            timeout=PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS,
        )

        if result:
            logger.info(
                "[polaris graph] Agentic analysis round %d: assessment=%s, "
                "continue=%s, web=%d, academic=%d, exa=%d, gaps=%s",
                round_number,
                result.convergence_assessment,
                result.should_continue,
                len(result.web_queries),
                len(result.academic_queries),
                len(result.exa_queries),
                result.perspective_gaps[:3] if result.perspective_gaps else "none",
            )
            tracer = get_tracer()
            if tracer:
                tracer.llm_call(
                    "search",
                    f"agentic_analysis_round_{round_number}",
                    assessment=result.convergence_assessment,
                    should_continue=result.should_continue,
                    web_queries=len(result.web_queries),
                    academic_queries=len(result.academic_queries),
                )
            return result

    except Exception as exc:
        logger.warning(
            "[polaris graph] Agentic round %d: LLM analysis failed: %s — "
            "falling back to perspective-based queries",
            round_number, str(exc)[:200],
        )

    # Fallback: generate perspective-based template queries
    return _agentic_fallback_analysis(
        original_query, uncovered, low_coverage, round_number,
    )


def _agentic_fallback_analysis(
    query: str,
    uncovered: list[str],
    low_coverage: list[str],
    round_number: int,
) -> "AgenticRoundAnalysis":
    """Generate fallback AgenticRoundAnalysis when LLM fails.

    Generates template queries targeting uncovered and low-coverage perspectives.
    """
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # Prioritize uncovered perspectives, then low-coverage
    target_perspectives = (uncovered + low_coverage)[:PG_AGENTIC_QUERIES_PER_ROUND]

    web_queries = []
    academic_queries = []
    for p in target_perspectives:
        p_lower = p.lower().replace("_", " ")
        if p in ("Scientific", "Methodological", "Historical"):
            academic_queries.append(f"{query} {p_lower} peer-reviewed")
        else:
            web_queries.append(f"{query} {p_lower}")

    # If no gaps remain, signal convergence
    should_continue = len(uncovered) > 0 or round_number < PG_AGENTIC_MIN_ROUNDS

    return AgenticRoundAnalysis(
        key_findings=[f"Fallback round {round_number}: targeting gaps"],
        perspective_gaps=uncovered,
        web_queries=web_queries[:PG_AGENTIC_WEB_PER_ROUND],
        academic_queries=academic_queries[:PG_AGENTIC_ACADEMIC_PER_ROUND],
        exa_queries=[],
        convergence_assessment="expanding" if should_continue else "narrowing",
        should_continue=should_continue,
        reasoning=f"Fallback: {len(uncovered)} uncovered, {len(low_coverage)} low-coverage perspectives",
    )


def _compute_convergence(
    round_summaries: list[dict],
    perspective_hits: dict[str, int],
    analysis: "AgenticRoundAnalysis",
    research_notebook: Optional[list[dict]] = None,
) -> tuple[bool, str]:
    """Multi-signal convergence detection.

    Requires 2+ signals AND round >= MIN_ROUNDS to converge:
    1. URL overlap > threshold in last window
    2. Theme saturation > threshold (perspectives covered)
    3. Diminishing returns (new-URL count declining over window)
    4. LLM says "saturated"
    5. Knowledge saturation (notebook large + few/no knowledge gaps)
    6. Notebook growth stall (no new notes in recent window)

    Returns (converged, reason).
    """
    signals = []
    window = PG_AGENTIC_CONVERGENCE_WINDOW
    notebook = research_notebook or []

    if len(round_summaries) < PG_AGENTIC_MIN_ROUNDS:
        return False, f"minimum rounds not reached ({len(round_summaries)} < {PG_AGENTIC_MIN_ROUNDS})"

    # Signal 1: URL overlap — check if recent rounds produce few new URLs
    if len(round_summaries) >= window:
        recent = round_summaries[-window:]
        total_new = sum(r.get("new_urls", 0) for r in recent)
        total_results = sum(
            r.get("web_results", 0) + r.get("academic_results", 0)
            for r in recent
        )
        if total_results > 0:
            overlap_ratio = 1.0 - (total_new / max(total_results, 1))
            if overlap_ratio >= PG_AGENTIC_CONVERGENCE_URL_OVERLAP:
                signals.append(f"url_overlap={overlap_ratio:.2f}>={PG_AGENTIC_CONVERGENCE_URL_OVERLAP}")

    # Signal 2: Theme saturation — check perspective coverage
    covered_count = sum(1 for count in perspective_hits.values() if count > 0)
    saturation = covered_count / max(len(STORM_PERSPECTIVES), 1)
    if saturation >= PG_AGENTIC_CONVERGENCE_THEME_SATURATION:
        signals.append(f"theme_saturation={saturation:.2f}>={PG_AGENTIC_CONVERGENCE_THEME_SATURATION}")

    # Signal 3: Diminishing returns — new URL count declining over window
    if len(round_summaries) >= window:
        recent_new = [r.get("new_urls", 0) for r in round_summaries[-window:]]
        if len(recent_new) >= 2:
            first_half = sum(recent_new[:len(recent_new) // 2])
            second_half = sum(recent_new[len(recent_new) // 2:])
            if first_half > 0 and second_half <= first_half * 0.5:
                signals.append(f"diminishing_returns={second_half}/{first_half}")

    # Signal 4: LLM assessment
    if analysis.convergence_assessment == "saturated":
        signals.append("llm_saturated")

    # Signal 5: Knowledge saturation — notebook is large and LLM identifies few/no gaps
    if (
        len(notebook) >= PG_AGENTIC_KNOWLEDGE_SATURATION_PAGES
        and len(analysis.knowledge_gaps) <= 1
    ):
        signals.append(
            f"knowledge_saturation=notebook_{len(notebook)}_gaps_{len(analysis.knowledge_gaps)}"
        )

    # Signal 6: Notebook growth stall — no new notes in recent window
    if len(round_summaries) >= window:
        recent_notes = [
            r.get("pages_summarized", 0) for r in round_summaries[-window:]
        ]
        avg_new_notes = sum(recent_notes) / max(len(recent_notes), 1)
        if avg_new_notes < PG_AGENTIC_MIN_NEW_NOTES_PER_ROUND:
            signals.append(f"notebook_stall=avg_{avg_new_notes:.1f}<{PG_AGENTIC_MIN_NEW_NOTES_PER_ROUND}")

    # Require 2+ signals for convergence
    converged = len(signals) >= 2
    reason = ", ".join(signals) if signals else "no convergence signals"

    return converged, reason


def _partition_seeds(
    sub_queries: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Partition seed queries into web, academic, and exa buckets.

    Uses a simple heuristic: first 6 are web, next 2 are academic, last 1 is exa.
    If fewer queries, distributes proportionally.
    """
    total = len(sub_queries)
    if total == 0:
        return [], [], []

    # Proportional split: ~67% web, ~22% academic, ~11% exa
    web_count = max(1, int(total * 0.67))
    acad_count = max(1, int(total * 0.22))
    # Remaining go to exa (at least 0)
    exa_count = max(0, total - web_count - acad_count)

    web_queries = sub_queries[:web_count]
    academic_queries = sub_queries[web_count:web_count + acad_count]
    exa_queries = sub_queries[web_count + acad_count:]

    return web_queries, academic_queries, exa_queries


def _deduplicate_results(
    results: list[dict],
    key: str = "url",
) -> list[dict]:
    """Deduplicate results by URL."""
    seen: set[str] = set()
    deduped: list[dict] = []

    for r in results:
        url = r.get(key, "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(r)

    if len(results) != len(deduped):
        logger.info(
            "[polaris graph] Deduplicated: %d -> %d results",
            len(results),
            len(deduped),
        )

    return deduped


# ---------------------------------------------------------------------------
# FIX-306: Citation chasing (snowball search)
# ---------------------------------------------------------------------------

async def _chase_citations(
    academic_results: list[dict],
    query: str = "",
) -> list[dict]:
    """Follow references from top academic results to find primary sources.

    Uses Semantic Scholar /paper/{id}/references endpoint.
    IMP-3: Filters chased papers by embedding similarity to query.
    """
    s2_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if not s2_api_key:
        logger.warning("[polaris graph] Citation chasing skipped: no S2 API key")
        return []

    # Get papers with S2 paper IDs, sorted by citation count (most impactful first)
    papers_with_ids = [
        r for r in academic_results
        if r.get("paperId") or r.get("paper_id")
    ]
    papers_with_ids.sort(
        key=lambda r: r.get("citationCount", 0), reverse=True
    )

    max_chase = PG_CITATION_CHASE_MAX
    chased_results: list[dict] = []
    chased_count = 0

    for paper in papers_with_ids[:max_chase]:
        paper_id = paper.get("paperId") or paper.get("paper_id")
        if not paper_id:
            continue

        refs = await _fetch_s2_references(paper_id, s2_api_key)
        chased_results.extend(refs)
        chased_count += 1

        # Rate limit: 1 RPS
        await asyncio.sleep(1.0)

    if chased_results:
        logger.info(
            "[polaris graph] Citation chasing: recovered %d additional papers "
            "from %d seed papers",
            len(chased_results),
            chased_count,
        )
        # OBS-3: Trace citation chasing results
        tracer = get_tracer()
        if tracer:
            tracer.search_result(
                "search", "s2_citation_chase",
                f"{chased_count} seed papers",
                len(chased_results),
            )

    # FIX-059-E: Pre-filter chased papers (no abstract / zero topic overlap)
    if chased_results and query:
        chased_results = _prefilter_academic_results(chased_results, query)

    # IMP-3: Filter chased papers by embedding similarity to query
    if chased_results and query and PG_CITATION_CHASE_MIN_RELEVANCE > 0:
        chased_results = _filter_chased_by_relevance(chased_results, query)

    return chased_results


def _filter_chased_by_relevance(
    papers: list[dict],
    query: str,
) -> list[dict]:
    """IMP-3: Filter citation-chased papers by embedding similarity to query.

    Papers without abstracts or with low similarity are removed.
    Graceful fallback: returns all papers if embedding fails.
    """
    try:
        import numpy as np
        from src.utils.embedding_service import embed_text, embed_texts

        # Build text for each paper (title + abstract)
        paper_texts = []
        for p in papers:
            title = p.get("title", "")
            abstract = p.get("abstract", "") or ""
            paper_texts.append(f"{title}. {abstract}".strip())

        # Embed query and papers
        query_vec = np.array(embed_text(query))
        paper_vecs = np.array(embed_texts(paper_texts))
        similarities = paper_vecs @ query_vec

        threshold = PG_CITATION_CHASE_MIN_RELEVANCE
        filtered = []
        for i, paper in enumerate(papers):
            if similarities[i] >= threshold:
                filtered.append(paper)

        removed = len(papers) - len(filtered)
        if removed > 0:
            logger.info(
                "[polaris graph] IMP-3: Citation chase filter: %d -> %d papers "
                "(removed %d below %.2f similarity)",
                len(papers),
                len(filtered),
                removed,
                threshold,
            )

        return filtered

    except ImportError:
        logger.warning(
            "[polaris graph] IMP-3: EmbeddingService not available — "
            "keeping all chased papers"
        )
        return papers
    except Exception as exc:
        logger.warning(
            "[polaris graph] IMP-3: Citation chase filter failed: %s — "
            "keeping all papers",
            str(exc)[:200],
        )
        return papers


async def _fetch_s2_references(
    paper_id: str,
    api_key: str,
) -> list[dict]:
    """Fetch references for a paper from Semantic Scholar.

    FIX-D4: Prefers openAccessPdf URL over S2 landing page, since
    S2 landing pages are JS-rendered and 100% fail to fetch.
    """
    import aiohttp

    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references"
    params = {
        "fields": "paperId,title,abstract,url,year,authors,citationCount,venue,openAccessPdf",
        "limit": 20,
    }
    headers = {"x-api-key": api_key}

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=headers, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        references = data.get("data", [])
        results: list[dict] = []

        for ref in references:
            cited_paper = ref.get("citedPaper", {})
            if not cited_paper or not cited_paper.get("title"):
                continue

            # FIX-D4: Prefer open access PDF URL over S2 landing page
            # S2 landing pages are JS-rendered and 100% fail to fetch
            oa_pdf = cited_paper.get("openAccessPdf") or {}
            paper_url = oa_pdf.get("url", "")
            if not paper_url:
                paper_url = cited_paper.get("url", "")
            if not paper_url and cited_paper.get("paperId"):
                paper_url = (
                    f"https://api.semanticscholar.org/graph/v1/paper/"
                    f"{cited_paper['paperId']}"
                )

            authors = cited_paper.get("authors", [])
            author_names = [
                a.get("name", "") for a in authors if isinstance(a, dict)
            ]

            results.append({
                "paperId": cited_paper.get("paperId", ""),
                "title": cited_paper.get("title", ""),
                "abstract": cited_paper.get("abstract", ""),
                "url": paper_url,
                "year": cited_paper.get("year"),
                "authors": author_names,
                "citationCount": cited_paper.get("citationCount", 0),
                "venue": cited_paper.get("venue", ""),
                "source_type": "academic",
                "search_engine": "s2_citation_chase",
            })

        return results

    except Exception as exc:
        logger.warning(
            "[polaris graph] S2 reference fetch failed for %s: %s",
            paper_id[:20],
            str(exc)[:100],
        )
        return []
