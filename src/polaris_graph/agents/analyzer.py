"""
Evidence analyzer agent for polaris graph.

Fetches content from search results, extracts atomic facts,
scores quality. Uses reason() mode for deep analysis.

SOTA upgrades:
- HTML cleaning via extract_text_forensic() (Change 3)
- Externalized content caps from env vars (Change 3/4)
- MinHash evidence deduplication (Change 5)
- FIX-B1: Source URL blocklist (commercial/affiliate domains)
- FIX-B2: Domain authority scoring (tier-based multiplier)
- FIX-B3: Off-topic detection gate (embedding similarity)
- FIX-D3: Snippet quality penalty (downgrade snippet-only evidence)
- FIX-F1: Windows embedding path fix (OSError errno 22)
- FIX-A1: Retry failed analysis batches once before giving up
- FIX-A2: Embedding failure keyword fallback instead of silent pass-through
- FIX-A3: Track failed/total batch counts in return dict
- FIX-ENV3: Wire evidence hierarchy into analyzer
- FIX-S2-4: Source-level topic gate (embedding similarity on title+abstract)
"""

import asyncio
import errno
import hashlib
import re
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import platform

import numpy as np

# FIX-I1: Pre-set short cache path on Windows BEFORE any embedding import.
# sentence-transformers cache path too long for Windows 260-char limit -> [Errno 22].
if platform.system() == "Windows":
    _short_cache = os.getenv("PG_ST_CACHE_PATH", r"C:\st_cache")
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", _short_cache)
    os.environ.setdefault("HF_HOME", _short_cache)
    os.makedirs(_short_cache, exist_ok=True)
    logging.getLogger(__name__).info(
        "[polaris graph] FIX-I1: Windows ST cache set to %s (prevents Errno 22)",
        _short_cache,
    )

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.schemas import SourceAnalysis, SourceAnalysisBatch, StructuredDataExtraction
from src.polaris_graph.state import (
    EvidencePiece,
    ResearchState,
    MAX_SOURCES_TO_ANALYZE,
    PG_MAX_CONTENT_LENGTH,
    PG_CONTENT_PER_SOURCE,
    PG_MIN_CONTENT_LENGTH,
    PG_ANALYSIS_CONCURRENCY,
    PG_ANALYSIS_BATCH_SIZE,
    PG_ANALYSIS_BATCH_TIMEOUT,
    PG_FETCH_CONCURRENCY,
    PG_EVIDENCE_DEDUP_ENABLED,
    PG_EVIDENCE_DEDUP_THRESHOLD,
    PG_VERIFIER_CONTENT_CAP,
    PG_PREFER_MARKDOWN,
    PG_PAYWALL_DOMAINS,
    PG_MIN_CONTENT_LENGTH_ACADEMIC,
)
from src.polaris_graph.memory.content_cache import (
    get_cached_content,
    cache_content,
    extract_readability_html,
)

logger = logging.getLogger(__name__)

# FIX-C4: Off-topic threshold imported from state.py (single source of truth).
# Previously duplicated here with different default (0.15 vs 0.45 in state.py).
from src.polaris_graph.state import PG_OFFTOPIC_THRESHOLD  # noqa: E402

# FIX-S2-4: Source-level topic gate threshold (LAW VI: from env var).
_PG_SOURCE_TOPIC_GATE = float(os.getenv("PG_SOURCE_TOPIC_GATE", "0.30"))

# FIX-BUDGET: Evidence extraction budget cap — stop processing batches once cap reached.
# Saves ~60% extraction cost on large search result sets.
PG_MAX_EVIDENCE_TO_EXTRACT = int(os.getenv("PG_MAX_EVIDENCE_TO_EXTRACT", "600"))

# FIX-059-D (BUG-4): Minimum quote word count -- reject quotes shorter than this.
# Headings and nav labels are typically 5-10 words; 15 filters them out.
PG_MIN_QUOTE_WORDS = int(os.getenv("PG_MIN_QUOTE_WORDS", "15"))

# FIX-C4: Consolidate env var reads at module level (single source of truth).
# Previously read inline in analyze_sources() — violates LAW VI (zero hard-coding).
PG_SNIPPET_DROP_PCT = float(os.getenv("PG_SNIPPET_DROP_PCT", "0.40"))
PG_SNIPPET_RERANK_ENABLED = os.getenv("PG_SNIPPET_RERANK_ENABLED", "1") == "1"


# FIX-059-D (H-09): Compiled regex for markdown link stripping.
# Converts [text](url) -> text before storing direct_quote.
_RE_MD_LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
_RE_MD_IMAGE = re.compile(r'!\[([^\]]*)\]\([^)]+\)')
_RE_MD_BOLD = re.compile(r'\*\*([^*]+)\*\*')
_RE_MD_ITALIC = re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)')

# FIX-R10: Domains that should not be cited for quantitative/scientific claims.
# Consumer sites, plumber sites, filter vendors -- reduce authority to 0.1.
_LOW_AUTHORITY_PATTERNS = re.compile(
    r'(plumb|hvac|filter-?site|cleanwater(?:for|4)|handyman|home-?repair|'
    r'renovation|cleaning-?service|appliance-?repair|contractor)',
    re.IGNORECASE,
)

# FIX-CITE-3/C6: Low-credibility health/news domains that should be demoted
# for queries explicitly requesting "clinical research and meta-analyses".
# These produce pop-health content, not peer-reviewed evidence.
_LOW_CREDIBILITY_DOMAINS = frozenset([
    "webmd.com",
    "healthcentral.com",
    "nutritionfacts.org",
    "equip.health",
    "brokenscience.org",
    "ktla.com",
    "tctmd.com",
    "jeffersonhealth.org",
    "healthline.com",
    "verywellhealth.com",
    "medicalnewstoday.com",
    "everydayhealth.com",
    "livestrong.com",
    # FIX-CITE-3/S5: Additional low-credibility domains from TEST_067 audit
    "droracle.ai",
    "centerwellprimarycare.com",
    "orthomolecular.org",
    "eatingwell.com",
    "sciencefocus.com",
    "aarp.org",
    "diabetesonthenet.com",
    # FIX-071: Additional from TEST_071 audit
    "healthshots.com",
    "theconversation.com",
    "agencia.fapesp.br",
    "sochob.cl",
])
_DOMAIN_AUTHORITY_LOW_CREDIBILITY = 0.2


def _strip_markdown(text: str) -> str:
    """FIX-059-D (H-09): Strip markdown syntax from quote text.

    Removes markdown link syntax [text](url), image syntax ![alt](url),
    bold **text**, and italic *text* to prevent junk evidence.
    """
    if not text:
        return text
    text = _RE_MD_IMAGE.sub(r'\1', text)  # Images first (! prefix)
    text = _RE_MD_LINK.sub(r'\1', text)   # Then links
    text = _RE_MD_BOLD.sub(r'\1', text)   # Bold
    text = _RE_MD_ITALIC.sub(r'\1', text) # Italic
    return text.strip()

ANALYSIS_SYSTEM = """You are a research evidence analyst. Extract atomic facts from source material.

Rules:
1. Extract 8-15 atomic facts per source. Focus on the MOST relevant, specific, and unique claims, statistics, findings, and conclusions. Quality over quantity — prioritize facts that DIRECTLY answer the research question over tangential details. Missing a highly relevant fact is worse than including marginally relevant ones.
   CRITICAL: ONLY extract from the ARTICLE BODY TEXT. NEVER extract from: navigation menus, cookie consent banners, URL paths/slugs, abbreviation/glossary tables, author byline metadata, page footers/headers, table of contents page numbers, product category labels, or marketing taglines. If the source is mostly non-content (nav, ads, cookie text), extract ZERO facts and set source_quality to 0.0.
2. Each atomic fact = ONE specific claim with the EXACT quote from the source (minimum 10 words, up to 200 chars). A quote shorter than 5 words is NEVER acceptable — skip that fact entirely.
3. Source quality: Score each source individually on 0.0-1.0 based on:
   - Peer review status (peer-reviewed journal > preprint > report > blog)
   - Author credentials (named experts > organizations > anonymous)
   - Recency (2023-2026 > 2018-2022 > older)
   - Specificity to research question (directly relevant > tangentially related)
   Do NOT use fixed scores for source types. Vary scores based on each source's specific qualities.
4. Rate relevance to the SPECIFIC research question on 0.0-1.0:
   - 0.9-1.0: Directly answers part of the research question with specific data
   - 0.7-0.8: Provides important context or supporting evidence
   - 0.5-0.6: Tangentially relevant or provides background
   - 0.1-0.4: Marginally relevant, mostly off-topic
   Each fact must get a UNIQUE relevance score. No two facts from the same source should have identical scores.
5. Include exact numbers, dates, measurements, names, standards.
6. For EVERY quantitative finding, extract ALL of the following when available:
   - Effect size with units (MD, SMD, WMD, OR, HR, RR)
   - 95% confidence interval (e.g., "95% CI -5.54 to -3.05")
   - Heterogeneity (I-squared value, e.g., "I²=96%")
   - Number of studies/trials included (e.g., "7 RCTs")
   - Total sample size (e.g., "n=269")
   - Evidence certainty/quality rating (e.g., "GRADE: moderate", "high certainty")
   - Study duration/follow-up period
   Missing any of these when the source provides them is a CRITICAL extraction failure.
7. For review/meta-analysis papers, extract findings from EACH cited study individually.
   Prioritize pooled estimates with I² and CI over narrative summaries.
8. For each atomic fact, tag the research perspective it belongs to.
9. CRITICAL (ARCH-4): The 'statement' field must be a DIRECT PARAPHRASE of the source text.
   Do NOT infer, extrapolate, or add information beyond what the direct_quote states.
   If the direct_quote is fewer than 10 words, the statement must be equally narrow in scope.
   A 2-word quote like 'distilled water' can only support a statement about distilled water,
   not a full sentence about healthcare settings or bacterial contamination.
   Perspectives: Scientific, Regulatory, Industry, Economic, Public_Health, Historical, Regional, Methodological, Emerging_Trends.
   Choose the single best-fit perspective.

Output format (return ONLY this JSON structure):
{"analyses": [{"source_url": "https://example.com", "source_title": "Study Title", "source_type": "journal_article", "source_quality": 0.8, "overall_relevance": 0.7, "year": 2024, "authors": ["Smith J"], "venue": "Water Research", "doi": "", "atomic_facts": [{"statement": "E. coli was detected in 30% of tested filters after 6 months", "direct_quote": "E. coli presence in 30% of tested POU filters", "fact_category": "statistic", "relevance_score": 0.9, "confidence": 0.8, "perspective": "Scientific"}], "evidence_summary": "Bacterial contamination in POU water filters"}]}"""


# ---------------------------------------------------------------------------
# FIX-B1: Source URL blocklist
# ---------------------------------------------------------------------------

# Domain blocklist: commercial, affiliate, and low-quality sources
_BLOCKED_DOMAINS = frozenset([
    "cnfilter.net",
    "uswatersystems.com",
    "waterfilteradviser.com",
    "filterwateronline.com",
    "bestreviews.com",
    "amazon.com",
    "ebay.com",
    "alibaba.com",
    "aliexpress.com",
    # FIX-QG1: Commercial filter retailers identified in PG_TEST_023 audit
    "frizzlife.com",
    "aquasana.com",
    "multipure.com",
    "tapwaterdata.com",
    "mytapscore.com",
    "honestwaterfilter.com",
    "springwellwater.com",
    "premierh2o.com",
    "glacierfreshfilter.com",
    "aquageneral.com",
    "7sage.com",
])

# Path-qualified domain blocks (only block specific paths on these domains)
_BLOCKED_DOMAIN_PATHS = [
    ("consumerreports.org", "/shop"),
    ("reddit.com", "/r/"),
]

# URL path patterns that indicate commercial/affiliate content
_BLOCKED_PATH_PATTERNS = frozenset([
    "/shop/",
    "/product/",
    "/products/",
    "/buy/",
    "/cart/",
    "/affiliate/",
    "/sponsored/",
    "/ad/",
    "/checkout/",
])

# Commercial TLDs that host primarily product content
_BLOCKED_TLDS = frozenset([
    ".shop",
    ".store",
    ".buy",
    ".sale",
    ".deals",
])


def _is_blocked_source(url: str) -> bool:
    """FIX-B1: Check whether a URL should be rejected based on blocklist rules.

    Rejects:
    - Known commercial/affiliate domains
    - Path-qualified domain blocks (e.g., consumerreports.org/shop)
    - URLs with commercial path patterns (/product/, /cart/, etc.)
    - Domains with commercial TLDs (.shop, .store, etc.)

    Returns True if the URL should be blocked.
    """
    if not url:
        return False

    url_lower = url.lower()

    try:
        parsed = urlparse(url_lower)
        hostname = parsed.hostname or ""
        path = parsed.path or ""
    except Exception:
        return False

    # Check exact domain blocklist (match domain and subdomains)
    for blocked in _BLOCKED_DOMAINS:
        if hostname == blocked or hostname.endswith("." + blocked):
            return True

    # Check path-qualified domain blocks
    for domain, blocked_path in _BLOCKED_DOMAIN_PATHS:
        if (hostname == domain or hostname.endswith("." + domain)):
            if blocked_path in path:
                return True

    # Check commercial path patterns
    for pattern in _BLOCKED_PATH_PATTERNS:
        if pattern in path:
            return True

    # Check commercial TLDs
    for tld in _BLOCKED_TLDS:
        if hostname.endswith(tld):
            return True

    return False


# ---------------------------------------------------------------------------
# FIX-B2: Domain authority scoring
# ---------------------------------------------------------------------------

# TIER 1 (1.0): High-authority academic, government, and top journals
_TIER1_DOMAINS = frozenset([
    "nature.com",
    "sciencedirect.com",
    "frontiersin.org",
    "springer.com",
    "wiley.com",
    "thelancet.com",
    "bmj.com",
    "nejm.org",
    "cell.com",
    "pnas.org",
    "acs.org",
    "rsc.org",
    "iwaponline.com",
    "who.int",
    "epa.gov",
    "cdc.gov",
])

# TIER 1 also includes .gov and .edu TLDs (checked separately)
_TIER1_TLDS = frozenset([".gov", ".edu"])

# TIER 2 (0.85): High-quality secondary sources
_TIER2_DOMAINS = frozenset([
    "ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "nsf.org",
    "iso.org",
    "astm.org",
    "awwa.org",
    "reuters.com",
    "apnews.com",
])

# TIER 2 partial matches (substring in hostname)
_TIER2_PARTIALS = frozenset([
    "pubmed",
    "pmc",
])

# TIER 2 path-qualified
_TIER2_DOMAIN_PATHS = [
    ("bbc.com", "/news"),
]

# TIER 3 (0.7): Industry reports and trade publications
_TIER3_DOMAINS = frozenset([
    "wateronline.com",
    "engineering.com",
    "chemengonline.com",
    "wqa.org",
    "nrdc.org",
    "ewg.org",
])

_DOMAIN_AUTHORITY_TIER1 = 1.0
_DOMAIN_AUTHORITY_TIER2 = 0.85
_DOMAIN_AUTHORITY_TIER3 = 0.7
_DOMAIN_AUTHORITY_DEFAULT = float(os.getenv("PG_DEFAULT_DOMAIN_AUTHORITY", "0.5"))


def _get_domain_authority(url: str) -> float:
    """FIX-B2: Return a domain authority multiplier for the given URL.

    Tiers:
    - TIER 1 (1.0):  .gov, .edu, top journals (Nature, Science, etc.)
    - TIER 2 (0.85): PubMed, NIH, standards bodies, wire services
    - TIER 3 (0.7):  Industry trade publications (non-blog)
    - TIER 4 (PG_DEFAULT_DOMAIN_AUTHORITY, default 0.5): Everything else
    - BLOCKED (0.0):  Anything on the blocklist

    The multiplier is applied to relevance_score before tier assignment,
    so commercial blogs get lower tiers.
    """
    if not url:
        return _DOMAIN_AUTHORITY_DEFAULT

    # BLOCKED check first
    if _is_blocked_source(url):
        return 0.0

    url_lower = url.lower()
    try:
        parsed = urlparse(url_lower)
        hostname = parsed.hostname or ""
        path = parsed.path or ""
    except Exception:
        return _DOMAIN_AUTHORITY_DEFAULT

    # TIER 1: Check TLDs (.gov, .edu) with path-based demotion.
    # FIX-B4: .edu TLD gave blanket 1.0 to community college blogs,
    # university news pages, and student projects — same as Nature/BMJ.
    # Now: .edu gets TIER 1 only for journal/research paths. News,
    # blogs, and general pages get TIER 2 (0.85).
    # FIX-B4: Demote .edu subdomains/paths that are news, blogs, etc.
    _EDU_DEMOTE_PATTERNS = {
        "news", "today", "blog", "stories", "press",
        "media", "magazine", "events", "myctcd",
    }
    for tld in _TIER1_TLDS:
        if hostname.endswith(tld):
            if tld == ".edu":
                # Check both subdomain (today.uic.edu) and path (/news/...)
                _host_parts = hostname.replace(tld, "").split(".")
                _is_non_research = (
                    any(dp in path for dp in _EDU_DEMOTE_PATTERNS)
                    or any(dp in part for part in _host_parts for dp in _EDU_DEMOTE_PATTERNS)
                )
                if _is_non_research:
                    return _DOMAIN_AUTHORITY_TIER2  # 0.85 not 1.0
            return _DOMAIN_AUTHORITY_TIER1

    # TIER 1: Check specific domains (exact or subdomain match)
    for domain in _TIER1_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return _DOMAIN_AUTHORITY_TIER1

    # TIER 2: Check specific domains
    for domain in _TIER2_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return _DOMAIN_AUTHORITY_TIER2

    # TIER 2: Check partial hostname matches (pubmed, pmc)
    for partial in _TIER2_PARTIALS:
        if partial in hostname:
            return _DOMAIN_AUTHORITY_TIER2

    # TIER 2: Path-qualified (e.g., bbc.com/news)
    for domain, required_path in _TIER2_DOMAIN_PATHS:
        if (hostname == domain or hostname.endswith("." + domain)):
            if required_path in path:
                return _DOMAIN_AUTHORITY_TIER2

    # TIER 3: Trade/industry publications
    for domain in _TIER3_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            # Exclude blog sections from tier 3
            if "/blog" in path:
                return _DOMAIN_AUTHORITY_DEFAULT
            return _DOMAIN_AUTHORITY_TIER3

    # FIX-CITE-3/C6: Low-credibility health/news domains
    for domain in _LOW_CREDIBILITY_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return _DOMAIN_AUTHORITY_LOW_CREDIBILITY

    # FIX-R10: Pattern-based low authority (plumbers, HVAC, etc.)
    if _LOW_AUTHORITY_PATTERNS.search(url_lower):
        return 0.1

    # TIER 4: Default — unknown domains get conservative score
    return _DOMAIN_AUTHORITY_DEFAULT


def _import_text_extractor():
    """Import SOTA text extraction from main pipeline."""
    from src.utils.ingest import extract_text_forensic

    return extract_text_forensic


# ---------------------------------------------------------------------------
# FIX-S2-4: Source-level topic gate
# ---------------------------------------------------------------------------


async def _source_topic_gate(
    fetched: list[dict],
    query: str,
    timeout_seconds: int = 60,
) -> list[dict]:
    """FIX-S2-4: Filter entire sources by embedding similarity BEFORE evidence extraction.

    Semantic Scholar returns wildly off-topic papers (tick genetics, bat fungus,
    psychiatry) that contaminate the evidence pool. This gate computes cosine
    similarity between the research query and each source's title+abstract/snippet,
    removing sources below PG_SOURCE_TOPIC_GATE threshold.

    This is a SOURCE-level filter (coarse, fast, runs once on titles) as opposed
    to the existing FIX-B3 EVIDENCE-level off-topic filter (fine-grained, runs
    on extracted statements after LLM analysis). Filtering here avoids wasting
    LLM calls on sources that are clearly irrelevant.

    Runs embedding in a thread pool with asyncio timeout to prevent event-loop
    starvation from CPU-bound sentence-transformers.

    Graceful fallback: if embedding fails or times out, returns fetched unchanged.

    Args:
        fetched: List of fetched source dicts (url, title, content, snippet, ...).
        query: The original research query.
        timeout_seconds: Max seconds for the embedding operation.

    Returns:
        Filtered list of fetched source dicts.
    """
    if not fetched:
        return fetched

    threshold = _PG_SOURCE_TOPIC_GATE

    # Build source-level text: title + abstract/snippet for each source.
    # Content may be very long (10K+ chars); title+abstract is sufficient for
    # topic relevance and keeps embedding fast.
    source_texts = []
    for src in fetched:
        title = src.get("title", "")
        # Prefer snippet (usually abstract for academic sources) over full content
        abstract_or_snippet = src.get("snippet", "")
        if not abstract_or_snippet:
            # Fall back to first 500 chars of content as abstract proxy
            abstract_or_snippet = src.get("content", "")[:500]
        source_text = (title + ". " + abstract_or_snippet).strip()
        # If somehow empty, use a placeholder that will score low
        if not source_text or source_text == ".":
            source_text = title if title else "unknown source"
        source_texts.append(source_text)

    def _do_source_embedding():
        """Synchronous embedding for source-level topic gate, runs in thread pool."""
        from src.utils.embedding_service import embed_text, embed_texts

        t0 = time.time()

        # Embed query once
        query_vec = np.array(embed_text(query))

        # Batch-embed all source texts
        source_vecs = np.array(embed_texts(source_texts))

        # Cosine similarity (embeddings are pre-normalized -> dot product)
        similarities = source_vecs @ query_vec

        elapsed = time.time() - t0
        logger.info(
            "[polaris graph] FIX-S2-4: Source embedding complete in %.1fs for %d sources. "
            "sim min=%.3f, median=%.3f, max=%.3f",
            elapsed,
            len(fetched),
            float(np.min(similarities)),
            float(np.median(similarities)),
            float(np.max(similarities)),
        )
        return similarities

    try:
        logger.info(
            "[polaris graph] FIX-S2-4: Running source topic gate on %d sources "
            "(threshold=%.2f, timeout=%ds)...",
            len(fetched),
            threshold,
            timeout_seconds,
        )

        loop = asyncio.get_running_loop()
        similarities = await asyncio.wait_for(
            loop.run_in_executor(None, _do_source_embedding),
            timeout=timeout_seconds,
        )

        # Filter sources below threshold
        before_count = len(fetched)
        passed = []
        removed_details = []
        for i, src in enumerate(fetched):
            sim = float(similarities[i])
            if sim >= threshold:
                passed.append(src)
            else:
                removed_details.append(
                    (src.get("title", "?")[:80], sim)
                )

        removed_count = before_count - len(passed)

        if removed_count > 0:
            logger.info(
                "[polaris graph] FIX-S2-4: Source topic gate removed %d/%d sources "
                "with similarity < %.2f",
                removed_count,
                before_count,
                threshold,
            )
            # Log removed source titles at DEBUG level for diagnosis
            for removed_title, removed_sim in removed_details[:10]:
                logger.debug(
                    "[polaris graph] FIX-S2-4: Removed source: '%s' (sim=%.3f)",
                    removed_title,
                    removed_sim,
                )
            if len(removed_details) > 10:
                logger.debug(
                    "[polaris graph] FIX-S2-4: ... and %d more removed sources",
                    len(removed_details) - 10,
                )

            # OBS-4: Trace source-level filtering
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "analyze", "source_topic_gated", len(passed),
                    removed=removed_count,
                    threshold=threshold,
                )
        else:
            logger.info(
                "[polaris graph] FIX-S2-4: Source topic gate passed all %d sources "
                "(threshold=%.2f)",
                before_count,
                threshold,
            )

        return passed

    except (asyncio.TimeoutError, ImportError, Exception) as exc:
        # FIX-TOPIC-FALLBACK: Keyword-based fallback when embeddings unavailable.
        # Without this, ALL sources pass through (including S2 noise like tick
        # genetics for water filtration queries). Extract query keywords and
        # keep sources whose title/snippet contains at least one keyword.
        logger.warning(
            "[polaris graph] FIX-S2-4: Source topic gate embedding failed: %s — "
            "applying keyword fallback on %d sources",
            str(exc)[:200],
            len(fetched),
        )
        query_keywords = {
            w.lower().strip(".,;:!?()[]\"'")
            for w in query.split()
            if len(w.strip(".,;:!?()[]\"'")) > 3
        }
        if not query_keywords:
            return fetched

        passed = []
        for src, src_text in zip(fetched, source_texts):
            text_lower = src_text.lower()
            hits = sum(1 for kw in query_keywords if kw in text_lower)
            if hits >= 1:
                passed.append(src)
        if len(passed) < max(5, len(fetched) // 3):
            # Fallback too aggressive — keep all to avoid starving pipeline
            logger.warning(
                "[polaris graph] FIX-TOPIC-FALLBACK: Keyword filter too aggressive "
                "(%d/%d passed) — keeping all sources",
                len(passed), len(fetched),
            )
            return fetched
        logger.info(
            "[polaris graph] FIX-TOPIC-FALLBACK: Keyword fallback kept %d/%d sources "
            "(%d removed for zero query keyword overlap)",
            len(passed), len(fetched), len(fetched) - len(passed),
        )
        return passed


# ---------------------------------------------------------------------------
# GEMINI-ARCH: Structured Data Extraction (Phase 2B)
# ---------------------------------------------------------------------------

_STRUCTURED_DATA_SYSTEM = (
    "You are a structured data extraction specialist. "
    "Extract all numerical data points from the provided text. "
    "For each data point: identify the data_type "
    "(statistic/comparison/time_series/measurement/ranking), "
    "label, value, year, unit, and context."
)


async def _extract_structured_data(
    client: OpenRouterClient,
    content: str,
    source_url: str,
    evidence_id: str,
) -> list[dict]:
    """Extract structured data points (statistics, comparisons, time-series) from source content.

    Returns list of StructuredDataPoint dicts.

    Gated behind PG_STRUCTURED_DATA_EXTRACTION env var (default '0' = disabled).
    Uses generate_structured() with StructuredDataExtraction schema.
    On error, returns empty list (logs warning).
    """
    if not content or not content.strip():
        return []

    # Truncate to ~5000 chars to save tokens (LAW VI: cap from constant, not magic number)
    truncated_content = content[:5000]

    prompt = (
        f"Extract all numerical data points from this text. "
        f"For each: identify the data_type (statistic/comparison/time_series/"
        f"measurement/ranking), label, value, year, unit, and context.\n\n"
        f"Source URL: {source_url}\n"
        f"Content:\n{truncated_content}"
    )

    # FIX-TIMEOUT: Structured data extraction timeout configurable via env var.
    # LLM takes 200+ seconds on complex content; previous 60s caused 100% timeouts.
    _sd_timeout = int(os.getenv("PG_STRUCTURED_DATA_TIMEOUT", "300"))

    try:
        parsed = await client.generate_structured(
            prompt=prompt,
            schema=StructuredDataExtraction,
            system=_STRUCTURED_DATA_SYSTEM,
            max_tokens=4096,
            timeout=_sd_timeout,
            reasoning_enabled=False,
        )

        results = []
        for dp in parsed.data_points:
            point_dict = dp.model_dump()
            point_dict["evidence_id"] = evidence_id
            point_dict["source_url"] = source_url
            results.append(point_dict)

        if results:
            logger.info(
                "[polaris graph] GEMINI-ARCH: Extracted %d structured data points "
                "from %s",
                len(results),
                source_url[:80],
            )
        return results

    except Exception as exc:
        logger.warning(
            "[polaris graph] GEMINI-ARCH: Structured data extraction failed "
            "for %s: %s — returning empty list",
            source_url[:80],
            str(exc)[:200],
        )
        return []


async def _enrich_evidence_cards(
    client: OpenRouterClient,
    evidence: list[dict],
    source_contents: dict[str, str],
) -> list[dict]:
    """RC-1: Post-extraction enrichment -- add methodology, conditions, limitations, comparable metrics.

    Processes evidence in batches of 10 per LLM call for cost efficiency.
    Merges enrichment fields back into evidence dicts in-place.

    Args:
        client: OpenRouter LLM client.
        evidence: List of EvidencePiece dicts to enrich.
        source_contents: {source_url: content_text} for context.

    Returns:
        The same evidence list with enrichment fields populated.
    """
    if not evidence:
        return evidence

    from src.polaris_graph.schemas import EvidenceCardBatch

    batch_size = int(os.getenv("PG_V3_CARD_BATCH_SIZE", "10"))
    enriched_count = 0

    for batch_start in range(0, len(evidence), batch_size):
        batch = evidence[batch_start:batch_start + batch_size]

        # Build batch prompt
        evidence_lines = []
        for ev in batch:
            url = ev.get("source_url", "")
            content_snippet = source_contents.get(url, "")[:2000]
            evidence_lines.append(
                f"Evidence ID: {ev.get('evidence_id', '?')}\n"
                f"Statement: {ev.get('statement', '')}\n"
                f"Quote: {ev.get('direct_quote', '')[:300]}\n"
                f"Source context: {content_snippet[:500]}"
            )

        batch_text = "\n---\n".join(evidence_lines)

        system = (
            "For each evidence finding below, extract:\n"
            "1. methodology: How this finding was obtained (experimental method, study type)\n"
            "2. conditions: Key experimental parameters (temperature, pH, concentration, sample size)\n"
            "3. limitations: Any stated limitations of this finding\n"
            "4. strength_signals: Quality indicators from this list ONLY: "
            "peer_reviewed, large_sample, replicated, meta_analysis, rct, longitudinal\n"
            "5. comparable_metrics: Quantitative values that could be compared across studies.\n"
            "   Each metric needs: metric_name, value (number), unit, condition, entity\n\n"
            "Return a JSON object with a 'cards' array containing one enrichment per evidence piece.\n"
            "If information is not available, use empty strings/lists. Do NOT invent data."
        )

        try:
            result = await client.generate_structured(
                prompt=f"Enrich these {len(batch)} evidence pieces:\n\n{batch_text}",
                schema=EvidenceCardBatch,
                system=system,
                max_tokens=4096,
                timeout=int(os.getenv("PG_V3_CARD_TIMEOUT", "120")),
            )

            # Merge enrichments back into evidence dicts
            card_map = {c.evidence_id: c for c in result.cards}
            for ev in batch:
                card = card_map.get(ev.get("evidence_id", ""))
                if card:
                    ev["methodology"] = card.methodology or ev.get("methodology")
                    ev["conditions"] = card.conditions or ev.get("conditions")
                    ev["limitations"] = card.limitations or ev.get("limitations")
                    ev["strength_signals"] = card.strength_signals or ev.get("strength_signals")
                    if card.comparable_metrics:
                        ev["comparable_metrics"] = [
                            m.model_dump() for m in card.comparable_metrics
                        ]
                    enriched_count += 1
        except Exception as exc:
            logger.warning(
                "[polaris graph] RC-1: Evidence card enrichment failed for batch %d-%d: %s",
                batch_start, batch_start + len(batch), str(exc)[:200],
            )

    logger.info(
        "[polaris graph] RC-1: Enriched %d/%d evidence pieces with cards",
        enriched_count, len(evidence),
    )
    return evidence


async def analyze_sources(
    client: OpenRouterClient,
    state: ResearchState,
    on_evidence_progress: "callable | None" = None,
) -> dict:
    """
    Fetch and analyze all search results.

    Returns state update with evidence list.

    Args:
        on_evidence_progress: Optional callback called after each batch completes
            with the current accumulated evidence list. Used by graph.py to
            update the timeout-recovery snapshot progressively.
    """
    web_results = state.get("web_results", [])
    academic_results = state.get("academic_results", [])
    query = state["original_query"]

    # Merge and rank all results
    all_results = _rank_and_merge(web_results, academic_results)

    # Cap at max sources to analyze
    sources_to_analyze = all_results[:MAX_SOURCES_TO_ANALYZE]

    # FIX-SNIPPET-RERANK: Pre-fetch snippet reranking by embedding similarity.
    # Drops bottom PG_SNIPPET_DROP_PCT of results before costly content fetching.
    # FIX-C4: Use module-level constants instead of inline env var reads
    snippet_drop_pct = PG_SNIPPET_DROP_PCT
    snippet_rerank_enabled = PG_SNIPPET_RERANK_ENABLED
    if snippet_rerank_enabled and len(sources_to_analyze) >= 10:
        try:
            from src.utils.embedding_service import embed_texts as _embed_texts
            snippets = [
                (r.get("snippet") or r.get("title") or "")[:500]
                for r in sources_to_analyze
            ]
            # Filter out empty snippets
            non_empty = [(i, s) for i, s in enumerate(snippets) if s.strip()]
            if non_empty and len(non_empty) >= 5:
                import numpy as _np
                snippet_texts = [s for _, s in non_empty]
                all_texts = [query] + snippet_texts
                embeddings = _np.array(_embed_texts(all_texts), dtype=_np.float32)
                query_emb = embeddings[0:1]  # (1, d)
                snippet_embs = embeddings[1:]  # (n, d)
                # Cosine similarity (embeddings are L2-normalized)
                sims = (snippet_embs @ query_emb.T).flatten()
                # Map back to original indices with scores
                scored = [(non_empty[j][0], float(sims[j])) for j in range(len(non_empty))]
                scored.sort(key=lambda x: x[1], reverse=True)
                # Keep top (1 - drop_pct) of results
                keep_count = max(5, int(len(scored) * (1 - snippet_drop_pct)))
                keep_indices = set(idx for idx, _ in scored[:keep_count])
                # Also keep results that had empty snippets (can't score them)
                empty_indices = set(range(len(sources_to_analyze))) - set(
                    i for i, _ in non_empty
                )
                keep_indices.update(empty_indices)
                pre_count = len(sources_to_analyze)
                sources_to_analyze = [
                    r for i, r in enumerate(sources_to_analyze) if i in keep_indices
                ]
                dropped = pre_count - len(sources_to_analyze)
                if dropped > 0:
                    logger.info(
                        "[polaris graph] FIX-SNIPPET-RERANK: Dropped %d/%d sources "
                        "below query similarity threshold (kept %d, drop_pct=%.0f%%)",
                        dropped, pre_count, len(sources_to_analyze),
                        snippet_drop_pct * 100,
                    )
                    # OBS-TRACE: Emission 6 — Snippet rerank
                    tracer = get_tracer()
                    if tracer:
                        tracer.evidence("analyze", "snippet_reranked", len(sources_to_analyze),
                            reranked_count=len(sources_to_analyze),
                            dropped=dropped, pre_count=pre_count)
        except Exception as exc:
            logger.warning(
                "[polaris graph] FIX-SNIPPET-RERANK: Failed (non-fatal): %s",
                str(exc)[:200],
            )

    logger.info(
        "[polaris graph] Analyzing %d sources (from %d total)",
        len(sources_to_analyze),
        len(all_results),
    )

    # Fetch content for all sources (concurrency from env)
    fetched, content_cache_hits = await _fetch_all_content(
        sources_to_analyze, concurrency=PG_FETCH_CONCURRENCY
    )

    # FIX-S2-4: Source-level topic gate — filter entire sources by embedding
    # similarity BEFORE evidence extraction. Prevents wasting LLM calls on
    # off-topic S2 papers (tick genetics, bat fungus, psychiatry, oncology).
    fetched = await _source_topic_gate(fetched, query)

    # RC-4: Content quality gate (v3 Hybrid) — reject garbled/boilerplate before extraction
    if os.getenv("PG_V3_CONTENT_QUALITY_GATE", "0") == "1":
        from src.polaris_graph.retrieval.content_quality_gate import score_content_quality
        threshold = float(os.getenv("PG_V3_CONTENT_QUALITY_THRESHOLD", "0.3"))
        pre_gate_count = len(fetched)
        quality_passed = []
        for item in fetched:
            content_text = item.get("content", "")
            url = item.get("url", "")
            if not content_text:
                quality_passed.append(item)  # Can't score empty, let downstream handle
                continue
            quality_score, reasons = score_content_quality(content_text, url)
            if quality_score >= threshold:
                quality_passed.append(item)
            else:
                logger.warning(
                    "[polaris graph] RC-4: Rejecting %s (quality=%.2f, reasons=%s)",
                    url[:80], quality_score, reasons,
                )
        fetched = quality_passed
        rejected = pre_gate_count - len(fetched)
        if rejected > 0:
            logger.info(
                "[polaris graph] RC-4: Content quality gate rejected %d/%d sources",
                rejected, pre_gate_count,
            )


    # Batch size from env (LAW VI). Default 1 = one source per LLM call.
    # Concurrency from env (PG_ANALYSIS_CONCURRENCY).
    evidence: list[EvidencePiece] = []
    batch_size = PG_ANALYSIS_BATCH_SIZE
    semaphore = asyncio.Semaphore(PG_ANALYSIS_CONCURRENCY)
    # Per-batch timeout from env — prevents single slow batches from blocking
    batch_timeout = PG_ANALYSIS_BATCH_TIMEOUT

    batches = [
        fetched[i : i + batch_size]
        for i in range(0, len(fetched), batch_size)
    ]

    completed_count = 0

    evidence_cap = PG_MAX_EVIDENCE_TO_EXTRACT
    budget_exhausted = False

    async def _run_batch(batch_idx: int, batch: list[dict]) -> list[EvidencePiece]:
        nonlocal completed_count, budget_exhausted
        # FIX-BUDGET: Skip batch if evidence cap already reached
        if budget_exhausted:
            return []
        async with semaphore:
            try:
                result = await asyncio.wait_for(
                    _analyze_batch(client, batch, query),
                    timeout=batch_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[polaris graph] Batch %d/%d timed out after %.0fs — retrying once with same batch",
                    batch_idx + 1, len(batches), batch_timeout,
                )
                # FIX-A1: Retry once on timeout before giving up
                try:
                    result = await asyncio.wait_for(
                        _analyze_batch(client, batch, query),
                        timeout=batch_timeout,
                    )
                except (asyncio.TimeoutError, Exception) as retry_exc:
                    logger.error(
                        "[polaris graph] FIX-A1: Batch %d/%d retry also failed: %s",
                        batch_idx + 1, len(batches), str(retry_exc)[:100],
                    )
                    return []
            if result:
                # Progressive accumulation — evidence available immediately
                evidence.extend(result)
                completed_count += 1
                logger.info(
                    "[polaris graph] Batch %d/%d: extracted %d evidence pieces "
                    "(%d total so far)",
                    batch_idx + 1,
                    len(batches),
                    len(result),
                    len(evidence),
                )
                # WAVE-3.4: Extraction batch progress trace
                _batch_tracer = get_tracer()
                if _batch_tracer:
                    _batch_tracer.llm_call("analyze", "extraction_batch",
                        batch_index=batch_idx + 1, total_batches=len(batches),
                        evidence_extracted=len(result), evidence_total=len(evidence),
                        sources_in_batch=len(batch),
                        source_urls=[s.get("url", "") for s in batch])
                # FIX-BUDGET: Check if evidence cap reached
                if len(evidence) >= evidence_cap:
                    budget_exhausted = True
                    logger.info(
                        "[polaris graph] FIX-BUDGET: Evidence cap reached (%d >= %d). "
                        "Remaining batches will be skipped.",
                        len(evidence), evidence_cap,
                    )
                # Progressive snapshot callback for timeout recovery
                if on_evidence_progress is not None:
                    on_evidence_progress(evidence, fetched)
            return result

    batch_results = await asyncio.gather(
        *[_run_batch(i, b) for i, b in enumerate(batches)]
    )
    failed_batches = 0
    for batch_evidence in batch_results:
        if not batch_evidence:
            failed_batches += 1

    # SF-10 + FIX-I2: Track failure rate and escalate logging at high failure rates
    total_batches = len(batches)
    if failed_batches:
        failure_rate = failed_batches / max(total_batches, 1)
        if failure_rate > 0.5:
            logger.error(
                "[polaris graph] FIX-I2: ANALYSIS BATCH SUMMARY: %d/%d failed (%.1f%%). "
                "Evidence severely reduced. Check logs for per-batch error details.",
                failed_batches,
                total_batches,
                failure_rate * 100,
            )
        else:
            logger.warning(
                "[polaris graph] FIX-I2: %d/%d analysis batches failed (%.1f%%)",
                failed_batches,
                total_batches,
                failure_rate * 100,
            )

    # FIX-049: Source confidence enrichment BEFORE tier assignment.
    # SOTA-11 was originally at lines 831-862, AFTER both _assign_quality_tiers() calls.
    # Signal 2 (Source Authority, 25% weight) blends domain_authority with source_confidence:
    #   authority = 0.6 * domain_authority + 0.4 * source_confidence
    # But source_confidence defaulted to 0.0 because enrichment hadn't run yet,
    # making the 40% source_confidence contribution completely dead.
    # Moving it here ensures PageRank + type hierarchy + citation count scores
    # are available for BOTH tier assignment passes.
    try:
        from src.polaris_graph.agents.source_confidence import (
            _is_enabled as _source_confidence_enabled,
            get_source_confidence,
            get_type_confidence,
            compute_composite_confidence,
        )
        if _source_confidence_enabled() and evidence:
            unique_urls = list({e.get("source_url", "") for e in evidence if e.get("source_url")})
            pagerank_scores = await get_source_confidence(unique_urls)
            enriched = 0
            for ev in evidence:
                src_url = ev.get("source_url", "")
                pr_score = pagerank_scores.get(src_url, 0.0)
                type_score = get_type_confidence(ev.get("source_type", "unknown"))
                citation_count = ev.get("citation_count", 0)
                ev["source_confidence"] = compute_composite_confidence(
                    pr_score, type_score, citation_count,
                )
                enriched += 1
            logger.info(
                "[polaris graph] SOTA-11: Source confidence enriched %d/%d evidence",
                enriched, len(evidence),
            )
        elif not _source_confidence_enabled():
            logger.info("[polaris graph] SOTA-11: Source confidence DISABLED")
    except Exception as exc:
        logger.warning(
            "[polaris graph] SOTA-11: Source confidence failed (non-fatal): %s",
            str(exc)[:200],
        )

    # TIER-3 Stage 1: Hydrate evidence with source_content from content store
    # for _ground_quotes_verbatim and _validate_extraction_claims (both sync).
    # Content is temporary — stripped after these functions return.
    try:
        from src.polaris_graph.memory.source_content_store import (
            get_content_batch as _get_batch,
            PG_SOURCE_CONTENT_STORE_ENABLED as _store_enabled,
        )
        if _store_enabled:
            _urls = list({ev.get("source_url", "") for ev in evidence if ev.get("source_url")})
            _url_content = await _get_batch(_urls)
            _hydrated = 0
            for ev in evidence:
                _src_url = ev.get("source_url", "")
                if _src_url and _src_url in _url_content:
                    ev["source_content"] = _url_content[_src_url][:PG_CONTENT_PER_SOURCE]
                    _hydrated += 1
            if _hydrated:
                logger.debug(
                    "[polaris graph] TIER-3: Hydrated %d/%d evidence with source_content from store",
                    _hydrated, len(evidence),
                )
    except Exception as _hydrate_exc:
        logger.debug(
            "[polaris graph] TIER-3: Content hydration failed (non-fatal): %s",
            str(_hydrate_exc)[:200],
        )

    # FIX-050: Ground quotes and validate BEFORE tier assignment.
    # _ground_quotes_verbatim() replaces LLM's approximate quotes with verbatim source
    # text. Signal 3 (Content Density, 20% weight) calls _compute_quote_substance() on
    # direct_quote — if grounding runs AFTER tier assignment, quote_substance is computed
    # from the LLM's quote (which may differ in length/structure from the grounded text).
    # Same class of bug as FIX-049 (enrichment after consumer).
    # _validate_extraction_claims() also benefits: it checks direct_quote against
    # source_content, which is more accurate on already-grounded quotes.
    evidence = _ground_quotes_verbatim(evidence)
    evidence = _validate_extraction_claims(evidence)

    # TIER-3 Stage 1: Strip hydrated source_content to keep state lean.
    for ev in evidence:
        ev.pop("source_content", None)

    # FIX-QM26: Unified embedding pass — embed once, use for both relevance
    # scoring AND off-topic filtering. Runs in a thread with asyncio timeout
    # to prevent event-loop starvation from CPU-bound sentence-transformers.
    evidence = await _unified_embedding_pass(evidence, query)

    # Quality tier assignment (post-embedding, reads all 5 signals including
    # nli_self_check_score from prior iteration verification via FIX-051)
    evidence = _assign_quality_tiers(evidence)

    # GRADE-PASS: Assign standardized GRADE certainty ratings to evidence.
    # Examines each evidence statement + source context to determine:
    # high (RCT/meta-analysis, low heterogeneity), moderate (RCT, some concerns),
    # low (observational/high heterogeneity), very low (case reports/expert opinion).
    _grade_enabled = os.getenv("PG_GRADE_STANDARDIZATION", "1") == "1"
    if _grade_enabled and evidence:
        try:
            # FIX-071: Reduced from 20 to 5. GLM-5 truncates output before
            # finishing 20 items, resulting in only 14% rated. Batch of 5
            # needs only 5 lines output — well within GLM-5's reliable range.
            _grade_batch_size = 5
            _grade_updated = 0
            for _gi in range(0, len(evidence), _grade_batch_size):
                _grade_batch = evidence[_gi:_gi + _grade_batch_size]
                _grade_items = "\n".join(
                    f"{j+1}. [{e.get('quality_tier','?')}] "
                    f"Source: {e.get('source_title','')[:60]} | "
                    f"Statement: {e.get('statement','')[:150]}"
                    for j, e in enumerate(_grade_batch)
                )
                # FIX-071B: Retry on empty + reason() for GRADE assignment
                _grade_resp = None
                for _ga in range(2):
                    try:
                        _grade_resp = await client.reason(
                            prompt=(
                                f"Assign GRADE certainty ratings to each evidence item below.\n"
                                f"Ratings: HIGH (systematic review of RCTs, low heterogeneity), "
                                f"MODERATE (RCT with some concerns, or consistent observational), "
                                f"LOW (observational studies, high heterogeneity, indirect evidence), "
                                f"VERY_LOW (case reports, expert opinion, serious limitations).\n\n"
                                f"For each item, output ONLY the number and rating, one per line:\n"
                                f"1. HIGH\n2. MODERATE\n...\n\n"
                                f"EVIDENCE:\n{_grade_items}"
                            ),
                            effort="low",
                            max_tokens=500,
                        )
                        if _grade_resp.content.strip():
                            break
                    except (ValueError, RuntimeError):
                        if _ga == 0:
                            continue
                if not _grade_resp or not _grade_resp.content.strip():
                    continue  # Skip this batch
                # Parse ratings — try structured format first, then extract from reasoning
                import re as _gre
                _ratings = _gre.findall(
                    r"(\d+)\.\s*(HIGH|MODERATE|LOW|VERY_LOW)",
                    _grade_resp.content.upper(),
                )
                # FIX-GLM5: If structured parsing fails, extract from reasoning text.
                # GLM-5 writes "**Item 1:**...Rating: High" or "*Rating:* Low"
                if len(_ratings) < len(_grade_batch) // 2:
                    _text = _grade_resp.content.upper()
                    for _bi, _be in enumerate(_grade_batch):
                        if any(n == str(_bi + 1) for n, _ in _ratings):
                            continue  # Already parsed
                        # Strategy 1: "ITEM N" block followed by "RATING: X"
                        _block = _gre.search(
                            rf"ITEM\s*{_bi+1}[:\s].*?RATING[:\s]*\*?\*?\s*(HIGH|MODERATE|VERY[_\s]LOW|LOW)",
                            _text, _gre.DOTALL,
                        )
                        if _block:
                            _ratings.append((str(_bi + 1), _block.group(1).replace(" ", "_")))
                            continue
                        # Strategy 2: "N." or "ITEM N" followed eventually by rating keyword
                        _loose = _gre.search(
                            rf"(?:ITEM\s*{_bi+1}|\b{_bi+1}\b\.\s*\*?\*?)"
                            rf".*?(HIGH|MODERATE|VERY[_\s]LOW|(?<!\w)LOW(?!\w))",
                            _text, _gre.DOTALL,
                        )
                        if _loose:
                            _ratings.append((str(_bi + 1), _loose.group(1).replace(" ", "_")))
                for _num_str, _rating in _ratings:
                    _idx = int(_num_str) - 1
                    if 0 <= _idx < len(_grade_batch):
                        _grade_batch[_idx]["grade_certainty"] = _rating.lower()
                        _grade_updated += 1

            if _grade_updated > 0:
                logger.info(
                    "[polaris graph] GRADE-PASS: Assigned certainty ratings to "
                    "%d/%d evidence pieces",
                    _grade_updated, len(evidence),
                )
        except Exception as _grade_exc:
            logger.warning(
                "[polaris graph] GRADE-PASS: Failed (non-blocking): %s",
                str(_grade_exc)[:200],
            )

    # FIX-059-D (BUG-4 Part 5): Exact string dedup before SemHash
    # Trivial O(n) pass removes byte-identical quotes that SemHash would
    # also catch, but this is faster and deterministic.
    _seen_quotes: set[str] = set()
    _pre_dedup_count = len(evidence)
    _deduped_evidence: list[EvidencePiece] = []
    for _ev in evidence:
        _eq = _ev.get("direct_quote", "")
        if _eq and _eq in _seen_quotes:
            continue
        if _eq:
            _seen_quotes.add(_eq)
        _deduped_evidence.append(_ev)
    if len(_deduped_evidence) < _pre_dedup_count:
        logger.info(
            "[polaris graph] FIX-059-D: Exact string dedup removed %d/%d evidence",
            _pre_dedup_count - len(_deduped_evidence),
            _pre_dedup_count,
        )
    evidence = _deduped_evidence

    # FIX-047-K13: Per-URL evidence cap (before global dedup)
    evidence = _cap_evidence_per_url(evidence)

    # Change 5: MinHash evidence deduplication
    evidence = _deduplicate_evidence(evidence)

    # OBS-TRACE: Emission 4 — Dedup summary
    tracer = get_tracer()
    if tracer:
        tracer.evidence("analyze", "dedup_summary", len(evidence),
            pre_dedup=_pre_dedup_count, post_dedup=len(evidence))

    # FIX-ENV3: Wire evidence hierarchy into analyzer
    # evidence_hierarchy module exists but was never called anywhere
    try:
        from src.polaris_graph.memory.evidence_hierarchy import store_evidence
        hierarchy_stored = 0
        vector_id = state.get("vector_id", "unknown")
        for e in evidence:
            await store_evidence(
                evidence_id=e.get("evidence_id", ""),
                vector_id=vector_id,
                cluster_id=e.get("fact_category", "other"),
                l0_summary=e.get("statement", "")[:200],
                l1_overview=e.get("statement", ""),
                l2_json=e,
                perspective=e.get("perspective", "Scientific"),
                quality_tier=e.get("quality_tier", "BRONZE"),
                relevance_score=e.get("relevance_score", 0.0),
            )
            hierarchy_stored += 1
        if hierarchy_stored > 0:
            logger.info(
                "[polaris graph] FIX-ENV3: Stored %d evidence pieces in "
                "evidence hierarchy (vector=%s)",
                hierarchy_stored, vector_id,
            )
    except ImportError:
        logger.warning(
            "[polaris graph] FIX-ENV3: evidence_hierarchy module not available — skipping"
        )
    except Exception as hier_exc:
        logger.warning(
            "[polaris graph] FIX-ENV3: Evidence hierarchy storage failed: %s — continuing",
            str(hier_exc)[:200],
        )

    # FIX-H6: Warn when analysis produces zero evidence — possible total analysis failure
    if not evidence:
        logger.warning(
            "[polaris graph] FIX-H6: Analysis returned 0 evidence from %d fetched "
            "sources and %d batches — possible total analysis failure. "
            "Check per-batch error logs above.",
            len(fetched),
            len(batches),
        )

    # QUERY-GATE: When query explicitly requests clinical/academic evidence,
    # hard-exclude non-academic sources from synthesis entirely.
    _clinical_keywords = ["clinical research", "meta-analyses", "systematic review",
                          "randomized controlled", "clinical trials", "peer-reviewed"]
    _query_is_clinical = any(kw in query.lower() for kw in _clinical_keywords)
    if _query_is_clinical and os.getenv("PG_ACADEMIC_ONLY_GATE", "1") == "1":
        # FIX-B3: Gate threshold must be ABOVE default authority (0.5) to
        # actually filter. Old threshold (>= 0.5) equaled the default,
        # making the gate a no-op (53% non-journal sources passed).
        # New: require authority >= 0.6 OR journal_article source_type.
        _gate_threshold = float(os.getenv("PG_ACADEMIC_GATE_THRESHOLD", "0.6"))
        _academic_source_types = {"journal_article", "academic"}
        _before = len(evidence)
        evidence = [
            e for e in evidence
            if (
                _get_domain_authority(e.get("source_url", "")) >= _gate_threshold
                or e.get("source_type") in _academic_source_types
            )
        ]
        _excluded = _before - len(evidence)
        if _excluded > 0:
            logger.info(
                "[polaris graph] QUERY-GATE FIX-B3: Excluded %d non-academic "
                "evidence (authority < %.1f and not journal_article)",
                _excluded, _gate_threshold,
            )

    gold_count = sum(1 for e in evidence if e.get("quality_tier") == "GOLD")
    silver_count = sum(1 for e in evidence if e.get("quality_tier") == "SILVER")
    bronze_count = sum(1 for e in evidence if e.get("quality_tier") == "BRONZE")

    logger.info(
        "[polaris graph] Analysis complete: %d evidence pieces from %d sources. "
        "GOLD=%d, SILVER=%d, BRONZE=%d",
        len(evidence),
        len(fetched),
        gold_count,
        silver_count,
        bronze_count,
    )

    # OBS-4: Trace evidence extraction summary
    tracer = get_tracer()
    if tracer:
        tracer.evidence(
            "analyze", "extracted", len(evidence),
            sources_fetched=len(fetched),
            gold=gold_count,
            silver=silver_count,
            bronze=bronze_count,
        )

        # Emit individual evidence detail (top 50 by tier+relevance)
        top_evidence = sorted(evidence, key=lambda e: (
            {"GOLD": 3, "SILVER": 2, "BRONZE": 1}.get(e.get("quality_tier", ""), 0),
            e.get("relevance_score", 0),
        ), reverse=True)[:50]
        tracer.evidence(
            "analyze", "evidence_detail", len(top_evidence),
            items=[{
                "id": e.get("evidence_id", "")[:20],
                "statement": e.get("statement", "")[:200],
                "quote": e.get("direct_quote", "")[:150],
                "source_url": e.get("source_url", "")[:150],
                "source_title": e.get("source_title", "")[:100],
                "tier": e.get("quality_tier", ""),
                "relevance": round(e.get("relevance_score", 0), 3),
                "perspective": e.get("perspective", ""),
            } for e in top_evidence],
        )

    # (FIX-049: SOTA-11 source confidence moved before tier assignment — see above)

    # G3: Inject uploaded documents as GOLD-tier evidence
    # Documents are loaded with full content by build_and_run() via DocumentIngester.
    # We chunk the full content into ~2000-char segments for evidence extraction.
    uploaded_docs = state.get("uploaded_documents", [])
    if uploaded_docs:
        doc_ev_count = 0
        chunk_size = int(os.getenv("PG_DOC_EVIDENCE_CHUNK_SIZE", "2000"))
        max_chunks_per_doc = int(os.getenv("PG_DOC_MAX_CHUNKS", "20"))
        for doc in uploaded_docs:
            content = doc.get("content", "") or doc.get("content_preview", "")
            if not content:
                continue
            filename = doc.get("filename", "Uploaded Document")
            doc_id = doc.get("doc_id", "unk")

            # Chunk full content into overlapping segments
            chunks = []
            for i in range(0, len(content), chunk_size):
                chunk_text = content[i:i + chunk_size].strip()
                if len(chunk_text) >= 50:  # Skip tiny trailing fragments
                    chunks.append({"text": chunk_text, "chunk_id": f"chunk_{i // chunk_size}"})
            chunks = chunks[:max_chunks_per_doc]

            for chunk in chunks:
                ev_id = f"ev_doc_{doc_id}_{chunk['chunk_id']}"
                doc_evidence = {
                    "id": ev_id,
                    "claim": chunk["text"][:500],
                    "source_url": f"uploaded://{filename}",
                    "source_title": filename,
                    "tier": "gold",
                    "source_type": "uploaded_document",
                    "relevance": 0.95,
                    "authority": 1.0,
                    "perspective": "Primary Source",
                    "direct_quote": chunk["text"],
                }
                evidence.append(doc_evidence)
                doc_ev_count += 1
        if doc_ev_count:
            logger.info(
                "[polaris graph] G3: Added %d GOLD evidence pieces from %d uploaded documents",
                doc_ev_count, len(uploaded_docs),
            )

    # IMP-1 + FIX-CAP1: Preserve full source content for verifier.
    # CRITICAL: Use PG_CONTENT_PER_SOURCE (10K) not PG_VERIFIER_CONTENT_CAP (5K).
    # Analyzer sees 10K chars; verifier must see the SAME 10K chars, otherwise
    # any fact extracted from chars 5001-10000 is guaranteed NOT_SUPPORTED.
    content_cap = PG_CONTENT_PER_SOURCE

    # G3: Include uploaded document content in fetched_content for verifier
    doc_fetched = []
    if uploaded_docs:
        for doc in uploaded_docs:
            doc_content = doc.get("content", "") or doc.get("content_preview", "")
            if doc_content:
                doc_fetched.append({
                    "url": f"uploaded://{doc.get('filename', 'document')}",
                    "title": doc.get("filename", "Uploaded Document"),
                    "content": doc_content[:content_cap] if content_cap > 0 else "",
                })

    # GEMINI-ARCH: Structured data extraction pass (Phase 2B).
    # Gated behind PG_STRUCTURED_DATA_EXTRACTION env var (default '0' = disabled).
    # Runs after evidence extraction; extracts numerical data points from each
    # fetched source for downstream table/chart generation.
    #
    # FIX-E2E-1: Cap sources and total time to prevent runaway extraction.
    # Previous E2E run: 378 calls + 309 retries = 210 min, $3.49 on a single node.
    # Now capped at PG_STRUCTURED_DATA_MAX_SOURCES (default 50) and
    # PG_STRUCTURED_DATA_TOTAL_TIMEOUT (default 1800s = 30 min).
    structured_data: list[dict] = []
    if os.getenv("PG_STRUCTURED_DATA_EXTRACTION", "0") == "1":
        _sd_max_sources = int(os.getenv("PG_STRUCTURED_DATA_MAX_SOURCES", "50"))
        _sd_total_timeout = int(os.getenv("PG_STRUCTURED_DATA_TOTAL_TIMEOUT", "1800"))
        _sd_sources = fetched[:_sd_max_sources]

        logger.info(
            "[polaris graph] GEMINI-ARCH: Structured data extraction enabled — "
            "processing %d/%d fetched sources (cap=%d, timeout=%ds)",
            len(_sd_sources), len(fetched), _sd_max_sources, _sd_total_timeout,
        )
        _sd_semaphore = asyncio.Semaphore(PG_ANALYSIS_CONCURRENCY)

        async def _sd_one(src: dict) -> list[dict]:
            async with _sd_semaphore:
                src_url = src.get("url", "")
                src_content = src.get("content", "")
                if not src_content or len(src_content) < PG_MIN_CONTENT_LENGTH:
                    return []
                # Use first evidence_id from this source, or synthesize one
                src_ev_id = ""
                for ev in evidence:
                    if ev.get("source_url", "") == src_url:
                        src_ev_id = ev.get("evidence_id", "")
                        break
                if not src_ev_id:
                    src_ev_id = f"ev_sd_{hashlib.md5(src_url.encode()).hexdigest()[:12]}"
                return await _extract_structured_data(
                    client, src_content, src_url, src_ev_id,
                )

        # FIX-E2E-1: Use asyncio.wait() with timeout instead of gather().
        # gather() waits for ALL tasks; wait() returns done/pending after timeout.
        _sd_tasks = [asyncio.create_task(_sd_one(s)) for s in _sd_sources]
        if _sd_tasks:
            _sd_done, _sd_pending = await asyncio.wait(
                _sd_tasks, timeout=_sd_total_timeout,
            )
            # Cancel any still-running tasks
            if _sd_pending:
                logger.warning(
                    "[polaris graph] FIX-E2E-1: Structured extraction hit %ds timeout — "
                    "cancelling %d/%d remaining tasks",
                    _sd_total_timeout, len(_sd_pending), len(_sd_tasks),
                )
                for t in _sd_pending:
                    t.cancel()
                # Wait for cancellations to complete
                await asyncio.gather(*_sd_pending, return_exceptions=True)

            # Collect completed results
            for t in _sd_done:
                try:
                    _sd_batch = t.result()
                    if isinstance(_sd_batch, list):
                        structured_data.extend(_sd_batch)
                except Exception:
                    pass  # Individual task failure already logged in _extract_structured_data

        if structured_data:
            logger.info(
                "[polaris graph] GEMINI-ARCH: Extracted %d total structured data "
                "points from %d sources (completed %d/%d tasks)",
                len(structured_data),
                sum(1 for t in (_sd_done if _sd_tasks else set())
                    if not t.cancelled() and not t.exception()
                    and isinstance(t.result(), list) and t.result()),
                len(_sd_done) if _sd_tasks else 0,
                len(_sd_tasks) if _sd_tasks else 0,
            )
    else:
        logger.debug(
            "[polaris graph] GEMINI-ARCH: Structured data extraction DISABLED "
            "(PG_STRUCTURED_DATA_EXTRACTION != '1')"
        )

    # RC-1: Evidence card enrichment (v3 Hybrid)
    if os.getenv("PG_V3_EVIDENCE_CARDS", "0") == "1" and evidence:
        # Build source_contents map from fetched content
        _rc1_source_contents: dict[str, str] = {}
        for _rc1_item in fetched:
            _rc1_url = _rc1_item.get("url", "")
            _rc1_content = _rc1_item.get("content", "")
            if _rc1_url and _rc1_content:
                _rc1_source_contents[_rc1_url] = _rc1_content[:5000]

        evidence = await _enrich_evidence_cards(client, evidence, _rc1_source_contents)

    # FIX-A3: Include failed/total batch counts in return dict
    return {
        "evidence": evidence,
        "content_cache_hits": content_cache_hits,
        "fetched_content": [
            {
                "url": f.get("url", ""),
                "title": f.get("title", ""),
                "content": f.get("content", "")[:content_cap] if content_cap > 0 else "",
            }
            for f in fetched
        ] + doc_fetched,
        "structured_data": structured_data,
        "status": "verifying",
        "failed_batch_count": failed_batches,
        "total_batch_count": len(batches),
    }


async def _fetch_all_content(
    results: list[dict],
    concurrency: int = 10,
) -> tuple[list[dict], int]:
    """Fetch content for all search results using AccessBypass.

    AccessBypass provides: direct fetch -> Unpaywall -> Archive.org -> Sci-Hub.
    Each URL has a hard 60s timeout to prevent hanging.
    Content is cleaned with extract_text_forensic() for HTML sources.

    Returns (fetched_list, cache_hits_count).
    """
    cache_hits = 0

    try:
        from src.tools.access_bypass import AccessBypass

        bypass = AccessBypass()
    except ImportError:
        bypass = None
        logger.warning("[polaris graph] AccessBypass not available, using direct fetch")

    # FIX-QM25: Do NOT use trafilatura for content cleaning in polaris_graph.
    # Jina Reader and Firecrawl already return clean markdown. Trafilatura is
    # CPU-bound (uses lxml/BS4 under the hood) and blocks the asyncio event
    # loop via GIL contention, causing 100+ minute hangs on large HTML docs
    # (e.g., 265K char book chapters from nationalacademies.org).
    # Use lightweight regex-based HTML stripping instead.
    extract_text = None

    semaphore = asyncio.Semaphore(concurrency)

    async def _fetch_one(result: dict) -> dict:
        async with semaphore:
            url = result.get("url", "")
            if not url:
                return {}

            # FIX-B1: Check blocklist BEFORE any fetch attempt
            if _is_blocked_source(url):
                logger.info(
                    "[polaris graph] FIX-B1: Blocked source skipped: %s",
                    url[:80],
                )
                # WAVE-3.5: Trace blocked source
                _blk_tracer = get_tracer()
                if _blk_tracer:
                    _blk_tracer.fetch("analyze", url, "blocked")
                return {}

            # AREA-2: Skip paywall domains — don't waste fetch attempts
            parsed_url = urlparse(url.lower())
            pw_hostname = parsed_url.hostname or ""
            is_paywall = any(
                pw_hostname == d or pw_hostname.endswith("." + d)
                for d in PG_PAYWALL_DOMAINS
            )
            if is_paywall:
                snippet = result.get("snippet", result.get("abstract", ""))
                if snippet and len(snippet) >= PG_MIN_CONTENT_LENGTH_ACADEMIC:
                    logger.info(
                        "[polaris graph] AREA-2: Paywall domain %s — using snippet (%d chars)",
                        pw_hostname, len(snippet),
                    )
                    return {
                        "url": url,
                        "title": result.get("title", ""),
                        "content": snippet,
                        "source_type": result.get("source_type", "web"),
                        "snippet": snippet,
                        "fetch_method": "paywall_snippet",
                    }
                logger.info(
                    "[polaris graph] AREA-2: Paywall domain %s — no usable snippet",
                    pw_hostname,
                )
                # WAVE-3.5: Trace paywall skip
                _pw_tracer = get_tracer()
                if _pw_tracer:
                    _pw_tracer.fetch("analyze", url, "paywall_skip")
                return {}

            # AREA-5: Check content cache before fetching
            nonlocal cache_hits
            cached = await get_cached_content(url)
            if cached and cached.get("content"):
                cache_hits += 1
                logger.debug(
                    "[polaris graph] AREA-5: Cache hit for %s (%d chars)",
                    url[:60], cached.get("content_length", 0),
                )
                return {
                    "url": url,
                    "title": cached.get("title", "") or result.get("title", ""),
                    "content": cached["content"][:PG_MAX_CONTENT_LENGTH],
                    "source_type": result.get("source_type", "web"),
                    "snippet": result.get("snippet", ""),
                    "fetch_method": "cache",
                }

            tracer = get_tracer()
            fetch_start = time.monotonic()
            fetch_status = "failed"
            content_len = 0

            try:
                if bypass:
                    # Hard 60s timeout for the ENTIRE bypass chain
                    # (direct + unpaywall + archive.org + sci-hub)
                    access_result = await asyncio.wait_for(
                        bypass.fetch_with_bypass(url),
                        timeout=60.0,
                    )
                    if access_result.success:
                        # A1.1: Capture raw HTML before cleaning
                        _raw_html_for_cache = access_result.content
                        raw = access_result.content[:PG_MAX_CONTENT_LENGTH]
                        content = _clean_content(raw, url, extract_text)
                        content_len = len(content)
                        fetch_status = "success"
                        # OBS-4: Trace successful fetch
                        if tracer:
                            tracer.fetch(
                                "analyze", url, fetch_status,
                                content_len=content_len,
                                duration_ms=(time.monotonic() - fetch_start) * 1000,
                                method="bypass",
                            )
                        # AREA-5: Cache successful fetch
                        # A1.1: Include raw HTML and readability HTML
                        _readability_html = extract_readability_html(_raw_html_for_cache)
                        await cache_content(
                            url, content[:PG_MAX_CONTENT_LENGTH],
                            title=result.get("title", ""),
                            fetch_method="bypass",
                            raw_html=_raw_html_for_cache,
                            readability_html=_readability_html,
                        )
                        return {
                            "url": url,
                            "title": result.get("title", ""),
                            "content": content[:PG_MAX_CONTENT_LENGTH],
                            "source_type": result.get("source_type", "web"),
                            "snippet": result.get("snippet", ""),
                            "fetch_method": "bypass",
                        }
                else:
                    # Simple direct fetch fallback
                    import aiohttp

                    timeout_cfg = aiohttp.ClientTimeout(total=20)
                    # FETCH-1: Prefer markdown content negotiation
                    headers = {"User-Agent": "Polaris/1.0 (research-agent)"}
                    if PG_PREFER_MARKDOWN:
                        headers["Accept"] = "text/markdown"

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url, timeout=timeout_cfg, ssl=False,
                            headers=headers,
                        ) as resp:
                            if resp.status == 200:
                                content_type = resp.headers.get("Content-Type", "")
                                is_markdown = "text/markdown" in content_type
                                text = await resp.text(errors="replace")

                                if text and len(text) >= PG_MIN_CONTENT_LENGTH:
                                    if is_markdown:
                                        # FETCH-1: Cloudflare returned markdown
                                        content = text[:PG_MAX_CONTENT_LENGTH]
                                        fetch_status = "markdown"
                                        logger.info(
                                            "[polaris graph] FETCH-1: Got markdown for %s "
                                            "(%d chars)",
                                            url[:60],
                                            len(content),
                                        )
                                    else:
                                        # Standard HTML — apply normal cleaning
                                        content = _clean_content(
                                            text[:PG_MAX_CONTENT_LENGTH], url, extract_text
                                        )
                                        fetch_status = "success"

                                    content_len = len(content)
                                    # OBS-4: Trace successful fetch
                                    if tracer:
                                        tracer.fetch(
                                            "analyze", url, fetch_status,
                                            content_len=content_len,
                                            duration_ms=(time.monotonic() - fetch_start) * 1000,
                                            method="direct",
                                            is_markdown=is_markdown,
                                        )
                                    # AREA-5: Cache successful fetch
                                    # A1.1: Include raw HTML and readability HTML
                                    _direct_readability = extract_readability_html(text) if not is_markdown else ""
                                    await cache_content(
                                        url, content[:PG_MAX_CONTENT_LENGTH],
                                        title=result.get("title", ""),
                                        fetch_method="markdown" if is_markdown else "direct",
                                        raw_html=text if not is_markdown else "",
                                        readability_html=_direct_readability,
                                    )
                                    return {
                                        "url": url,
                                        "title": result.get("title", ""),
                                        "content": content[:PG_MAX_CONTENT_LENGTH],
                                        "source_type": result.get("source_type", "web"),
                                        "snippet": result.get("snippet", ""),
                                    }
            except asyncio.TimeoutError:
                fetch_status = "timeout"
                logger.info(
                    "[polaris graph] Fetch timed out (60s) for %s",
                    url[:80],
                )
            except Exception as exc:
                fetch_status = "error"
                # SF-11: Upgrade to WARNING — fetch failures degrade content quality
                logger.warning(
                    "[polaris graph] Fetch FAILED for %s: %s — will use snippet fallback",
                    url[:80],
                    str(exc)[:100],
                )

            # FIX-P4: Retry with trafilatura on primary fetch failure
            if fetch_status in ("timeout", "error"):
                try:
                    import trafilatura
                    _traf_result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: trafilatura.fetch_url(url),
                    )
                    if _traf_result:
                        _traf_content = trafilatura.extract(
                            _traf_result, include_comments=False,
                            include_tables=True, favor_precision=True,
                        )
                        if _traf_content and len(_traf_content) >= PG_MIN_CONTENT_LENGTH:
                            content = _traf_content[:PG_MAX_CONTENT_LENGTH]
                            content_len = len(content)
                            fetch_status = "trafilatura_retry"
                            logger.info(
                                "[polaris graph] FIX-P4: Trafilatura retry SUCCESS for %s (%d chars)",
                                url[:60], content_len,
                            )
                            if tracer:
                                tracer.fetch(
                                    "analyze", url, "trafilatura_retry",
                                    content_len=content_len,
                                    duration_ms=(time.monotonic() - fetch_start) * 1000,
                                    method="trafilatura",
                                )
                            # A1.1: Include raw HTML and readability HTML
                            _traf_readability = extract_readability_html(_traf_result) if _traf_result else ""
                            await cache_content(
                                url, content[:PG_MAX_CONTENT_LENGTH],
                                title=result.get("title", ""),
                                fetch_method="trafilatura",
                                raw_html=_traf_result or "",
                                readability_html=_traf_readability,
                            )
                            return {
                                "url": url,
                                "title": result.get("title", ""),
                                "content": content[:PG_MAX_CONTENT_LENGTH],
                                "source_type": result.get("source_type", "web"),
                                "snippet": result.get("snippet", ""),
                            }
                except Exception as _traf_exc:
                    logger.debug(
                        "[polaris graph] FIX-P4: Trafilatura retry also failed for %s: %s",
                        url[:60], str(_traf_exc)[:100],
                    )

            # SF-12: Fallback to snippet logged at WARNING — quality degradation visible
            snippet = result.get("snippet", result.get("abstract", ""))
            if snippet:
                fetch_status = "snippet_fallback"
                content_len = len(snippet)
                logger.warning(
                    "[polaris graph] Using snippet fallback for %s (%d chars vs full content)",
                    url[:60],
                    len(snippet),
                )

            # OBS-4: Trace fallback/failure
            if tracer:
                tracer.fetch(
                    "analyze", url, fetch_status,
                    content_len=content_len,
                    duration_ms=(time.monotonic() - fetch_start) * 1000,
                    method="fallback",
                )

            # FIX-D3: Mark snippet fallback results so downstream can penalize
            return {
                "url": url,
                "title": result.get("title", ""),
                "content": snippet,
                "source_type": result.get("source_type", "web"),
                "snippet": result.get("snippet", ""),
                "fetch_method": "snippet",
            }

    tasks = [_fetch_one(r) for r in results]
    all_fetched = await asyncio.gather(*tasks)

    fetched = [f for f in all_fetched if f and f.get("content")]

    # Filter out snippet-only sources (< MIN_CONTENT_LENGTH chars)
    # These are too short for meaningful fact extraction and waste LLM calls
    before_filter = len(fetched)
    fetched = [
        f for f in fetched
        if len(f.get("content", "")) >= PG_MIN_CONTENT_LENGTH
    ]

    logger.info(
        "[polaris graph] Fetched content for %d/%d sources "
        "(%d removed for short content, %d from cache)",
        len(fetched),
        len(results),
        before_filter - len(fetched),
        cache_hits,
    )

    # TIER-3 Stage 1: Store fetched content in URL-keyed SQLite store.
    # Content is stored once per URL; evidence dicts reference by source_url only.
    try:
        from src.polaris_graph.memory.source_content_store import (
            store_content as _store_content,
            PG_SOURCE_CONTENT_STORE_ENABLED as _store_enabled,
        )
        if _store_enabled:
            _stored_count = 0
            for f in fetched:
                _url = f.get("url", "")
                _content = f.get("content", "")
                _title = f.get("title", "")
                if _url and _content:
                    success = await _store_content(_url, _content, _title)
                    if success:
                        _stored_count += 1
            if _stored_count:
                logger.info(
                    "[polaris graph] TIER-3: Stored %d/%d source contents in "
                    "content store (dedup from evidence dicts)",
                    _stored_count, len(fetched),
                )
    except Exception as _store_exc:
        logger.debug(
            "[polaris graph] TIER-3: Content store write failed: %s",
            str(_store_exc)[:200],
        )

    # OBS-TRACE: Emission 7 — Fetch summary
    tracer = get_tracer()
    if tracer:
        tracer.evidence("analyze", "fetch_summary", len(fetched),
            total_attempted=len(results), success=len(fetched),
            short_content_removed=before_filter - len(fetched),
            cache_hits=cache_hits)

    return fetched, cache_hits


def _clean_content(raw: str, url: str, extract_fn) -> str:
    """Clean raw content: lightweight HTML stripping for direct-fetch HTML.

    FIX-QM25: Does NOT use trafilatura (CPU-bound, blocks event loop via GIL).
    Jina Reader and Firecrawl already return clean markdown. For the rare
    direct-fetch fallback that returns HTML, uses fast regex stripping.
    """
    import re as _re

    # Cap content to prevent memory issues
    capped = raw[:100_000]

    # Detect HTML by checking for common HTML markers
    lower_start = capped[:500].lower()
    if "<html" in lower_start or "<body" in lower_start or "<!doctype" in lower_start:
        # Lightweight HTML-to-text: strip tags, decode entities, collapse whitespace
        text = _re.sub(r"<script[^>]*>.*?</script>", " ", capped, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"&nbsp;", " ", text)
        text = _re.sub(r"&amp;", "&", text)
        text = _re.sub(r"&lt;", "<", text)
        text = _re.sub(r"&gt;", ">", text)
        text = _re.sub(r"&#\d+;", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()
        if len(text) >= 100:
            return text

    return capped


def _strip_non_article_content(content: str) -> str:
    """FIX-047-K3: Remove non-article content before LLM extraction.

    T047 audit found 24 evidence pieces (9.3%) extracted from cookie consent
    banners, navigation menus, page footers, and other non-article elements.
    This function strips common non-content patterns from fetched text.

    Does NOT use trafilatura (CPU-bound, blocks event loop per FIX-QM25).
    Uses fast regex heuristics instead.
    """
    import re as _re

    if not content or len(content) < 100:
        return content

    lines = content.split("\n")
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            filtered_lines.append(line)
            continue

        lower = stripped.lower()

        # Skip cookie consent / privacy banner lines
        if any(phrase in lower for phrase in (
            "cookie", "we use cookies", "privacy policy", "accept all",
            "reject all", "cookie settings", "consent to", "advertising",
            "track the user", "manage preferences", "gdpr",
        )):
            continue

        # Skip navigation-style lines (short, title case, no punctuation)
        if (
            len(stripped) < 40
            and stripped.istitle()
            and not any(c in stripped for c in ".?!:;,")
            and not any(c.isdigit() for c in stripped)
        ):
            continue

        # Skip lines that are mostly URL paths
        url_char_count = sum(1 for c in stripped if c in "/:?&=.#%")
        if len(stripped) > 10 and url_char_count / len(stripped) > 0.3:
            continue

        # Skip social media sharing buttons and copyright lines
        if any(phrase in lower for phrase in (
            "share on facebook", "share on twitter", "share on linkedin",
            "follow us", "subscribe to", "all rights reserved", "copyright ©",
        )):
            continue

        filtered_lines.append(line)

    result = "\n".join(filtered_lines)

    # Collapse excessive whitespace
    result = _re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


async def _analyze_batch(
    client: OpenRouterClient,
    batch: list[dict],
    query: str,
) -> list[EvidencePiece]:
    """Analyze a batch of sources and extract atomic facts."""
    source_texts = []
    for source in batch:
        content = source.get("content", "")[:PG_CONTENT_PER_SOURCE]
        # FIX-047-K3: Strip non-article content (cookie banners, nav menus)
        # before passing to LLM. T047 audit: 24 evidence pieces from junk.
        content = _strip_non_article_content(content)
        # FIX-H7: Strip markdown artifacts from markdown-fetched content.
        # Jina Reader and Firecrawl return markdown with link syntax, image
        # tags, and header markers that pollute evidence extraction.
        if content and (content.lstrip().startswith("#") or "[" in content[:200]):
            content = _strip_markdown(content)
        source_texts.append(
            f"Source URL: {source.get('url', '')}\n"
            f"Source title: {source.get('title', '')}\n"
            f"Source type: {source.get('source_type', 'web')}\n"
            f"Content:\n{content}\n"
            f"---"
        )

    prompt = f"""Research question: {query}

Analyze the following {len(batch)} sources and extract the TOP 8-15 MOST
relevant atomic facts per source. Focus on the most specific, unique, and
directly relevant numbers, dates, measurements, claims, findings,
regulations, and standards. Quality over quantity.

Sources:
{"".join(source_texts)}"""

    try:
        # Use generate_structured() — reasoning OFF for clean JSON output.
        # reason() + schema causes LLM to put JSON in reasoning_content,
        # which breaks parsing. generate_structured() reliably produces JSON.
        # EXT-3: Keep max_tokens=16384 — with DUR-2 batch_size=3, extraction
        # output for 3 sources × 15 facts × ~150 tokens/fact = ~6750 tokens.
        # 8192 risks truncation. 16384 is safe with truncation recovery as backup.
        parsed = await client.generate_structured(
            prompt=prompt,
            schema=SourceAnalysisBatch,
            system=ANALYSIS_SYSTEM,
            max_tokens=16384,
            timeout=180,
            reasoning_enabled=False,  # FIX-I2b: Evidence extraction is pattern-matching, not reasoning
        )

        evidence: list[EvidencePiece] = []
        for analysis in parsed.analyses:
            # FIX-D3: Determine fetch method and source content for this source
            source_fetch_method = None
            source_content_for_ev = ""
            source_perspective = ""
            source_citation_count = 0
            for src in batch:
                if src.get("url", "") == analysis.source_url:
                    source_fetch_method = src.get("fetch_method")
                    source_content_for_ev = src.get("content", "")
                    # WARN-1 FIX: Capture STORM perspective tag from search result
                    source_perspective = src.get("perspective_source", "")
                    # FIX-048-K2: Propagate citation count from search metadata
                    source_citation_count = src.get("citation_count", 0) or src.get("citationCount", 0)
                    break

            # FIX-D3: Apply snippet quality penalty to source_quality
            source_quality = analysis.source_quality
            if source_fetch_method == "snippet":
                source_quality = max(0.0, source_quality - 0.3)

            for fact in analysis.atomic_facts:
                # Skip facts with no statement (validator couldn't extract one)
                if not fact.statement or len(fact.statement.strip()) < 10:
                    continue
                # FIX-047-K1: Discard junk extractions with short/empty quotes.
                # T047 audit found 28 JUNK pieces with 1-3 word quotes from nav
                # menus, URL slugs, cookie banners, abbreviation tables.
                _quote = (fact.direct_quote or "").strip()
                if len(_quote.split()) < PG_MIN_QUOTE_WORDS:
                    logger.debug(
                        "[polaris graph] FIX-047-K1: Discarding short quote "
                        "(%d words) from %s: '%s'",
                        len(_quote.split()),
                        analysis.source_url[:60],
                        _quote[:80],
                    )
                    continue
                # FIX-047-K1b: Discard quotes that are URL fragments, cookie
                # consent text, or navigation labels (non-content extractions).
                _quote_lower = _quote.lower()
                _is_url_fragment = any(
                    marker in _quote_lower
                    for marker in ("http://", "https://", ".com/", ".gov/", ".org/", ".edu/", "www.")
                )
                _is_cookie_text = any(
                    marker in _quote_lower
                    for marker in ("cookie", "advertising", "track the user", "consent", "privacy policy")
                )
                _is_nav_label = (
                    len(_quote.split()) <= 6
                    and _quote.istitle()
                    and not any(c.isdigit() for c in _quote)
                )
                if _is_url_fragment or _is_cookie_text:
                    logger.debug(
                        "[polaris graph] FIX-047-K1b: Discarding non-content "
                        "quote from %s: '%s'",
                        analysis.source_url[:60],
                        _quote[:80],
                    )
                    continue
                eid = _make_evidence_id(
                    analysis.source_url, fact.statement
                )
                piece = EvidencePiece(
                    evidence_id=eid,
                    source_url=analysis.source_url,
                    source_title=analysis.source_title,
                    source_type=analysis.source_type,
                    direct_quote=_strip_markdown(fact.direct_quote)[:500],  # FIX-059-D (H-09)
                    statement=fact.statement,
                    fact_category=fact.fact_category,
                    relevance_score=fact.relevance_score,
                    quality_tier="UNSCORED",
                    citation_key="",
                    year=analysis.year if analysis.year > 0 else None,
                    authors=analysis.authors,
                    venue=analysis.venue,
                    doi=analysis.doi,
                    # WARN-1 FIX: Prefer STORM perspective_source over LLM-assigned
                    perspective=source_perspective or getattr(fact, "perspective", "Scientific"),
                )
                # RC-1: Propagate fetch_method for ALL sources (not just snippet)
                piece["fetch_method"] = source_fetch_method or "unknown"
                piece["source_quality"] = source_quality
                # FIX-048-K2: Propagate citation count for tier scoring
                piece["citation_count"] = source_citation_count
                # TIER-3 Stage 1: source_content NO LONGER stored in evidence dict.
                # Content lives in source_content_store (SQLite, keyed by URL).
                # Consumers (verifier, hallucination_detector) read from store.

                # FIX-QUOTE: Post-extraction quote validation.
                # Check if the direct_quote actually exists in the source content.
                # If not, the LLM likely embellished — penalize relevance.
                _dq = fact.direct_quote[:200].strip().lower() if fact.direct_quote else ""
                _src_content_raw = ""
                _src_content = ""
                for src in batch:
                    if src.get("url", "") == analysis.source_url:
                        _src_content_raw = src.get("content", "")
                        _src_content = _src_content_raw.lower()
                        break
                if _dq and len(_dq) >= 20 and _src_content:
                    _match_pos = _src_content.find(_dq[:50])
                    if _match_pos < 0:
                        piece["quote_verified"] = False
                        piece["quote_char_start"] = None
                        piece["quote_char_end"] = None
                        # Penalize relevance for unverifiable quotes
                        piece["relevance_score"] = max(
                            0.0, piece.get("relevance_score", 0.5) - 0.2,
                        )
                    else:
                        piece["quote_verified"] = True
                        # A1.3: Compute char offsets in original (non-lowered) content
                        piece["quote_char_start"] = _match_pos
                        # Find full quote extent: try matching progressively longer
                        # substrings of the quote to find the actual end position.
                        _full_dq = fact.direct_quote.strip().lower()
                        _end_pos = _match_pos + len(_dq[:50])
                        _full_match_pos = _src_content.find(_full_dq, _match_pos)
                        if _full_match_pos >= 0:
                            _end_pos = _full_match_pos + len(_full_dq)
                        piece["quote_char_end"] = _end_pos

                evidence.append(piece)

        return evidence

    except Exception as exc:
        # FIX-I2: Enhanced failure logging for root cause diagnosis
        error_type = type(exc).__name__
        error_msg = str(exc)[:300]
        for source in batch:
            logger.error(
                "[polaris graph] Analysis batch FAILED: type=%s, msg=%s, "
                "source_url=%s, content_len=%d",
                error_type,
                error_msg,
                source.get("url", "?")[:80],
                len(source.get("content", "")),
            )
        # FIX-A1: Retry once before accepting empty result
        try:
            logger.info(
                "[polaris graph] FIX-A1: Retrying failed analysis batch "
                "(%d sources) once",
                len(batch),
            )
            parsed = await client.generate_structured(
                prompt=prompt,
                schema=SourceAnalysisBatch,
                system=ANALYSIS_SYSTEM,
                max_tokens=16384,
                timeout=180,
                reasoning_enabled=False,
            )
            evidence_retry: list[EvidencePiece] = []
            for analysis in parsed.analyses:
                # RC-1: Find source content for retry path too
                retry_src_content = ""
                retry_fetch_method = "unknown"
                retry_citation_count = 0
                for src in batch:
                    if src.get("url", "") == analysis.source_url:
                        retry_src_content = src.get("content", "")
                        retry_fetch_method = src.get("fetch_method", "unknown")
                        retry_citation_count = src.get("citation_count", 0) or src.get("citationCount", 0)
                        break
                for fact in analysis.atomic_facts:
                    if not fact.statement or len(fact.statement.strip()) < 10:
                        continue
                    eid = _make_evidence_id(analysis.source_url, fact.statement)
                    piece = EvidencePiece(
                        evidence_id=eid,
                        source_url=analysis.source_url,
                        source_title=analysis.source_title,
                        source_type=analysis.source_type,
                        direct_quote=_strip_markdown(fact.direct_quote)[:500],  # FIX-059-D (H-09)
                        statement=fact.statement,
                        fact_category=fact.fact_category,
                        relevance_score=fact.relevance_score,
                        quality_tier="UNSCORED",
                        citation_key="",
                        year=analysis.year if analysis.year > 0 else None,
                        authors=analysis.authors,
                        venue=analysis.venue,
                        doi=analysis.doi,
                        perspective=getattr(fact, "perspective", "Scientific"),
                    )
                    piece["source_quality"] = analysis.source_quality
                    piece["fetch_method"] = retry_fetch_method
                    piece["citation_count"] = retry_citation_count
                    # TIER-3 Stage 1: source_content stored in content store, not evidence dict.
                    evidence_retry.append(piece)
            logger.info(
                "[polaris graph] FIX-A1: Retry recovered %d evidence pieces",
                len(evidence_retry),
            )
            return evidence_retry
        except Exception as retry_exc:
            logger.error(
                "[polaris graph] FIX-A1: Retry also failed: %s",
                str(retry_exc)[:200],
            )
            return []


def _rank_and_merge(
    web_results: list[dict],
    academic_results: list[dict],
) -> list[dict]:
    """Merge web and academic results with balanced representation.

    Previous approach gave academic a 2x boost, causing 7K+ noisy S2
    papers to drown out 500+ relevant web results.  Now we interleave:
    take top web results first (they're almost always on-topic from
    Serper), then top academic results.
    """
    # Sort each pool by its own relevance
    web_sorted = sorted(
        web_results,
        key=lambda r: r.get("score", 0.5),
        reverse=True,
    )
    # FIX-059-E (H-11): S2 papers without scores default to 0.0, not 0.5.
    # This prevents unscored papers from ranking above genuinely relevant results.
    academic_sorted = sorted(
        academic_results,
        key=lambda r: r.get("score", 0.0),
        reverse=True,
    )

    # Cap academic results to avoid noise domination
    academic_cap = min(len(academic_sorted), MAX_SOURCES_TO_ANALYZE)
    academic_sorted = academic_sorted[:academic_cap]

    # Interleave: 60% web, 40% academic (web results are more on-topic)
    merged: list[dict] = []
    web_idx = 0
    acad_idx = 0
    seen_urls: set[str] = set()

    while len(merged) < MAX_SOURCES_TO_ANALYZE * 2:
        # Take 3 web results
        for _ in range(3):
            if web_idx < len(web_sorted):
                url = web_sorted[web_idx].get("url", "")
                if url not in seen_urls:
                    merged.append(web_sorted[web_idx])
                    seen_urls.add(url)
                web_idx += 1
        # Take 2 academic results
        for _ in range(2):
            if acad_idx < len(academic_sorted):
                url = academic_sorted[acad_idx].get("url", "")
                if url not in seen_urls:
                    merged.append(academic_sorted[acad_idx])
                    seen_urls.add(url)
                acad_idx += 1
        # Stop when both pools exhausted
        if web_idx >= len(web_sorted) and acad_idx >= len(academic_sorted):
            break

    return merged


def _apply_embedding_relevance(
    evidence: list[EvidencePiece],
    query: str,
) -> list[EvidencePiece]:
    """IMP-2: Replace LLM-assigned relevance with embedding-based cosine similarity.

    LLM-assigned scores cluster at midpoints (300/441 identical at 0.70).
    Embedding similarity is deterministic and produces a true continuum.
    Original LLM score is preserved as ``llm_relevance_score`` for debugging.

    Graceful fallback: if embedding fails, keeps LLM scores unchanged.

    FIX-F1: Handles Windows OSError errno 22 (Invalid argument) from long
    cache paths by setting SENTENCE_TRANSFORMERS_HOME to a short path.
    """
    if not evidence:
        return evidence

    def _do_embedding(retry_count: int = 0):
        """Inner embedding logic with optional retry for FIX-F1."""
        from src.utils.embedding_service import embed_text, embed_texts

        # Embed the query once
        query_vec = np.array(embed_text(query))

        # Batch-embed all evidence statements
        statements = [e.get("statement", "") for e in evidence]
        statement_vecs = np.array(embed_texts(statements))

        # Cosine similarity (embeddings are pre-normalized -> dot product)
        similarities = statement_vecs @ query_vec
        return similarities

    try:
        try:
            similarities = _do_embedding()
        except OSError as os_err:
            # FIX-F1: Windows errno 22 (Invalid argument) from long cache paths
            if os_err.errno == errno.EINVAL:
                short_cache = os.getenv(
                    "PG_ST_CACHE_PATH", r"C:\st_cache"
                )
                logger.warning(
                    "[polaris graph] FIX-F1: OSError errno 22 (Windows path issue). "
                    "Setting SENTENCE_TRANSFORMERS_HOME=%s and retrying once.",
                    short_cache,
                )
                os.environ["SENTENCE_TRANSFORMERS_HOME"] = short_cache
                # Force re-import / re-init by clearing singleton
                try:
                    from src.utils import embedding_service as _es_mod
                    _es_mod._embedding_service = None
                    _es_mod.EmbeddingService._instance = None
                except Exception as reset_exc:
                    logger.debug("Embedding singleton reset failed: %s", reset_exc)
                similarities = _do_embedding(retry_count=1)
            else:
                raise

        replaced = 0
        for i, e in enumerate(evidence):
            # Preserve original LLM score
            e["llm_relevance_score"] = e.get("relevance_score", 0.5)
            # Replace with embedding similarity
            e["relevance_score"] = float(round(similarities[i], 4))
            replaced += 1

        # Log score distribution for debugging
        scores = [e["relevance_score"] for e in evidence]
        if scores:
            mean_rel = float(np.mean(scores))
            logger.info(
                "[polaris graph] IMP-2: Embedding relevance applied to %d evidence. "
                "min=%.3f, median=%.3f, max=%.3f, std=%.3f",
                replaced,
                min(scores),
                float(np.median(scores)),
                max(scores),
                float(np.std(scores)),
            )
            # OBS-4: Trace relevance scoring
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "analyze", "relevance_scored", len(evidence),
                    method="embedding",
                    mean_relevance=round(mean_rel, 4),
                )

    except ImportError:
        logger.warning(
            "[polaris graph] IMP-2: EmbeddingService not available — "
            "keeping LLM relevance scores"
        )
    except Exception as exc:
        logger.warning(
            "[polaris graph] IMP-2: Embedding relevance failed: %s — "
            "keeping LLM scores",
            str(exc)[:200],
        )

    return evidence


# FIX-G2: Map non-canonical LLM-generated source_type values to canonical types
_SOURCE_TYPE_ALIASES: dict[str, str] = {
    "government": "government_report",
    "government_regulation": "government_report",
    "government_press_release": "government_report",
    "peer_reviewed_journal": "journal_article",
    "peer_reviewed": "journal_article",
    "research_paper": "journal_article",
    "scientific_article": "journal_article",
    "academic": "journal_article",
    "market_report": "industry_report",
    "industry_blog": "industry_report",
    "technical_report": "industry_report",
    "white_paper": "industry_report",
    "news_article": "news",
    "news_blog": "news",
}


def _compute_quote_substance(quote: str) -> float:
    """FIX-047-K7: Score quote substantiveness (0.0 to 1.0).

    T047 audit root cause: PubMed URL reference was assigned GOLD because
    the single-factor domain_authority * LLM_relevance had no secondary
    validation of quote substance. This function scores the actual content
    quality of the direct_quote.

    Signals:
    - Word count (< 5 words → 0.0, 5-10 → 0.3, 10-20 → 0.6, 20+ → 1.0)
    - Contains numbers/data (concrete evidence)
    - Contains proper sentences (not just fragments)
    - NOT a URL, nav label, or abbreviation
    """
    if not quote:
        return 0.0

    words = quote.split()
    word_count = len(words)

    # Absolute veto: less than 5 words is never substantive
    if word_count < 5:
        return 0.0

    # Word count score (0.0-0.4)
    if word_count >= 20:
        wc_score = 0.4
    elif word_count >= 10:
        wc_score = 0.3
    elif word_count >= 7:
        wc_score = 0.2
    else:
        wc_score = 0.1

    # Contains numbers/measurements (0.0-0.2)
    import re as _re
    has_numbers = bool(_re.search(r"\d+\.?\d*", quote))
    number_score = 0.2 if has_numbers else 0.0

    # Contains sentence structure (has period, question, or is multi-clause) (0.0-0.2)
    has_sentence = "." in quote or "?" in quote or ", " in quote
    sentence_score = 0.2 if has_sentence else 0.0

    # Contains unique type-token ratio (lexical diversity) (0.0-0.2)
    unique_words = set(w.lower() for w in words if len(w) > 2)
    ttr = len(unique_words) / max(1, word_count)
    diversity_score = min(0.2, ttr * 0.3)

    return min(1.0, wc_score + number_score + sentence_score + diversity_score)


def _compute_freshness(ev: dict) -> float:
    """FIX-048-K2: Compute freshness score from publication year.

    Returns 0.0-1.0: current year = 1.0, loses 0.1 per year, min 0.0.
    """
    year = ev.get("year")
    if not year:
        return 0.3  # Unknown year — neutral default
    try:
        year = int(year)
    except (ValueError, TypeError):
        return 0.3
    current_year = 2026
    age = current_year - year
    return max(0.0, min(1.0, 1.0 - age * 0.1))


def _compute_embedding_relevance(ev: dict) -> float:
    """FIX-048-K2: Get embedding-based relevance score.

    Uses the pre-computed relevance_score from _unified_embedding_pass() when
    available (set by IMP-2). Falls back to llm_relevance_score.
    """
    # After _unified_embedding_pass(), relevance_score = embedding cosine similarity.
    # Before that, relevance_score = LLM-assigned score.
    emb_score = ev.get("relevance_score", 0.0)
    if emb_score > 0:
        return float(emb_score)
    return float(ev.get("llm_relevance_score", 0.5))


def _assign_quality_tiers(evidence: list[EvidencePiece]) -> list[EvidencePiece]:
    """FIX-048-K2: Assign quality tiers using 5-signal weighted composite.

    Replaces crude 2-branch if/else with multi-signal composite scoring.
    T047 audit found GOLD assigned to PubMed URL reference (#140) and
    BRONZE to EPA cost data (#19) because only domain_authority * LLM_relevance
    was used. Now uses 5 independent signals:

    | Signal              | Weight | Source                          |
    |---------------------|--------|---------------------------------|
    | Semantic Relevance  | 0.25   | Embedding cosine(claim, query)  |
    | Source Authority     | 0.25   | Domain authority + src_confidence|
    | Content Density      | 0.20   | Quote substance (words, numbers) |
    | Freshness            | 0.10   | Publication year decay           |
    | Factual Grounding    | 0.20   | NLI self-check score (post-verify)|

    Veto rules (force BRONZE): quote < 5 words, substance < 0.2, junk content.
    FIX-D3: Snippet evidence capped at SILVER.
    FIX-G2: Non-canonical source_type normalized.
    NRC-6: Blog/commercial source types get relevance penalty.
    """
    # Signal weights (LAW VI: from env vars)
    w_relevance = float(os.getenv("PG_TIER_W_RELEVANCE", "0.25"))
    w_authority = float(os.getenv("PG_TIER_W_AUTHORITY", "0.25"))
    w_density = float(os.getenv("PG_TIER_W_DENSITY", "0.20"))
    w_freshness = float(os.getenv("PG_TIER_W_FRESHNESS", "0.10"))
    w_grounding = float(os.getenv("PG_TIER_W_GROUNDING", "0.20"))

    # Tier thresholds (LAW VI: from env vars)
    gold_threshold = float(os.getenv("PG_TIER_GOLD_THRESHOLD", "0.65"))
    silver_threshold = float(os.getenv("PG_TIER_SILVER_THRESHOLD", "0.40"))

    # NRC-6: Blog source penalty
    _blog_penalty = float(os.getenv("PG_BLOG_SOURCE_PENALTY", "0.3"))
    _blog_types = frozenset([
        "blog", "commercial", "marketing", "news_blog", "opinion",
        "affiliate", "sponsored",
    ])
    blog_penalized = 0

    # Veto thresholds
    _min_substance_for_silver = float(os.getenv("PG_MIN_SUBSTANCE_FOR_SILVER", "0.2"))
    _min_substance_for_gold = float(os.getenv("PG_MIN_SUBSTANCE_FOR_GOLD", "0.4"))

    # FIX-058D-v2: Read Signal 5 default ONCE before loop (was per-piece, N redundant getenv calls)
    _sig5_default = float(os.getenv("PG_TIER_SIGNAL5_DEFAULT", "0.3"))

    substance_vetoes = 0
    composite_scores: list[float] = []

    for e in evidence:
        # --- Pre-processing: normalize source type ---
        source_type = e.get("source_type", "")
        source_type = _SOURCE_TYPE_ALIASES.get(source_type, source_type)
        e["source_type"] = source_type

        # NRC-6: Apply blog source penalty
        relevance = e.get("relevance_score", 0.5)
        if source_type in _blog_types:
            relevance = relevance * _blog_penalty
            e["relevance_score"] = relevance
            blog_penalized += 1

        # --- Signal 1: Semantic Relevance (0.25) ---
        sig_relevance = _compute_embedding_relevance(e)

        # --- Signal 2: Source Authority (0.25) ---
        source_url = e.get("source_url", "")
        authority = _get_domain_authority(source_url)
        src_confidence = e.get("source_confidence", 0.0)
        if src_confidence > 0:
            authority = 0.6 * authority + 0.4 * src_confidence
        # Authoritative source types get a boost
        authoritative_types = ("journal_article", "government_report", "standard",
                               "industry_report", "book", "academic")
        if source_type in authoritative_types:
            authority = min(1.0, authority + 0.15)
        sig_authority = authority

        # FIX-P4: Demote snippet-only evidence authority by 50%
        if e.get("fetch_method") == "snippet" or e.get("is_snippet"):
            sig_authority *= 0.5

        # FIX-R10: Penalize consumer/commercial domains
        _src_url = e.get("source_url", "")
        if _src_url and _LOW_AUTHORITY_PATTERNS.search(_src_url):
            sig_authority = min(sig_authority, 0.1)
            logger.debug(
                "[polaris graph] FIX-R10: Low authority domain: %s -> authority capped at 0.1",
                _src_url[:60],
            )

        # --- Signal 3: Content Density (0.20) ---
        quote = e.get("direct_quote", "")
        substance = _compute_quote_substance(quote)
        e["quote_substance"] = substance
        sig_density = substance  # Already 0.0-1.0

        # --- Signal 4: Freshness (0.10) ---
        sig_freshness = _compute_freshness(e)

        # --- Signal 5: Factual Grounding (0.20) ---
        # Uses NLI self-check score if available (set by verifier after first pass).
        # On first call (before verification), defaults to 0.3 (slightly pessimistic).
        # FIX-058D: Configurable via PG_TIER_SIGNAL5_DEFAULT env var (LAW VI). Was 0.5 = inflated.
        sig_grounding = float(e.get("nli_self_check_score", _sig5_default))

        # WAVE-3.1: FIX signal storage bug — store computed signals back on evidence
        e["sig_relevance"] = sig_relevance
        e["sig_authority"] = sig_authority
        e["sig_density"] = sig_density
        e["sig_freshness"] = sig_freshness
        e["sig_grounding"] = sig_grounding

        # --- Composite Score ---
        composite = (
            w_relevance * sig_relevance
            + w_authority * sig_authority
            + w_density * sig_density
            + w_freshness * sig_freshness
            + w_grounding * sig_grounding
        )
        e["tier_composite_score"] = round(composite, 4)
        composite_scores.append(composite)

        # --- Tier Assignment ---
        if composite >= gold_threshold:
            tier = "GOLD"
        elif composite >= silver_threshold:
            tier = "SILVER"
        else:
            tier = "BRONZE"

        # FIX-D3: Snippet evidence can never be GOLD
        is_snippet = e.get("fetch_method") == "snippet"
        veto_reason = ""
        if is_snippet and tier == "GOLD":
            tier = "SILVER"
            veto_reason = "snippet_cap"

        # Veto rules: thin quotes force BRONZE
        if substance < _min_substance_for_gold and tier == "GOLD":
            tier = "SILVER"
            substance_vetoes += 1
            veto_reason = "substance<" + str(_min_substance_for_gold)
        if substance < _min_substance_for_silver and tier in ("GOLD", "SILVER"):
            tier = "BRONZE"
            substance_vetoes += 1
            veto_reason = "substance<" + str(_min_substance_for_silver)

        # FIX-P3: Veto vendor name lists masquerading as evidence.
        # If the quote has no sentence-ending punctuation and multiple commas,
        # it's likely a list of names/products, not a factual claim.
        _quote = e.get("direct_quote", "")
        _sentence_ends = len(re.findall(r'[.!?]', _quote))
        _comma_count = _quote.count(',')
        if _sentence_ends < 1 and _comma_count > 3 and tier in ("GOLD", "SILVER"):
            tier = "BRONZE"
            veto_reason = "list_not_prose"
            logger.debug(
                "[polaris graph] FIX-P3: Vetoed %s to BRONZE (list_not_prose): "
                "%d commas, %d sentence endings",
                e.get("evidence_id", "?")[:20], _comma_count, _sentence_ends,
            )

        # Veto: blocked domain (authority=0.0) can never be above BRONZE.
        # Even if other signals compensate, blocked sources are inherently
        # untrustworthy (commercial, affiliate, etc.).
        if sig_authority == 0.0 and tier in ("GOLD", "SILVER"):
            tier = "BRONZE"
            veto_reason = "blocked_domain_zero_authority"

        e["quality_tier"] = tier
        e["veto_reason"] = veto_reason

    # --- Logging ---
    if blog_penalized > 0:
        logger.info(
            "[polaris graph] NRC-6: Applied blog source penalty (%.2f) to %d/%d "
            "evidence pieces before tier assignment",
            _blog_penalty, blog_penalized, len(evidence),
        )

    if substance_vetoes > 0:
        logger.info(
            "[polaris graph] FIX-048-K2: Quote substance veto demoted %d evidence "
            "pieces (min_gold=%.2f, min_silver=%.2f)",
            substance_vetoes, _min_substance_for_gold, _min_substance_for_silver,
        )

    if composite_scores:
        gold_count = sum(1 for e in evidence if e.get("quality_tier") == "GOLD")
        silver_count = sum(1 for e in evidence if e.get("quality_tier") == "SILVER")
        bronze_count = sum(1 for e in evidence if e.get("quality_tier") == "BRONZE")
        import statistics
        logger.info(
            "[polaris graph] FIX-048-K2: 5-signal tier scoring: %d GOLD, %d SILVER, "
            "%d BRONZE (composite: mean=%.3f, median=%.3f, std=%.3f, "
            "thresholds: gold=%.2f, silver=%.2f)",
            gold_count, silver_count, bronze_count,
            statistics.mean(composite_scores),
            statistics.median(composite_scores),
            statistics.stdev(composite_scores) if len(composite_scores) > 1 else 0.0,
            gold_threshold, silver_threshold,
        )

    # OBS-TRACE: Emission 3 — Tier signal distribution
    tracer = get_tracer()
    if tracer:
        import statistics as _tier_stats
        # FIX-P6: Use actual stored key names (sig_* not semantic_*/source_*/etc)
        signal_names = ["sig_relevance", "sig_authority", "sig_density", "sig_freshness", "sig_grounding"]
        signal_stats = {}
        for sn in signal_names:
            vals = [e.get(sn, 0.0) for e in evidence if e.get(sn) is not None]
            if vals:
                sv = sorted(vals)
                signal_stats[sn] = {"min": round(sv[0], 3), "median": round(sv[len(sv)//2], 3),
                                    "max": round(sv[-1], 3), "count": len(sv)}
        tracer.evidence("analyze", "tier_signal_distribution", len(evidence),
            signal_stats=signal_stats,
            tier_counts={"GOLD": sum(1 for e in evidence if e.get("quality_tier") == "GOLD"),
                         "SILVER": sum(1 for e in evidence if e.get("quality_tier") == "SILVER"),
                         "BRONZE": sum(1 for e in evidence if e.get("quality_tier") == "BRONZE")})

        # WAVE-3.2: Per-evidence scoring detail (ALL evidence, no cap)
        tracer.evidence("analyze", "tier_scoring_detail", len(evidence),
            scores=[{
                "id": e.get("evidence_id", ""),
                "tier": e.get("quality_tier", ""),
                "composite": round(e.get("tier_composite_score", 0), 4),
                "sig_relevance": round(e.get("sig_relevance", 0), 4),
                "sig_authority": round(e.get("sig_authority", 0), 4),
                "sig_density": round(e.get("sig_density", 0), 4),
                "sig_freshness": round(e.get("sig_freshness", 0), 4),
                "sig_grounding": round(e.get("sig_grounding", 0), 4),
                "veto_reason": e.get("veto_reason", ""),
                "source_url": e.get("source_url", ""),
                "statement": e.get("statement", ""),
            } for e in evidence])

    return evidence


def _filter_offtopic_evidence(
    evidence: list[EvidencePiece],
    query: str,
) -> list[EvidencePiece]:
    """FIX-B3: Remove evidence with low embedding similarity to the query.

    Uses cosine similarity between each evidence statement and the query.
    Evidence below PG_OFFTOPIC_THRESHOLD is removed as off-topic.

    Graceful fallback: if embedding fails, returns evidence unchanged.
    """
    if not evidence:
        return evidence

    threshold = PG_OFFTOPIC_THRESHOLD

    # FIX-V9: Adaptive off-topic threshold — if median similarity is low
    # (narrow topic with few matching terms), lower threshold to preserve diversity
    adaptive_enabled = os.getenv("PG_OFFTOPIC_ADAPTIVE", "0") == "1"

    try:
        from src.utils.embedding_service import embed_text, embed_texts

        query_vec = np.array(embed_text(query))
        statements = [e.get("statement", "") for e in evidence]
        statement_vecs = np.array(embed_texts(statements))

        # Cosine similarity (embeddings are pre-normalized -> dot product)
        similarities = statement_vecs @ query_vec

        # FIX-V9: Adaptive threshold — lower when median similarity is low
        if adaptive_enabled:
            median_sim = float(np.median(similarities))
            if median_sim < threshold:
                old_threshold = threshold
                threshold = max(0.10, median_sim - 0.05)
                logger.info(
                    "[polaris graph] FIX-V9: Adaptive off-topic threshold: "
                    "median_sim=%.3f < base=%.3f, lowered to %.3f",
                    median_sim, old_threshold, threshold,
                )

        before_count = len(evidence)
        filtered = []
        for i, e in enumerate(evidence):
            if float(similarities[i]) >= threshold:
                filtered.append(e)

        removed_count = before_count - len(filtered)
        if removed_count > 0:
            logger.info(
                "[polaris graph] FIX-B3: Off-topic filter removed %d/%d evidence "
                "(threshold=%.2f)",
                removed_count,
                before_count,
                threshold,
            )
            # OBS-4: Trace off-topic filtering
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "analyze", "offtopic_filtered", len(filtered),
                    removed=removed_count,
                    threshold=threshold,
                )
        else:
            logger.info(
                "[polaris graph] FIX-B3: Off-topic filter passed all %d evidence "
                "(threshold=%.2f)",
                before_count,
                threshold,
            )

        return filtered

    except ImportError:
        logger.warning(
            "[polaris graph] FIX-B3: EmbeddingService not available — "
            "skipping off-topic filter"
        )
        return evidence
    except Exception as exc:
        logger.warning(
            "[polaris graph] FIX-B3: Off-topic filter failed: %s — skipping",
            str(exc)[:200],
        )
        return evidence


async def _unified_embedding_pass(
    evidence: list[EvidencePiece],
    query: str,
    timeout_seconds: int = 180,
) -> list[EvidencePiece]:
    """FIX-QM26: Single embedding pass for both relevance scoring and off-topic filtering.

    Previously, _apply_embedding_relevance() and _filter_offtopic_evidence() each
    independently embedded all evidence statements (2x redundant work). This function:
    1. Embeds query + all statements ONCE
    2. Uses cosine similarities for relevance scoring (IMP-2)
    3. Uses same similarities for off-topic filtering (FIX-B3)
    4. Runs in a thread with asyncio timeout to prevent event-loop starvation

    Graceful fallback: if embedding fails or times out, returns evidence unchanged
    with original LLM scores.
    """
    if not evidence:
        return evidence

    def _do_embed_and_score():
        """Synchronous embedding + scoring, runs in thread pool."""
        from src.utils.embedding_service import embed_text, embed_texts

        logger.info(
            "[polaris graph] FIX-QM26: Starting unified embedding for %d evidence pieces...",
            len(evidence),
        )
        t0 = time.time()

        # Embed query once
        query_vec = np.array(embed_text(query))

        # Batch-embed all evidence statements once
        statements = [e.get("statement", "") for e in evidence]
        statement_vecs = np.array(embed_texts(statements))

        # Cosine similarity (embeddings are pre-normalized -> dot product)
        similarities = statement_vecs @ query_vec

        elapsed = time.time() - t0
        logger.info(
            "[polaris graph] FIX-QM26: Embedding complete in %.1fs for %d pieces. "
            "sim min=%.3f, median=%.3f, max=%.3f",
            elapsed,
            len(evidence),
            float(np.min(similarities)),
            float(np.median(similarities)),
            float(np.max(similarities)),
        )
        return similarities

    try:
        import asyncio

        logger.info(
            "[polaris graph] FIX-QM26: Launching embedding in thread pool "
            "(timeout=%ds, %d evidence)...",
            timeout_seconds,
            len(evidence),
        )
        loop = asyncio.get_running_loop()
        similarities = await asyncio.wait_for(
            loop.run_in_executor(None, _do_embed_and_score),
            timeout=timeout_seconds,
        )

        # --- IMP-2: Apply embedding relevance scores ---
        replaced = 0
        for i, e in enumerate(evidence):
            e["llm_relevance_score"] = e.get("relevance_score", 0.5)
            e["relevance_score"] = float(round(similarities[i], 4))
            replaced += 1

        scores = [e["relevance_score"] for e in evidence]
        if scores:
            logger.info(
                "[polaris graph] IMP-2: Embedding relevance applied to %d evidence. "
                "min=%.3f, median=%.3f, max=%.3f, std=%.3f",
                replaced,
                min(scores),
                float(np.median(scores)),
                max(scores),
                float(np.std(scores)),
            )
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "analyze", "relevance_scored", len(evidence),
                    method="embedding",
                    mean_relevance=round(float(np.mean(scores)), 4),
                )

        # --- FIX-B3: Off-topic filtering using same similarities ---
        threshold = PG_OFFTOPIC_THRESHOLD

        # FIX-V9: Adaptive off-topic threshold (applied in unified pass)
        adaptive_enabled_unified = os.getenv("PG_OFFTOPIC_ADAPTIVE", "0") == "1"
        if adaptive_enabled_unified:
            median_sim = float(np.median(similarities))
            if median_sim < threshold:
                old_threshold = threshold
                threshold = max(0.10, median_sim - 0.05)
                logger.info(
                    "[polaris graph] FIX-V9: Adaptive off-topic threshold: "
                    "median_sim=%.3f < base=%.3f, lowered to %.3f",
                    median_sim, old_threshold, threshold,
                )

        before_count = len(evidence)
        filtered = [
            e for i, e in enumerate(evidence)
            if float(similarities[i]) >= threshold
        ]
        removed_count = before_count - len(filtered)

        if removed_count > 0:
            logger.info(
                "[polaris graph] FIX-B3: Off-topic filter removed %d/%d evidence "
                "(threshold=%.2f)",
                removed_count,
                before_count,
                threshold,
            )
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "analyze", "offtopic_filtered", len(filtered),
                    removed=removed_count,
                    threshold=threshold,
                )
        else:
            logger.info(
                "[polaris graph] FIX-B3: Off-topic filter passed all %d evidence "
                "(threshold=%.2f)",
                before_count,
                threshold,
            )

        return filtered

    except asyncio.TimeoutError:
        logger.warning(
            "[polaris graph] FIX-QM26: Embedding timed out after %ds — "
            "keeping LLM scores, skipping off-topic filter",
            timeout_seconds,
        )
        return evidence
    except OSError as os_err:
        if os_err.errno == errno.EINVAL:
            # FIX-F1: Windows errno 22 — try short cache path and retry
            short_cache = os.getenv("PG_ST_CACHE_PATH", r"C:\st_cache")
            logger.warning(
                "[polaris graph] FIX-F1: OSError errno 22. "
                "Setting SENTENCE_TRANSFORMERS_HOME=%s, falling back to LLM scores.",
                short_cache,
            )
            os.environ["SENTENCE_TRANSFORMERS_HOME"] = short_cache
        else:
            logger.warning(
                "[polaris graph] FIX-QM26: OSError during embedding: %s — "
                "keeping LLM scores",
                str(os_err)[:200],
            )
        return evidence
    except ImportError:
        logger.error(
            "[polaris graph] FIX-A2: EmbeddingService not available — "
            "IMP-2 embedding relevance DISABLED. "
            "Install sentence-transformers to enable."
        )
        # BUG-4 FIX: Apply same keyword fallback as generic Exception path
        # instead of returning unfiltered evidence
        if query:
            query_words = set(query.lower().split())
            before = len(evidence)
            evidence = [
                e for e in evidence
                if len(query_words & set(e.get("statement", "").lower().split())) >= 2
            ]
            removed = before - len(evidence)
            if removed > 0:
                logger.info(
                    "[polaris graph] BUG-4 FIX: Keyword fallback removed %d/%d "
                    "evidence (required 2+ query word overlap)",
                    removed, before,
                )
        return evidence
    except Exception as exc:
        logger.error(
            "[polaris graph] FIX-A2: Embedding failed: %s — "
            "keeping LLM scores, applying keyword fallback filter",
            str(exc)[:200],
        )
        # FIX-A2: Basic keyword fallback instead of keeping all unfiltered
        if query:
            query_words = set(query.lower().split())
            before = len(evidence)
            evidence = [
                e for e in evidence
                if len(query_words & set(e.get("statement", "").lower().split())) >= 2
            ]
            removed = before - len(evidence)
            if removed > 0:
                logger.info(
                    "[polaris graph] FIX-A2: Keyword fallback removed %d/%d "
                    "evidence (required 2+ query word overlap)",
                    removed, before,
                )
        return evidence


def _validate_extraction_claims(evidence: list[EvidencePiece]) -> list[EvidencePiece]:
    """NRC-5: Post-extraction validation of evidence claims.

    For each evidence piece:
    1. Verify direct_quote is approximately found in source_content (fuzzy match).
       If not found and source_content exists, mark quote_verified=False.
    2. Detect claim inflation: if a single cross-reference claim has > 20
       evidence_ids, flag as suspicious and cap at 10 most relevant.

    Returns the evidence list with quote_verified flags updated.
    """
    max_claim_evidence = int(os.getenv("PG_MAX_EVIDENCE_PER_CLAIM", "20"))
    validated = 0
    unverified = 0

    for ev in evidence:
        quote = ev.get("direct_quote", "")
        content = ev.get("source_content", "")

        if not quote or not content:
            continue

        # Check if first 50 chars of quote appear in content (case-insensitive)
        quote_prefix = quote[:50].lower().strip()
        if len(quote_prefix) >= 10 and quote_prefix not in content.lower():
            # Also try checking individual significant words (fuzzy match)
            quote_words = {
                w.lower() for w in quote[:100].split()
                if len(w) > 4
            }
            if quote_words:
                content_lower = content.lower()
                matching_words = sum(1 for w in quote_words if w in content_lower)
                match_ratio = matching_words / len(quote_words)
                if match_ratio < 0.5:
                    ev["quote_verified"] = False
                    unverified += 1
                else:
                    ev["quote_verified"] = True
                    validated += 1
            else:
                ev["quote_verified"] = True
                validated += 1
        else:
            ev["quote_verified"] = True
            validated += 1

    if unverified > 0:
        logger.warning(
            "[polaris graph] NRC-5: %d/%d evidence pieces have unverified quotes "
            "(direct_quote not found in source_content)",
            unverified,
            validated + unverified,
        )
    elif validated > 0:
        logger.info(
            "[polaris graph] NRC-5: All %d evidence quotes verified against source_content",
            validated,
        )

    # NRC-5 Part 2: Claim inflation detection
    # Group evidence by source_url. If a single source has > max_claim_evidence
    # pieces, cap at the most relevant to prevent citation inflation from
    # paywall-blocked or LLM-fabricated sources.
    if max_claim_evidence > 0 and len(evidence) > max_claim_evidence:
        source_groups: dict[str, list[int]] = {}
        for idx, ev in enumerate(evidence):
            src_url = ev.get("source_url", "")
            if not src_url:
                continue  # Skip evidence without source_url entirely
            domain = urlparse(src_url).netloc or src_url
            source_groups.setdefault(domain, []).append(idx)

        capped_indices: set[int] = set()
        inflation_capped = 0
        for src_url, indices in source_groups.items():
            if len(indices) > max_claim_evidence:
                # Sort by relevance_score descending, keep top N
                sorted_indices = sorted(
                    indices,
                    key=lambda i: evidence[i].get("relevance_score", 0.0),
                    reverse=True,
                )
                keep = set(sorted_indices[:max_claim_evidence])
                drop = set(sorted_indices[max_claim_evidence:])
                capped_indices.update(drop)
                inflation_capped += len(drop)
                logger.info(
                    "[polaris graph] NRC-5: Source %s had %d evidence pieces, "
                    "capped to %d most relevant",
                    src_url[:80], len(indices), max_claim_evidence,
                )

        if inflation_capped > 0:
            evidence = [
                ev for idx, ev in enumerate(evidence)
                if idx not in capped_indices
            ]
            logger.info(
                "[polaris graph] NRC-5: Claim inflation capping removed %d "
                "evidence pieces (%d remaining)",
                inflation_capped, len(evidence),
            )

    return evidence


def _ground_quotes_verbatim(evidence: list[EvidencePiece]) -> list[EvidencePiece]:
    """FIX-047I: Replace LLM-generated quotes with verbatim source text.

    Implements the LangExtract deterministic quoting pattern:
    - Uses the LLM's approximate quote as a search anchor
    - Finds the best-matching substring in source_content
    - Replaces the LLM quote with the verbatim source text

    This eliminates the 3.2% embellishment rate where short LLM quotes
    (1-3 words) were expanded into longer claims. After grounding, all
    quotes are provably verbatim from the source.
    """
    grounded = 0
    failed = 0

    for ev in evidence:
        quote = ev.get("direct_quote", "")
        content = ev.get("source_content", "")

        if not quote or not content or len(quote) < 10:
            continue

        content_lower = content.lower()
        quote_lower = quote.lower().strip()

        # Strategy 1: Exact substring match (most quotes)
        idx = content_lower.find(quote_lower)
        if idx >= 0:
            # Replace with verbatim text (preserving original casing)
            ev["direct_quote"] = content[idx:idx + len(quote)]
            ev["quote_grounded"] = True
            grounded += 1
            continue

        # Strategy 2: Progressive prefix match (handles LLM truncation)
        found = False
        for prefix_len in [80, 60, 40, 25]:
            if prefix_len >= len(quote_lower):
                continue
            prefix = quote_lower[:prefix_len]
            idx = content_lower.find(prefix)
            if idx >= 0:
                # Found prefix — extract verbatim text of similar length
                end = min(len(content), idx + len(quote) + 50)
                # Find sentence boundary near expected end
                candidate = content[idx:end]
                # Trim at sentence boundary (period, exclamation, question mark)
                for punct in ['. ', '.\n', '! ', '? ']:
                    punct_idx = candidate.find(punct, len(quote) - 20)
                    if punct_idx > 0:
                        candidate = candidate[:punct_idx + 1]
                        break
                else:
                    # No sentence boundary found — take original quote length
                    # FIX-059-D (H-07): Extend to next word boundary to avoid mid-word cuts
                    end_pos = idx + len(quote)
                    _space_pos = content.find(' ', end_pos)
                    if _space_pos != -1 and _space_pos - end_pos < 50:
                        end_pos = _space_pos
                    candidate = content[idx:end_pos]

                ev["direct_quote"] = candidate.strip()
                ev["quote_grounded"] = True
                grounded += 1
                found = True
                break

        if not found:
            # Strategy 3: Keyword density search (last resort)
            words = [w.lower() for w in quote.split() if len(w) > 4]
            if len(words) >= 3:
                best_idx = -1
                best_hits = 0
                # Scan content in 200-char windows
                for scan_idx in range(0, len(content_lower) - 200, 100):
                    # FIX-059-D (H-08): Snap window start to word boundary
                    _win_start = scan_idx
                    if _win_start > 0:
                        _sp = content_lower.rfind(' ', max(0, _win_start - 20), _win_start)
                        if _sp != -1:
                            _win_start = _sp + 1
                    window = content_lower[_win_start:_win_start + 200]
                    hits = sum(1 for w in words if w in window)
                    if hits > best_hits:
                        best_hits = hits
                        best_idx = scan_idx

                if best_hits >= len(words) * 0.6 and best_idx >= 0:
                    # FIX-059-D (H-08): Snap extraction start to word boundary
                    _ext_start = best_idx
                    if _ext_start > 0:
                        _sp2 = content.rfind(' ', max(0, _ext_start - 20), _ext_start)
                        if _sp2 != -1:
                            _ext_start = _sp2 + 1
                    _ext_end = _ext_start + len(quote) + 30
                    # FIX-059-D (H-07): Extend to word boundary on extraction end
                    _sp3 = content.find(' ', _ext_end)
                    if _sp3 != -1 and _sp3 - _ext_end < 50:
                        _ext_end = _sp3
                    verbatim = content[_ext_start:_ext_end].strip()
                    # Trim to sentence boundary
                    for punct in ['. ', '.\n']:
                        punct_idx = verbatim.find(punct, len(quote) - 20)
                        if punct_idx > 0:
                            verbatim = verbatim[:punct_idx + 1]
                            break
                    ev["direct_quote"] = verbatim
                    ev["quote_grounded"] = True
                    grounded += 1
                else:
                    ev["quote_grounded"] = False
                    failed += 1
            else:
                ev["quote_grounded"] = False
                failed += 1

    if grounded > 0 or failed > 0:
        logger.info(
            "[polaris graph] FIX-047I: Deterministic quoting: %d/%d quotes "
            "grounded verbatim (%d could not be matched)",
            grounded,
            grounded + failed,
            failed,
        )

    return evidence


def _cap_evidence_per_url(evidence: list[EvidencePiece]) -> list[EvidencePiece]:
    """FIX-048-K13: Semantic dedup per source URL using SemHash.

    Replaces simple count cap with semantic deduplication. For each URL
    group, uses SemHash (Model2Vec static embeddings) to detect near-duplicate
    statements and keep only semantically unique evidence.

    Falls back to count-based cap if SemHash is unavailable or fails.

    Env vars:
    - PG_SEMHASH_DEDUP_ENABLED: Enable semantic dedup (default: 1)
    - PG_SEMHASH_SIMILARITY_THRESHOLD: Dedup threshold 0-1 (default: 0.85)
    - PG_MAX_EVIDENCE_PER_URL: Count cap fallback (default: 5)
    """
    max_per_url = int(os.getenv("PG_MAX_EVIDENCE_PER_URL", "5"))
    semhash_enabled = os.getenv("PG_SEMHASH_DEDUP_ENABLED", "1") == "1"
    semhash_threshold = float(os.getenv("PG_SEMHASH_SIMILARITY_THRESHOLD", "0.85"))

    if max_per_url <= 0 or len(evidence) <= 1:
        return evidence

    # Group by source URL
    from collections import defaultdict
    url_groups: dict[str, list[EvidencePiece]] = defaultdict(list)
    for e in evidence:
        url = e.get("source_url", "unknown")
        url_groups[url].append(e)

    # Try SemHash semantic dedup if enabled
    if semhash_enabled:
        result = _semhash_dedup_per_url(url_groups, semhash_threshold, max_per_url)
        if result is not None:
            return result

    # Fallback: count-based cap
    return _count_cap_per_url(url_groups, max_per_url, len(evidence))


def _semhash_dedup_per_url(
    url_groups: dict[str, list],
    threshold: float,
    max_per_url: int,
) -> list[EvidencePiece] | None:
    """Run SemHash self_deduplicate within each URL group.

    Returns deduplicated evidence list, or None if SemHash unavailable
    (caller should fall back to count cap).
    """
    try:
        from semhash import SemHash
    except ImportError:
        logger.info(
            "[polaris graph] FIX-048-K13: SemHash not installed — "
            "falling back to count-based cap. Install with: pip install semhash"
        )
        return None

    deduped: list[EvidencePiece] = []
    total_removed = 0
    groups_deduped = 0
    t0 = time.time()

    for url, pieces in url_groups.items():
        if len(pieces) <= 1:
            deduped.extend(pieces)
            continue

        # Extract statements for SemHash
        statements = [p.get("statement", "") for p in pieces]

        try:
            semhash_index = SemHash.from_records(records=statements)
            result = semhash_index.self_deduplicate(threshold=threshold)

            # Map selected records back to evidence pieces.
            # SemHash result.selected contains the deduplicated text records.
            selected_stmts = list(result.selected)
            selected_set = set(selected_stmts)
            kept = []
            for i, piece in enumerate(pieces):
                if statements[i] in selected_set:
                    kept.append(piece)
                    selected_set.discard(statements[i])

            # Apply count cap on top of semantic dedup
            if len(kept) > max_per_url:
                kept.sort(
                    key=lambda e: (
                        e.get("relevance_score", 0.0),
                        len(e.get("statement", "")),
                    ),
                    reverse=True,
                )
                kept = kept[:max_per_url]

            removed_count = len(pieces) - len(kept)
            total_removed += removed_count
            deduped.extend(kept)
            if removed_count > 0:
                groups_deduped += 1

        except Exception as exc:
            logger.debug(
                "[polaris graph] FIX-048-K13: SemHash failed for URL %s (%d pieces): %s — "
                "falling back to count cap for this group",
                url[:60], len(pieces), str(exc)[:100],
            )
            # Count-cap fallback for this single group
            if len(pieces) > max_per_url:
                sorted_pieces = sorted(
                    pieces,
                    key=lambda e: (
                        e.get("relevance_score", 0.0),
                        len(e.get("statement", "")),
                    ),
                    reverse=True,
                )
                deduped.extend(sorted_pieces[:max_per_url])
                total_removed += len(pieces) - max_per_url
                groups_deduped += 1
            else:
                deduped.extend(pieces)

    elapsed = time.time() - t0
    total_input = sum(len(p) for p in url_groups.values())
    if total_removed > 0:
        logger.info(
            "[polaris graph] FIX-048-K13: SemHash dedup removed %d/%d evidence "
            "pieces (%d URL groups deduped, threshold=%.2f, %.1fs)",
            total_removed, total_input, groups_deduped, threshold, elapsed,
        )
    else:
        logger.info(
            "[polaris graph] FIX-048-K13: SemHash dedup kept all %d evidence "
            "(no semantic duplicates above threshold=%.2f, %.1fs)",
            total_input, threshold, elapsed,
        )

    return deduped


def _count_cap_per_url(
    url_groups: dict[str, list],
    max_per_url: int,
    total_evidence: int,
) -> list[EvidencePiece]:
    """Fallback: simple count cap per URL (pre-FIX-048 behavior)."""
    capped: list[EvidencePiece] = []
    total_removed = 0
    for url, pieces in url_groups.items():
        if len(pieces) <= max_per_url:
            capped.extend(pieces)
        else:
            sorted_pieces = sorted(
                pieces,
                key=lambda e: (
                    e.get("relevance_score", 0.0),
                    len(e.get("statement", "")),
                ),
                reverse=True,
            )
            capped.extend(sorted_pieces[:max_per_url])
            total_removed += len(pieces) - max_per_url

    if total_removed > 0:
        logger.info(
            "[polaris graph] FIX-047-K13: Per-URL count cap (%d) removed %d/%d "
            "evidence pieces (%d URLs capped)",
            max_per_url, total_removed, total_evidence,
            sum(1 for pieces in url_groups.values() if len(pieces) > max_per_url),
        )

    return capped


def _deduplicate_evidence(evidence: list[EvidencePiece]) -> list[EvidencePiece]:
    """Deduplicate evidence using MinHash from ContentDeduplicator.

    Same fact from different sources creates duplicate evidence.
    MinHash efficiently detects near-duplicate statements.
    Controlled by PG_EVIDENCE_DEDUP_ENABLED env var.
    """
    if not PG_EVIDENCE_DEDUP_ENABLED or len(evidence) <= 1:
        return evidence

    try:
        from src.utils.content_deduplicator import ContentDeduplicator

        dedup = ContentDeduplicator()
        items = [
            {"content": e.get("statement", ""), **e}
            for e in evidence
        ]
        result = dedup.deduplicate(items, content_key="content")

        if result.unique_count < len(evidence):
            logger.info(
                "[polaris graph] Evidence dedup: %d -> %d unique "
                "(%d exact, %d near-duplicates removed)",
                len(evidence),
                result.unique_count,
                result.exact_duplicates,
                result.near_duplicates,
            )

        # WAVE-3.3: Dedup detail trace
        tracer = get_tracer()
        if tracer:
            dup_pairs = []
            if hasattr(result, "duplicates"):
                for d in result.duplicates:
                    dup_pairs.append({
                        "original_idx": getattr(d, "original_index", 0),
                        "duplicate_idx": getattr(d, "duplicate_index", 0),
                        "similarity": round(getattr(d, "similarity", 0), 3),
                        "type": getattr(d, "duplicate_type", ""),
                    })
            tracer.evidence("analyze", "dedup_detail", len(evidence),
                before_count=len(evidence),
                after_count=result.unique_count,
                exact_removed=result.exact_duplicates,
                near_removed=result.near_duplicates,
                minhash_pairs=dup_pairs[:200])

        # Convert back to EvidencePiece format (remove the extra "content" key)
        deduped: list[EvidencePiece] = []
        for item in result.unique_items:
            # Remove the "content" key we added for dedup
            item.pop("content", None)
            deduped.append(item)

        return deduped

    except ImportError:
        logger.warning(
            "[polaris graph] ContentDeduplicator not available — skipping dedup"
        )
        return evidence
    except Exception as exc:
        logger.warning(
            "[polaris graph] Evidence dedup failed: %s — skipping",
            str(exc)[:200],
        )
        return evidence


def _make_evidence_id(url: str, statement: str) -> str:
    """Generate deterministic evidence ID."""
    raw = f"{url}:{statement}"
    return "ev_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
