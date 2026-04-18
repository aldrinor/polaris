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
import os
import re
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
        url = oa_pdf or p.get("url", "") or ""
        if not url:
            continue
        abstract = p.get("abstract") or ""
        ext_ids = p.get("externalIds") or {}
        doi = ext_ids.get("DOI", "")
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


def _openalex_enrich(url: str, title: str) -> dict[str, Any]:
    """Query OpenAlex for pub_type / source_type / is_peer_reviewed."""
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            # Try title search first
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
        }
    except Exception as exc:
        logger.debug("[live_retriever] OpenAlex enrich failed for %r: %s", url, exc)
        return {}


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


def _fetch_content(url: str, max_chars: int) -> tuple[str, bool]:
    """Fetch URL content. Returns (content, success)."""
    try:
        with httpx.Client(
            timeout=DEFAULT_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (POLARIS-honest-rebuild/1.0) "
                    "research-assistant"
                ),
            },
        ) as c:
            r = c.get(url)
        if r.status_code != 200:
            return "", False
        ctype = (r.headers.get("content-type", "") or "").lower()
        raw = r.text if "text" in ctype or "html" in ctype or "json" in ctype else ""
        if not raw and r.content:
            raw = r.content.decode("utf-8", errors="ignore")
        content = _strip_html(raw)[:max_chars]
        return content, bool(content)
    except Exception as exc:
        logger.debug("[live_retriever] fetch %r failed: %s", url, exc)
        return "", False


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
            ))

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

    # ── Step 4: cap, fetch, enrich, classify ────────────────────────
    candidates = candidates[:fetch_cap]

    classified_sources: list[CorpusSource] = []
    evidence_rows: list[dict[str, Any]] = []
    fetched = 0
    failed_fetch = 0

    for i, cand in enumerate(candidates):
        # Rate-limit gently (Serper doesn't but S2 prefers <= 1rps)
        if i > 0 and i % 5 == 0:
            time.sleep(0.2)

        # Fetch content (for tier classification + evidence)
        content, ok = _fetch_content(cand.url, DEFAULT_CONTENT_MAX_CHARS)
        api_calls["fetch"] += 1
        if not ok:
            failed_fetch += 1
        else:
            fetched += 1

        # Optional OpenAlex enrichment
        oa = {}
        if enable_openalex_enrich:
            oa = _openalex_enrich(cand.url, cand.title)
            if oa:
                api_calls["openalex"] += 1

        # Classify via tier_classifier
        domain_ = _domain_of(cand.url)
        signals = ClassificationSignals(
            url=cand.url,
            title=cand.title,
            publisher="",
            fetched_content_length=len(content),
            openalex_publication_type=oa.get("openalex_pub_type", "") or "",
            openalex_source_type=oa.get("openalex_source_type", "") or "",
            openalex_is_peer_reviewed=bool(oa.get("is_peer_reviewed", False)),
            source_type_hint="",
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
