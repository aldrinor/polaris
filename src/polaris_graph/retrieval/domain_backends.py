"""
Domain-specific retrieval backends — HONEST-REBUILD R-6 Gap-2.

Each domain (clinical / policy / tech / due_diligence) has unique
authoritative sources that generic Serper+S2 misses:

  clinical:     PubMed / ClinicalTrials.gov / Cochrane — already well-
                covered by S2 academic search, no new backend needed.

  policy:       Federal Register, agency guidance pages. Implemented
                via targeted Serper queries with site: operators so the
                same Serper budget gets policy-authoritative hits.

  tech:         arXiv API (direct, not via S2) for preprints and
                conference papers. GitHub README fetching for
                open-source project documentation.

  due_diligence:  SEC EDGAR full-text search for 10-K / 10-Q / 8-K
                filings — primary documents of record for public
                companies. No API key needed.

DESIGN:
  - Each backend returns SearchCandidate objects (same shape as the
    generic retriever), so the caller merges them transparently.
  - Each backend has a hard cap on the number of hits it contributes
    (PG_DOMAIN_MAX_HITS env var, default 10).
  - Backends fail open: if arXiv / SEC / Federal Register API is down
    or throws, return empty list and log; don't break retrieval.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import httpx

from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    SearchCandidate,
)

logger = logging.getLogger("polaris_graph.domain_backends")

PG_DOMAIN_MAX_HITS = int(os.getenv("PG_DOMAIN_MAX_HITS", "10"))
HTTP_TIMEOUT = float(os.getenv("PG_DOMAIN_HTTP_TIMEOUT", "15"))


# ─────────────────────────────────────────────────────────────────────────────
# Shared httpx helper
# ─────────────────────────────────────────────────────────────────────────────


def _http_get_json(url: str, params: dict | None = None) -> dict | None:
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "POLARIS-honest-rebuild/1.0"},
        ) as c:
            r = c.get(url, params=params)
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None
    except Exception as exc:
        logger.debug("http_get_json %r failed: %s", url, exc)
        return None


def _http_get_text(url: str, params: dict | None = None) -> str | None:
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "POLARIS-honest-rebuild/1.0"},
        ) as c:
            r = c.get(url, params=params)
        if r.status_code != 200:
            return None
        return r.text
    except Exception as exc:
        logger.debug("http_get_text %r failed: %s", url, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TECH: arXiv
# ─────────────────────────────────────────────────────────────────────────────

_ARXIV_API = "http://export.arxiv.org/api/query"


def _parse_arxiv_feed(xml: str, limit: int) -> list[SearchCandidate]:
    if not xml:
        return []
    # Minimal Atom XML parsing without pulling a dependency. arXiv
    # returns predictable structure.
    candidates: list[SearchCandidate] = []
    # Entries are <entry>...</entry>
    entries = re.findall(r"<entry>(.*?)</entry>", xml, flags=re.DOTALL)
    for e in entries[:limit]:
        title_m = re.search(r"<title>(.*?)</title>", e, flags=re.DOTALL)
        summary_m = re.search(r"<summary>(.*?)</summary>", e, flags=re.DOTALL)
        id_m = re.search(r"<id>(.*?)</id>", e, flags=re.DOTALL)
        if not id_m:
            continue
        arxiv_url = id_m.group(1).strip()
        # Prefer the abs URL (html) over PDF
        if "/abs/" not in arxiv_url:
            arxiv_url = arxiv_url.replace("http://", "https://")
        title = (title_m.group(1).strip() if title_m else "")
        # Collapse whitespace
        title = re.sub(r"\s+", " ", title)
        summary = (summary_m.group(1).strip() if summary_m else "")
        summary = re.sub(r"\s+", " ", summary)[:400]
        candidates.append(SearchCandidate(
            url=arxiv_url, title=title, snippet=summary, source="arxiv",
        ))
    return candidates


def arxiv_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[SearchCandidate]:
    """Query arXiv via the Atom API. Fail-open."""
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max(1, min(limit, 30)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    xml = _http_get_text(_ARXIV_API, params=params)
    if not xml:
        return []
    try:
        return _parse_arxiv_feed(xml, limit)
    except Exception as exc:
        logger.warning("[domain_backends] arxiv parse failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# POLICY: Serper with site: filters for federal register + agencies
# ─────────────────────────────────────────────────────────────────────────────

_POLICY_SITE_FILTERS = (
    "site:federalregister.gov",
    "site:regulations.gov",
    "site:fda.gov",
    "site:cms.gov",
    "site:hhs.gov",
    "site:ftc.gov",
    "site:sec.gov",
    "site:treasury.gov",
    "site:ema.europa.eu",
    "site:nice.org.uk",
)


def policy_targeted_serper(
    query: str, limit: int = PG_DOMAIN_MAX_HITS,
) -> list[SearchCandidate]:
    """Issue a Serper query with a policy-site OR clause.

    The policy domain's authoritative sources are regulatory agency
    pages. Rather than spin up a new API, we use Serper with a
    `(site:federalregister.gov OR site:fda.gov OR ...)` bundle so the
    same API budget returns policy-biased results.
    """
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return []
    site_clause = " OR ".join(_POLICY_SITE_FILTERS)
    q = f"{query} ({site_clause})"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as c:
            r = c.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": q, "num": max(1, min(limit, 20))},
            )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception as exc:
        logger.debug("[domain_backends] policy serper failed: %s", exc)
        return []
    out: list[SearchCandidate] = []
    for item in (data.get("organic") or [])[:limit]:
        url = item.get("link", "") or ""
        if not url:
            continue
        out.append(SearchCandidate(
            url=url,
            title=item.get("title", "") or "",
            snippet=item.get("snippet", "") or "",
            source="serper_policy",
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DUE DILIGENCE: SEC EDGAR full-text search
# ─────────────────────────────────────────────────────────────────────────────

_SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


def sec_edgar_search(
    query: str, limit: int = PG_DOMAIN_MAX_HITS,
) -> list[SearchCandidate]:
    """Full-text search SEC EDGAR for 10-K / 10-Q / 8-K / DEF 14A.

    No API key required. Fail-open.
    """
    params = {
        "q": query,
        "dateRange": "custom",
        "startdt": "2019-01-01",
        "forms": "10-K,10-Q,8-K,DEF 14A,S-1",
    }
    data = _http_get_json(_SEC_SEARCH_URL, params=params)
    if not data:
        return []
    hits = data.get("hits", {}).get("hits", []) or []
    out: list[SearchCandidate] = []
    for h in hits[:limit]:
        src = h.get("_source", {}) or {}
        adsh = src.get("adsh", "")
        cik = (h.get("_id", "").split(":")[0]
               if ":" in h.get("_id", "")
               else src.get("ciks", [""])[0])
        form = src.get("form", "")
        display_name = src.get("display_names", [""])[0] or ""
        filed = src.get("file_date", "")
        if not adsh:
            continue
        # Construct a filing URL
        cik_no_leading_zero = str(int(cik)) if cik else ""
        adsh_no_dash = adsh.replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_no_leading_zero}/{adsh_no_dash}/{adsh}-index.htm"
        )
        out.append(SearchCandidate(
            url=url,
            title=f"{display_name} — {form} filed {filed}",
            snippet=(src.get("display_names", [""])[0] or "")[:200],
            source="sec_edgar",
            metadata={"form": form, "cik": cik, "adsh": adsh},
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# GitHub (technical docs) — optional, no auth
# ─────────────────────────────────────────────────────────────────────────────

_GITHUB_SEARCH = "https://api.github.com/search/repositories"


def github_search_repos(
    query: str, limit: int = PG_DOMAIN_MAX_HITS,
) -> list[SearchCandidate]:
    """Search GitHub repositories for a query term. Fail-open.

    Unauthenticated GitHub API has a 10 req/min limit; fine for our
    once-per-query usage.
    """
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": max(1, min(limit, 30)),
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as c:
            r = c.get(
                _GITHUB_SEARCH, params=params,
                headers={
                    "User-Agent": "POLARIS-honest-rebuild/1.0",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception as exc:
        logger.debug("[domain_backends] github search failed: %s", exc)
        return []
    out: list[SearchCandidate] = []
    for item in (data.get("items") or [])[:limit]:
        url = item.get("html_url", "") or ""
        if not url:
            continue
        stars = item.get("stargazers_count", 0)
        desc = item.get("description") or ""
        out.append(SearchCandidate(
            url=url,
            title=f"{item.get('full_name', '')} ({stars}★)",
            snippet=desc[:300],
            source="github",
            metadata={"stars": stars, "lang": item.get("language", "")},
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DomainBackendResult:
    domain: str
    candidates: list[SearchCandidate]
    backends_used: list[str]
    per_backend_counts: dict[str, int]


def run_domain_backends(
    *,
    domain: str,
    research_question: str,
    amplified_queries: list[str] | None = None,
    max_hits_per_backend: int = PG_DOMAIN_MAX_HITS,
) -> DomainBackendResult:
    """Run all applicable domain backends for the given domain.

    For each domain, returns a merged list of SearchCandidate that the
    caller can concatenate with the generic Serper+S2 retrieval.
    Fail-open: backends that raise return empty lists.
    """
    queries: list[str] = [research_question]
    if amplified_queries:
        queries.extend(amplified_queries[:3])   # cap amplified count

    candidates: list[SearchCandidate] = []
    used: list[str] = []
    per: dict[str, int] = {}

    def _run(name: str, fn) -> None:
        nonlocal candidates, used, per
        try:
            got: list[SearchCandidate] = []
            for q in queries:
                got.extend(fn(q, limit=max_hits_per_backend))
                if len(got) >= max_hits_per_backend * 2:
                    break
            # Dedup by URL
            seen_urls = {c.url for c in candidates}
            new = [c for c in got if c.url and c.url not in seen_urls]
            candidates.extend(new)
            used.append(name)
            per[name] = len(new)
        except Exception as exc:
            logger.warning("[domain_backends] %s failed: %s", name, exc)
            per[name] = 0

    if domain == "tech":
        _run("arxiv", arxiv_search)
        _run("github", github_search_repos)
    elif domain == "policy":
        _run("serper_policy", policy_targeted_serper)
    elif domain == "due_diligence":
        _run("sec_edgar", sec_edgar_search)
    # clinical: rely on generic Serper + S2 (PubMed-indexed academic is
    # well-covered by S2's bulk endpoint).

    return DomainBackendResult(
        domain=domain,
        candidates=candidates,
        backends_used=used,
        per_backend_counts=per,
    )
