"""
Live retriever — HONEST-REBUILD.

Performs REAL retrieval using Serper (web) + Semantic Scholar (academic)
+ OpenAlex (canonicalization) and wires every candidate URL through the
honest-rebuild modules in one clean path:

    1. Serper + Semantic Scholar bulk search
    2. Convert hits into SearchCandidate
    3. scope_query_validator on amplified queries
    4. prefetch_offtopic_filter on candidates (if embedder available)
    5. Fetch each URL's content (basic http.get) with size cap
    6. Classify each with tier_classifier
    7. Return list[CorpusSource] + evidence rows

This is the live alternative to the pre-rebuild searcher.py path,
which had complex dependencies into src/agents/ that we're trying
to archive. Keeping the live retriever in polaris_graph/retrieval/
means the honest-rebuild pipeline is self-contained.

Performance: rate-limited, caps total candidates. Designed to be
called ONCE per research question (not repeatedly in a loop).
"""
from __future__ import annotations

import logging
import math
import os
import asyncio
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    SearchCandidate,
    filter_search_results,
)
from src.polaris_graph.retrieval.scope_query_validator import (
    validate_amplified_queries,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)

logger = logging.getLogger("polaris_graph.live_retriever")


SERPER_ENDPOINT = "https://google.serper.dev/search"
S2_BULK_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"

# Hard caps
DEFAULT_MAX_SERPER = int(os.getenv("PG_LIVE_MAX_SERPER", "20"))
DEFAULT_MAX_S2 = int(os.getenv("PG_LIVE_MAX_S2", "20"))
DEFAULT_FETCH_CAP = int(os.getenv("PG_LIVE_FETCH_CAP", "40"))
DEFAULT_CONTENT_MAX_CHARS = int(os.getenv("PG_LIVE_CONTENT_MAX", "25000"))
DEFAULT_HTTP_TIMEOUT = float(os.getenv("PG_LIVE_HTTP_TIMEOUT", "20"))


@dataclass
class LiveRetrievalResult:
    classified_sources: list[CorpusSource]
    evidence_rows: list[dict[str, Any]]
    total_candidates_pre_filter: int
    candidates_kept_by_scope: int
    candidates_kept_by_offtopic: int
    candidates_fetched: int
    candidates_failed_fetch: int
    api_calls: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# API clients
# ─────────────────────────────────────────────────────────────────────────────


def _serper_search(query: str, num: int = 10) -> list[dict[str, Any]]:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        logger.warning("[live_retriever] SERPER_API_KEY missing — skipping Serper")
        return []
    # I-safety-002b (#925) PR-2: record that the Path-B-required backend was actually
    # invoked (key present + call attempted). assert_post_run rejects a run where a
    # required backend was never tried. Lazy + best-effort; no-op when gate is off.
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_attempt("serper")
    except Exception:
        pass
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": max(1, min(num, 20))}
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            r = c.post(SERPER_ENDPOINT, json=payload, headers=headers)
        if r.status_code != 200:
            logger.warning(
                "[live_retriever] Serper returned %s for %r",
                r.status_code, query[:60],
            )
            return []
        data = r.json()
    except Exception as exc:
        logger.warning("[live_retriever] Serper exception: %s", exc)
        return []
    organic = data.get("organic", []) or []
    out: list[dict[str, Any]] = []
    for item in organic:
        out.append({
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "source": "serper",
        })
    return out


def _s2_bulk_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    # I-safety-002b (#925) PR-2: record S2 backend attempt (lazy, best-effort).
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_attempt("semantic_scholar")
    except Exception:
        pass
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": query,
        "fields": "title,abstract,url,openAccessPdf,externalIds,year,venue",
        "limit": max(1, min(limit, 100)),
    }
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            r = c.get(S2_BULK_ENDPOINT, params=params, headers=headers)
        if r.status_code != 200:
            logger.warning(
                "[live_retriever] S2 returned %s for %r",
                r.status_code, query[:60],
            )
            return []
        data = r.json()
    except Exception as exc:
        logger.warning("[live_retriever] S2 exception: %s", exc)
        return []
    papers = data.get("data", []) or []
    out: list[dict[str, Any]] = []
    for p in papers:
        oa_pdf = (p.get("openAccessPdf") or {}).get("url", "")
        ext_ids = p.get("externalIds") or {}
        doi = ext_ids.get("DOI", "")
        # Full-scale fix (cycle 11): prefer open-access PDF, fall back
        # to DOI-resolved URL. Never return a bare semanticscholar.org
        # landing page — those are T7 abstract-only stubs that
        # AccessBypass deliberately skips and that inflate the T7
        # fraction in corpus adequacy. If neither oa_pdf nor DOI is
        # available, skip the paper entirely.
        if oa_pdf:
            url = oa_pdf
        elif doi:
            url = f"https://doi.org/{doi}"
        else:
            # Bare S2 landing page would be returned here; skip.
            continue
        abstract = p.get("abstract") or ""
        out.append({
            "url": url,
            "title": p.get("title", "") or "",
            "snippet": (abstract[:500] if abstract else "")[:500],
            "source": "s2",
            "s2_paper_id": p.get("paperId", ""),
            "doi": doi,
            "year": p.get("year"),
            "venue": p.get("venue"),
        })
    return out


_DOI_FROM_URL_RE = re.compile(
    r"(10\.\d{4,9}/[^\s?#]+?)(?:[?#]|/full|/abstract|/pdf|/meta|\.html|$)",
    re.IGNORECASE,
)


# BUG-M-17 (Codex full-scale pass 2): bounded body-text inspection
# for article-type signals. Reads high-signal regions of fetched
# content (meta tags, first 4KB, abstract/methods lead) for SR/MA,
# case-report, perspective, guidance markers. Used by the classifier
# as a SECONDARY signal when the title is truncated or non-diagnostic.
#
# NOT a full-body scan — Codex pass 2 explicitly warned:
# "do not scan the entire body naively for generic terms. Add a
#  bounded secondary narrative/SR signal extractor that inspects
#  high-signal fetched regions only."

# BUG-M-17b (Codex pass 3 BLOCKED fix): tightened to require context,
# not lone keywords. Explicit publisher metadata and section headers
# are trusted; lone body keywords are REJECTED because primary papers
# routinely cite prior systematic reviews, meta-analyses, case series,
# and guidelines in their background/methods without themselves being
# that article type.

# High-precision metadata patterns — trust these alone.
# Each entry: (regex_pattern, attribute_order_flexible)
_BODY_META_ARTICLE_TYPE_TAGS: tuple[str, ...] = (
    # HTML meta citation_article_type (both attr orders)
    r'<meta[^>]+citation_article_type[^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+citation_article_type',
    r'<meta[^>]+article:section[^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+article:section',
    r'<meta[^>]+prism\.section[^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+prism\.section',
    # JSON-LD
    r'"articleType"\s*:\s*"([^"]+)"',
)

# Publisher-embedded article-type HEADERS (top-of-page text).
# Frontiers "SYSTEMATIC REVIEW article", Nature "Article type: X" etc.
_BODY_PUBLISHER_HEADERS: tuple[str, ...] = (
    # Frontiers-style: "SYSTEMATIC REVIEW article" (all caps, with space + "article")
    r'\b(SYSTEMATIC REVIEW|META[- ]ANALYSIS|NETWORK META[- ]ANALYSIS|'
    r'CASE REPORT|CASE SERIES|PERSPECTIVE|EDITORIAL|'
    r'GUIDELINE|COMMENTARY|LETTER|BRIEF REPORT|OPINION) article\b',
    # Nature family: "Article type: <Type>"
    r'Article type:?\s*(Systematic Review|Meta-Analysis|Meta[- ]Analysis|'
    r'Network Meta[- ]Analysis|Case Report|Case Series|Perspective|'
    r'Editorial|Commentary|Letter|Brief Report|Opinion|Guideline)',
)

# Strong contextual patterns that need to co-occur to call SR_MA from body.
# NEVER fire on a lone keyword — require the declared-intent-or-method shape.
_BODY_SR_MA_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "objective: to conduct a systematic review / meta-analysis"
    r'objective[s]?:\s*to\s+(conduct|perform|undertake)\s+(a\s+)?(systematic review|meta[- ]analysis)',
    # "we conducted a systematic review"
    r'we\s+(conducted|performed|undertook)\s+(a\s+)?(systematic review|meta[- ]analysis)',
    # M-17c (Codex pass 4): "this SR/MA" must be followed by a
    # self-descriptive predicate within a short window. Rejects
    # citation-byline shapes like "this meta-analysis by Smith et al.
    # shaped the endpoint hierarchy" where SR/MA is the cited work,
    # not the fetched paper.
    r'this\s+(systematic review(?:\s+and\s+meta[- ]analysis)?|meta[- ]analysis)'
    r'\s+(aims?|evaluates?|examines?|investigates?|assesses?|reviews?|'
    r'reports?|presents?|summarizes?|synthesizes?|demonstrates?|'
    r'pools?|analyses|analyzes|combines?|explores?|'
    r'was\s+(conducted|performed|undertaken|registered|designed))\b',
    # M-17c: "PRISMA" with contextual search/selection/extraction/flow diagram
    r'PRISMA.{0,40}(search|selection|extraction|flow diagram)',
    r'(search|selection|extraction|flow diagram).{0,40}PRISMA',
    # M-17c (Codex pass 4): Cochrane tightened. Previously
    # "cochrane (systematic )?review" fired on "A Cochrane review
    # found..." citation in a primary trial. Now requires declarative
    # "this Cochrane review" + self-descriptive verb, OR registration
    # metadata (Cochrane Library CD-number).
    r'this\s+cochrane\s+(systematic\s+)?review\s+'
    r'(aims?|evaluates?|examines?|investigates?|assesses?|reports?|'
    r'presents?|summarizes?|was\s+(conducted|performed|registered))\b',
    # Cochrane Library registration ID (unique to Cochrane SRs)
    r'cochrane\s+(database|library).*CD\d{6}',
    # Conclusive meta-analytic methods signature: "pooled estimate" + "random-effects"
    r'(pooled (estimate|effect|odds ratio|risk ratio|hazard ratio)).{0,200}(random[- ]effects|fixed[- ]effects)',
    r'(random[- ]effects|fixed[- ]effects).{0,200}(pooled (estimate|effect|odds ratio|risk ratio|hazard ratio))',
)

# Case report body patterns — require declarative "we report/present"
# OR the X-year-old patient opener together with PATIENT-centered framing.
_BODY_CASE_REPORT_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "we report/describe/present a/the case"  (declarative)
    r'we\s+(report|describe|present)\s+(a|the)\s+case\b',
    # "here we report/describe a case"
    r'here\s+we\s+(report|describe|present)\s+(a|the)\s+case\b',
    # "we report a X-year-old patient" (opener)
    r'we\s+report\s+(a|an)\s+\d+[- ]year[- ]old',
    # Patient opener at very beginning of abstract (first 300 chars)
    # handled separately below — not in this tuple.
)

# Guideline body patterns — declarative intent.
# M-17c (Codex pass 4): tightened. Previously "this (clinical
# practice) guideline" and "consensus statement from" fired on
# citation-byline references like "according to a consensus
# statement from the Endocrine Society" in a primary trial.
# Now requires the fetched article to EITHER say "this clinical
# practice guideline" (fully qualified) OR be followed by a
# self-descriptive verb ("provides", "recommends", "was developed",
# "we developed").
# M-17d (Codex pass 5): the unanchored "(clinical practice )?
# guideline <verb>" still fired on dated external citations like
# "The 2025 clinical practice guideline recommends...". Now requires
# explicit "this" self-reference in front of the guideline noun.
# M-17e (Codex pass 6): "this guideline" alone is insufficient when
# the lead has already cited an external guideline (anaphoric
# reference). The detector now additionally rejects matches preceded
# by anaphoric-citation markers. Ambiguous verbs "summarizes" and
# "describes" have been removed because they apply equally to cited
# external guidelines. The bare "this clinical practice guideline"
# phrase must appear at sentence start (not as object of "followed").
# "updates?" added to close a recall miss.
_BODY_GUIDELINE_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "This clinical practice guideline" at sentence start — must be
    # subject, not object of "followed this guideline during trial"
    r'(?:^|[.!?]\s+|\n\s*)this\s+clinical\s+practice\s+guideline\b',
    # "This (clinical practice) guideline ... <verb>" — must be "this"
    # to reject dated/external citations (M-17d). Verb list tightened
    # to unambiguous self-authorship verbs (M-17e).
    r'this\s+(clinical\s+practice\s+)?guideline\s+'
    r'(provides|recommends|was\s+developed|is\s+intended|'
    r'presents|outlines|aims?|establishes|offers|updates?)',
    # "this consensus statement ... verb" (declarative, not cited)
    r'this\s+consensus\s+statement\s+'
    r'(provides|recommends|was\s+developed|outlines|presents|'
    r'aims?|establishes|summarizes)',
    # "Consensus statement from X: <descriptive phrase>" — structural
    # form of a consensus paper, NOT "according to a consensus
    # statement from". Require the consensus statement to be the
    # subject of a descriptive predicate.
    r'consensus\s+statement\s+from\s+(the\s+)?[A-Z][A-Za-z ]+\s+'
    r'(provides|recommends|was\s+developed|outlines|presents|aims?)',
    # "Expert consensus panel/group was convened/developed..."
    r'expert\s+consensus\s+(panel|group)\s+'
    r'(was\s+convened|developed|provides|recommends|presents)',
    # Declarative: "we developed this clinical/practical guidance"
    r'we\s+(developed|provide)\s+(this\s+)?(clinical|practical)\s+guidance',
)

# Perspective/commentary body patterns — declarative framing, not
# audience phrases alone.
_BODY_PERSPECTIVE_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "In this perspective / commentary / editorial"
    r'in\s+this\s+(perspective|commentary|editorial|opinion)',
    # "This perspective examines / reviews"
    r'this\s+(perspective|commentary|editorial)\s+(examines|reviews|discusses|considers)',
    # "offer a perspective on"
    r'(offer|present|provide)\s+a\s+perspective\s+(on|for|of)',
)


def _classify_from_meta_keywords(captured: str) -> str:
    """Map a captured metadata/header value to a tier signal. Used
    for publisher-embedded explicit article-type tags (high precision).
    """
    c = (captured or "").lower().strip()
    if not c:
        return ""
    if any(k in c for k in ("systematic review", "meta-analysis",
                            "meta analysis", "cochrane",
                            "network meta-analysis",
                            "network meta analysis")):
        return "SR_MA"
    if "case report" in c or "case series" in c:
        return "CASE_REPORT"
    if "perspective" in c:
        return "PERSPECTIVE"
    if "guideline" in c or "consensus" in c:
        return "GUIDELINE"
    if "editorial" in c or "commentary" in c:
        return "PERSPECTIVE"
    if "letter" in c or "opinion" in c or "brief report" in c:
        return "PERSPECTIVE"
    return ""


def _detect_article_type_from_body(raw_content: str) -> str:
    """Bounded body-text inspection for article-type signal.

    Returns one of: "SR_MA", "CASE_REPORT", "PERSPECTIVE", "GUIDELINE",
    or "" (no signal). Inspects only the first 8KB of content to keep
    cost bounded.

    M-17b (Codex pass 3 BLOCKED): tightened to avoid false positives
    from primary papers citing prior systematic reviews / case reports
    as background. Now requires either:

    (P1) explicit publisher-embedded article-type metadata
         (HTML meta tag, JSON-LD articleType, Nature-style "Article
         type:" header, Frontiers-style "SYSTEMATIC REVIEW article"
         section marker), OR
    (P2) a declarative contextual body pattern that indicates the
         fetched article IS the given type (not merely citing it).

    Lone keywords like "systematic review" or "case report" alone
    are NOT sufficient — primary trial abstracts commonly cite prior
    reviews in their background, and primary-study methods often
    mention excluding case series.
    """
    if not raw_content:
        return ""
    # Bound the scan window
    head = raw_content[:8000]
    lead = head[:4000]
    lead_lower = lead.lower()

    # ── Priority 1a: explicit meta / JSON-LD article-type tags
    for pattern in _BODY_META_ARTICLE_TYPE_TAGS:
        m = re.search(pattern, head, re.IGNORECASE)
        if m and m.lastindex:
            signal = _classify_from_meta_keywords(m.group(1))
            if signal:
                return signal

    # ── Priority 1b: publisher-embedded article-type headers
    # These are ALL-CAPS or structured banners at the page top
    # (Frontiers "SYSTEMATIC REVIEW article", Nature "Article type: X")
    for pattern in _BODY_PUBLISHER_HEADERS:
        m = re.search(pattern, head, re.IGNORECASE)
        if m and m.lastindex:
            signal = _classify_from_meta_keywords(m.group(1))
            if signal:
                return signal

    # ── Priority 2: declarative body patterns (must co-occur with
    # study-type context, not lone keywords)
    for pattern in _BODY_SR_MA_CONTEXT_PATTERNS:
        if re.search(pattern, lead_lower, re.IGNORECASE):
            return "SR_MA"
    for pattern in _BODY_CASE_REPORT_CONTEXT_PATTERNS:
        if re.search(pattern, lead_lower, re.IGNORECASE):
            return "CASE_REPORT"
    # "X-year-old patient" opener as first significant content in abstract
    # (look only in first 500 chars to avoid methods/exclusion-criteria false positives)
    opener = lead_lower[:500]
    if re.search(
        r'^\s*(a|this)\s+\d+[- ]year[- ]old\s+(man|woman|male|female|patient)\s+(presented|was\s+admitted|with)',
        opener,
    ):
        return "CASE_REPORT"
    # M-17e (Codex pass 6): anaphoric-citation guard. If the lead
    # contains a citation-style reference to an external guideline
    # ("followed the 2025 ADA guideline", "according to the NICE
    # guideline"), a subsequent "This guideline <verb>" is likely
    # anaphoric to that external citation rather than self-declarative.
    # We therefore require the guideline match to precede, not follow,
    # any such external-guideline citation in the lead.
    _ANAPHORIC_GUIDELINE_CITATION = re.compile(
        r'(?:followed|following|according\s+to|citing|cited|per|'
        r'as\s+recommended\s+by|as\s+per|based\s+on|in\s+line\s+with)'
        r'\s+(?:the\s+)?(?:\d{4}\s+)?(?:[a-z]+\s+)?(?:clinical\s+practice\s+)?'
        r'guidelines?\b',
        re.IGNORECASE,
    )
    for pattern in _BODY_GUIDELINE_CONTEXT_PATTERNS:
        m = re.search(pattern, lead_lower, re.IGNORECASE)
        if m:
            # Reject if an external-guideline citation appears in the
            # preceding 300 chars (anaphoric reference) — e.g. "followed
            # the 2025 ADA guideline ... This guideline summarizes".
            preceding = lead_lower[max(0, m.start() - 300): m.start()]
            if _ANAPHORIC_GUIDELINE_CITATION.search(preceding):
                continue
            return "GUIDELINE"
    for pattern in _BODY_PERSPECTIVE_CONTEXT_PATTERNS:
        if re.search(pattern, lead_lower, re.IGNORECASE):
            return "PERSPECTIVE"

    return ""


def _extract_title_from_content(content: str) -> str:
    """Extract the full paper title from fetched page content.

    M-13 fallback (Codex pass 13): OpenAlex DOI lookup doesn't work
    for MDPI URLs (they don't embed DOI in URL path). And OpenAlex
    title-search with a truncated Serper snippet often misses the
    right paper. As a third recovery path, parse the fetched HTML
    or markdown for the real title.

    - Jina Reader and Crawl4AI often emit markdown with `Title: ...`
      or `# Title` on the first line.
    - Direct HTTP returns HTML; look for `<title>...</title>` tag.
    - trafilatura output is plain text; the first significant line
      is usually the title.

    Returns empty string if no plausible title found.
    """
    if not content:
        return ""
    # Jina/Crawl4AI "Title: X" pattern
    m = re.search(r"^\s*Title:\s*(.+?)\s*$", content[:2000], re.MULTILINE)
    if m:
        t = m.group(1).strip()
        if 10 <= len(t) <= 500:
            return t
    # Markdown H1
    m = re.search(r"^\s*#\s+(.+?)\s*$", content[:2000], re.MULTILINE)
    if m:
        t = m.group(1).strip()
        if 10 <= len(t) <= 500 and "content" not in t.lower()[:30]:
            return t
    # HTML <title> tag
    m = re.search(r"<title[^>]*>(.+?)</title>", content[:4000],
                  re.IGNORECASE | re.DOTALL)
    if m:
        t = m.group(1).strip()
        # Strip journal suffixes like " — Frontiers", " | MDPI"
        t = re.sub(r"\s*[|\-—–]\s*(mdpi|frontiers|nejm|jama|lancet|"
                   r"bmc|springer|nature|science|cell|plos).*$", "",
                   t, flags=re.IGNORECASE)
        if 10 <= len(t) <= 500:
            return t
    return ""


def _extract_doi_from_url(url: str) -> str:
    """Extract a DOI from a URL if present. Handles Frontiers
    (`/10.3389/fphar.2022.1016639/full`), JAMA, NEJM, OUP, Sage,
    ACS, RSC, Wiley, and direct `doi.org/...` URLs. MDPI URLs don't
    embed DOIs; return empty there.
    """
    if not url:
        return ""
    # Direct DOI URL
    u = url.strip()
    if "doi.org/" in u.lower():
        idx = u.lower().find("doi.org/") + len("doi.org/")
        doi = u[idx:].split("?")[0].split("#")[0].rstrip("/")
        return doi
    # Embedded DOI in publisher URLs
    m = _DOI_FROM_URL_RE.search(u)
    if m:
        return m.group(1).rstrip("/").rstrip(".")
    return ""


def _openalex_enrich(url: str, title: str) -> dict[str, Any]:
    """Query OpenAlex for pub_type / source_type / is_peer_reviewed.

    M-13 (BUG-M-13, Codex pass 13): prefer DOI-based lookup over
    title search. When the URL embeds a DOI (Frontiers, JAMA, NEJM,
    OUP, etc.), OpenAlex's /works/doi:<doi> endpoint is exact and
    always returns the full display_name. Title-based search often
    fails when Serper truncated the title or returned a variant
    that OpenAlex doesn't index. Falls back to title search when no
    DOI can be extracted (e.g., MDPI URLs, publisher blog posts).
    """
    try:
        doi = _extract_doi_from_url(url)
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            if doi:
                # Exact DOI lookup — most reliable. OpenAlex accepts
                # both the bare DOI and the URL form; use bare DOI.
                r = c.get(f"{OPENALEX_ENDPOINT}/doi:{doi}")
                if r.status_code != 200:
                    # Fall back to title search if DOI not indexed
                    r = c.get(
                        OPENALEX_ENDPOINT,
                        params={
                            "search": (title or url)[:200],
                            "per-page": 1,
                        },
                    )
                    if r.status_code != 200:
                        return {}
                    data = r.json()
                    results = data.get("results", [])
                    if not results:
                        return {}
                    work = results[0]
                else:
                    work = r.json()  # single-work response from /works/doi
            else:
                r = c.get(
                    OPENALEX_ENDPOINT,
                    params={
                        "search": (title or url)[:200],
                        "per-page": 1,
                    },
                )
                if r.status_code != 200:
                    return {}
                data = r.json()
                results = data.get("results", [])
                if not results:
                    return {}
                work = results[0]
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        return {
            "openalex_pub_type": work.get("type", "") or "",
            "openalex_source_type": source.get("type", "") or "",
            "is_peer_reviewed": bool(
                work.get("type") in ("article", "review")
                and source.get("type") == "journal"
            ),
            "openalex_id": work.get("id", ""),
            # BUG-M-12 (Codex pass 12): preserve OpenAlex's full
            # display_name. Serper snippet titles are often truncated
            # mid-title, losing "systematic review and meta-analysis",
            # "perspective for primary care providers", etc. suffixes
            # that the classifier needs to demote false T1s.
            "openalex_full_title": work.get("display_name", "") or "",
        }
    except Exception as exc:
        logger.debug("[live_retriever] OpenAlex enrich failed for %r: %s", url, exc)
        return {}


def _env_float(name: str, default: float) -> float:
    """Positive-*finite*-float env knob with a safe fallback (LAW VI).

    Non-finite overrides (``inf``/``-inf``/``nan``) fall back to ``default``:
    ``float("inf")`` parses fine and is ``> 0``, but feeding it to e.g.
    ``threading.Thread.join(timeout=...)`` raises ``OverflowError`` on
    Windows (I-bug-116 / #556).
    """
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def _env_int(name: str, default: int) -> int:
    """Positive-int env knob with a safe fallback (LAW VI — no hardcode)."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _bounded_openalex_enrich(
    url: str, title: str, stats: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Wall-clock-bounded wrapper around `_openalex_enrich` (GH #554).

    `_openalex_enrich` issues `httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT)`
    requests. `httpx`'s timeout bounds each request *phase*
    (connect/read/write/pool) but NOT total request time, so a wedged or
    byte-trickling OpenAlex response (slowloris pattern) is never
    hard-bounded. The post-`parallel_fetch` candidate loop in
    `run_live_retrieval` is synchronous, so one wedged enrich call hangs the
    whole run before it reaches any terminal verdict (#554 — demo-fatal).

    Run the call in a daemon thread and abandon it past
    `PG_OPENALEX_ENRICH_DEADLINE` (default 45 s = 2x the 20 s httpx phase
    timeout, covering the DOI-lookup + title-search-fallback double request,
    + margin). Enrichment is optional — the tier classifier degrades
    gracefully to title/content signals without it. `stats["enrich_timeouts"]`
    is incremented on timeout so the caller can fail-fast.
    """
    deadline = _env_float("PG_OPENALEX_ENRICH_DEADLINE", 45.0)
    holder: dict[str, Any] = {}

    def _worker() -> None:
        try:
            holder["value"] = _openalex_enrich(url, title)
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    worker = threading.Thread(
        target=_worker, name="openalex-enrich", daemon=True,
    )
    worker.start()
    worker.join(timeout=deadline)
    if worker.is_alive():
        if stats is not None:
            stats["enrich_timeouts"] = stats.get("enrich_timeouts", 0) + 1
        logger.warning(
            "[live_retriever] OpenAlex enrich exceeded %.0fs for %s — "
            "skipping enrichment (daemon thread abandoned)",
            deadline, url[:80],
        )
        return {}
    if "error" in holder:
        logger.debug(
            "[live_retriever] OpenAlex enrich raised for %r: %s",
            url, holder["error"],
        )
        return {}
    return holder.get("value", {})


# ─────────────────────────────────────────────────────────────────────────────
# Content fetching (very basic — just enough to get tier + evidence)
# ─────────────────────────────────────────────────────────────────────────────


def _strip_html(html: str) -> str:
    """Extract visible text from HTML via basic regex (trafilatura if available)."""
    try:
        import trafilatura  # type: ignore
        extracted = trafilatura.extract(html) or ""
        if extracted:
            return extracted
    except Exception:
        pass
    # Fallback: strip tags + collapse whitespace
    no_tags = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    no_tags = re.sub(r"<style[^>]*>.*?</style>", " ", no_tags, flags=re.DOTALL | re.IGNORECASE)
    no_tags = re.sub(r"<[^>]+>", " ", no_tags)
    no_tags = re.sub(r"\s+", " ", no_tags)
    return no_tags.strip()


def _fetch_content_httpx_naive(url: str, max_chars: int) -> tuple[str, bool, str, str]:
    """Legacy naive httpx fetcher. Kept as emergency fallback when
    AccessBypass is unavailable (tests that don't want Crawl4AI browser
    spawning, or sandboxes without Playwright)."""
    try:
        with httpx.Client(
            timeout=DEFAULT_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (POLARIS-honest-rebuild/1.0) "
                    "research-assistant"
                ),
                # BUG-BROTLI-R8d: httpx/aiohttp advertise `br` by default
                # but can't always decode it. Forbid it so servers don't
                # return Brotli-encoded bodies we can't read.
                "Accept-Encoding": "gzip, deflate",
            },
        ) as c:
            r = c.get(url)
        if r.status_code != 200:
            return "", False, "", ""
        ctype = (r.headers.get("content-type", "") or "").lower()
        raw = r.text if "text" in ctype or "html" in ctype or "json" in ctype else ""
        if not raw and r.content:
            raw = r.content.decode("utf-8", errors="ignore")
        # BUG-M-13/M-14: extract title from raw HTML BEFORE stripping
        # (the <title> tag is gone after _strip_html).
        extracted_title = _extract_title_from_content(raw)
        # BUG-M-17: detect article-type from bounded body region.
        body_type = _detect_article_type_from_body(raw)
        content = _strip_html(raw)[:max_chars]
        return content, bool(content), extracted_title, body_type
    except Exception as exc:
        logger.debug(
            "[live_retriever] naive-httpx fetch %r failed: %s", url, exc,
        )
        return "", False, "", ""


def refetch_for_extraction(url: str, max_chars: int = 2000) -> str:
    """M-42b (2026-04-22): re-fetch source content for deterministic
    trial-table / timeline extraction when the evidence row's
    existing `direct_quote` is thin (<100 chars) or the row was
    never successfully fetched.

    Returns a 2000-char extract (head + decimal-windows) via
    _fetch_content + _build_provenance_quote, or empty string when
    the URL cannot be fetched or returns thin content.

    Caller is expected to cache the result on the evidence row for
    the remainder of the run so repeat table generation within the
    same sweep does not re-hit the network.

    Generic wrapper — not trial/drug/domain-specific. Used by the
    M-42b trial-table builder and the Trial Program Timeline builder.

    M-45 (2026-04-22): see `refetch_for_extraction_with_diagnostics`
    for a variant that returns structured per-URL diagnostics
    (backend, char count, body type, eligibility, failure mode) for
    the V28 preflight and downstream audits. This function is a thin
    wrapper around that variant.
    """
    quote, _diag = refetch_for_extraction_with_diagnostics(url, max_chars)
    return quote


# M-45 pass-2 (Codex audit HIGH): per-URL method + failure-reason
# telemetry. Module-level dict populated by `_fetch_content` just
# before it returns, then read by `refetch_for_extraction_with_
# diagnostics`. Keyed by url; overwritten on each call so memory
# stays bounded. Not thread-safe for concurrent refetches of the
# same URL, but the current sweep path is sequential per URL.
_M45_LAST_FETCH_TELEMETRY: dict[str, dict[str, Any]] = {}


def _m45_record_fetch_telemetry(
    url: str, method: str, failure_reason: str = "",
) -> None:
    """M-45 pass-2: record the final AccessBypass method + failure
    reason for a fetch call. Overwrites any prior entry for the same
    URL so repeat refetches in one run show the latest attempt."""
    _M45_LAST_FETCH_TELEMETRY[url] = {
        "method": method or "unknown",
        "failure_reason": failure_reason,
    }


def _m45_pop_fetch_telemetry(url: str) -> dict[str, Any]:
    """M-45 pass-2: read + remove the telemetry for a URL so it's
    not reused by a later unrelated call. Returns empty dict if no
    entry was recorded."""
    return _M45_LAST_FETCH_TELEMETRY.pop(url, {})


def refetch_for_extraction_with_diagnostics(
    url: str, max_chars: int = 2000,
) -> tuple[str, dict[str, Any]]:
    """M-45 (2026-04-22): refetch with structured per-URL diagnostics.

    Codex V28 plan pass-2 APPROVED this diagnostic-first approach.
    V27 still produced thin quotes for paywalled PDFs despite the
    AccessBypass cascade existing. This variant records WHY each
    refetch landed or failed so audits can branch the fix
    (explicit-wire Jina/Firecrawl, better extraction window, or
    strict skip) based on real data instead of assumption.

    Returns (quote, diagnostics) where:
      - quote: same as `refetch_for_extraction` — non-empty iff the
        refetched content is ≥100 chars and the provenance quote
        was built; empty string otherwise. Strict ≥100 char contract
        preserved (no statement fallback, no prose fallback).
      - diagnostics: dict with these keys:
          url: the input URL (truncated to 200 chars for JSON safety)
          attempted: bool — did we try the fetch at all
          method: str — AccessBypass method that produced content
            ('crawl4ai', 'jina', 'firecrawl', 'httpx', 'archive_org',
            'scihub', or 'none')
          raw_char_count: int — bytes returned by _fetch_content
            before provenance-quote extraction
          body_type: str — 'abstract' / 'full_text' / 'paywall_shell'
            / 'html_meta' per `_detect_article_type_from_body`
          eligible: bool — True iff quote was emitted (≥100 chars)
          failure_mode: str — one of:
            '' (eligible), 'exception', 'fetch_failed',
            'thin_content', 'paywall_shell'
          exception_type: str — class name when failure_mode=exception
    """
    diagnostics: dict[str, Any] = {
        "url": (url or "")[:200],
        "attempted": False,
        "method": "none",
        "raw_char_count": 0,
        "body_type": "",
        "eligible": False,
        "failure_mode": "",
        "exception_type": "",
    }
    if not url:
        diagnostics["failure_mode"] = "empty_url"
        return "", diagnostics
    diagnostics["attempted"] = True
    try:
        content, ok, _title, body_type = _fetch_content(url, max_chars)
    except Exception as exc:
        logger.warning(
            "[refetch_for_extraction] fetch failed for %s: %s", url, exc,
        )
        diagnostics["failure_mode"] = "exception"
        diagnostics["exception_type"] = type(exc).__name__
        # M-45 pass-2: read any telemetry recorded before the exception.
        te = _m45_pop_fetch_telemetry(url)
        diagnostics["method"] = te.get("method", "none")
        return "", diagnostics

    diagnostics["raw_char_count"] = len(content) if content else 0
    diagnostics["body_type"] = body_type or ""
    # M-45 pass-2 (Codex audit HIGH): read the winning AccessBypass
    # method + failure reason that `_fetch_content` recorded. Pre-
    # pass-2 the method was always "none" because `_fetch_content`
    # discarded `result.access_method` before returning.
    tele = _m45_pop_fetch_telemetry(url)
    if tele:
        diagnostics["method"] = tele.get("method", "none")
        reason = tele.get("failure_reason", "")
        if reason and "timeout" in reason:
            diagnostics["failure_mode"] = "timeout"

    if not ok or not content:
        # M-45 pass-2: preserve timeout classification from telemetry
        # (set above) instead of overwriting with generic fetch_failed.
        if diagnostics["failure_mode"] != "timeout":
            diagnostics["failure_mode"] = "fetch_failed"
        return "", diagnostics
    if len(content) < 100:
        if diagnostics["failure_mode"] != "timeout":
            diagnostics["failure_mode"] = "thin_content"
        return "", diagnostics
    # Paywall-shell detection: body_type marker set by
    # _detect_article_type_from_body. We still build a provenance
    # quote from the content but tag the diagnostic so downstream
    # audits can filter these out if they want only full-text sources.
    if body_type == "paywall_shell":
        diagnostics["failure_mode"] = "paywall_shell"
        # Continue to build the quote — the shell may still contain
        # enough abstract text to hit ≥100 chars. Eligibility is
        # determined by the provenance-quote length check below.
    quote = _build_provenance_quote(
        content, head_chars=min(1500, max_chars), window_chars=500,
        max_total_chars=max_chars,
    )
    if not quote or len(quote) < 100:
        if not diagnostics["failure_mode"]:
            diagnostics["failure_mode"] = "thin_content"
        return "", diagnostics
    diagnostics["eligible"] = True
    if diagnostics["failure_mode"] == "paywall_shell":
        # Eligible despite shell marker — abstract-only case.
        diagnostics["failure_mode"] = ""
    return quote, diagnostics


def _fetch_content(url: str, max_chars: int) -> tuple[str, bool, str, str]:
    """Fetch URL content using the AccessBypass cascade (Crawl4AI +
    Jina Reader + Firecrawl concurrent, fallback to direct HTTP +
    Archive.org + institutional proxy + Sci-Hub).

    BUG-FETCH-R8d (2026-04-18): the live smoke test of
    clinical_tirzepatide_t2dm showed 19/20 candidates failed via the
    previous naive httpx.Client. `src/tools/access_bypass.py` already
    had the full cascade (including BUG-BROTLI fix, concurrent Crawl4AI
    /Jina/Firecrawl, paywall detection) but pipeline A wasn't wired
    to it. This is the wiring.

    The AccessBypass call is async; live_retriever's fetch loop is
    sync by historical choice. We run the async call in a fresh event
    loop per URL. Full async refactor of run_live_retrieval (with
    asyncio.gather for concurrency) is tracked as R-RETRIEVE-ASYNC in
    docs/todo_list.md.

    Env opt-out: set PG_DISABLE_ACCESS_BYPASS=1 to fall back to the
    naive httpx path (useful when Playwright/Crawl4AI is unavailable).
    """
    if os.getenv("PG_DISABLE_ACCESS_BYPASS", "0") == "1":
        # M-45 pass-2: record env-opt-out so diagnostics can see it.
        _m45_record_fetch_telemetry(
            url, "httpx_naive", "pg_disable_access_bypass=1"
        )
        return _fetch_content_httpx_naive(url, max_chars)
    try:
        from src.tools.access_bypass import AccessBypass
    except Exception as exc:
        logger.warning(
            "[live_retriever] AccessBypass unavailable (%s); "
            "falling back to naive httpx", exc,
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive", f"access_bypass_import_failed: {exc}"
        )
        return _fetch_content_httpx_naive(url, max_chars)

    # Run AccessBypass in a dedicated thread so each call gets its own
    # fresh event loop. This works whether we're called from sync or
    # async context (expansion path runs inside a live loop). Crawl4AI
    # leaves background tasks that make subsequent asyncio.run() in the
    # same thread fail with "cannot be called from a running event loop".
    result_holder: dict[str, Any] = {}

    def _bypass_worker() -> None:
        try:
            bypass = AccessBypass()
            result_holder["value"] = asyncio.run(
                bypass.fetch_with_bypass(url, prefer_legal=True)
            )
        except Exception as exc:  # noqa: BLE001
            result_holder["error"] = exc

    worker = threading.Thread(target=_bypass_worker, daemon=True)
    worker.start()
    # BUG-FETCH-R8d medium-1 (Codex pass 4): bound the join so a wedged
    # Crawl4AI/Playwright browser startup/cleanup can't hang the sweep
    # indefinitely. AccessBypass has internal timeouts but they don't
    # cover every subprocess/import/browser-cleanup failure mode.
    # Default 90s = Crawl4AI worst-case (~70s) + margin. Override via
    # PG_FETCH_DEADLINE_SECONDS. Set to 0 to disable (not recommended).
    try:
        deadline = float(os.getenv("PG_FETCH_DEADLINE_SECONDS", "90"))
    except ValueError:
        deadline = 90.0
    worker.join(timeout=deadline if deadline > 0 else None)
    if worker.is_alive():
        logger.warning(
            "[live_retriever] AccessBypass timed out after %.0fs for %s "
            "— falling back to naive httpx (thread will continue as daemon)",
            deadline, url[:80],
        )
        # M-45 pass-2: record AccessBypass timeout so diagnostics can
        # distinguish timeout from backend refusal.
        _m45_record_fetch_telemetry(
            url, "httpx_naive", f"access_bypass_timeout_{int(deadline)}s",
        )
        return _fetch_content_httpx_naive(url, max_chars)

    if "error" in result_holder:
        exc = result_holder["error"]
        logger.warning(
            "[live_retriever] AccessBypass raised for %s: %s: %s",
            url[:80], type(exc).__name__, exc,
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive",
            f"access_bypass_raised_{type(exc).__name__}",
        )
        return _fetch_content_httpx_naive(url, max_chars)
    if "value" not in result_holder:
        logger.warning(
            "[live_retriever] AccessBypass produced no result for %s",
            url[:80],
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive", "access_bypass_no_result"
        )
        return _fetch_content_httpx_naive(url, max_chars)
    result = result_holder["value"]

    method = getattr(result, "access_method", "unknown") or "unknown"
    if not result.success or not result.content:
        reason = (result.metadata or {}).get("reason") if hasattr(result, "metadata") else None
        logger.info(
            "[live_retriever] fetch_miss %s (method=%s reason=%s)",
            url[:80], method, reason or "no_content",
        )
        # M-45 pass-2: record the winning backend + reason even on miss
        # so downstream audits can see which backend was last invoked.
        _m45_record_fetch_telemetry(url, method, reason or "no_content")
        return "", False, "", ""
    # BUG-M-14 (Codex pass 14): extract the full page title from the
    # raw result.content BEFORE _strip_html removes <title> tags. Jina
    # markdown has "Title: X" on first line; Crawl4AI cleaned text has
    # the same. HTML fetches have <title>.
    extracted_title = _extract_title_from_content(result.content)
    # BUG-M-17 (Codex pass 2): detect article-type from body.
    body_type = _detect_article_type_from_body(result.content)
    # result.content is already extracted (Jina = markdown, Crawl4AI =
    # cleaned text). _strip_html is a safety net for direct-HTTP path
    # which returns raw HTML.
    content = _strip_html(result.content)[:max_chars]
    logger.info(
        "[live_retriever] fetch_ok %s (method=%s chars=%d)",
        url[:80], method, len(content),
    )
    # M-45 pass-2: record winning backend for diagnostics.
    _m45_record_fetch_telemetry(url, method, "")
    return content, bool(content), extracted_title, body_type


def _domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except Exception:
        return ""


_DECIMAL_PATTERN = re.compile(r"-?\d+\.\d+")


_PDF_METADATA_PATTERNS = (
    re.compile(r"^\s*%PDF", re.MULTILINE),
    re.compile(r"endobj|xref|startxref|trailer", re.IGNORECASE),
    re.compile(r"\.(pdf|obj|endstream)\s+\d+", re.IGNORECASE),
)
_FORMATTING_NOISE_MARKERS = (
    "/Contents", "/MediaBox", "/Font", "/FontName",
    "<<", ">>", "stream\n",
)


def is_content_starved(content: str, min_useful_chars: int = 200) -> bool:
    """R-5 Fix D: detect evidence rows whose fetched content is PDF
    metadata / formatting fragments / empty text — not useful prose.

    Returns True if the content should NOT be passed to the generator
    (because the LLM would admit it has no answer, wasting tokens).

    Heuristics:
      - Length of visible text < min_useful_chars
      - PDF metadata markers dominate
      - Ratio of alphabetic chars to total chars is low
    """
    if not content or len(content.strip()) < min_useful_chars:
        return True

    # PDF-metadata dominance check
    pdf_hits = 0
    for pat in _PDF_METADATA_PATTERNS:
        if pat.search(content):
            pdf_hits += 1
    if pdf_hits >= 2:
        return True

    # Formatting-marker dominance check
    marker_count = sum(content.count(m) for m in _FORMATTING_NOISE_MARKERS)
    if marker_count > 20 and marker_count / max(1, len(content) / 100) > 0.5:
        return True

    # Alphabetic ratio: if less than 40% of chars are letters, probably
    # not readable prose (e.g., binary-looking PDF remnants).
    alpha = sum(1 for ch in content if ch.isalpha())
    total = len(content)
    if total > 0 and alpha / total < 0.4:
        return True

    return False


def _build_provenance_quote(
    content: str,
    head_chars: int = 1500,
    window_chars: int = 500,
    max_total_chars: int = 12000,
    max_windows: int = 20,
) -> str:
    """Build a direct_quote that contains the head of the document AND
    500-char windows around every decimal found in the full content.

    Fixes Fix-3: strict_verify was dropping sentences that cited real
    numbers living outside the first 1500 chars (e.g., STEP 5 -15.2%
    in the results section of a Nature paper). Caller stores the result
    as evidence.direct_quote; Phase 4 _find_span_for_decimal will now
    find the decimal because a window containing it is in the quote.

    Returns a concatenation: head || "\\n\\n[...]\\n\\n" || window_1 || ...
    Deduplicates overlapping windows. Caps total length at max_total_chars
    to keep prompt budget under control.
    """
    if not content:
        return ""
    head = content[:head_chars]
    if len(content) <= head_chars:
        return head

    # Find all decimal positions in the full content
    positions: list[tuple[int, int]] = []
    for m in _DECIMAL_PATTERN.finditer(content):
        start = max(0, m.start() - window_chars // 2)
        end = min(len(content), m.end() + window_chars // 2)
        positions.append((start, end))

    # De-overlap: merge adjacent windows that touch each other
    positions.sort()
    merged: list[tuple[int, int]] = []
    for s, e in positions:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Drop windows already fully inside the head
    merged = [(s, e) for s, e in merged if e > head_chars]

    # Cap count
    merged = merged[:max_windows]

    chunks = [head]
    total = len(head)
    for s, e in merged:
        chunk = content[s:e]
        # Stop if we'd exceed the total cap
        if total + len(chunk) + 6 > max_total_chars:
            break
        chunks.append(chunk)
        total += len(chunk) + 6  # rough separator overhead

    return "\n\n[...]\n\n".join(chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Fetch-time relevance rerank + per-sub-query reservation (I-meta-002-q1d #951/#943)
# ─────────────────────────────────────────────────────────────────────────────

# Pure-lexical, no-model relevance: stopword-filtered content-word overlap of a
# candidate's (title+snippet) against the research question. NO embedder / no model
# load (§8.4) — sentence-transformers/CUDA are never touched on the ranking path.
_RERANK_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "of", "in",
    "on", "at", "to", "for", "with", "by", "from", "as", "that", "this", "these",
    "those", "it", "its", "be", "been", "what", "which", "who", "how", "why",
    "when", "where", "we", "our", "their", "between", "into", "about", "than",
})


def _rerank_content_tokens(text: str) -> set[str]:
    """Lowercase content-word tokens (3+ chars, stopword-filtered). Pure lexical."""
    toks = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", (text or "").lower())
    return {t for t in toks if t not in _RERANK_STOPWORDS}


def _lexical_relevance_score(candidate: "SearchCandidate", question_tokens: set[str]) -> float:
    """Overlap fraction of the candidate's (title+snippet) content tokens with the
    question tokens. 0.0 when either side is empty. Deterministic, no network/model."""
    if not question_tokens:
        return 0.0
    cand_tokens = _rerank_content_tokens(getattr(candidate, "snippet_text", "") or "")
    if not cand_tokens:
        return 0.0
    return len(cand_tokens & question_tokens) / float(len(question_tokens))


def _rerank_and_reserve(
    candidates: list["SearchCandidate"],
    *,
    research_question: str,
    fetch_cap: int,
    n_seed_injected: int,
) -> list["SearchCandidate"]:
    """Replace arrival-order truncation with a no-spend, no-model-load relevance rerank
    that reserves at least one slot per sub-query (I-meta-002-q1d #951, Codex brief-gate
    iter-1 required-changes).

    Seed lane (I-bug-776 #817): primary-trial DOI seeds carry empty title/snippet, so
    relevance scoring would drop them. They are SPLIT OUT by `source == "primary_trial_doi"`
    and prepended AFTER ranking — never ranked, never dropped, exactly additive as before.

    Reservation: group non-seeds by `query_origin`; sort each group by (-score, index);
    take at most ONE reserved item per origin while capacity remains (origins with the best
    candidate score reserved first when origins exceed cap); then fill the remaining slots
    by global (-score, index). The long full-paragraph/anchor query is not starved.

    Fail-open (never raise): on any error fall back to the previous arrival-order behavior
    `candidates[:fetch_cap + n_seed_injected]`.
    """
    try:
        seeds = [c for c in candidates if getattr(c, "source", "") == "primary_trial_doi"]
        non_seeds = [c for c in candidates if getattr(c, "source", "") != "primary_trial_doi"]
        if fetch_cap <= 0 or not non_seeds:
            return seeds + non_seeds[:max(fetch_cap, 0)]

        question_tokens = _rerank_content_tokens(research_question)
        # (score, original_index, candidate) so ties + zero-overlap fall back to arrival order.
        scored = [
            (_lexical_relevance_score(c, question_tokens), i, c)
            for i, c in enumerate(non_seeds)
        ]
        # Group by origin, each group sorted by (-score, index).
        groups: dict[str, list[tuple[float, int, "SearchCandidate"]]] = {}
        for entry in scored:
            origin = getattr(entry[2], "query_origin", "") or "_unlabeled"
            groups.setdefault(origin, []).append(entry)
        for entries in groups.values():
            entries.sort(key=lambda e: (-e[0], e[1]))

        selected_idx: set[int] = set()
        chosen: list[tuple[float, int, "SearchCandidate"]] = []
        # Phase 1 — reserve >=1 slot per origin (origins ranked by their best candidate score),
        # bounded by capacity.
        origins_by_best = sorted(
            groups.items(), key=lambda kv: (-kv[1][0][0], kv[1][0][1])
        )
        for _origin, entries in origins_by_best:
            if len(chosen) >= fetch_cap:
                break
            top = entries[0]
            chosen.append(top)
            selected_idx.add(top[1])
        # Phase 2 — fill remaining slots by global (-score, index).
        if len(chosen) < fetch_cap:
            remainder = sorted(
                (e for e in scored if e[1] not in selected_idx),
                key=lambda e: (-e[0], e[1]),
            )
            for entry in remainder:
                if len(chosen) >= fetch_cap:
                    break
                chosen.append(entry)
                selected_idx.add(entry[1])
        # Emit non-seeds in original arrival order among the selected set (stable corpus).
        selected_non_seeds = [c for i, c in enumerate(non_seeds) if i in selected_idx]
        return seeds + selected_non_seeds
    except Exception as exc:  # fail-open: never break retrieval on a ranking error
        logger.warning("[live_retriever] rerank failed (%s) — arrival-order fallback", exc)
        return candidates[:fetch_cap + n_seed_injected]


# ─────────────────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────────────────


def run_live_retrieval(
    *,
    research_question: str,
    amplified_queries: Optional[list[str]] = None,
    protocol: Optional[dict[str, Any]] = None,
    max_serper: int = DEFAULT_MAX_SERPER,
    max_s2: int = DEFAULT_MAX_S2,
    fetch_cap: int = DEFAULT_FETCH_CAP,
    enable_openalex_enrich: bool = True,
    enable_prefetch_filter: bool = False,
    domain: Optional[str] = None,
    seed_urls: Optional[list[str]] = None,
) -> LiveRetrievalResult:
    """Execute live retrieval and classify the corpus.

    Args:
        research_question: Raw user query (anchor for scope validator).
        amplified_queries: Optional extra queries (scope-validated).
        protocol: Protocol dict; used for scope validation.
        max_serper: Max Serper results per query.
        max_s2: Max S2 results per query.
        fetch_cap: Hard cap on total URLs to fetch (cost control).
        enable_openalex_enrich: Toggle OpenAlex lookup per URL.
        enable_prefetch_filter: Toggle embedding-based off-topic filter
            (slow; off by default for the first live run).
        domain: Optional scope-template domain name (clinical / policy /
            tech / due_diligence). When set, R-6 Gap-2 domain backends
            augment the generic Serper+S2 retrieval with arxiv (tech),
            SEC EDGAR (DD), or policy-site targeted Serper queries.

    Returns LiveRetrievalResult.
    """
    api_calls: dict[str, int] = {"serper": 0, "s2": 0, "openalex": 0, "fetch": 0}
    notes: list[str] = []

    # ── Step 1: compile the effective query list ──────────────────────
    all_queries: list[str] = [research_question]
    if amplified_queries:
        all_queries.extend(amplified_queries)
    # Scope validation (de-drift)
    if protocol:
        valid = validate_amplified_queries(
            all_queries, protocol, always_keep_anchor=True,
        )
        effective_queries = valid.kept
        notes.append(
            f"scope_query_validator: {len(valid.kept)} kept / "
            f"{len(valid.dropped)} dropped"
        )
    else:
        effective_queries = list(all_queries)

    # ── Step 2: run Serper + S2 across queries ──────────────────────
    seen_urls: set[str] = set()
    candidates: list[SearchCandidate] = []

    # I-bug-776 (#817) layer-4 (Codex decision b): direct primary-trial DOI seed
    # candidates. Injected at the FRONT so the fetch_cap slice always includes
    # them (a reserved anchored-primary lane), and fetch_cap is bumped by the
    # seed count below so they are ADDITIVE — they do not evict search/guideline
    # candidates. They pass the SAME fetch / Unpaywall-OA / extraction / tier /
    # adequacy gates as every other source: a seed counts as T1 ONLY if the tier
    # classifier identifies the fetched content as a primary trial (no laundering).
    _n_seed_injected = 0
    for _surl in seed_urls or []:
        if _surl and _surl not in seen_urls:
            seen_urls.add(_surl)
            candidates.append(SearchCandidate(
                url=_surl, title="", snippet="", source="primary_trial_doi",
                query_origin="primary_trial_doi_seed",
            ))
            _n_seed_injected += 1
    if _n_seed_injected:
        logger.info(
            "[live_retriever] injected %d direct primary-trial DOI seed candidates",
            _n_seed_injected,
        )

    for q in effective_queries:
        logger.info("[live_retriever] SERPER q=%r", q[:80])
        serper_hits = _serper_search(q, num=max_serper)
        api_calls["serper"] += 1
        for hit in serper_hits:
            url = hit.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(SearchCandidate(
                url=url,
                title=hit.get("title", ""),
                snippet=hit.get("snippet", ""),
                source="serper",
                query_origin=q,
            ))

        logger.info("[live_retriever] S2 q=%r", q[:80])
        s2_hits = _s2_bulk_search(q, limit=max_s2)
        api_calls["s2"] += 1
        for hit in s2_hits:
            url = hit.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(SearchCandidate(
                url=url,
                title=hit.get("title", ""),
                snippet=hit.get("snippet", ""),
                source="s2",
                metadata={"doi": hit.get("doi"), "year": hit.get("year")},
                query_origin=q,
            ))

    # ── Step 2a: R-6 Gap-2 domain-routed backends ──────────────────
    # arXiv for tech, SEC EDGAR for due-diligence, policy-site Serper
    # for policy. Fail-open: any backend exception yields 0 new hits.
    if domain:
        try:
            from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                run_domain_backends,
            )
            domain_result = run_domain_backends(
                domain=domain,
                research_question=research_question,
                amplified_queries=amplified_queries,
            )
            for cand in domain_result.candidates:
                url = cand.url
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                # I-meta-002-q1d (#951): give domain-backend candidates a stable origin
                # bucket so the per-sub-query rerank reservation handles them consistently.
                if not getattr(cand, "query_origin", ""):
                    cand.query_origin = "domain_backend"
                candidates.append(cand)
            if domain_result.backends_used:
                notes.append(
                    f"domain_backends({domain}): "
                    f"{domain_result.per_backend_counts}"
                )
                for backend_name in domain_result.backends_used:
                    api_calls[backend_name] = (
                        api_calls.get(backend_name, 0) + 1
                    )
        except Exception as exc:
            logger.warning(
                "[live_retriever] domain_backends failed for %r: %s",
                domain, exc,
            )

    total_pre_filter = len(candidates)
    logger.info("[live_retriever] %d unique candidates from search", total_pre_filter)

    # ── Step 3: prefetch off-topic filter ──────────────────────────
    if enable_prefetch_filter and candidates:
        filt = filter_search_results(candidates, research_question)
        candidates = filt.kept
        notes.append(
            f"prefetch_offtopic: {filt.total_kept} kept / "
            f"{filt.total_rejected} rejected (threshold={filt.threshold_used:.2f})"
        )
    kept_by_offtopic = len(candidates)

    # ── Step 4: fetch-time relevance rerank + per-sub-query reservation, then cap ──
    # I-meta-002-q1d (#951, #943): replace arrival-order truncation with a no-spend,
    # no-model-load lexical relevance rerank that reserves >=1 slot per sub-query so a
    # long full-paragraph query cannot monopolize the cap (the breadth of amplified
    # queries was previously illusory). I-bug-776 (#817) layer-4 seed lane preserved:
    # primary-trial DOI seeds (empty title/snippet) are split out and prepended AFTER
    # ranking so relevance scoring can never drop them — they remain additive.
    candidates = _rerank_and_reserve(
        candidates,
        research_question=research_question,
        fetch_cap=fetch_cap,
        n_seed_injected=_n_seed_injected,
    )

    classified_sources: list[CorpusSource] = []
    evidence_rows: list[dict[str, Any]] = []
    fetched = 0
    failed_fetch = 0

    # ------------------------------------------------------------------
    # M-INT-1 — Parallel fetch into live_retriever (Phase E1)
    # ------------------------------------------------------------------
    # Wires `parallel_fetch.parallel_fetch(...)` into the content-fetch
    # loop. Per FINAL_PLAN.md M-INT-1: imported, invoked, run-log
    # evidence, and PG_USE_PARALLEL_FETCH=0 disables (rollback).
    #
    # The substrate's ParallelFetcher Protocol expects (bytes, str,
    # int). Live retrieval's existing _fetch_content returns
    # (content, ok, title, body_type) — we wrap it in an adapter
    # that stashes the full 4-tuple in a side dict keyed by URL,
    # then post-process serially using the side dict.
    use_parallel = os.environ.get("PG_USE_PARALLEL_FETCH", "1") != "0"
    fetched_side: dict[str, tuple[str, bool, str, str]] = {}

    if use_parallel and candidates:
        from src.polaris_graph.audit_ir.parallel_fetch import (
            FetchTask,
            parallel_fetch,
        )

        class _LiveContentParallelFetcher:
            """Adapter wrapping `_fetch_content(url, max_chars)` for
            the parallel_fetch substrate's ParallelFetcher Protocol.
            Stashes the full 4-tuple (content, ok, title, body_type)
            in a thread-safe side dict so the post-processing loop
            can read it back per-candidate."""

            def __init__(self, max_chars: int) -> None:
                self.max_chars = max_chars
                self._lock = threading.Lock()
                self.results = fetched_side

            def fetch(
                self, task: "FetchTask"
            ) -> tuple[bytes, str, int]:
                content, ok, title, body_type = _fetch_content(
                    task.source_url, self.max_chars,
                )
                with self._lock:
                    self.results[task.source_url] = (
                        content, ok, title, body_type,
                    )
                payload = (content or "").encode("utf-8", errors="replace")
                return (payload, "text/plain", 200 if ok else 502)

        try:
            max_workers = int(os.environ.get(
                "PG_LIVE_RETRIEVER_MAX_WORKERS", "8",
            ))
        except ValueError:
            max_workers = 8
        try:
            per_task_timeout = float(os.environ.get(
                "PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS", "120",
            ))
        except ValueError:
            per_task_timeout = 120.0

        fetch_tasks = [
            FetchTask(
                source_url=c.url,
                backend_id="default",
                task_metadata={"index": idx},
            )
            for idx, c in enumerate(candidates)
        ]
        fetcher = _LiveContentParallelFetcher(DEFAULT_CONTENT_MAX_CHARS)
        parallel_report = parallel_fetch(
            fetch_tasks, fetcher,
            max_workers=max_workers,
            per_task_timeout=per_task_timeout,
        )
        # Run-log evidence: persist the substrate's report into
        # api_calls so the manifest sees a non-zero invocation count.
        api_calls["parallel_fetch_success_count"] = (
            parallel_report.success_count
        )
        api_calls["parallel_fetch_errored_count"] = (
            parallel_report.errored_count
        )
        api_calls["parallel_fetch_timeout_count"] = (
            parallel_report.timeout_count
        )
        logger.info(
            "[live_retriever] M-INT-1 parallel_fetch: %d success, "
            "%d errored, %d timeout (max_workers=%d, "
            "per_task_timeout=%.0fs)",
            parallel_report.success_count,
            parallel_report.errored_count,
            parallel_report.timeout_count,
            max_workers, per_task_timeout,
        )

    # #554 (I-bug-115): bound the synchronous post-fetch candidate loop so a
    # wedged per-candidate operation can never hang the run with no terminal
    # verdict. Layer 1 = per-candidate enrich bound (_bounded_openalex_enrich);
    # Layer 2 = this overall wall-clock budget; Layer 3 = per-candidate
    # progress logging below so any future loop stall is diagnosable.
    _loop_deadline = time.monotonic() + _env_float(
        "PG_POST_FETCH_LOOP_BUDGET", 900.0,
    )
    _enrich_failfast = _env_int("PG_OPENALEX_ENRICH_FAILFAST", 3)
    _enrich_stats: dict[str, int] = {}
    _enrich_disabled = False

    for i, cand in enumerate(candidates):
        if time.monotonic() > _loop_deadline:
            logger.warning(
                "[live_retriever] post-fetch loop budget exceeded — stopping "
                "at candidate %d/%d (%d already classified)",
                i, len(candidates), len(classified_sources),
            )
            break
        logger.info(
            "[live_retriever] post-fetch candidate %d/%d %s",
            i + 1, len(candidates), cand.url[:60],
        )
        if use_parallel:
            content, ok, content_title_from_fetch, body_article_type = (
                fetched_side.get(cand.url, ("", False, "", ""))
            )
        else:
            # Fallback serial path (PG_USE_PARALLEL_FETCH=0).
            # Rate-limit gently (Serper doesn't but S2 prefers <= 1rps)
            if i > 0 and i % 5 == 0:
                time.sleep(0.2)
            # Fetch content (for tier classification + evidence)
            content, ok, content_title_from_fetch, body_article_type = (
                _fetch_content(cand.url, DEFAULT_CONTENT_MAX_CHARS)
            )
        api_calls["fetch"] += 1
        if not ok:
            failed_fetch += 1
        else:
            fetched += 1

        # Optional OpenAlex enrichment — wall-clock-bounded (#554). After
        # PG_OPENALEX_ENRICH_FAILFAST timeouts in this run, stop attempting
        # enrichment: it prevents abandoned daemon threads from accumulating
        # when OpenAlex is degraded for the whole run.
        oa = {}
        if enable_openalex_enrich and not _enrich_disabled:
            oa = _bounded_openalex_enrich(cand.url, cand.title, _enrich_stats)
            if oa:
                api_calls["openalex"] += 1
            if _enrich_stats.get("enrich_timeouts", 0) >= _enrich_failfast:
                _enrich_disabled = True
                logger.warning(
                    "[live_retriever] OpenAlex enrich timed out %dx — "
                    "disabling enrichment for the rest of this run",
                    _enrich_stats["enrich_timeouts"],
                )

        # Classify via tier_classifier
        domain_ = _domain_of(cand.url)
        # BUG-M-12 / M-13 (Codex pass 12/13): title resolution order
        # (longest → most reliable):
        #   1. OpenAlex display_name (full title from DOI lookup when
        #      URL embeds a DOI; otherwise from title-search fallback)
        #   2. Content-extracted title from fetched page (Jina/Crawl4AI
        #      markdown or HTML <title>) — catches MDPI/JAMA/PMC URLs
        #      where DOI isn't in the URL path
        #   3. Serper snippet title (often truncated)
        # Existing detectors (_detect_systematic_review_from_title,
        # _detect_narrative_flavor_from_title) then see the full
        # suffix and demote correctly.
        # BUG-M-14 (Codex pass 14): use the title extracted at fetch
        # time (from raw content BEFORE _strip_html stripped tags)
        # rather than trying to re-extract from the already-stripped
        # text. Fall back to the content-based extraction on stripped
        # text in case fetch didn't populate it.
        content_title = content_title_from_fetch or _extract_title_from_content(content)
        openalex_title = oa.get("openalex_full_title", "") or ""
        # Pick the longest candidate — longer titles carry more signal
        # (SR/MA / perspective / guidance suffixes).
        title_candidates = [t for t in (openalex_title, content_title, cand.title) if t]
        if title_candidates:
            classifier_title = max(title_candidates, key=len)
        else:
            classifier_title = cand.title or ""
        signals = ClassificationSignals(
            url=cand.url,
            title=classifier_title,
            publisher="",
            fetched_content_length=len(content),
            openalex_publication_type=oa.get("openalex_pub_type", "") or "",
            openalex_source_type=oa.get("openalex_source_type", "") or "",
            openalex_is_peer_reviewed=bool(oa.get("is_peer_reviewed", False)),
            source_type_hint="",
            # BUG-M-17 (Codex pass 2): body-inspection secondary signal.
            body_article_type=body_article_type,
        )
        tier_result = classify_source_tier(signals)

        classified_sources.append(CorpusSource(
            url=cand.url,
            title=cand.title,
            domain=domain_,
            tier=tier_result.tier.value,
            tier_confidence=tier_result.confidence,
            tier_rule=tier_result.matched_rules[0] if tier_result.matched_rules else "",
            tier_reasons=list(tier_result.reasons),
        ))

        # Build direct_quote: head-window (first 1500 chars) PLUS 500-char
        # windows around every decimal in the full content. This way the
        # Phase-4 provenance verifier can find numeric claims that live
        # deep in the fetched HTML (e.g., STEP 5 -15.2% on page 3 of a
        # Nature paper). Without this, strict_verify drops real data
        # because the number it's looking for is outside the head window.
        if content:
            # R-5 Fix D: skip content-starved evidence (PDF metadata,
            # empty body, formatting noise). Passing these to the
            # generator wastes tokens and produces "no extractable
            # text" admissions in the output.
            if is_content_starved(content):
                logger.info(
                    "[live_retriever] skipping content-starved evidence "
                    "for %r (len=%d)", cand.url, len(content),
                )
            else:
                direct_quote = _build_provenance_quote(
                    content, head_chars=1500, window_chars=500,
                )
                evidence_rows.append({
                    "evidence_id": f"ev_{i:03d}",
                    "source_url": cand.url,
                    "statement": cand.title[:300],
                    "direct_quote": direct_quote,
                    "tier": tier_result.tier.value,
                    "source": cand.source,
                    "full_content_length": len(content),
                })

    return LiveRetrievalResult(
        classified_sources=classified_sources,
        evidence_rows=evidence_rows,
        total_candidates_pre_filter=total_pre_filter,
        candidates_kept_by_scope=len(effective_queries),
        candidates_kept_by_offtopic=kept_by_offtopic,
        candidates_fetched=fetched,
        candidates_failed_fetch=failed_fetch,
        api_calls=api_calls,
        notes=notes,
    )
