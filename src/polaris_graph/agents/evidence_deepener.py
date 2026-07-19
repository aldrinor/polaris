"""
Evidence Deepener — closes the 25% gap to Gemini/ChatGPT Deep Research.

The remaining quality gap is NOT the LLM — it's the evidence depth.
Gemini writes better because it reads specific primary studies (RCTs,
landmark trials). Our pipeline only reads meta-analyses and reviews.

This module sits between `verify` and `evaluate` in the graph:
  plan → search → storm → analyze → verify → **DEEPEN** → evaluate → synthesize

Six operations:
1. Named study extraction: LLM reads evidence, extracts referenced paper names
2. S2 paper ID resolution: Convert source URLs → S2 paper IDs
3. S2 citation chasing: Follow references from meta-analyses to primary RCTs
4. S2 recommendations: Find related papers from seed IDs
5. Mechanism keyword search: Targeted queries for HOW/WHY mechanisms
6. Re-analyze: Fetch content, extract evidence, merge into pool

Feature flag: PG_EVIDENCE_DEEPENER=1 (default ON).
Only runs on first iteration (like STORM).
"""

import asyncio
import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote as _url_quote

import aiohttp
from dotenv import load_dotenv

from src.polaris_graph.llm.openrouter_client import (
    OpenRouterClient,
    get_generator_timeout_seconds,
)
from src.polaris_graph.state import ResearchState
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.settings import resolve

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (LAW VI: all from env)
# ---------------------------------------------------------------------------

PG_EVIDENCE_DEEPENER = resolve("PG_EVIDENCE_DEEPENER") == "1"

# Max papers to resolve S2 IDs for (URL→paperId)
PG_DEEPENER_MAX_RESOLVE = int(resolve("PG_DEEPENER_MAX_RESOLVE"))

# Max meta-analyses to chase citations from
PG_DEEPENER_MAX_CHASE_SEEDS = int(resolve("PG_DEEPENER_MAX_CHASE_SEEDS"))

# Max references to keep per seed paper
PG_DEEPENER_REFS_PER_SEED = int(resolve("PG_DEEPENER_REFS_PER_SEED"))

# Max papers for S2 recommendations call
PG_DEEPENER_RECOMMEND_SEEDS = int(resolve("PG_DEEPENER_RECOMMEND_SEEDS"))

# Max recommendation results to keep
PG_DEEPENER_RECOMMEND_LIMIT = int(resolve("PG_DEEPENER_RECOMMEND_LIMIT"))

# Number of mechanism keyword queries
PG_DEEPENER_MECHANISM_QUERIES = int(resolve("PG_DEEPENER_MECHANISM_QUERIES"))

# Total cap on new evidence from deepening (prevents synthesis starvation)
PG_DEEPENER_EVIDENCE_CAP = int(resolve("PG_DEEPENER_EVIDENCE_CAP"))

# Time budget for entire deepening pass (seconds)
PG_DEEPENER_TIMEOUT = int(resolve("PG_DEEPENER_TIMEOUT"))


def _resolve_llm_op_timeout(op_timeout_floor: int) -> int:
    """I-arch-004 F20 (#1255): per-operation wall for the LLM-bound deepener ops (OP-1 named-study
    extraction, OP-5 mechanism keyword-gen — both ``client.reason()`` on a reasoning-first model).

    The shared ``_OP_TIMEOUT`` (default 120s) is an HTTP/S2 clock; using it for an LLM op killed a
    reasoning-first extraction mid-reasoning (one such call can take MINUTES). Size the LLM-op wall
    off the generator budget instead:
      * env PG_DEEPENER_LLM_OP_TIMEOUT set -> that value (LAW VI override, wins outright),
      * else -> max(op_timeout_floor, LIVE generator timeout) so the default can only GROW above the
        historical 120s, never regress (honors the Gate-B slate's set_generator_timeout_seconds).
    The pass is still bounded overall by PG_DEEPENER_TIMEOUT (_over_budget checks) + the $ hard cap.
    """
    explicit = resolve("PG_DEEPENER_LLM_OP_TIMEOUT")
    if explicit is not None:
        return int(explicit)
    return max(int(op_timeout_floor), get_generator_timeout_seconds())

# S2 rate limit (requests per second) — free tier = 1, with key = 10
_S2_RPS = float(resolve("PG_S2_RPS"))
_S2_INTERVAL = 1.0 / max(_S2_RPS, 0.1)

# S2 API base
_S2_BASE = "https://api.semanticscholar.org"
_S2_FIELDS = "paperId,title,abstract,url,year,authors,citationCount,venue,openAccessPdf,fieldsOfStudy"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def deepen_evidence(
    client: OpenRouterClient,
    state: ResearchState,
) -> dict[str, Any]:
    """Run the evidence deepening loop.

    Returns a state update dict with:
      - deepened_papers: list of newly discovered papers
      - deepener_stats: metadata about the deepening pass
    """
    if not PG_EVIDENCE_DEEPENER:
        logger.info("[deepener] PG_EVIDENCE_DEEPENER=0 — skipping")
        return {}

    # Only run on first iteration
    iteration = state.get("iteration_count", 0)
    if iteration > 1:
        logger.info("[deepener] Skipping on iteration %d (runs once)", iteration)
        return {}

    evidence = state.get("evidence", [])
    query = state.get("original_query", "")
    if not evidence or not query:
        logger.warning("[deepener] No evidence or query — skipping")
        return {}

    s2_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if not s2_api_key:
        logger.warning("[deepener] No SEMANTIC_SCHOLAR_API_KEY — skipping")
        return {}

    tracer = get_tracer()
    if tracer:
        tracer.node_start("deepen_evidence", evidence_count=len(evidence))

    t0 = time.monotonic()
    stats: dict[str, Any] = {
        "named_studies_extracted": 0,
        "s2_ids_resolved": 0,
        "citations_chased": 0,
        "recommendations_found": 0,
        "mechanism_papers_found": 0,
        "pdfs_fetched": 0,
        "new_papers_total": 0,
        "elapsed_seconds": 0,
    }

    logger.info(
        "[deepener] Starting evidence deepening: %d evidence, query='%s'",
        len(evidence), query[:80],
    )

    all_new_papers: list[dict] = []
    existing_urls = {e.get("source_url", "") for e in evidence}

    # Per-operation timeout (seconds) — prevents one hung operation
    # from consuming the entire budget. E2E1 failure: OP-1 LLM retry
    # consumed 928s out of 720s budget, leaving 0 papers.
    # This HTTP/S2 clock bounds the network-bound ops (OP-2 ID resolve, OP-3 citation
    # chase, OP-4 recommendations, OP-6 PDF fetch) — those are S2/aiohttp calls, NOT LLM.
    _OP_TIMEOUT = int(resolve("PG_DEEPENER_OP_TIMEOUT"))
    # I-arch-004 F20 (#1255): see _resolve_llm_op_timeout — the LLM-bound ops (OP-1, OP-5) are
    # sized off the generator budget so a reasoning-first call is not killed by the cheap HTTP clock.
    _LLM_OP_TIMEOUT = _resolve_llm_op_timeout(_OP_TIMEOUT)

    try:
        # OP-1: Named study extraction (LLM call — can hang on retries)
        try:
            named_studies = await asyncio.wait_for(
                _extract_named_studies(client, evidence, query),
                timeout=_LLM_OP_TIMEOUT,  # F20: generator-sized (reasoning-first LLM call)
            )
        except asyncio.TimeoutError:
            logger.warning("[deepener] OP-1: Timed out after %ds", _LLM_OP_TIMEOUT)
            named_studies = []
        stats["named_studies_extracted"] = len(named_studies)
        logger.info("[deepener] OP-1: Extracted %d named studies", len(named_studies))

        # OP-2: S2 paper ID resolution from existing evidence URLs
        try:
            resolved_ids = await asyncio.wait_for(
                _resolve_s2_paper_ids(evidence, s2_api_key),
                timeout=_OP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("[deepener] OP-2: Timed out after %ds", _OP_TIMEOUT)
            resolved_ids = {}
        stats["s2_ids_resolved"] = len(resolved_ids)
        logger.info("[deepener] OP-2: Resolved %d S2 paper IDs", len(resolved_ids))

        # Time check
        if _over_budget(t0):
            logger.warning("[deepener] Time budget exceeded after OP-2")
            return _finalize(all_new_papers, stats, t0, tracer, existing_urls)

        # OP-3: S2 citation chasing from meta-analyses
        try:
            chased_papers = await asyncio.wait_for(
                _chase_citations_deep(
                    resolved_ids, named_studies, s2_api_key, query,
                ),
                timeout=_OP_TIMEOUT * 2,  # Citation chasing makes many calls
            )
        except asyncio.TimeoutError:
            logger.warning("[deepener] OP-3: Timed out after %ds", _OP_TIMEOUT * 2)
            chased_papers = []
        all_new_papers.extend(chased_papers)
        stats["citations_chased"] = len(chased_papers)
        logger.info("[deepener] OP-3: Chased %d papers from citations", len(chased_papers))

        if _over_budget(t0):
            logger.warning("[deepener] Time budget exceeded after OP-3")
            return _finalize(all_new_papers, stats, t0, tracer, existing_urls)

        # OP-4: S2 recommendations
        seed_ids = [pid for pid in list(resolved_ids.values())[:PG_DEEPENER_RECOMMEND_SEEDS] if pid]
        if seed_ids:
            try:
                recommended = await asyncio.wait_for(
                    _get_s2_recommendations(seed_ids, s2_api_key, query),
                    timeout=_OP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning("[deepener] OP-4: Timed out after %ds", _OP_TIMEOUT)
                recommended = []
            all_new_papers.extend(recommended)
            stats["recommendations_found"] = len(recommended)
            logger.info("[deepener] OP-4: Got %d recommendations", len(recommended))

        if _over_budget(t0):
            logger.warning("[deepener] Time budget exceeded after OP-4")
            return _finalize(all_new_papers, stats, t0, tracer, existing_urls)

        # OP-5: Mechanism keyword search (LLM + multiple S2 calls)
        # F20: the LLM keyword-gen leg is reasoning-first; size off the generator timeout. The
        # `+ _OP_TIMEOUT` adds back the original HTTP slack for the trailing multi-S2 calls so a
        # generator-sized run never regresses below the prior `_OP_TIMEOUT * 2` wall.
        _op5_timeout = _LLM_OP_TIMEOUT + _OP_TIMEOUT
        try:
            mechanism_papers = await asyncio.wait_for(
                _mechanism_search(client, query, s2_api_key),
                timeout=_op5_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("[deepener] OP-5: Timed out after %ds", _op5_timeout)
            mechanism_papers = []
        all_new_papers.extend(mechanism_papers)
        stats["mechanism_papers_found"] = len(mechanism_papers)
        logger.info("[deepener] OP-5: Found %d mechanism papers", len(mechanism_papers))

        # OP-6: Fetch full text for open-access papers using the
        # battle-tested access_bypass.py stack (Jina, Crawl4AI, PDF extract).
        try:
            pdf_count = await asyncio.wait_for(
                _fetch_full_text(all_new_papers),
                timeout=_OP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("[deepener] OP-6: Timed out after %ds", _OP_TIMEOUT)
            pdf_count = 0
        stats["pdfs_fetched"] = pdf_count
        logger.info("[deepener] OP-6: Fetched full text for %d papers", pdf_count)

    except asyncio.CancelledError:
        logger.warning("[deepener] Cancelled — returning partial results")
    except Exception as exc:
        logger.error("[deepener] Unexpected error: %s", str(exc)[:300])

    return _finalize(all_new_papers, stats, t0, tracer, existing_urls)


# ---------------------------------------------------------------------------
# OP-1: Named study extraction
# ---------------------------------------------------------------------------

async def _extract_named_studies(
    client: OpenRouterClient,
    evidence: list[dict],
    query: str,
) -> list[dict]:
    """Extract named studies/trials/authors from evidence statements.

    Returns list of {name, authors, context} for S2 search.
    """
    # Collect evidence text — both statements AND direct_quotes.
    # FIX-B6: statements are paraphrased claims ("ADF reduced weight by 6%")
    # which lack author references. direct_quotes contain the original text
    # ("Trepanowski et al. (2017) reported...") where regex can find names.
    statements = []
    quotes_for_regex = []
    for ev in evidence[:100]:
        stmt = ev.get("statement", "")
        if stmt:
            statements.append(stmt[:300])
        quote = ev.get("direct_quote", "")
        if quote:
            quotes_for_regex.append(quote[:300])

    if not statements:
        return []

    evidence_block = "\n".join(f"- {s}" for s in statements[:50])

    prompt = (
        f"Research query: {query}\n\n"
        f"Below are evidence statements from a literature review. Extract ALL "
        f"named studies, trials, and author references mentioned.\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"For each named study, output ONE line in this format:\n"
        f"STUDY: <first_author_last_name> | <year_if_known> | <short_description>\n\n"
        f"Examples:\n"
        f"STUDY: Trepanowski | 2017 | 12-month ADF vs daily calorie restriction RCT\n"
        f"STUDY: Varady | 2022 | meta-analysis of alternate-day fasting protocols\n"
        f"STUDY: Longo | 2016 | fasting-mimicking diet clinical trial\n\n"
        f"Output ONLY the STUDY lines. If no named studies are found, output: NONE"
    )

    try:
        result = await client.reason(
            prompt=prompt,
            effort=resolve("PG_DEEPENER_REASONING_EFFORT"),  # operator 2026-06-13: reasoning MAX
            # I-arch-003 (#1253): reason() takes the reasoning-ON branch which (pre-fix) had NO 32768
            # floor, so the old max_tokens=2000 was eaten by V4-Pro's ~17-18k reasoning tokens -> empty
            # study list -> silent snowball loss. Floored to the reasoning-first minimum; the
            # openrouter_client branch-2 floor now also backstops this, but the explicit value documents
            # intent and protects a non-reasoning-first PG_SWEEP_DEEPENER_MODEL override (LAW VI).
            max_tokens=int(os.getenv("PG_DEEPENER_EXTRACT_MAX_TOKENS", "32768")),
        )
        text = result.content.strip()

        # GLM-5 CoT stripping: if the LLM returned planning/reasoning
        # instead of STUDY: lines, strip the CoT prefix.
        # Known markers from openrouter_client.py COT-3.
        _cot_markers = [
            "1. **Analyze", "Let me analyze", "I need to extract",
            "The user wants", "Let me identify", "Looking at the evidence",
        ]
        for marker in _cot_markers:
            if text.startswith(marker):
                # Find the first STUDY: line after the CoT
                idx = text.upper().find("STUDY:")
                if idx > 0:
                    text = text[idx:]
                    logger.info("[deepener] OP-1: Stripped CoT prefix (%d chars)", idx)
                break
    except Exception as exc:
        logger.warning("[deepener] OP-1: LLM extraction failed: %s", str(exc)[:200])
        text = ""

    # Parse STUDY: lines from LLM output
    studies = _parse_study_lines(text)

    # Fallback: if LLM failed or returned CoT garbage, extract
    # "Author et al. (YYYY)" patterns directly from evidence text.
    # Zero API cost, catches most named references.
    if len(studies) < 2:
        # FIX-B6: Search direct_quotes first (contain "Author et al. (YYYY)")
        # then statements as fallback. Quotes have author references,
        # statements usually don't.
        regex_studies = _regex_extract_studies(quotes_for_regex + statements)
        # Merge without duplicates (by author last name)
        existing_authors = {s["author"].lower() for s in studies}
        for rs in regex_studies:
            if rs["author"].lower() not in existing_authors:
                studies.append(rs)
                existing_authors.add(rs["author"].lower())
        if regex_studies:
            logger.info(
                "[deepener] OP-1: Regex fallback added %d studies (total %d)",
                len(regex_studies), len(studies),
            )

    return studies


def _parse_study_lines(text: str) -> list[dict]:
    """Parse STUDY: lines from LLM output."""
    studies = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.upper().startswith("STUDY:"):
            continue
        parts = line[6:].strip().split("|")
        if len(parts) >= 2:
            author = parts[0].strip()
            year = parts[1].strip() if len(parts) > 1 else ""
            desc = parts[2].strip() if len(parts) > 2 else ""
            if author and author.upper() != "NONE":
                studies.append({
                    "author": author,
                    "year": year,
                    "description": desc,
                })
    return studies


def _regex_extract_studies(statements: list[str]) -> list[dict]:
    """Extract author references from evidence statements using regex.

    Catches patterns like:
    - "Trepanowski et al. (2017)"
    - "Varady et al., 2022"
    - "Longo and Mattson (2014)"
    - "Smith (2023) found that..."
    """
    studies = []
    seen_authors: set[str] = set()

    # Pattern 1: "Author et al. (YYYY)" or "Author et al., YYYY"
    p1 = re.compile(
        r"([A-Z][a-z]+)\s+et\s+al\.?\s*[,(]\s*(\d{4})\s*\)?",
    )
    # Pattern 2: "Author and Author (YYYY)"
    p2 = re.compile(
        r"([A-Z][a-z]+)\s+and\s+[A-Z][a-z]+\s*\(\s*(\d{4})\s*\)",
    )
    # Pattern 3: "Author (YYYY) found/showed/reported"
    p3 = re.compile(
        r"([A-Z][a-z]{2,})\s*\(\s*(\d{4})\s*\)\s*(?:found|showed|reported|demonstrated|observed)",
    )

    for stmt in statements:
        for pattern in [p1, p2, p3]:
            for match in pattern.finditer(stmt):
                author = match.group(1)
                year = match.group(2)
                if author.lower() not in seen_authors and len(author) > 2:
                    seen_authors.add(author.lower())
                    # Extract surrounding context as description
                    start = max(0, match.start() - 10)
                    end = min(len(stmt), match.end() + 60)
                    desc = stmt[start:end].strip()
                    studies.append({
                        "author": author,
                        "year": year,
                        "description": desc,
                    })

    return studies


# ---------------------------------------------------------------------------
# OP-2: S2 paper ID resolution
# ---------------------------------------------------------------------------

async def _resolve_s2_paper_ids(
    evidence: list[dict],
    api_key: str,
) -> dict[str, str]:
    """Resolve source URLs from evidence to S2 paper IDs.

    Returns {source_url: paperId} for papers that resolve.
    Only resolves academic-looking URLs (DOI, pubmed, arxiv, S2).
    """
    # Collect unique academic URLs
    academic_urls: list[str] = []
    seen = set()
    for ev in evidence:
        url = ev.get("source_url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        # Only try to resolve URLs that look academic
        if _is_academic_url(url):
            academic_urls.append(url)

    if not academic_urls:
        return {}

    # Cap resolution attempts
    urls_to_resolve = academic_urls[:PG_DEEPENER_MAX_RESOLVE]
    resolved: dict[str, str] = {}

    for url in urls_to_resolve:
        paper_id = await _resolve_single_url(url, api_key)
        if paper_id:
            resolved[url] = paper_id
        await asyncio.sleep(_S2_INTERVAL)

    return resolved


def _is_academic_url(url: str) -> bool:
    """Check if a URL is likely an academic paper (worth resolving via S2)."""
    academic_patterns = [
        "doi.org", "pubmed", "ncbi.nlm.nih.gov", "arxiv.org",
        "semanticscholar.org", "scholar.google", "pmc/articles",
        "nature.com", "science.org", "sciencedirect.com",
        "wiley.com", "springer.com", "bmj.com", "thelancet.com",
        "cell.com", "nejm.org", "jamanetwork.com", "tandfonline.com",
        "mdpi.com", "frontiersin.org", "plos.org", "biorxiv.org",
        "medrxiv.org", "cochranelibrary.com",
    ]
    url_lower = url.lower()
    return any(p in url_lower for p in academic_patterns)


async def _resolve_single_url(url: str, api_key: str) -> str:
    """Resolve a single URL to S2 paper ID.

    Tries multiple resolution strategies:
    1. DOI extraction → /paper/DOI:{doi}
    2. ArXiv ID → /paper/ARXIV:{id}
    3. PubMed ID → /paper/PMID:{id}
    4. Direct URL → /paper/URL:{url}
    """
    headers = {"x-api-key": api_key}
    timeout = aiohttp.ClientTimeout(total=15)

    # Strategy 1: Extract DOI
    doi = _extract_doi(url)
    if doi:
        paper_id = await _s2_lookup(f"DOI:{doi}", headers, timeout)
        if paper_id:
            return paper_id

    # Strategy 2: ArXiv ID
    arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", url)
    if arxiv_match:
        paper_id = await _s2_lookup(f"ARXIV:{arxiv_match.group(1)}", headers, timeout)
        if paper_id:
            return paper_id

    # Strategy 3: PubMed ID
    pmid_match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", url)
    if not pmid_match:
        pmid_match = re.search(r"ncbi\.nlm\.nih\.gov/pubmed/(\d+)", url)
    if pmid_match:
        paper_id = await _s2_lookup(f"PMID:{pmid_match.group(1)}", headers, timeout)
        if paper_id:
            return paper_id

    # Strategy 4: URL resolution (least reliable, skip for non-standard URLs)
    if any(d in url.lower() for d in ["doi.org", "semanticscholar.org"]):
        paper_id = await _s2_lookup(f"URL:{url}", headers, timeout)
        if paper_id:
            return paper_id

    return ""


def _extract_doi(url: str) -> str:
    """Extract DOI from a URL."""
    # Direct DOI URL
    doi_match = re.search(r"doi\.org/(10\.\d{4,}/[^\s?#]+)", url)
    if doi_match:
        return doi_match.group(1)
    # DOI in query params or path
    doi_match = re.search(r"(10\.\d{4,}/[A-Za-z0-9._\-/()]+)", url)
    if doi_match:
        return doi_match.group(1).rstrip(".")
    return ""


async def _s2_lookup(identifier: str, headers: dict, timeout: aiohttp.ClientTimeout) -> str:
    """Look up a paper on S2 by identifier. Returns paperId or empty string.

    URL-encodes the identifier to handle DOI slashes (10.1001/jama... → 10.1001%2Fjama...).
    Without encoding, the slash creates extra path segments → 404.
    Pattern from src/utils/source_quality.py:346.
    """
    url = f"{_S2_BASE}/graph/v1/paper/{_url_quote(identifier, safe='')}"
    params = {"fields": "paperId"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("paperId", "")
                return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# OP-3: Citation chasing (deep — from resolved meta-analyses)
# ---------------------------------------------------------------------------

async def _chase_citations_deep(
    resolved_ids: dict[str, str],
    named_studies: list[dict],
    api_key: str,
    query: str,
) -> list[dict]:
    """Chase citations from meta-analyses AND search for named studies.

    Three strategies (from legacy citation_chainer.py pattern):
    A) Backward snowball: references from resolved papers (foundational works)
    B) Forward snowball: papers citing resolved papers (newer work building on them)
    C) Author search: S2 search for named studies extracted by LLM
    """
    headers = {"x-api-key": api_key}
    timeout = aiohttp.ClientTimeout(total=30)
    all_papers: list[dict] = []
    seen_ids: set[str] = set()

    # Strategy A: Backward snowball — references from resolved papers
    seed_ids = list(resolved_ids.values())[:PG_DEEPENER_MAX_CHASE_SEEDS]
    for paper_id in seed_ids:
        if not paper_id:
            continue
        refs = await _fetch_references(paper_id, headers, timeout)
        for ref in refs[:PG_DEEPENER_REFS_PER_SEED]:
            pid = ref.get("paperId", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(ref)
        await asyncio.sleep(_S2_INTERVAL)

    # Strategy B: Forward snowball — papers citing our seeds (newer papers)
    # Capped at top 5 most-cited seeds to find the most impactful newer work
    forward_seeds = sorted(
        [(pid, url) for url, pid in resolved_ids.items() if pid],
        key=lambda x: x[0],  # paperId as tiebreaker
    )[:5]
    for paper_id, _ in forward_seeds:
        cits = await _fetch_citations(paper_id, headers, timeout)
        for cit in cits[:5]:  # Top 5 citing papers per seed
            pid = cit.get("paperId", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(cit)
        await asyncio.sleep(_S2_INTERVAL)

    # Strategy C: Author search for named studies
    for study in named_studies[:15]:
        author = study.get("author", "")
        year = study.get("year", "")
        search_q = f"{author} {query.split()[0] if query else ''}"
        if year:
            search_q += f" {year}"

        results = await _s2_search(search_q, headers, timeout, limit=3)
        for paper in results:
            pid = paper.get("paperId", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(paper)
        await asyncio.sleep(_S2_INTERVAL)

    # Filter by relevance to query
    if all_papers and query:
        all_papers = _filter_by_query_relevance(all_papers, query)

    return all_papers


async def _fetch_references(
    paper_id: str,
    headers: dict,
    timeout: aiohttp.ClientTimeout,
) -> list[dict]:
    """Fetch references for a paper from S2."""
    url = f"{_S2_BASE}/graph/v1/paper/{paper_id}/references"
    params = {
        "fields": _S2_FIELDS,
        "limit": 20,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        results = []
        for ref in data.get("data", []):
            cited = ref.get("citedPaper", {})
            if not cited or not cited.get("title"):
                continue
            results.append(_normalize_s2_paper(cited))
        return results
    except Exception as exc:
        logger.debug("[deepener] Reference fetch failed for %s: %s", paper_id[:20], str(exc)[:100])
        return []


async def _fetch_citations(
    paper_id: str,
    headers: dict,
    timeout: aiohttp.ClientTimeout,
) -> list[dict]:
    """Fetch papers that CITE this paper (forward snowballing).

    Finds newer papers building on the seed — the legacy citation_chainer
    does this via OpenAlex, we use S2 /paper/{id}/citations.
    """
    url = f"{_S2_BASE}/graph/v1/paper/{paper_id}/citations"
    params = {
        "fields": _S2_FIELDS,
        "limit": 10,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        results = []
        for cit in data.get("data", []):
            citing = cit.get("citingPaper", {})
            if not citing or not citing.get("title"):
                continue
            results.append(_normalize_s2_paper(citing))
        return results
    except Exception as exc:
        logger.debug("[deepener] Citation fetch failed for %s: %s", paper_id[:20], str(exc)[:100])
        return []


async def _s2_search(
    query: str,
    headers: dict,
    timeout: aiohttp.ClientTimeout,
    limit: int = 5,
) -> list[dict]:
    """Search S2 for papers matching a query."""
    url = f"{_S2_BASE}/graph/v1/paper/search"
    params = {
        "query": query[:200],
        "fields": _S2_FIELDS,
        "limit": limit,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        results = []
        for paper in data.get("data", []):
            if paper.get("title"):
                results.append(_normalize_s2_paper(paper))
        return results
    except Exception as exc:
        logger.debug("[deepener] S2 search failed for '%s': %s", query[:40], str(exc)[:100])
        return []


def _normalize_s2_paper(paper: dict) -> dict:
    """Normalize an S2 paper dict to our standard search result format."""
    oa_pdf = paper.get("openAccessPdf") or {}
    paper_url = oa_pdf.get("url", "")
    if not paper_url:
        paper_url = paper.get("url", "")
    if not paper_url and paper.get("paperId"):
        paper_url = f"https://www.semanticscholar.org/paper/{paper['paperId']}"

    authors = paper.get("authors", [])
    author_names = [
        a.get("name", "") for a in authors if isinstance(a, dict)
    ]

    return {
        "paperId": paper.get("paperId", ""),
        "title": paper.get("title", ""),
        "abstract": paper.get("abstract", ""),
        "url": paper_url,
        "year": paper.get("year"),
        "authors": author_names,
        "citationCount": paper.get("citationCount", 0),
        "venue": paper.get("venue", ""),
        "openAccessPdf": oa_pdf.get("url", ""),
        "fieldsOfStudy": paper.get("fieldsOfStudy", []),
        "source_type": "academic",
        "search_engine": "s2_deepener",
    }


# ---------------------------------------------------------------------------
# OP-4: S2 recommendations
# ---------------------------------------------------------------------------

async def _get_s2_recommendations(
    seed_ids: list[str],
    api_key: str,
    query: str,
) -> list[dict]:
    """Get paper recommendations from S2 based on seed papers."""
    url = f"{_S2_BASE}/recommendations/v1/papers"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=30)

    body = {
        "positivePaperIds": seed_ids,
        "fields": _S2_FIELDS,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, headers=headers, timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    logger.debug("[deepener] S2 recommendations: HTTP %d", resp.status)
                    return []
                data = await resp.json()

        papers = []
        for paper in data.get("recommendedPapers", [])[:PG_DEEPENER_RECOMMEND_LIMIT]:
            if paper.get("title"):
                papers.append(_normalize_s2_paper(paper))

        # Filter by relevance
        if papers and query:
            papers = _filter_by_query_relevance(papers, query)

        return papers
    except Exception as exc:
        logger.warning("[deepener] S2 recommendations failed: %s", str(exc)[:200])
        return []


# ---------------------------------------------------------------------------
# OP-5: Mechanism keyword search
# ---------------------------------------------------------------------------

async def _mechanism_search(
    client: OpenRouterClient,
    query: str,
    api_key: str,
) -> list[dict]:
    """Generate and execute mechanism-focused search queries.

    Finds the WHY/HOW papers that citation chasing misses —
    basic science papers on pathways, mechanisms, molecular biology.
    """
    # Generate mechanism queries via LLM
    prompt = (
        f"Research topic: {query}\n\n"
        f"Generate {PG_DEEPENER_MECHANISM_QUERIES} academic search queries "
        f"that target the BIOLOGICAL MECHANISMS and PATHWAYS underlying this topic.\n\n"
        f"Focus on:\n"
        f"- Molecular/cellular mechanisms (e.g., autophagy pathways, mTOR signaling)\n"
        f"- Physiological processes (e.g., hormonal regulation, metabolic adaptation)\n"
        f"- Dose-response relationships and thresholds\n"
        f"- Animal model studies that explain clinical findings\n\n"
        f"Output ONE query per line, no numbering, no explanation.\n"
        f"Each query should be 4-8 words, suitable for Semantic Scholar search."
    )

    try:
        result = await client.reason(
            prompt=prompt,
            effort=resolve("PG_DEEPENER_REASONING_EFFORT"),  # operator 2026-06-13: reasoning MAX
            # I-arch-003 (#1253): same reasoning-ON / no-floor land mine as _extract_named_studies — the
            # old max_tokens=500 was the MOST starved site on the live path (500 total vs ~17-18k V4-Pro
            # reasoning -> guaranteed empty -> silent fallback to deterministic mechanism queries).
            # Floored to the reasoning-first minimum (LAW VI; branch-2 floor backstops too).
            max_tokens=int(os.getenv("PG_DEEPENER_MECHANISM_MAX_TOKENS", "32768")),
        )
        text = result.content.strip()
    except Exception as exc:
        logger.warning("[deepener] OP-5: Mechanism query generation failed: %s", str(exc)[:200])
        # Fallback: generate basic mechanism queries
        text = _fallback_mechanism_queries(query)

    # Start with deterministic fallback queries (always on-topic).
    # LLM queries are stochastic — GLM-5 sometimes generates garbage
    # ("Pull Request Acceptance", "SQLite") that wastes S2 API calls.
    fallback = [q.strip() for q in _fallback_mechanism_queries(query).split("\n") if q.strip()]

    # Parse LLM queries and add only if they contain a topic word
    topic_words = set(re.findall(r"\w{4,}", query.lower()))
    llm_queries = []
    for line in text.split("\n"):
        line = line.strip().lstrip("0123456789.-) ")
        if line and len(line) > 5 and len(line.split()) <= 12:
            # Only keep LLM query if it contains at least one topic word
            line_lower = line.lower()
            if any(tw in line_lower for tw in topic_words):
                llm_queries.append(line)

    # Combine: fallback first (guaranteed on-topic), then LLM extras
    queries = fallback[:3] + llm_queries[:PG_DEEPENER_MECHANISM_QUERIES - 3]
    queries = queries[:PG_DEEPENER_MECHANISM_QUERIES]

    logger.info("[deepener] OP-5: Searching %d mechanism queries: %s",
                len(queries), [q[:50] for q in queries])

    # Execute searches
    headers = {"x-api-key": api_key}
    timeout = aiohttp.ClientTimeout(total=30)
    all_papers: list[dict] = []
    seen_ids: set[str] = set()

    for mq in queries:
        results = await _s2_search(mq, headers, timeout, limit=5)
        for paper in results:
            pid = paper.get("paperId", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(paper)
        await asyncio.sleep(_S2_INTERVAL)

    # Filter by relevance to original query — mechanism queries diverge
    # from the topic, so S2 may return off-topic papers (e.g., "Pull
    # Request Acceptance" for a fasting query). This filter catches them.
    if all_papers and query:
        all_papers = _filter_by_query_relevance(all_papers, query)

    return all_papers


def _fallback_mechanism_queries(query: str) -> str:
    """Generate basic mechanism queries when LLM fails."""
    # Extract key topic words
    words = query.lower().split()
    topic = " ".join(words[:4])
    return "\n".join([
        f"{topic} molecular mechanism pathway",
        f"{topic} cellular signaling",
        f"{topic} dose response threshold",
        f"{topic} animal model study",
        f"{topic} systematic review mechanism",
    ])


# ---------------------------------------------------------------------------
# OP-6: Full-text fetch via access_bypass.py
# ---------------------------------------------------------------------------

async def _fetch_full_text(papers: list[dict]) -> int:
    """Fetch full text for papers using the access_bypass.py stack.

    Uses the battle-tested fetch pipeline: Jina Reader, Crawl4AI,
    trafilatura, PDF extraction (PyMuPDF), direct fetch. This handles
    publisher landing pages, paywalls, and JS-rendered content that
    simple aiohttp cannot.

    Enriches each paper dict with 'full_text' field.
    Returns count of successfully fetched papers.
    """
    try:
        from src.tools.access_bypass import AccessBypass
    except ImportError:
        logger.warning("[deepener] OP-6: access_bypass not importable — skipping")
        return 0

    bypass = AccessBypass()
    fetched = 0
    max_fetch = int(resolve("PG_DEEPENER_MAX_PDF_FETCH"))

    # Prioritize papers with OA-PDF URLs, then by citation count
    fetchable = []
    for paper in papers:
        oa_url = paper.get("openAccessPdf", "")
        regular_url = paper.get("url", "")
        if oa_url or regular_url:
            fetchable.append((paper, oa_url, regular_url))
    fetchable.sort(key=lambda x: x[0].get("citationCount", 0), reverse=True)

    for paper, oa_url, regular_url in fetchable[:max_fetch]:
        # Try OA-PDF URL first, fall back to regular URL
        urls_to_try = [u for u in [oa_url, regular_url] if u]
        for url in urls_to_try:
            try:
                result = await bypass.fetch_with_bypass(url)
                if result.success and result.content and len(result.content) > 500:
                    paper["full_text"] = result.content[:25000]
                    fetched += 1
                    logger.debug(
                        "[deepener] OP-6: Fetched %d chars from %s via %s",
                        len(result.content), url[:50], result.access_method,
                    )
                    break  # Got content, skip remaining URLs
            except Exception as exc:
                logger.debug(
                    "[deepener] OP-6: Fetch failed for %s: %s",
                    url[:50], str(exc)[:100],
                )

    return fetched


# ---------------------------------------------------------------------------
# Relevance filtering
# ---------------------------------------------------------------------------

def _filter_by_query_relevance(papers: list[dict], query: str) -> list[dict]:
    """Filter papers by SEMANTIC similarity to the query.

    Primary: embedding cosine similarity (same pattern as IMP-3 in searcher.py).
    Fallback: keyword overlap with stopwords (if embeddings unavailable).

    Critical: word-level matching can't distinguish "intermittent fasting"
    from "intermittent claudication". Embedding similarity can.
    """
    if not papers:
        return papers

    threshold = float(resolve("PG_DEEPENER_RELEVANCE_THRESHOLD"))

    # Primary: embedding-based filter
    try:
        import numpy as np
        from src.utils.embedding_service import embed_text, embed_texts

        paper_texts = [
            f"{p.get('title', '')}. {p.get('abstract', '') or ''}".strip()
            for p in papers
        ]

        query_vec = np.array(embed_text(query))
        paper_vecs = np.array(embed_texts(paper_texts))
        similarities = paper_vecs @ query_vec

        filtered = [
            papers[i] for i in range(len(papers))
            if similarities[i] >= threshold
        ]

        removed = len(papers) - len(filtered)
        if removed > 0:
            logger.info(
                "[deepener] Embedding filter: %d -> %d papers "
                "(removed %d below %.2f similarity)",
                len(papers), len(filtered), removed, threshold,
            )

        if filtered:
            return filtered
        logger.warning("[deepener] Embedding filter removed ALL — keyword fallback")
    except ImportError:
        logger.info("[deepener] EmbeddingService not available — keyword fallback")
    except Exception as exc:
        logger.warning("[deepener] Embedding filter failed: %s — keyword fallback", str(exc)[:200])

    # Fallback: keyword overlap with stopwords removed
    _STOPWORDS = {
        "research", "study", "studies", "results", "analysis", "evidence",
        "clinical", "health", "effects", "outcomes", "review", "quality",
        "benefits", "risks", "impact", "findings", "data", "methods",
        "patients", "treatment", "group", "control", "compared", "significant",
        "associated", "mean", "change", "changes", "level", "levels",
        "related", "based", "using", "between", "within", "total",
    }
    query_words = set(re.findall(r"\w{4,}", query.lower())) - _STOPWORDS
    if not query_words:
        return papers

    scored = []
    for paper in papers:
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        paper_words = set(re.findall(r"\w{4,}", text))
        overlap = len(query_words & paper_words) / max(len(query_words), 1) if paper_words else 0.0
        scored.append((overlap, paper))

    relevant = [(s, p) for s, p in scored if s > 0]
    if not relevant:
        papers.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
        return papers[:10]

    relevant.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in relevant]


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------

def _over_budget(t0: float) -> bool:
    """Check if we've exceeded the time budget."""
    return (time.monotonic() - t0) > PG_DEEPENER_TIMEOUT


def _finalize(
    papers: list[dict],
    stats: dict,
    t0: float,
    tracer: Any,
    existing_urls: set[str],
) -> dict[str, Any]:
    """Deduplicate, cap, and return the deepening results."""
    elapsed = round(time.monotonic() - t0, 1)
    stats["elapsed_seconds"] = elapsed

    # Deduplicate by URL and paperId
    seen: set[str] = set()
    unique_papers: list[dict] = []
    for paper in papers:
        url = paper.get("url", "")
        pid = paper.get("paperId", "")
        # Skip papers already in evidence pool
        if url and url in existing_urls:
            continue
        # Skip duplicates within new papers
        dedup_key = pid or url
        if dedup_key and dedup_key in seen:
            continue
        if dedup_key:
            seen.add(dedup_key)
        unique_papers.append(paper)

    # Cap at evidence limit
    if len(unique_papers) > PG_DEEPENER_EVIDENCE_CAP:
        # Sort by citation count (most impactful first)
        unique_papers.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
        unique_papers = unique_papers[:PG_DEEPENER_EVIDENCE_CAP]

    stats["new_papers_total"] = len(unique_papers)

    logger.info(
        "[deepener] Complete: %d new papers (chased=%d, recommended=%d, "
        "mechanism=%d, pdfs=%d) in %.1fs",
        len(unique_papers),
        stats.get("citations_chased", 0),
        stats.get("recommendations_found", 0),
        stats.get("mechanism_papers_found", 0),
        stats.get("pdfs_fetched", 0),
        elapsed,
    )

    if tracer:
        tracer.node_end(
            "deepen_evidence",
            new_papers=len(unique_papers),
            named_studies=stats["named_studies_extracted"],
            s2_resolved=stats["s2_ids_resolved"],
            citations_chased=stats["citations_chased"],
            recommended=stats["recommendations_found"],
            mechanism=stats["mechanism_papers_found"],
            pdfs_fetched=stats["pdfs_fetched"],
            elapsed_seconds=elapsed,
        )

    if not unique_papers:
        return {"deepener_stats": stats}

    # Convert papers to search result format for the analyze node
    # These will be added to web_results/academic_results for re-analysis
    return {
        "deepened_papers": unique_papers,
        "deepener_stats": stats,
    }
