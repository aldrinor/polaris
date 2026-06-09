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
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
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
from src.polaris_graph.retrieval.query_decomposer import distill_keywords  # FX-18 (#1122)
from src.polaris_graph.authority.authority_model import score_source_authority
from src.polaris_graph.authority.source_class import AuthoritySignals
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)

logger = logging.getLogger("polaris_graph.live_retriever")


SERPER_ENDPOINT = "https://google.serper.dev/search"
S2_BULK_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
OPENALEX_SOURCES_ENDPOINT = "https://api.openalex.org/sources"

# Phase 0a (GH #983, ADDENDUM C5): root-level /works select= fieldset for the
# authority model. OpenAlex select= is ROOT-LEVEL ONLY (rejects nested props),
# so summary_stats / apc_prices / is_core / is_in_doaj come from a SEPARATE
# /sources/{id} fetch keyed by primary_location.source.id.
OPENALEX_WORKS_SELECT = (
    "id,doi,title,display_name,type,publication_year,cited_by_count,"
    "is_retracted,primary_location,authorships"
)
OPENALEX_SOURCES_SELECT = (
    "id,is_core,is_in_doaj,apc_prices,summary_stats"
)

# Versioned local cache for the authority-enrich payload (live path). The
# schema version is bumped (not CREATE-IF-NOT-EXISTS no-op) on any column
# change, with an ALTER/rebuild migration (C5 requirement).
AUTHORITY_CACHE_DB = Path(
    os.getenv("PG_AUTHORITY_CACHE_DB", "cache/authority_enrich.sqlite")
)
# I-ready-017 #1134 (Codex diff-gate P1-2): bumped 1->2 so cached enrich payloads
# written before the journal_only `is_retracted` + `openalex_venue` fields are
# REBUILT (not served stale) — a cached retracted article must not pass the
# journal_only predicate via a payload that predates the retraction field.
AUTHORITY_CACHE_SCHEMA_VERSION = 2

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
    # #958 (S2): fail-loud corpus-truncation signal. True when the post-fetch
    # loop budget (PG_POST_FETCH_LOOP_BUDGET) broke mid-corpus, leaving later
    # candidates unclassified. Defaults keep existing constructors valid.
    corpus_truncated: bool = False
    candidates_total: int = 0
    candidates_processed: int = 0
    # I-ready-017 #1134: journal_only metadata sidecar, keyed by canonical URL.
    # Populated ONLY on the journal_only ON path (None = OFF = byte-identical).
    # Carries the per-source journal-article signals (openalex pub_type /
    # source_type / is_peer_reviewed / is_retracted / doi / venue) that the
    # citeability predicate needs; merged across retrieval stages by the sweep.
    journal_metadata_sidecar: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-002-q1d (#945): per-call retrieval-trace helpers. Best-effort, lazy-import, no-op when the
# trace is not started — PURELY OBSERVATIONAL (the retrieval/verify chokepoint is never altered).
# Mirrors the existing record_retrieval_attempt idiom (lazy import + swallow any error).
# ─────────────────────────────────────────────────────────────────────────────
def _trace_query(backend: str, query: str, urls: list[str]) -> None:
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_query(backend, query, urls)
    except Exception:
        pass


def _trace_kept(url: str, backend: str) -> None:
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_kept(url, backend)
    except Exception:
        pass


def _trace_drop(url: str, reason: str) -> None:
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_drop(url, reason)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-007b (#meta-007): per-tool utilization tracer. Record-only + fail-safe.
# The tracer NEVER changes retrieval behavior or return values; any tracer error
# (import failure, None tracer, disk error) is swallowed here so a telemetry bug
# can never break retrieval. Lazy import keeps the dependency one-directional.
# ─────────────────────────────────────────────────────────────────────────────
def _trace_tool(
    tool_name: str,
    target: str = "",
    status: str = "ok",
    latency_ms: float = 0.0,
    bytes_sent: int = 0,
    bytes_received: int = 0,
    backend_used: str = "",
    error: str = "",
    **metadata: Any,
) -> None:
    try:
        from src.polaris_graph.telemetry.tool_tracer import (
            get_tool_tracer,
            tool_tracker_enabled,
        )
        # I-meta-007b P2b: gate on PG_ENABLE_TOOL_TRACKER (default ON) so a
        # direct caller OUTSIDE run_one_query (which never ran the per-query
        # reset/bind) cannot append to a stale ON singleton when tracking is
        # disabled. When OFF this is a pure no-op.
        if not tool_tracker_enabled():
            return
        get_tool_tracer().record(
            tool_name=tool_name,
            target=target,
            status=status,
            latency_ms=latency_ms,
            bytes_sent=bytes_sent,
            bytes_received=bytes_received,
            backend_used=backend_used,
            error=error,
            **metadata,
        )
    except Exception:  # noqa: BLE001 — telemetry must never break retrieval
        pass


def _resp_content_len(resp: Any) -> int:
    """Best-effort byte length of an httpx response body for telemetry.

    Returns 0 when the response object lacks a measurable ``content`` (e.g. a
    lightweight test double). NEVER raises — record-only telemetry must not
    depend on the response's concrete shape.
    """
    try:
        content = getattr(resp, "content", None)
        return len(content) if content else 0
    except Exception:  # noqa: BLE001 — telemetry must never break retrieval
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# API clients
# ─────────────────────────────────────────────────────────────────────────────


# FX-17 (#1126): Serper `num` is a PAGE size (provider max ~20); large result sets need the `page`
# param (pagination). The old code silently floored `num` to 20 with no warning and never paginated.
_SERPER_PAGE_MAX = 20


def _serper_fetch_page(
    query: str, per_page: int, page: int, headers: dict[str, str]
) -> tuple[list[dict[str, Any]], bool, float, int, str]:
    """FX-17 (#1126): fetch ONE Serper page. Returns (items, ok, latency_ms, resp_bytes, error).
    Byte-identical to the legacy single call when page==1 (no `page` key in the payload)."""
    payload: dict[str, Any] = {"q": query, "num": per_page}
    if page > 1:
        payload["page"] = page
    _t0 = time.time()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            r = c.post(SERPER_ENDPOINT, json=payload, headers=headers)
        _latency_ms = (time.time() - _t0) * 1000.0
        if r.status_code != 200:
            return [], False, _latency_ms, _resp_content_len(r), f"HTTP {r.status_code}"
        organic = (r.json().get("organic", []) or [])
        items = [
            {"url": it.get("link", ""), "title": it.get("title", ""),
             "snippet": it.get("snippet", ""), "source": "serper"}
            for it in organic
        ]
        return items, True, _latency_ms, _resp_content_len(r), ""
    except Exception as exc:
        return [], False, (time.time() - _t0) * 1000.0, 0, str(exc)


def _serper_search(
    query: str, num: int = 10, api_calls: dict[str, int] | None = None
) -> list[dict[str, Any]]:
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
    per_page = max(1, min(num, _SERPER_PAGE_MAX))
    # FX-17 (#1126): make the silent clamp VISIBLE — the inert PG_SWEEP_MAX_SERPER=100 used to floor
    # to 20 with no signal. Surface it loudly so the requested-vs-served gap stops lying.
    _clamped = num > _SERPER_PAGE_MAX
    if _clamped:
        logger.warning(
            "[live_retriever] Serper num=%d exceeds the page max %d — clamping per-page to %d and "
            "paginating to the PG_SERPER_TOTAL_PER_QUERY budget.", num, _SERPER_PAGE_MAX, per_page,
        )
    # FX-17 (#1126): total-URL budget across pages. DEFAULT = one page (per_page) -> byte-identical to
    # the legacy single call; the benchmark slate raises PG_SERPER_TOTAL_PER_QUERY. Page count is
    # bounded by PG_SERPER_MAX_PAGES (small) and early-stops when a page returns < per_page.
    try:
        _total = max(per_page, int(os.getenv("PG_SERPER_TOTAL_PER_QUERY", str(per_page))))
    except ValueError:
        _total = per_page
    try:
        _max_pages = max(1, int(os.getenv("PG_SERPER_MAX_PAGES", "3")))
    except ValueError:
        _max_pages = 3
    _n_pages = min(_max_pages, -(-_total // per_page))  # ceil(total/per_page)

    # BB-002 (I-beatboth-fix-000 #1171): a sub-`per_page` page-1 count is NOT a reliable
    # end-of-results signal for an OFFSET-paginated SERP API — Serper routinely returns
    # 10 organic on page 1 even when page 2 has more, so the legacy `len(items) < per_page`
    # break short-circuited before page 2 and the PG_SERPER_TOTAL_PER_QUERY budget was never
    # reached (de-facto 10/query ceiling — chokepoint #4). When PG_SERPER_STOP_ON_ZERO_NEW=1
    # the loop keeps offset-paging until (a) budget met, (b) a page returns 0 NEW (post-dedup)
    # items, or (c) PG_SERPER_MAX_PAGES — the only RELIABLE end-of-results signals. DEFAULT OFF
    # = byte-identical (the legacy short-page break is preserved). Discovery-breadth only; every
    # new URL flows through the same fetch -> strict_verify -> 4-role chokepoint unchanged.
    _stop_on_zero_new = os.getenv("PG_SERPER_STOP_ON_ZERO_NEW", "0").strip() in (
        "1", "true", "True",
    )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    _pages_fetched = 0
    _last_latency = 0.0
    _last_bytes = 0
    _last_err = ""
    for _page in range(1, _n_pages + 1):
        items, ok, _last_latency, _last_bytes, _last_err = _serper_fetch_page(
            query, per_page, _page, headers
        )
        # FX-17 (#1126) iter-2: count EACH HTTP page request (a real Serper API call), not once
        # per query. P2 fix — api_calls['serper'] used to undercount paginated breadth.
        if api_calls is not None:
            api_calls["serper"] = api_calls.get("serper", 0) + 1
        if not ok:
            _trace_tool(
                "serper", target=query, status="fail", latency_ms=_last_latency,
                bytes_sent=len(query), bytes_received=_last_bytes,
                backend_used="serper_api_v1", error=_last_err, page=_page,
            )
            logger.warning("[live_retriever] Serper page %d failed for %r: %s",
                           _page, query[:60], _last_err)
            break  # fail-open: keep pages already accumulated; do not discard.
        _pages_fetched += 1
        _new = 0
        for it in items:
            u = it.get("url", "")
            if u and u not in seen:
                seen.add(u)
                out.append(it)
                _new += 1
        if len(out) >= _total:
            break  # budget met.
        if _stop_on_zero_new:
            # BB-002 (#1171): keep paging past a short page; stop only when a page
            # added 0 NEW (post-dedup) URLs — the reliable end-of-results signal.
            if _new == 0:
                break
        elif len(items) < per_page:
            break  # legacy (default OFF): short page -> assume no more results.
    _trace_tool(
        "serper", target=query, status="ok" if out or not _last_err else "fail",
        latency_ms=_last_latency, bytes_sent=len(query), bytes_received=_last_bytes,
        backend_used="serper_api_v1", result_count=len(out),
        pages_fetched=_pages_fetched, num_requested=num, per_page=per_page,
        page_max=_SERPER_PAGE_MAX, clamped=_clamped, total_budget=_total,
        stop_on_zero_new=_stop_on_zero_new,   # BB-002 (#1171): which stop policy ran
    )
    _trace_query("serper", query, [o["url"] for o in out])
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
    # I-meta-007b: wall-clock for the tool tracer (record-only).
    _t0 = time.time()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            r = c.get(S2_BULK_ENDPOINT, params=params, headers=headers)
        _latency_ms = (time.time() - _t0) * 1000.0
        if r.status_code != 200:
            _trace_tool(
                "s2", target=query, status="fail", latency_ms=_latency_ms,
                bytes_received=_resp_content_len(r),
                backend_used="semantic_scholar_api", error=f"HTTP {r.status_code}",
            )
            logger.warning(
                "[live_retriever] S2 returned %s for %r",
                r.status_code, query[:60],
            )
            _trace_query("semantic_scholar", query, [])
            return []
        data = r.json()
    except Exception as exc:
        _trace_tool(
            "s2", target=query, status="fail",
            latency_ms=(time.time() - _t0) * 1000.0,
            backend_used="semantic_scholar_api", error=str(exc),
        )
        logger.warning("[live_retriever] S2 exception: %s", exc)
        _trace_query("semantic_scholar", query, [])
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
    # BB-004 (I-beatboth-fix-000 #1171): a HTTP-200 that yields ZERO usable papers
    # (all lacked oa_pdf + DOI, or `data` was empty) is a DEAD-BACKEND signal — the
    # legacy unconditional status="ok" reported it as success_rate=1.0 and masked the
    # collapse (15 S2 calls -> 0 results on drb_90 still showed success). LAW II
    # silent-downgrade fix: trace a DISTINCT "ok_zero" status + zero_yield=True so the
    # discovery_funnel / run-health surfaces it LOUDLY instead of as a clean success.
    # Telemetry/loudness ONLY — no evidence or verification path is touched; the
    # returned list is unchanged (empty), so downstream control flow is identical.
    _s2_zero_yield = len(out) == 0
    _trace_tool(
        "s2", target=query,
        status="ok_zero" if _s2_zero_yield else "ok",
        latency_ms=_latency_ms,
        bytes_received=_resp_content_len(r),
        backend_used="semantic_scholar_api", result_count=len(out),
        zero_yield=_s2_zero_yield,
    )
    _trace_query("semantic_scholar", query, [o["url"] for o in out])
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


def _candidate_oa_hints(metadata: Any) -> tuple[str, str]:
    """I-meta-007c: pull (doi, pmid) hints from a candidate's metadata dict.

    S2 candidates carry ``metadata["doi"]`` (line ~2001); PMIDs are not in the
    S2 dict today but the slot is honoured for forward-compat / testability.
    Returns ("", "") for non-dict / missing metadata. NEVER raises.

    Diff-gate P2a: the whole body is wrapped in a fail-open try/except returning
    ("", "") on ANY error, matching the resolver helpers' fail-open contract —
    a malformed metadata object must never break the retrieval loop."""
    try:
        if not isinstance(metadata, dict):
            return "", ""
        doi = str(metadata.get("doi") or "").strip()
        pmid = str(metadata.get("pmid") or "").strip()
        return doi, pmid
    except Exception:  # noqa: BLE001 — fail-OPEN, never break retrieval.
        return "", ""


def _authority_cache_init() -> None:
    """Create the authority-enrich cache with a VERSIONED migration (C5).

    Not a CREATE-IF-NOT-EXISTS no-op: a stale cache whose recorded schema
    version is older than AUTHORITY_CACHE_SCHEMA_VERSION is rebuilt rather than
    silently used with missing columns.
    """
    AUTHORITY_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTHORITY_CACHE_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            " id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
        )
        row = conn.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
        existing = row[0] if row else 0
        table_present = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='authority_enrich'"
        ).fetchone() is not None
        # Migrate whenever the recorded version is older than the current one
        # (existing=0 means an unversioned/legacy cache). Drop + rebuild the
        # payload table (the cache is a rebuildable accelerator, never the
        # source of truth) — NOT a CREATE-IF-NOT-EXISTS no-op (C5).
        if table_present and existing < AUTHORITY_CACHE_SCHEMA_VERSION:
            conn.execute("DROP TABLE IF EXISTS authority_enrich")
            logger.warning(
                "[live_retriever] authority cache schema %d < %d — migrating "
                "(rebuild)", existing, AUTHORITY_CACHE_SCHEMA_VERSION,
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS authority_enrich ("
            " key TEXT PRIMARY KEY,"
            " payload_json TEXT NOT NULL,"
            " fetched_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO schema_meta (id, version) VALUES (1, ?)"
            " ON CONFLICT(id) DO UPDATE SET version = excluded.version",
            (AUTHORITY_CACHE_SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()


# I-ready-017 #1134 (Codex diff-gate P1): run the versioned migration once before
# the FIRST cache access (read OR write), so a stale v1 payload — which predates
# the journal_only is_retracted/openalex_venue fields — is rebuilt away on the
# READ path too, never served unchanged. Previously the migration ran only on
# _authority_cache_put, so a get-before-put returned a stale payload and a cached
# retracted journal article could pass the journal_only predicate.
_authority_cache_migrated = False


def _ensure_authority_cache_migrated() -> None:
    global _authority_cache_migrated
    if not _authority_cache_migrated:
        _authority_cache_init()
        _authority_cache_migrated = True


def _authority_cache_get(key: str) -> Optional[dict[str, Any]]:
    _ensure_authority_cache_migrated()
    if not AUTHORITY_CACHE_DB.exists():
        return None
    conn = sqlite3.connect(AUTHORITY_CACHE_DB)
    try:
        row = conn.execute(
            "SELECT payload_json FROM authority_enrich WHERE key = ?", (key,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    if not row:
        return None
    import json
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def _authority_cache_put(key: str, payload: dict[str, Any]) -> None:
    import json
    _ensure_authority_cache_migrated()
    conn = sqlite3.connect(AUTHORITY_CACHE_DB)
    try:
        conn.execute(
            "INSERT INTO authority_enrich (key, payload_json) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET payload_json = excluded.payload_json,"
            " fetched_at = CURRENT_TIMESTAMP",
            (key, json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()


def _openalex_fetch_source(
    client: httpx.Client, source_id: str
) -> dict[str, Any]:
    """Separate /sources/{id} fetch for venue-level authority fields (C5).

    Returns the summary_stats / apc_prices / is_core / is_in_doaj subset, or
    {} on any failure (the model degrades to LOW confidence — never fabricates).
    """
    if not source_id:
        return {}
    sid = source_id.rsplit("/", 1)[-1]  # accept full URL or bare S-id
    if not sid.startswith("S"):
        return {}
    resp = client.get(
        f"{OPENALEX_SOURCES_ENDPOINT}/{sid}",
        params={"select": OPENALEX_SOURCES_SELECT},
    )
    if resp.status_code != 200:
        return {}
    src = resp.json()
    if not isinstance(src, dict):
        return {}
    return {
        "is_core": src.get("is_core"),
        "is_in_doaj": src.get("is_in_doaj"),
        "apc_prices": src.get("apc_prices"),
        "summary_stats": src.get("summary_stats") or {},
    }


def _build_authority_signals_dict(
    work: dict[str, Any], source_fields: dict[str, Any]
) -> dict[str, Any]:
    """Build the additive AuthoritySignals payload (C1/C5) as a plain dict.

    Stored as a dict so the live-path enrich return value stays JSON-cacheable;
    live_retriever reconstructs the AuthoritySignals dataclass at classify time.
    Missing fields stay absent/None -> the authority model returns LOW
    confidence (fail-honest, never fabricate).
    """
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    # First resolved institution (ROR) from authorships.
    ror_id = ""
    inst_type = ""
    country_code = ""
    for authorship in work.get("authorships") or []:
        for inst in authorship.get("institutions") or []:
            if inst.get("ror"):
                ror_id = inst.get("ror") or ""
                inst_type = inst.get("type") or ""
                country_code = inst.get("country_code") or ""
                break
        if ror_id:
            break

    stats = source_fields.get("summary_stats") or {}
    venue_summary_stats: dict[str, Any] = {}
    if isinstance(stats, dict):
        if "h_index" in stats:
            venue_summary_stats["h_index"] = stats.get("h_index")
        if "2yr_mean_citedness" in stats:
            venue_summary_stats["2yr_mean_citedness"] = stats.get("2yr_mean_citedness")

    return {
        "cited_by_count": work.get("cited_by_count"),
        "source_id": source.get("id", "") or "",
        "venue_summary_stats": venue_summary_stats or None,
        "is_core": source_fields.get("is_core"),
        "is_in_doaj": source_fields.get("is_in_doaj"),
        "apc_prices": source_fields.get("apc_prices"),
        "publication_year": work.get("publication_year"),
        "ror_id": ror_id,
        "institution_type": inst_type,
        "country_code": country_code,
    }


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
        # Diff-gate P2-B: READ the authority-enrich cache first, keyed by the
        # stable pre-fetch identifier (DOI when present, else the URL). A hit
        # returns the frozen enrich dict and AVOIDS the OpenAlex /works +
        # /sources round-trip entirely (the read path the cache exists for).
        enrich_cache_key = f"doi:{doi}" if doi else f"url:{url}"
        cached = _authority_cache_get(enrich_cache_key)
        if isinstance(cached, dict) and cached:
            return cached
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            if doi:
                # Exact DOI lookup — most reliable. OpenAlex accepts
                # both the bare DOI and the URL form; use bare DOI.
                # Phase 0a (C5): request the root-level authority select=.
                r = c.get(
                    f"{OPENALEX_ENDPOINT}/doi:{doi}",
                    params={"select": OPENALEX_WORKS_SELECT},
                )
                if r.status_code != 200:
                    # Fall back to title search if DOI not indexed
                    r = c.get(
                        OPENALEX_ENDPOINT,
                        params={
                            "search": (title or url)[:200],
                            "per-page": 1,
                            "select": OPENALEX_WORKS_SELECT,
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
                        "select": OPENALEX_WORKS_SELECT,
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

            # Phase 0a (C5): SEPARATE /sources/{id} fetch for venue-level
            # authority fields, keyed by primary_location.source.id. Absent
            # source / failed fetch -> empty -> LOW confidence downstream.
            source_id = source.get("id", "") or ""
            source_fields = _openalex_fetch_source(c, source_id)

        # Build the additive AuthoritySignals payload (dict form, cacheable).
        authority_signals = _build_authority_signals_dict(work, source_fields)

        enrich = {
            "openalex_pub_type": work.get("type", "") or "",
            "openalex_source_type": source.get("type", "") or "",
            "is_peer_reviewed": bool(
                work.get("type") in ("article", "review")
                and source.get("type") == "journal"
            ),
            # I-ready-017 #1134 (Codex diff-gate P1-2/P1-3): carry the journal
            # VENUE (for the distinct-journal adequacy count) and the RETRACTION
            # flag (so the journal_only predicate can reject retracted articles)
            # into the enrich dict -> sidecar. ADDITIVE; legacy consumers ignore.
            "openalex_venue": (source.get("display_name", "") or ""),
            "is_retracted": bool(work.get("is_retracted", False)),
            # Codex diff-gate P2: carry the OpenAlex work DOI so the journal_only
            # sidecar can credit an anchor discovered via a Serper/URL-only path
            # (not just SearchCandidate metadata). Normalized (no scheme).
            "doi": str(work.get("doi", "") or "").replace("https://doi.org/", "").replace("http://doi.org/", ""),
            "openalex_id": work.get("id", ""),
            # BUG-M-12 (Codex pass 12): preserve OpenAlex's full
            # display_name. Serper snippet titles are often truncated
            # mid-title, losing "systematic review and meta-analysis",
            # "perspective for primary care providers", etc. suffixes
            # that the classifier needs to demote false T1s.
            "openalex_full_title": work.get("display_name", "") or "",
            # Phase 0a (C1/C5): the additive authority payload, carried at
            # :1751 -> :1789 into ClassificationSignals.authority.
            "authority_signals": authority_signals,
        }
        # Diff-gate P2-B: WRITE the whole enrich dict under the SAME stable
        # pre-fetch key the read path uses, so a later lookup is a true cache
        # hit that skips the network (the read path is now exercised).
        _authority_cache_put(enrich_cache_key, enrich)
        return enrich
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


def _post_fetch_loop_budget(fetch_cap: int) -> float:
    """I-ready-003 (#1074) P1: the post-fetch loop wall-clock budget, SCALED with ``fetch_cap``.

    The loop classifies all ~``fetch_cap`` candidates serially (each paying an OpenAlex enrich
    round-trip). A FIXED budget that does not scale with ``fetch_cap`` silently truncates the corpus at
    full cap (the I-cap-005 ~40-URL silent-throttle class, one layer deeper). Returns
    ``max(PG_POST_FETCH_LOOP_BUDGET floor, fetch_cap * PG_POST_FETCH_PER_URL_BUDGET)`` — byte-identical
    for small caps (the 900s floor wins), and a conservative operator env can no longer silently win
    because the ``fetch_cap`` term floors it. Pure (env-only); unit-testable."""
    return max(
        _env_float("PG_POST_FETCH_LOOP_BUDGET", 900.0),
        max(0, int(fetch_cap)) * _env_float("PG_POST_FETCH_PER_URL_BUDGET", 4.0),
    )


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


# I-meta-002-q1d (#954): table-aware linearization. _strip_html flattens <table> markup to running text,
# so a result-table cell loses its header association ("Discontinuation due to nausea ... 3.8%" collapses to
# a floating "3.8") and integer / %-without-decimal cells become unanchored — strict_verify can then only
# verify the loose decimals that survive in prose, under-verifying the richest clinical data (results tables).
# This no-network pass detects <table> blocks and linearizes each data row as "header: cell | header: cell"
# BEFORE flattening, so the cell keeps its column header in the text the provenance window captures.
_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
# Capture each cell WITH its tag (th vs td) so a column-header row is distinguishable from a row-header.
_CELL_TAGGED_RE = re.compile(r"<(t[hd])\b[^>]*>(.*?)</t[hd]>", re.DOTALL | re.IGNORECASE)
# colspan/rowspan shift columns → index-zip would mis-align → degrade (Codex diff-gate iter-1 P1).
_SPAN_ATTR_RE = re.compile(r"\b(?:col|row)span\s*=", re.IGNORECASE)


def _cell_text(cell_html: str) -> str:
    """Strip inner tags from a single cell and collapse whitespace."""
    txt = re.sub(r"<[^>]+>", " ", cell_html)
    return re.sub(r"\s+", " ", txt).strip()


def _parse_row_cells(row_html: str) -> list[tuple[str, str]]:
    """Return [(tag, text)] for each <th>/<td> in the row (tag lowercased)."""
    return [(m.group(1).lower(), _cell_text(m.group(2))) for m in _CELL_TAGGED_RE.finditer(row_html)]


def linearize_html_tables(html: str) -> str:
    """Return result-table rows linearized so table numbers survive in text WITH their column header when —
    and ONLY when — the source unambiguously declares one. Pure regex, no network, fail-open ('').

    Header:cell association is emitted ONLY for the CANONICAL column-header table: the first non-empty row
    is ENTIRELY <th> with non-empty header text, the table has >1 column, NO colspan/rowspan anywhere, and
    <th> appears in NO other row (so it is column headers, not per-row row-headers). EVERY other shape —
    span tables, headerless tables, row-header / mixed <th>+<td> data rows, empty-<th>-before-data — DEGRADES
    to plain ' | '-joined cells. Joined still surfaces the number next to its row label, but a cell can NEVER
    receive a column header the source did not declare (no fabricated provenance). This single conservative
    rule covers the Codex diff-gate P1s (colspan/rowspan, headerless-multirow, row-header, empty-th-before-
    data) without enumerating each."""
    try:
        out_rows: list[str] = []
        for table_html in _TABLE_RE.findall(html or ""):
            raw_rows = _ROW_RE.findall(table_html)
            if not raw_rows:
                continue
            rows = [_parse_row_cells(r) for r in raw_rows]
            rows = [r for r in rows if any(text for _tag, text in r)]  # drop all-empty rows
            if not rows:
                continue

            def _join(r: list[tuple[str, str]]) -> str:
                return " | ".join(text for _tag, text in r if text)

            first = rows[0]
            canonical = (
                not _SPAN_ATTR_RE.search(table_html)              # no colspan/rowspan
                and len(first) > 1                                # multi-column
                and all(tag == "th" for tag, _t in first)         # row 0 is ENTIRELY <th> (column headers)
                and all(text for _tag, text in first)             # ... with non-empty header text
                and not any(tag == "th" for r in rows[1:] for tag, _t in r)  # <th> only in row 0
            )
            if not canonical:
                # DEGRADE: every ambiguous shape joins plainly — never a fabricated header:cell.
                out_rows.extend(j for r in rows if (j := _join(r)))
                continue
            # CANONICAL column-header table: zip each data row to the <th> header row by column index.
            headers = [text for _tag, text in first]
            for row in rows[1:]:
                cells = [text for _tag, text in row]
                pairs = [
                    f"{headers[j]}: {cells[j]}"
                    if j < len(headers) and headers[j] and cells[j]
                    else cells[j]
                    for j in range(len(cells))
                ]
                joined = " | ".join(p for p in pairs if p)
                if joined:
                    out_rows.append(joined)
        return "\n".join(r for r in out_rows if r)
    except Exception:  # noqa: BLE001 — additive observability; never break fetch on a malformed table
        return ""


_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# Bound the captured JSON-LD so a pathological page cannot balloon the payload
# the classifier scans (the junk patterns only need the @type marker near the top).
_JSONLD_MAX_CHARS = 20000


def _extract_jsonld_blocks(raw_html: str) -> str:
    """Capture the raw <script type="application/ld+json"> block contents from
    the RAW fetched HTML — BEFORE _strip_html() deletes every <script> block.

    Diff-gate P1-C: the structural junk-detection classifier (Signal C,
    news_article/login_wall/press_release classes) scans JSON-LD strings such as
    `"@type":"NewsArticle"` that live ONLY inside ld+json <script> blocks. Those
    blocks are destroyed by _strip_html (line removing <script>...</script>), so
    the demotion never fires unless the JSON-LD is extracted FIRST and routed to
    ClassificationSignals.structured_jsonld separately from the stripped body.

    Returns the concatenated block contents (bounded), or "" when the input is
    not raw HTML (e.g. Jina markdown / Crawl4AI cleaned text already had its
    <script> blocks removed upstream) — honestly empty, never fabricated. Pure
    regex, no network, fail-open ("").
    """
    if not raw_html or "ld+json" not in raw_html.lower():
        return ""
    try:
        blocks = [m.group(1).strip() for m in _JSONLD_SCRIPT_RE.finditer(raw_html)]
        joined = "\n".join(b for b in blocks if b)
        return joined[:_JSONLD_MAX_CHARS]
    except Exception:  # noqa: BLE001 — additive structural signal; never break fetch
        return ""


def _strip_html(html: str) -> str:
    """Extract visible text from HTML via basic regex (trafilatura if available), then APPEND table-aware
    linearized rows (#954) so result-table cells survive with their column headers regardless of how the
    base extractor flattened the tables. Default-ON; PG_FETCH_TABLE_LINEARIZE=0 disables the append."""
    base = ""
    try:
        import trafilatura  # type: ignore
        extracted = trafilatura.extract(html) or ""
        if extracted:
            base = extracted
    except Exception:
        pass
    if not base:
        # Fallback: strip tags + collapse whitespace
        no_tags = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        no_tags = re.sub(r"<style[^>]*>.*?</style>", " ", no_tags, flags=re.DOTALL | re.IGNORECASE)
        no_tags = re.sub(r"<[^>]+>", " ", no_tags)
        no_tags = re.sub(r"\s+", " ", no_tags)
        base = no_tags.strip()
    if os.getenv("PG_FETCH_TABLE_LINEARIZE", "1").strip().lower() not in ("0", "false", "no", "off", ""):
        tables = linearize_html_tables(html)
        if tables:
            base = (base + "\n\n" + tables).strip() if base else tables
    return base


def _fetch_content_httpx_naive(
    url: str, max_chars: int
) -> tuple[str, bool, str, str, str]:
    """Legacy naive httpx fetcher. Kept as emergency fallback when
    AccessBypass is unavailable (tests that don't want Crawl4AI browser
    spawning, or sandboxes without Playwright).

    Returns (content, ok, title, body_type, jsonld). Diff-gate P1-C: `jsonld`
    is the raw ld+json <script> block contents extracted from the RAW HTML
    BEFORE _strip_html deletes the <script> blocks (empty when the page carries
    no JSON-LD)."""
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
            return "", False, "", "", ""
        ctype = (r.headers.get("content-type", "") or "").lower()
        raw = r.text if "text" in ctype or "html" in ctype or "json" in ctype else ""
        if not raw and r.content:
            raw = r.content.decode("utf-8", errors="ignore")
        # BUG-M-13/M-14: extract title from raw HTML BEFORE stripping
        # (the <title> tag is gone after _strip_html).
        extracted_title = _extract_title_from_content(raw)
        # BUG-M-17: detect article-type from bounded body region.
        body_type = _detect_article_type_from_body(raw)
        # Diff-gate P1-C: capture raw ld+json BEFORE _strip_html removes <script>.
        jsonld = _extract_jsonld_blocks(raw)
        content = _strip_html(raw)[:max_chars]
        return content, bool(content), extracted_title, body_type, jsonld
    except Exception as exc:
        logger.debug(
            "[live_retriever] naive-httpx fetch %r failed: %s", url, exc,
        )
        return "", False, "", "", ""


def _fallback_naive_fetch(
    url: str,
    max_chars: int,
    t0: float,
    primary_reason: str,
) -> tuple[str, bool, str, str, str]:
    """Run the naive-httpx fallback and record its FINAL outcome (I-meta-007b P2a).

    Every content-fetch fallback in :func:`_fetch_content` (AccessBypass
    disabled / unavailable / timed out / raised / produced no result) ends by
    delegating to :func:`_fetch_content_httpx_naive`. The pre-fix code traced
    ``fail``/``timeout`` BEFORE that delegation, so a SUCCESSFUL fallback was
    still recorded as a failure. This helper traces the ACTUAL result instead:

    * ``status="ok"`` + real ``bytes_received`` (length of fetched content) when
      the naive fetch returned content,
    * ``status="fail"`` otherwise — carrying ``primary_reason`` (the reason the
      primary path fell back, e.g. ``access_bypass_timeout_90s``) in ``error``
      for diagnostics.

    ``backend_used="httpx_naive"`` uniformly because the naive fetcher is what
    actually ran. ``t0`` is the single wall-clock start captured at the top of
    :func:`_fetch_content` so latency reflects total fetch time. Record-only +
    fail-safe (``_trace_tool`` swallows its own errors); returns the naive
    fetcher's tuple unchanged so retrieval behavior is identical to before.
    """
    result = _fetch_content_httpx_naive(url, max_chars)
    content, ok = result[0], result[1]
    _trace_tool(
        "fetch_content",
        target=url,
        status="ok" if ok else "fail",
        latency_ms=(time.time() - t0) * 1000.0,
        backend_used="httpx_naive",
        bytes_received=len(content) if ok else 0,
        error="" if ok else str(primary_reason),
        primary_reason=str(primary_reason),
    )
    return result


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
        content, ok, _title, body_type, _jsonld = _fetch_content(url, max_chars)
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


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-007c: OPEN-ACCESS resolver for the LIVE retrieval loop.
#
# When AccessBypass returns a stub/empty/paywalled result for a candidate that
# carries a DOI (from S2 metadata or embedded in the URL), resolve the
# best open-access full text BEFORE giving up. Fail-OPEN: any resolver error
# returns "" and the caller falls through to its existing path — retrieval is
# NEVER broken by a resolver failure.
#
# Fallback order (exact, per `.codex/I-meta-007/_wiring_specs.txt`
# LANE wire:unpaywall-live-path):
#   1. Unpaywall v2 best-OA URL  -> fetch via AccessBypass
#   2. PubMed EFetch abstract (only when a PMID is available)
#   3. else "" (caller keeps its existing stub/fallback behaviour)
#
# The OA fetch REUSES the existing AccessBypass stack (already budgeted in the
# per-candidate fetch timeout) and the existing frame_fetcher parsers — no new
# network budget, no duplicated parsing. All helpers are module-level so tests
# can monkeypatch each seam independently (no real network, no spend).
#
# Env gates (LAW VI):
#   PG_ENABLE_LIVE_OA_RESOLVER  default "1"  — master on/off switch.
#   PG_UNPAYWALL_EMAIL          default placeholder — Unpaywall ToS email.
# ─────────────────────────────────────────────────────────────────────────────
# BB-007 (I-beatboth-fix-000 #1171): the placeholder Unpaywall email. The OA resolver treats this
# (or an empty value) as "resolver unavailable" and fails LOUD (traces a distinct signal) rather than
# issuing a doomed request that Unpaywall ToS rejects/throttles — a hidden cause of the fetch-fail rate.
_UNPAYWALL_PLACEHOLDER_EMAIL = "polaris@example.org"


def _oa_resolver_enabled() -> bool:
    """True iff the live OA resolver is enabled. Off iff the env var is set to
    a recognized falsey value ("0" / "false" / "no"); default ON."""
    raw = os.getenv("PG_ENABLE_LIVE_OA_RESOLVER", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def _try_oa_resolution(
    url: str,
    extracted_doi: str = "",
    pmid: str = "",
    max_chars: int = DEFAULT_CONTENT_MAX_CHARS,
) -> str:
    """Resolve open-access full text for a paywalled/stub candidate.

    Public entry point called from :func:`_fetch_content` when AccessBypass
    returns stub/empty content AND a DOI is available. Returns upgraded content
    (str, capped at ``max_chars``) or "" on any failure / when disabled.

    Fail-OPEN by contract: every internal failure mode returns "" so the caller
    falls through to its existing behaviour. NEVER raises.

    Diff-gate P1: a DOI is REQUIRED to do anything. The PubMed EFetch abstract
    is only a SECONDARY fallback AFTER a DOI-keyed Unpaywall miss — a PMID-only,
    no-DOI candidate must NOT be upgraded (Europe-PMC can emit metadata with
    doi=None + pmid set; that record must stay a miss, not become PubMed text).

    Fallback order (DOI required throughout):
      1. Unpaywall v2 best-OA URL  -> AccessBypass fetch
      2. PubMed EFetch abstract    (only after a DOI-keyed Unpaywall miss AND
                                     when ``pmid`` is present)
      3. ""
    """
    if not _oa_resolver_enabled():
        return ""
    doi = (extracted_doi or "").strip()
    # Diff-gate P1: DOI-present gate. Without a DOI the resolver does nothing —
    # the PMID is only a secondary fallback after a DOI-keyed Unpaywall miss.
    if not doi:
        return ""
    try:
        # Step 1: Unpaywall best-OA URL(s), prioritized pdf > html.
        if doi:
            for oa_url in _unpaywall_get_oa_urls(doi):
                if not oa_url:
                    continue
                content = _fetch_oa_url_via_bypass(oa_url, max_chars)
                if content:
                    logger.info(
                        "[live_retriever] OA resolver: Unpaywall hit for "
                        "doi=%s url=%r (%d chars)",
                        doi, oa_url[:80], len(content),
                    )
                    return content[:max_chars]
        # Step 2: PubMed EFetch abstract when a PMID is available.
        if pmid:
            abstract = _pubmed_fetch_abstract(pmid)
            if abstract:
                logger.info(
                    "[live_retriever] OA resolver: PubMed EFetch fallback "
                    "for pmid=%s (%d chars)",
                    pmid, len(abstract),
                )
                return abstract[:max_chars]
    except Exception as exc:  # noqa: BLE001 — fail-OPEN, never break retrieval.
        logger.debug(
            "[live_retriever] OA resolver error for doi=%s url=%r: %s",
            doi, url[:80], exc,
        )
        return ""
    return ""


def _unpaywall_get_oa_urls(doi: str) -> list[str]:
    """Query the Unpaywall v2 API for OA location URLs.

    Returns an ordered list ``[pdf_url, html_url]`` (each may be absent; the
    list is empty when the work is not OA or the lookup fails). Fail-OPEN: any
    error returns ``[]`` so the caller falls back to PubMed / its existing path.

    Reuses ``frame_fetcher._parse_unpaywall_response`` for the OA-URL parse so
    the live path and the M-56 frame path share one parser.
    """
    if not doi:
        return []
    try:
        import httpx as _httpx
        from src.polaris_graph.retrieval.frame_fetcher import (
            _parse_unpaywall_response,
        )

        # BB-007 (I-beatboth-fix-000 #1171): Unpaywall ToS REQUIRES a real contact email; the
        # placeholder polaris@example.org is rejected/throttled, so the resolver silently no-ops
        # (a hidden cause of the 67-72% fetch-fail rate). FAIL LOUD instead of silent: if the email
        # is the placeholder (or empty), trace a DISTINCT resolver-unavailable signal and return []
        # without issuing the doomed request. The benchmark slate must supply a REAL PG_UNPAYWALL_EMAIL.
        email = os.getenv("PG_UNPAYWALL_EMAIL", _UNPAYWALL_PLACEHOLDER_EMAIL).strip()
        if not email or email.lower() == _UNPAYWALL_PLACEHOLDER_EMAIL:
            logger.warning(
                "[live_retriever] OA resolver UNAVAILABLE: PG_UNPAYWALL_EMAIL is the placeholder "
                "%r — Unpaywall ToS requires a real contact email. Set a real PG_UNPAYWALL_EMAIL "
                "to enable OA full-text resolution (doi=%s).",
                _UNPAYWALL_PLACEHOLDER_EMAIL, doi,
            )
            _trace_tool(
                "oa_resolver", target=doi, status="unavailable",
                backend_used="unpaywall_v2",
                error="placeholder_unpaywall_email",
                resolver_unavailable=True,
            )
            return []
        endpoint = "https://api.unpaywall.org/v2/" + doi.strip()
        with _httpx.Client(timeout=10.0) as client:
            response = client.get(endpoint, params={"email": email})
        if response.status_code != 200:
            return []
        try:
            data = response.json()
        except Exception:  # noqa: BLE001 — malformed JSON => no OA.
            return []
        parsed = _parse_unpaywall_response(data if isinstance(data, dict) else {})
        if not parsed.get("is_oa"):
            return []
        # Prioritize PDF over landing-page HTML (PDF is full text; HTML may be
        # an abstract-only shell).
        urls = [parsed.get("oa_pdf_url") or "", parsed.get("oa_html_url") or ""]
        return [u for u in urls if u]
    except Exception as exc:  # noqa: BLE001 — fail-OPEN.
        logger.debug(
            "[live_retriever] Unpaywall OA query failed for doi=%s: %s",
            doi, exc,
        )
        return []


def _fetch_oa_url_via_bypass(oa_url: str, max_chars: int) -> str:
    """Fetch an OA URL via the existing AccessBypass stack.

    Reuses ``frame_fetcher._fetch_url_pattern`` — the proven sync/async-safe
    AccessBypass wrapper (also the documented monkeypatch seam) — so the live
    path does not re-implement the event-loop juggling. Returns content (str,
    capped at ``max_chars``) or "" on failure. Fail-OPEN.
    """
    if not oa_url:
        return ""
    try:
        from src.polaris_graph.retrieval.frame_fetcher import _fetch_url_pattern

        content, _final_url = _fetch_url_pattern(oa_url)
        if content:
            return content[:max_chars]
        return ""
    except Exception as exc:  # noqa: BLE001 — fail-OPEN.
        logger.debug(
            "[live_retriever] OA bypass fetch failed for %r: %s",
            oa_url[:80], exc,
        )
        return ""


def _pubmed_fetch_abstract(pmid: str) -> str:
    """Fetch an abstract from PubMed EFetch for ``pmid``.

    Reuses ``frame_fetcher._parse_pubmed_xml`` for the XML -> abstract parse so
    the live path and the M-56 frame path share one parser. Returns the
    abstract text or "" on failure. Fail-OPEN.
    """
    if not pmid:
        return ""
    try:
        import httpx as _httpx
        from src.polaris_graph.retrieval.frame_fetcher import _parse_pubmed_xml

        endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": str(pmid).strip(),
            "rettype": "abstract",
            "retmode": "xml",
        }
        with _httpx.Client(timeout=15.0) as client:
            response = client.get(endpoint, params=params)
        if response.status_code != 200 or not (response.text or "").strip():
            return ""
        parsed = _parse_pubmed_xml(response.text)
        return parsed.get("abstract") or ""
    except Exception as exc:  # noqa: BLE001 — fail-OPEN.
        logger.debug(
            "[live_retriever] PubMed abstract fetch failed for pmid=%s: %s",
            pmid, exc,
        )
        return ""


def _fetch_content(
    url: str,
    max_chars: int,
    doi_hint: str = "",
    pmid_hint: str = "",
) -> tuple[str, bool, str, str, str]:
    """Fetch URL content using the AccessBypass cascade (Crawl4AI +
    Jina Reader + Firecrawl concurrent, fallback to direct HTTP +
    Archive.org + institutional proxy + Sci-Hub).

    Returns (content, ok, title, body_type, jsonld). Diff-gate P1-C: `jsonld`
    is the raw ld+json <script> block contents extracted from the RAW fetched
    HTML BEFORE _strip_html removes <script> blocks, so the structural junk
    classifier (Signal C: NewsArticle / press-release / login-wall) can fire on
    the live ON path. Empty when the winning backend already returned cleaned
    text (Jina markdown / Crawl4AI) with no <script> blocks — honestly empty,
    never fabricated.

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

    I-meta-007c: ``doi_hint`` / ``pmid_hint`` are optional identifiers carried
    from the candidate's S2 metadata. When AccessBypass returns stub/empty/
    paywalled content AND a DOI is resolvable (hint or extracted from the URL),
    the OPEN-ACCESS resolver (Unpaywall v2 -> AccessBypass; else PubMed EFetch
    abstract) is tried BEFORE giving up. Gated by PG_ENABLE_LIVE_OA_RESOLVER
    (default "1"); fail-OPEN (resolver errors never break retrieval).
    """
    # I-meta-007b: single wall-clock for the tool tracer (record-only). The
    # naive-httpx fallbacks below are recorded as the content-fetch outcome so
    # the per-run summary reflects every fetch attempt's path + latency.
    _t0 = time.time()
    if os.getenv("PG_DISABLE_ACCESS_BYPASS", "0") == "1":
        # M-45 pass-2: record env-opt-out so diagnostics can see it.
        _m45_record_fetch_telemetry(
            url, "httpx_naive", "pg_disable_access_bypass=1"
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail), not the
        # pre-fallback "fail" — a successful naive fetch must be recorded ok.
        return _fallback_naive_fetch(
            url, max_chars, _t0, "pg_disable_access_bypass=1"
        )
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
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail).
        return _fallback_naive_fetch(
            url, max_chars, _t0, f"access_bypass_import_failed: {exc}"
        )

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
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail). The
        # backend that actually ran is httpx_naive, not access_bypass.
        return _fallback_naive_fetch(
            url, max_chars, _t0, f"access_bypass_timeout_{int(deadline)}s"
        )

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
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail).
        return _fallback_naive_fetch(
            url, max_chars, _t0, f"access_bypass_raised_{type(exc).__name__}"
        )
    if "value" not in result_holder:
        logger.warning(
            "[live_retriever] AccessBypass produced no result for %s",
            url[:80],
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive", "access_bypass_no_result"
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail).
        return _fallback_naive_fetch(
            url, max_chars, _t0, "access_bypass_no_result"
        )
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
        # I-meta-007c: AccessBypass returned a stub/empty/paywalled result.
        # Before giving up, try the OPEN-ACCESS resolver when a DOI is
        # available (from S2 metadata hint or embedded in the URL). On a hit
        # we return the upgraded content with ok=True so the longer body
        # re-tiers above T7 downstream. Fail-OPEN: an empty resolver result
        # leaves the existing stub return path untouched.
        #
        # Diff-gate P2b: when the resolver is gated OFF, do NOT compute the DOI
        # and do NOT call _try_oa_resolution — the OFF path is byte-identical to
        # the pre-existing stub control flow (resolver never invoked).
        # Diff-gate P1: enforce the DOI-present gate at the CALL SITE. Only enter
        # the OA-resolver branch when a non-empty DOI is resolvable (hint or
        # embedded in the URL). An empty-DOI candidate (e.g. an Europe-PMC record
        # with doi=None + pmid set) must NOT be upgraded via a PMID-only PubMed
        # fetch — it falls straight through to the pre-existing miss tuple.
        if _oa_resolver_enabled():
            oa_doi = (doi_hint or "").strip() or _extract_doi_from_url(url)
            if oa_doi:
                oa_content = _try_oa_resolution(
                    url=url,
                    extracted_doi=oa_doi,
                    pmid=(pmid_hint or "").strip(),
                    max_chars=max_chars,
                )
                if oa_content:
                    logger.info(
                        "[live_retriever] fetch_oa %s (doi=%s chars=%d) — "
                        "upgraded from stub via OA resolver",
                        url[:80], oa_doi, len(oa_content),
                    )
                    _m45_record_fetch_telemetry(url, "oa_resolver", "")
                    _trace_tool(
                        "fetch_content", target=url, status="ok",
                        latency_ms=(time.time() - _t0) * 1000.0,
                        backend_used="oa_resolver",
                        bytes_received=len(oa_content),
                        content_length=len(oa_content),
                    )
                    return oa_content, True, "", "", ""
        _trace_tool(
            "fetch_content", target=url, status="stub",
            latency_ms=(time.time() - _t0) * 1000.0,
            backend_used=method, error=str(reason or "no_content"),
        )
        return "", False, "", "", ""
    # BUG-M-14 (Codex pass 14): extract the full page title from the
    # raw result.content BEFORE _strip_html removes <title> tags. Jina
    # markdown has "Title: X" on first line; Crawl4AI cleaned text has
    # the same. HTML fetches have <title>.
    extracted_title = _extract_title_from_content(result.content)
    # BUG-M-17 (Codex pass 2): detect article-type from body.
    body_type = _detect_article_type_from_body(result.content)
    # Diff-gate P1-C: capture raw ld+json from result.content BEFORE _strip_html
    # removes <script> blocks. Direct-HTTP path returns raw HTML (JSON-LD present);
    # Jina/Crawl4AI return cleaned text with <script> already gone (honestly empty).
    jsonld = _extract_jsonld_blocks(result.content)
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
    _trace_tool(
        "fetch_content", target=url, status="ok",
        latency_ms=(time.time() - _t0) * 1000.0,
        backend_used=method, bytes_received=len(content),
        content_length=len(content),
    )
    return content, bool(content), extracted_title, body_type, jsonld


def _domain_of(url: str) -> str:
    try:
        # FX-13 (#1125): removeprefix, NOT lstrip — `lstrip("www.")` strips any leading char in the
        # SET {w, .}, corrupting domains like www.who.int -> "ho.int" / www.washington.edu ->
        # "ashington.edu". removeprefix removes only the literal "www." prefix.
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
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


# I-run11-010 (#1056, S1): bot-challenge / access-denial stub markers. A publisher 302-redirect to a
# captcha / "are you a robot" page can pass the length + alpha-ratio checks below (the ScienceDirect
# stub that admitted the required Elsevier journals to the drb_72 pool was 340 chars, ~55% alpha) and
# enter the evidence pool as a journal article — so claims "grounded" on it cannot verify. These are
# VERY specific access-denial phrases (not generic short text), matched case-insensitively, and only
# applied to SHORT bodies so a full article that merely mentions "captcha" is never false-dropped.
_ACCESS_DENIAL_MARKERS = (
    "are you a robot",
    # Codex #1056 diff-gate P2: require the challenge-PAGE phrasing, not a bare "captcha" mention, so
    # a short legitimate article/abstract that merely DISCUSSES CAPTCHA is not false-dropped.
    "captcha challenge",
    "captcha verification",
    "complete the captcha",
    "verify you are human",
    "verifying you are human",
    "confirm you are a human",
    "please confirm you are",
    "access denied",
    "enable javascript and cookies",
    "unusual traffic",
    "checking your browser",
    "请完成",  # CN: "please complete (the verification)"
    "人机验证",  # CN: "human-machine verification"
)
_ACCESS_DENIAL_MAX_CHARS = int(os.getenv("PG_ACCESS_DENIAL_MAX_CHARS", "3000"))


def _is_access_denial_stub(content: str) -> bool:
    """True if a (short) fetched body looks like a bot-challenge / access-denial page rather than
    article content (I-run11-010 #1056 S1). Keys on SPECIFIC access-denial phrases AND a short length
    so a legitimate full article that quotes one of these phrases is not false-dropped."""
    if not content or len(content.strip()) > _ACCESS_DENIAL_MAX_CHARS:
        return False
    low = content.lower()
    return any(marker in low for marker in _ACCESS_DENIAL_MARKERS)


def is_content_starved(content: str, min_useful_chars: int = 200) -> bool:
    """R-5 Fix D: detect evidence rows whose fetched content is PDF
    metadata / formatting fragments / empty text — not useful prose.

    Returns True if the content should NOT be passed to the generator
    (because the LLM would admit it has no answer, wasting tokens).

    Heuristics:
      - Length of visible text < min_useful_chars
      - Bot-challenge / access-denial stub (I-run11-010 #1056 S1)
      - PDF metadata markers dominate
      - Ratio of alphabetic chars to total chars is low
    """
    if not content or len(content.strip()) < min_useful_chars:
        return True

    # I-run11-010 (#1056, S1): a captcha / robot-challenge stub is starved even when it clears the
    # length + alpha-ratio bars — it carries no article content to ground a claim against.
    if _is_access_denial_stub(content):
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


# FX-15a (#1118): the injected-seed source classes that share the reserved/undroppable/unranked
# lane. `primary_trial_doi` = #817 layer-4 direct primary-trial DOI seeds; `agentic_seed` =
# agentic-discovered URLs; `deepener_seed` = citation-snowball deepener URLs (Codex iter-1 P1:
# these are primary-trial-DERIVED but NOT direct DOI seeds, so they must not pollute
# `primary_trial_doi` telemetry either). BB-006 (#1171): `storm_seed` = STORM interview-search-result
# URLs harvested URL-ONLY (the synthesized STORM text is NEVER ingested). ALL are split out and
# prepended unranked; FX-15b later makes the web-discovered classes droppable via the host-class
# filter (telemetry-correctness here is the prerequisite).
_SEED_SOURCE_LABELS: frozenset[str] = frozenset(
    {"primary_trial_doi", "agentic_seed", "deepener_seed", "storm_seed"}
)


# FX-15b (#1119): path/route markers for pages that CANNOT carry a single paper's content — pure
# navigation / search-result / table-of-contents / discussion listings. Matched as lowercase
# substrings of the URL. Chosen PRECISION-FIRST and EMPIRICALLY (Codex iter-1 P1 + evidence_pool.json
# cross-reference on the held drb_72 trace): every one appears ONLY on listing/nav pages, never on a
# page that fetched real evidence.
#
# DELIBERATELY EXCLUDED (Codex iter-1 P1 — these CAN bear evidence, so pre-fetch dropping is a
# precision failure; the POST-fetch tier classifier + content-starvation check handle the empty ones):
#   - `/conference/.../program/paper/<id>` — held S7SHZQ4n (50k chars) + S25ktKkD (30k chars) fetched
#     as REAL papers; the junk 8A8RRTQY has the IDENTICAL shape, so URL cannot distinguish them.
#   - `/annual-meeting/.../paper/...` — same ambiguity as conference papers.
#   - conference SUPPLEMENT abstracts (`/Supplement_`) — bear abstract-level evidence; let the tier
#     classifier DOWN-TIER them (it already does) rather than pre-fetch DROP them.
# `/issue/` (singular) is NOT a marker (it prefixes real article paths); `/issues/` (plural TOC
# listing) IS.
_LOW_CONTENT_PATH_MARKERS: tuple[str, ...] = (
    "/search", "/browse", "/issues/", "/forum/",
    "/toc/",  # journal table-of-contents listing (e.g. /toc/jpe/current) — never a real article
)


def _is_low_content_host_or_page(url: str, title: str = "") -> bool:
    """FX-15b (#1119): structural reject of pure NAV / SERP / table-of-contents / discussion URLs,
    applied to agentic-discovered seed URLs BEFORE fetch (a cheap deterministic floor that skips a
    wasted fetch on pages that cannot contain a paper). PRECISION-FIRST — must NEVER reject a page
    that could fetch real evidence (conference papers, supplement abstracts, working-paper PDFs are
    all KEPT and decided by the post-fetch tier classifier + content-starvation check). Pure + no
    network. Returns True iff the URL is a pure listing/nav page that should be dropped.
    """
    if not url:
        return False
    u = url.lower()
    if any(marker in u for marker in _LOW_CONTENT_PATH_MARKERS):
        return True
    # Paginated SERP / search-result listing pages (not an article).
    if "search-results" in u or "per-page=" in u:
        return True
    return False


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
    relevance scoring would drop them. They are SPLIT OUT by `source in _SEED_SOURCE_LABELS`
    (FX-15a #1118: the set `{primary_trial_doi, agentic_seed}` — both injected seed classes keep
    the additive/reserved lane) and prepended AFTER ranking — never ranked, never dropped, exactly
    additive as before.

    Reservation: group non-seeds by `query_origin`; sort each group by (-score, index);
    take at most ONE reserved item per origin while capacity remains (origins with the best
    candidate score reserved first when origins exceed cap); then fill the remaining slots
    by global (-score, index). The long full-paragraph/anchor query is not starved.

    Fail-open (never raise): on any error fall back to the previous arrival-order behavior
    `candidates[:fetch_cap + n_seed_injected]`.
    """
    try:
        seeds = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
        non_seeds = [c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS]
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
    seed_only: bool = False,
    seed_source: str = "primary_trial_doi",
    seed_query_origin: str = "primary_trial_doi_seed",
    research_frame: Any = None,
    anchor_seed: bool = True,
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
        research_frame: Optional planner `ResearchFrame` (I-meta-005 Phase 2
            #986). When set (ON-mode), the field-agnostic need-type registry
            REPLACES the domain backends at the Step-2a seam — discovery is
            keyed on the frame's declared `evidence_needs` + extracted
            `jurisdictions`, NOT a domain. Mutually exclusive with `domain` on
            the on-path (the sweep passes `domain=None` on-mode).
        anchor_seed: When True (default — OFF-mode byte-identical), the verbatim
            `research_question` is PREPENDED to the effective query list and the
            scope validator keeps it (`always_keep_anchor=True`). I-meta-005
            Phase 4 (#988) GAP rounds pass `anchor_seed=False` so the broad anchor
            is NOT re-fired: `all_queries = amplified_queries` ONLY, the scope
            validator does NOT re-add the anchor (`always_keep_anchor=False`), and
            the need-type backend is invoked with `anchor_seed=False` (no
            `research_question` prepend there either). A gap round therefore fires
            EXACTLY the gap sub-queries on BOTH the core Serper/S2 seam AND the
            need-type adapters.

    Returns LiveRetrievalResult.

    Raises:
        MalformedPlanError: when `research_frame` carries a malformed
            `evidence_needs` value OR a malformed jurisdiction SHAPE. This is
            validated UP-FRONT (before ANY live discovery, incl. core
            Serper/S2) and FAILS LOUD — it NEVER silently degrades to core
            Serper/S2 (brief §2.4 P2-note-1). Distinct from the fail-OPEN
            adapter/network handling at the Step-2a seam.
    """
    api_calls: dict[str, int] = {"serper": 0, "s2": 0, "openalex": 0, "fetch": 0}
    notes: list[str] = []

    # ── Step 0: UP-FRONT plan validation (I-meta-005 Phase 2, P2-note-1) ──
    # A malformed frame (bad evidence_need / bad jurisdiction SHAPE) must FAIL
    # LOUD here — BEFORE the core Serper/S2 baseline spends or populates any
    # candidate. The router's validation raises MalformedPlanError; we let it
    # propagate (it is a VALIDATION error, distinct from the fail-OPEN
    # adapter/network handling at Step 2a). Only fires on-mode (frame present).
    if research_frame is not None and not seed_only:
        from src.polaris_graph.discovery.need_type_router import (
            validate_frame_needs,
        )
        # Raises MalformedPlanError on a malformed value/SHAPE; a valid-shape
        # unknown jurisdiction + an empty evidence_needs both pass (non-fatal).
        validate_frame_needs(research_frame)

    # ── Step 1: compile the effective query list ──────────────────────
    # I-meta-005 Phase 4 (#988): `anchor_seed=False` (gap rounds) suppresses the
    # broad `research_question` anchor on BOTH the prepend AND the scope-validator
    # reinsertion, so a gap round fires ONLY the gap sub-queries (no wasted
    # anchor re-run). Default True = OFF-mode byte-identical.
    all_queries: list[str] = [research_question] if anchor_seed else []
    if amplified_queries:
        all_queries.extend(amplified_queries)
    # Scope validation (de-drift)
    if protocol:
        valid = validate_amplified_queries(
            all_queries, protocol, always_keep_anchor=anchor_seed,
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
            # FX-15a (#1118): the seed SOURCE/ORIGIN labels are now caller-supplied so the agentic
            # lane (seed_source='agentic_seed') is no longer mislabeled as a primary-trial DOI seed.
            # Defaults preserve the #817 layer-4 DOI-lane labels for every existing caller.
            candidates.append(SearchCandidate(
                url=_surl, title="", snippet="", source=seed_source,
                query_origin=seed_query_origin,
            ))
            _n_seed_injected += 1
    if _n_seed_injected:
        logger.info(
            "[live_retriever] injected %d direct seed candidates (source=%s, query_origin=%s)",
            _n_seed_injected, seed_source, seed_query_origin,
        )

    # I-meta-002-q1d (#942-deepener, Codex diff-gate iter-2 P1): seed_only processes ONLY the injected
    # seed_urls — no Serper/S2 fan-out and no domain backends. Used by the deepener pass so it fetches
    # exactly the citation-snowball-discovered URLs (and nothing else) through the same chokepoint.
    for q in ([] if seed_only else effective_queries):
        logger.info("[live_retriever] SERPER q=%r", q[:80])
        # FX-17 (#1126) iter-2: pass api_calls so each HTTP page (not each query) is counted inside
        # _serper_search. The old `+= 1` here undercounted paginated breadth.
        serper_hits = _serper_search(q, num=max_serper, api_calls=api_calls)
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

        # FX-18 (#1122): S2 bulk is a KEYWORD index — feeding it the 40-70-word NL query returned ~0
        # for 4/5 golden questions. Send a SHORT content-keyword distillation of `q` instead (pure,
        # stopword-filtered, capped). Flag-gated PG_S2_KEYWORD_DISTILL (default on); an empty
        # distillation falls back to the NL `q` (never an empty search). The candidate's `query_origin`
        # stays the NL `q` so the per-sub-query rerank reservation + plan-sufficiency are unchanged.
        _s2_query = q
        if os.getenv("PG_S2_KEYWORD_DISTILL", "1") != "0":
            _kw = distill_keywords(q, max_terms=int(os.getenv("PG_S2_KEYWORD_MAX_TERMS", "8")))
            if _kw:
                _s2_query = _kw
        logger.info("[live_retriever] S2 q=%r", _s2_query[:80])
        s2_hits = _s2_bulk_search(_s2_query, limit=max_s2)
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

        # FX-18 (#1122): OpenAlex /works?search handles NL queries that the S2 keyword index does not,
        # and is already built (domain_backends.openalex_search, fail-open). Wire it as a PARALLEL
        # academic backend — ADD (union), not replace S2 (Codex Q8) — sending the NL `q`; union+dedup
        # via the shared `seen_urls`. Candidates carry source="openalex_search"; default query_origin
        # to `q`. Flag-gated PG_OPENALEX_SEARCH (default on). Fail-open: a backend fault adds 0 hits.
        if os.getenv("PG_OPENALEX_SEARCH", "1") != "0":
            _oa_t0 = time.time()
            try:
                from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                    openalex_search,
                )
                _oa_hits = openalex_search(q, limit=max_s2)
                api_calls["openalex_search"] = api_calls.get("openalex_search", 0) + 1
                # FX-20 (#1128): trace openalex as a first-class backend so the discovery_funnel reads
                # its requested-vs-returned from the SAME tool_trace rows as serper/s2 (FX-18 wired the
                # call but never traced it — a tracer-only funnel would silently OMIT openalex).
                _trace_tool(
                    "openalex_search", target=q, status="ok",
                    latency_ms=(time.time() - _oa_t0) * 1000.0,
                    backend_used="openalex_works_api",
                    result_count=len(_oa_hits), num_requested=max_s2,
                )
                # FX-18b (#1123): mirror serper/s2 -> emit an openalex retrieval_trace row so RERUN §-1.1 can verify it fired.
                _trace_query("openalex_search", q, [getattr(c, "url", "") for c in _oa_hits])
                for cand in _oa_hits:
                    url = getattr(cand, "url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    if not getattr(cand, "query_origin", ""):
                        cand.query_origin = q
                    candidates.append(cand)
            except Exception as exc:
                _trace_tool(
                    "openalex_search", target=q, status="fail",
                    latency_ms=(time.time() - _oa_t0) * 1000.0,
                    backend_used="openalex_works_api",
                    error=str(exc), result_count=0, num_requested=max_s2,
                )
                logger.warning(
                    "[live_retriever] openalex_search failed for %r (fail-open): %s",
                    q[:60], exc,
                )

    # ── Step 2a: specialized issuer-class backends ──────────────────
    # I-meta-005 Phase 2 (#986) DUAL PATH:
    #   ON-mode (research_frame present): the field-agnostic NEED-TYPE registry
    #     REPLACES the domain backends — discovery is routed off the frame's
    #     declared evidence_needs + jurisdictions (NO `if domain ==` branch
    #     reached). The malformed-frame case already FAILED LOUD at Step 0.
    #   OFF-mode (domain set, no frame): the legacy R-6 Gap-2 domain switch runs
    #     byte-identically (arXiv for tech, SEC EDGAR for DD, policy-site Serper
    #     for policy, Europe PMC for clinical).
    # Both stay fail-OPEN at the live seam (ADAPTER/network exception -> 0 new
    # hits; the run degrades to the core Serper/S2 baseline). Skipped on the
    # seed_only deepener pass (no extra retrieval).
    if research_frame is not None and not seed_only:
        # ON-path: need-type registry dispatch. NO domain literal consulted.
        try:
            from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                run_need_type_backends,
            )
            need_result = run_need_type_backends(
                frame=research_frame,
                research_question=research_question,
                amplified_queries=amplified_queries,
                anchor_seed=anchor_seed,
            )
            for cand in need_result.candidates:
                url = cand.url
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                if not getattr(cand, "query_origin", ""):
                    cand.query_origin = "need_type_backend"
                candidates.append(cand)
            if need_result.backends_used:
                notes.append(
                    f"need_type_backends({need_result.needs}): "
                    f"{need_result.per_backend_counts}"
                )
                for backend_name in need_result.backends_used:
                    api_calls[backend_name] = (
                        api_calls.get(backend_name, 0) + 1
                    )
        except Exception as exc:
            # ADAPTER/network fail-open ONLY. A MalformedPlanError cannot reach
            # here — it raised at Step 0 before the baseline ran.
            logger.warning(
                "[live_retriever] need_type_backends failed (fail-open): %s",
                exc,
            )
    elif domain and not seed_only:
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
        # FX-15b (#1119): EXCLUDE the injected seeds (empty title/snippet, source in
        # _SEED_SOURCE_LABELS) from the semantic off-topic filter. They have no snippet to embed,
        # so `filter_search_results` would score them ~0 similarity and REJECT the entire reserved
        # seed lane (e.g. all agentic seeds). Filter only the non-seed search candidates; re-prepend
        # the seeds untouched (mirrors the seed split in `_rerank_and_reserve`). Seeds are never
        # off-topic-dropped — exactly as before this lane could enable the filter.
        _seed_cands = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
        _nonseed_cands = [
            c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS
        ]
        if _nonseed_cands:
            _pre_offtopic_urls = {c.url for c in _nonseed_cands}
            filt = filter_search_results(_nonseed_cands, research_question)
            candidates = _seed_cands + filt.kept
            for _dropped_url in _pre_offtopic_urls - {c.url for c in filt.kept}:
                _trace_drop(_dropped_url, "offtopic")
            notes.append(
                f"prefetch_offtopic: {filt.total_kept} kept / "
                f"{filt.total_rejected} rejected (threshold={filt.threshold_used:.2f})"
            )
        # else: only seeds present (e.g. seed_only mode) — nothing to off-topic filter.
    kept_by_offtopic = len(candidates)

    # ── Step 4: fetch-time relevance rerank + per-sub-query reservation, then cap ──
    # I-meta-002-q1d (#951, #943): replace arrival-order truncation with a no-spend,
    # no-model-load lexical relevance rerank that reserves >=1 slot per sub-query so a
    # long full-paragraph query cannot monopolize the cap (the breadth of amplified
    # queries was previously illusory). I-bug-776 (#817) layer-4 seed lane preserved:
    # primary-trial DOI seeds (empty title/snippet) are split out and prepended AFTER
    # ranking so relevance scoring can never drop them — they remain additive.
    _pre_rerank_urls = {c.url for c in candidates}
    candidates = _rerank_and_reserve(
        candidates,
        research_question=research_question,
        fetch_cap=fetch_cap,
        n_seed_injected=_n_seed_injected,
    )
    for _dropped_url in _pre_rerank_urls - {c.url for c in candidates}:
        _trace_drop(_dropped_url, "rerank_not_selected")

    classified_sources: list[CorpusSource] = []
    evidence_rows: list[dict[str, Any]] = []
    fetched = 0
    failed_fetch = 0
    # I-ready-017 #1134: journal_only metadata sidecar (ON-path only). Keyed by
    # canonical URL; carries per-source journal-article signals for the
    # citeability predicate. Stays None when the flag is OFF (byte-identical).
    from src.polaris_graph.nodes.journal_only_filter import (
        journal_only_flag_enabled as _jo_flag_enabled,
        journal_metadata_entry as _jo_meta_entry,
        canonicalize_url as _jo_canon,
    )
    _journal_only_on = _jo_flag_enabled()
    _journal_sidecar: dict[str, Any] = {} if _journal_only_on else {}

    # ------------------------------------------------------------------
    # M-INT-1 — Parallel fetch into live_retriever (Phase E1)
    # ------------------------------------------------------------------
    # Wires `parallel_fetch.parallel_fetch(...)` into the content-fetch
    # loop. Per FINAL_PLAN.md M-INT-1: imported, invoked, run-log
    # evidence, and PG_USE_PARALLEL_FETCH=0 disables (rollback).
    #
    # The substrate's ParallelFetcher Protocol expects (bytes, str,
    # int). Live retrieval's existing _fetch_content returns
    # (content, ok, title, body_type, jsonld) — we wrap it in an adapter
    # that stashes the full 5-tuple in a side dict keyed by URL,
    # then post-process serially using the side dict. Diff-gate P1-C: the 5th
    # element is the raw ld+json captured before _strip_html (Signal C input).
    use_parallel = os.environ.get("PG_USE_PARALLEL_FETCH", "1") != "0"
    fetched_side: dict[str, tuple[str, bool, str, str, str]] = {}

    if use_parallel and candidates:
        from src.polaris_graph.audit_ir.parallel_fetch import (
            FetchTask,
            parallel_fetch,
        )

        class _LiveContentParallelFetcher:
            """Adapter wrapping `_fetch_content(url, max_chars)` for
            the parallel_fetch substrate's ParallelFetcher Protocol.
            Stashes the full 5-tuple (content, ok, title, body_type, jsonld)
            in a thread-safe side dict so the post-processing loop
            can read it back per-candidate."""

            def __init__(self, max_chars: int) -> None:
                self.max_chars = max_chars
                self._lock = threading.Lock()
                self.results = fetched_side

            def fetch(
                self, task: "FetchTask"
            ) -> tuple[bytes, str, int]:
                # I-meta-007c: surface the per-candidate DOI/PMID hints
                # (stashed in task_metadata at task construction) so the OA
                # resolver can fire on the DEFAULT parallel path, not just the
                # serial fallback.
                _meta = task.task_metadata or {}
                content, ok, title, body_type, jsonld = _fetch_content(
                    task.source_url, self.max_chars,
                    doi_hint=str(_meta.get("doi") or ""),
                    pmid_hint=str(_meta.get("pmid") or ""),
                )
                with self._lock:
                    self.results[task.source_url] = (
                        content, ok, title, body_type, jsonld,
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

        fetch_tasks = []
        for idx, c in enumerate(candidates):
            # I-meta-007c: carry the candidate's DOI/PMID hints into the
            # FetchTask so _LiveContentParallelFetcher.fetch can pass them to
            # _fetch_content for the OA resolver (default = parallel path).
            _doi, _pmid = _candidate_oa_hints(getattr(c, "metadata", None))
            fetch_tasks.append(
                FetchTask(
                    source_url=c.url,
                    backend_id="default",
                    task_metadata={"index": idx, "doi": _doi, "pmid": _pmid},
                )
            )
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
    # I-ready-003 (#1074) P1: the post-fetch loop processes ALL ~fetch_cap candidates serially (each
    # paying an OpenAlex enrich round-trip + tier-classify). A FIXED budget that does NOT scale with
    # fetch_cap silently TRUNCATES the corpus at full cap (the I-cap-005 ~40-URL silent-throttle class,
    # one layer deeper): the slate raised fetch_cap 25x without scaling this wall-clock budget, so the
    # loop hit the deadline mid-corpus, set corpus_truncated, and broke — a "1000-URL" run classified
    # only the first few hundred. Scale the budget with fetch_cap: max(explicit env floor, fetch_cap *
    # per-URL budget). BYTE-IDENTICAL for small caps (the 900s env floor wins when fetch_cap is small);
    # a conservative operator env can no longer silently win because the fetch_cap term floors it.
    _loop_deadline = time.monotonic() + _post_fetch_loop_budget(fetch_cap)
    _enrich_failfast = _env_int("PG_OPENALEX_ENRICH_FAILFAST", 3)
    _enrich_stats: dict[str, int] = {}
    _enrich_disabled = False

    # #958 (S2): corpus-truncation counters. Initialized BEFORE the loop so the
    # empty/no-break path does not depend on a loop-local `i` (Codex P2). Default
    # = "processed all" / not truncated; the budget-break below overrides.
    _corpus_truncated = False
    _candidates_total = len(candidates)
    _candidates_processed = len(candidates)

    for i, cand in enumerate(candidates):
        if time.monotonic() > _loop_deadline:
            logger.warning(
                "[live_retriever] post-fetch loop budget exceeded — stopping "
                "at candidate %d/%d (%d already classified)",
                i, len(candidates), len(classified_sources),
            )
            # #958: record the truncation as a fail-loud signal (was log-only).
            # candidates_processed = the zero-based break index i = post-filter
            # candidates whose loop iteration began before the cutoff (Codex P2).
            _corpus_truncated = True
            _candidates_processed = i
            break
        logger.info(
            "[live_retriever] post-fetch candidate %d/%d %s",
            i + 1, len(candidates), cand.url[:60],
        )
        if use_parallel:
            content, ok, content_title_from_fetch, body_article_type, raw_jsonld = (
                fetched_side.get(cand.url, ("", False, "", "", ""))
            )
        else:
            # Fallback serial path (PG_USE_PARALLEL_FETCH=0).
            # Rate-limit gently (Serper doesn't but S2 prefers <= 1rps)
            if i > 0 and i % 5 == 0:
                time.sleep(0.2)
            # I-meta-007c: thread the DOI/PMID hints from S2 metadata so the
            # OA resolver can fire when AccessBypass returns a stub/paywall.
            _cand_doi, _cand_pmid = _candidate_oa_hints(
                getattr(cand, "metadata", None)
            )
            # Fetch content (for tier classification + evidence)
            content, ok, content_title_from_fetch, body_article_type, raw_jsonld = (
                _fetch_content(
                    cand.url, DEFAULT_CONTENT_MAX_CHARS,
                    doi_hint=_cand_doi, pmid_hint=_cand_pmid,
                )
            )
        api_calls["fetch"] += 1
        if not ok:
            failed_fetch += 1
            _trace_drop(cand.url, "fetch_failed")
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
        # Phase 0a (C1/C5): reconstruct the additive AuthoritySignals payload
        # from the live-path enrich dict. Absent/partial -> None / partial ->
        # the authority model returns LOW confidence (fail-honest). Inert on the
        # OFF path (the legacy rule body never reads `.authority`).
        authority_payload = None
        _auth_dict = oa.get("authority_signals")
        if isinstance(_auth_dict, dict):
            authority_payload = AuthoritySignals(
                cited_by_count=_auth_dict.get("cited_by_count"),
                source_id=_auth_dict.get("source_id", "") or "",
                venue_summary_stats=_auth_dict.get("venue_summary_stats"),
                is_core=_auth_dict.get("is_core"),
                is_in_doaj=_auth_dict.get("is_in_doaj"),
                apc_prices=_auth_dict.get("apc_prices"),
                publication_year=_auth_dict.get("publication_year"),
                ror_id=_auth_dict.get("ror_id", "") or "",
                institution_type=_auth_dict.get("institution_type", "") or "",
                country_code=_auth_dict.get("country_code", "") or "",
            )
        # I-ready-017 #1134: resolve the article DOI for the journal_only
        # citeability predicate (ADDITIVE — sourced from the candidate's OA
        # hints; "" when unknown). Cheap, no network.
        _jo_doi, _jo_pmid = _candidate_oa_hints(getattr(cand, "metadata", None))
        signals = ClassificationSignals(
            url=cand.url,
            title=classifier_title,
            publisher="",
            fetched_content_length=len(content),
            openalex_publication_type=oa.get("openalex_pub_type", "") or "",
            openalex_source_type=oa.get("openalex_source_type", "") or "",
            openalex_is_peer_reviewed=bool(oa.get("is_peer_reviewed", False)),
            doi=str(_jo_doi or ""),
            source_type_hint="",
            # BUG-M-17 (Codex pass 2): body-inspection secondary signal.
            body_article_type=body_article_type,
            authority=authority_payload,
            # Diff-gate P1-B/P1-C: wire the structural junk inputs so Signal C
            # (junk_detection) can actually fire on the ON path. INERT when OFF
            # (the legacy rule body never reads these).
            #   * fetched_body = the stripped visible page text (survives
            #     _strip_html; carries press-release / login-wall body cues).
            #   * structured_jsonld = the RAW ld+json <script> block contents
            #     captured by _fetch_content BEFORE _strip_html deleted the
            #     <script> blocks (P1-C). Without this the NewsArticle @type
            #     marker never reaches the classifier on the live path — it is
            #     destroyed by stripping. Honestly empty when the fetch backend
            #     already returned cleaned text (Jina/Crawl4AI) with no JSON-LD.
            #   * claim_vendor_token = the lowercased research question, used by
            #     the self-interest check (exact host-org-token == vendor-token
            #     equality, so a phrase can never false-fire). Extracting single
            #     candidate vendor tokens from the question is a Gate-A residual.
            fetched_body=content or "",
            structured_jsonld=raw_jsonld or "",
            claim_vendor_token=(research_question or "").strip().lower(),
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

        # I-ready-017 #1134: record the per-source journal-article signals into
        # the journal_only sidecar (ON-path only; keyed by canonical URL). The
        # citeability predicate reads these. OFF → never populated (no-op).
        if _journal_only_on:
            # Codex diff-gate P2: resolve the DOI from candidate metadata, then
            # the OpenAlex work DOI, then a DOI embedded in the URL — so an anchor
            # discovered via a Serper/URL-only path is still credited.
            _jo_doi_resolved = str(_jo_doi or "") or str(oa.get("doi", "") or "")
            if not _jo_doi_resolved:
                _jo_doi_m = re.search(r"10\.\d{4,9}/[^\s?#\"'<>]+", cand.url or "")
                if _jo_doi_m:
                    _jo_doi_resolved = _jo_doi_m.group(0)
            _journal_sidecar[_jo_canon(cand.url)] = _jo_meta_entry(
                openalex_pub_type=oa.get("openalex_pub_type", "") or "",
                openalex_source_type=oa.get("openalex_source_type", "") or "",
                is_peer_reviewed=bool(oa.get("is_peer_reviewed", False)),
                is_retracted=bool(oa.get("is_retracted", False)),
                doi=_jo_doi_resolved,
                venue=oa.get("openalex_venue", "") or "",
            )

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
                _trace_drop(cand.url, "content_starved")
            else:
                direct_quote = _build_provenance_quote(
                    content, head_chars=1500, window_chars=500,
                )
                _row = {
                    "evidence_id": f"ev_{i:03d}",
                    "source_url": cand.url,
                    "statement": cand.title[:300],
                    "direct_quote": direct_quote,
                    "tier": tier_result.tier.value,
                    "source": cand.source,
                    "full_content_length": len(content),
                    # #956 (S2): the sub-query that surfaced this candidate, so
                    # the evidence selector can reserve per-sub-topic diversity.
                    # Additive only; absent/empty for seed-lane or legacy rows.
                    "query_origin": getattr(cand, "query_origin", "") or "",
                }
                # I-meta-005 Phase 3 (#987): per-row AUTHORITY sidecar. ON-mode
                # ONLY (research_frame present), and INDEPENDENT of the legacy
                # `PG_USE_AUTHORITY_MODEL` tier switch — the plan-sufficiency gate
                # reads the NUMERIC `authority_score`, so planner mode computes it
                # DIRECTLY via the Phase-0a pure function over the SAME `signals`
                # already built for tier classification (no network, spend-free).
                # Honest LOW score/confidence when signals are thin (never a
                # silent 0.0). OFF-mode the keys are ABSENT -> rows byte-identical
                # (the legacy domain-keyed gate never reads them).
                if research_frame is not None:
                    _auth = score_source_authority(signals)
                    _row["authority_score"] = float(_auth.authority_score)
                    _row["authority_confidence"] = _auth.authority_confidence.value
                evidence_rows.append(_row)
                _trace_kept(cand.url, cand.source)

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
        corpus_truncated=_corpus_truncated,
        candidates_total=_candidates_total,
        candidates_processed=_candidates_processed,
        journal_metadata_sidecar=(_journal_sidecar if _journal_only_on else None),
    )
