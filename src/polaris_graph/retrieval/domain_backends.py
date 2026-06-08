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
    # I-safety-002b (#925) PR-2: record serper attempt for the Path-B gate (best-effort).
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_attempt("serper")
    except Exception:
        pass
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
    # I-meta-002-q1d (#945): per-call retrieval trace (best-effort, no-op when not started).
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_query("serper_policy", q, [c.url for c in out])
    except Exception:
        pass
    return out


def site_scoped_serper(
    query: str,
    *,
    scopes: list[str],
    source: str = "serper_scoped",
    limit: int = PG_DOMAIN_MAX_HITS,
) -> list[SearchCandidate]:
    """Field-agnostic, JURISDICTION-driven Serper scope query (I-meta-005
    Phase 2 #986). The generalized cousin of `policy_targeted_serper`: the
    `site:` scopes are PASSED IN (resolved from `jurisdiction_scopes.yaml` by
    the need-type router), NOT read from the US-only `_POLICY_SITE_FILTERS`
    literal. NO host literal lives in this function — knowledge is in the DATA.

    `scopes` is a list of bare canonical hosts (e.g. `["canada.ca", "gc.ca"]`);
    each becomes a `site:<host>` clause. Empty scopes -> [] (no scope query is
    fired; the caller falls back to core open_web + scholarly). Fail-open.
    """
    if not scopes:
        return []
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_attempt("serper")
    except Exception:
        pass
    site_clause = " OR ".join(f"site:{host}" for host in scopes)
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
        logger.debug("[domain_backends] scoped serper failed: %s", exc)
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
            source=source,
        ))
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_query(source, q, [c.url for c in out])
    except Exception:
        pass
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
        # I-fetch-001 (#1167): the EDGAR full-text `_id` is
        # `<accession>:<primary_doc>` — splitting it on ":" yields the
        # dash-bearing accession number, NOT the CIK, so `int(cik)` below
        # raised ValueError on EVERY hit (zero SEC candidates returned).
        # The CIK lives in the `ciks` array on `_source`; take it from
        # there and skip (fail-loud per hit, not per backend) any hit
        # whose CIK is missing or non-numeric.
        ciks = src.get("ciks") or []
        cik = (ciks[0] or "").strip() if ciks else ""
        form = src.get("form", "")
        display_name = src.get("display_names", [""])[0] or ""
        filed = src.get("file_date", "")
        if not adsh:
            continue
        if not cik.isdigit():
            logger.debug(
                "sec_edgar_search: skipping hit %r with non-numeric "
                "cik %r", h.get("_id", ""), cik,
            )
            continue
        # Construct a filing URL
        cik_no_leading_zero = str(int(cik))
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
# CLINICAL: Europe PMC (keyless, free) primary-literature backend (I-meta-002-q1d #942-clinical)
# ─────────────────────────────────────────────────────────────────────────────

_EUROPE_PMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def europe_pmc_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[SearchCandidate]:
    """Query Europe PMC (KEYLESS, FREE — no API key, no cost) for clinical primary literature.
    Fail-open: any error / empty body returns [] (the run degrades to generic Serper + S2).

    Emits ONLY resolvable primary-literature URLs in PMCID -> DOI -> PMID priority — PMC is the
    strongest keyless, fetchable full-text path (Codex brief-gate); a record carrying none of those
    ids is SKIPPED (a europepmc.org landing page does not fetch as primary content). Candidates flow
    through the SAME fetch / tier / strict_verify chokepoint as Serper/S2 (no tier laundering).
    """
    # Fail-open guard wraps the HTTP call AND the parse (Codex diff-gate iter-1 P1): a network/helper
    # exception must degrade to [] (generic Serper + S2), never break the clinical run.
    try:
        data = _http_get_json(
            _EUROPE_PMC_API,
            params={
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": max(1, min(limit, 25)),
            },
        )
        if not data:
            return []
        results = (data.get("resultList") or {}).get("result") or []
        out: list[SearchCandidate] = []
        for r in results:
            pmcid = str(r.get("pmcid") or "").strip()
            doi = str(r.get("doi") or "").strip()
            pmid = str(r.get("pmid") or "").strip()
            if pmcid:
                url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
            elif doi:
                url = f"https://doi.org/{doi}"
            elif pmid:
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            else:
                continue  # no resolvable primary-literature id — never emit a landing page
            title = str(r.get("title") or "").strip()
            snippet = re.sub(r"\s+", " ", str(r.get("abstractText") or "")).strip()[:300]
            out.append(SearchCandidate(
                url=url,
                title=title,
                snippet=snippet,
                source="europe_pmc",
                metadata={
                    "doi": doi or None,
                    "pmid": pmid or None,
                    "pmcid": pmcid or None,
                    "year": r.get("pubYear"),
                    "is_oa": r.get("isOpenAccess"),
                },
            ))
            if len(out) >= limit:
                break
        return out
    except Exception as exc:
        logger.warning("[domain_backends] europe_pmc failed (fail-open): %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY LITERATURE: OpenAlex /works keyword SEARCH (I-meta-005 Phase 2 #986)
# ─────────────────────────────────────────────────────────────────────────────
# DISTINCT from the OpenAlex ENRICHMENT path in live_retriever
# (`/works/doi:<doi>` per-URL lookup). This is the keyword DISCOVERY adapter:
# `/works?search=<query>` returns NEW candidate works the keyword set surfaces,
# re-keyed under the `primary_literature` need (NOT a domain). Keyless / free.
# Fail-open: any error / empty body returns [] (the run degrades to the core
# Serper + S2 + the other primary-lit adapters). The CORE baseline already runs
# S2 over the sub-queries, so this ADDS non-baseline scholarly-graph breadth.

_OPENALEX_WORKS_SEARCH = "https://api.openalex.org/works"


def openalex_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[SearchCandidate]:
    """Keyword-SEARCH OpenAlex /works for primary-literature discovery.

    Emits a resolvable primary-literature URL per work in DOI -> OpenAlex-id
    priority; a work with neither is SKIPPED. Candidates flow through the SAME
    fetch / tier / strict_verify chokepoint as Serper/S2. Fail-open.
    """
    try:
        data = _http_get_json(
            _OPENALEX_WORKS_SEARCH,
            params={
                "search": query,
                "per_page": max(1, min(limit, 25)),
            },
        )
        if not data:
            return []
        results = data.get("results") or []
        out: list[SearchCandidate] = []
        for work in results:
            doi = str(work.get("doi") or "").strip()
            oa_id = str(work.get("id") or "").strip()
            if doi:
                # OpenAlex DOIs are full URLs (https://doi.org/...).
                url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
            elif oa_id:
                url = oa_id
            else:
                continue  # no resolvable id — skip
            title = str(work.get("display_name") or "").strip()
            out.append(SearchCandidate(
                url=url,
                title=title,
                snippet="",
                source="openalex_search",
                metadata={
                    "doi": doi or None,
                    "openalex_id": oa_id or None,
                    "year": work.get("publication_year"),
                },
            ))
            if len(out) >= limit:
                break
        return out
    except Exception as exc:
        logger.warning("[domain_backends] openalex_search failed (fail-open): %s", exc)
        return []


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
    elif domain == "clinical":
        # I-meta-002-q1d (#942-clinical): add Europe PMC primary-literature breadth on top of generic
        # Serper + S2. Keyless/free + fail-open; kill-switch PG_CLINICAL_EUROPE_PMC=0. (ClinicalTrials.gov
        # + openFDA/DailyMed are named fast-follows — CT.gov runtime 403, openFDA needs an allowlist change.)
        if os.getenv("PG_CLINICAL_EUROPE_PMC", "1").strip() in ("1", "true", "True"):
            _run("europe_pmc", europe_pmc_search)

    return DomainBackendResult(
        domain=domain,
        candidates=candidates,
        backends_used=used,
        per_backend_counts=per,
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-005 Phase 2 (#986): NEED-TYPE on-path dispatcher (field-agnostic)
# ─────────────────────────────────────────────────────────────────────────────
# Replaces `run_domain_backends` on the ON-path. Routes off the planner frame's
# DECLARED evidence-needs + extracted jurisdiction via the need-type registry —
# NO `if domain ==` branch reached on-mode (EXIT P2-4). OFF-mode the legacy
# switch above runs byte-identically. The router import is LAZY (the router
# imports adapters FROM this module — avoids a circular import at module load).


@dataclass
class NeedTypeBackendResult:
    """On-path analogue of `DomainBackendResult` — carries NO domain field
    (field-agnostic). `needs` records the declared evidence-needs routed."""

    needs: list[str]
    candidates: list[SearchCandidate]
    backends_used: list[str]
    per_backend_counts: dict[str, int]


def run_need_type_backends(
    *,
    frame: Any,
    research_question: str,
    amplified_queries: list[str] | None = None,
    max_hits_per_backend: int = PG_DOMAIN_MAX_HITS,
    registry: Any = None,
    anchor_seed: bool = True,
) -> NeedTypeBackendResult:
    """Run the need-type-routed discovery adapters for the planner `frame`.

    The field-agnostic ON-path replacement for `run_domain_backends`. Resolves
    the adapter union via `need_type_router.route_needs_to_adapters(frame)`
    (NO domain literal), then runs each adapter with the SAME dedupe-by-URL +
    per-backend cap discipline as the legacy switch (brief §2.5).

    Validation note (brief §2.4 P2-note-1): a MALFORMED frame
    (`evidence_needs` not in the enum / jurisdiction bad SHAPE) raises
    `MalformedPlanError` from the router's up-front validation — that
    propagates (it is NOT swallowed here). The live seam validates the frame
    BEFORE any discovery; this function additionally surfaces a malformed frame
    loudly if reached. ADAPTER exceptions stay fail-open (each `_run` swallows).

    I-meta-005 Phase 4 (#988): `anchor_seed=False` (gap rounds) builds
    `queries = amplified_queries` ONLY (NO `research_question` prepend) AND lifts
    the 3-query amplified cap, so a gap round fires ALL gap sub-queries through
    the need-type adapters (parity with the core seam). Default True =
    OFF/on-single-pass byte-identical (anchor prepended, amplified capped at 3).
    """
    # Lazy imports (router imports adapters from THIS module).
    from src.polaris_graph.discovery.need_type_router import (
        route_needs_to_adapters,
    )
    from src.polaris_graph.planning.research_planner import (
        validate_evidence_needs,
    )

    # route_needs_to_adapters validates SHAPE + need-enum up-front and re-raises
    # MalformedPlanError (fail loud, NOT fail-open).
    adapters = route_needs_to_adapters(frame, registry=registry)
    # Record the normalized declared needs (after fallback) for telemetry.
    declared_needs = validate_evidence_needs(
        list(getattr(frame, "evidence_needs", []) or [])
    )

    if anchor_seed:
        queries: list[str] = [research_question]
        if amplified_queries:
            queries.extend(amplified_queries[:3])   # cap amplified count (parity)
    else:
        # I-meta-005 Phase 4 (#988) gap round: NO anchor prepend, NO 3-query cap.
        queries = list(amplified_queries or [])

    candidates: list[SearchCandidate] = []
    used: list[str] = []
    per: dict[str, int] = {}

    def _run(name: str, fn) -> None:
        nonlocal candidates, used, per
        try:
            got: list[SearchCandidate] = []
            for q in queries:
                got.extend(fn(q, limit=max_hits_per_backend))
                # I-meta-005 Phase 4 (#988): the result-count early-break is a
                # legacy parity cap for the anchor + 3-amplified case. On a gap
                # round (anchor_seed=False) every query is a DISTINCT under-covered
                # facet that must get its own retrieval, so do NOT break early or a
                # high-yield early facet would starve later specialized gap facets
                # (P4-10). The gap-query list is already budget-truncated upstream,
                # so firing all of them is bounded. anchor_seed=True (OFF / single
                # pass) keeps the exact legacy break -> byte-identical.
                if anchor_seed and len(got) >= max_hits_per_backend * 2:
                    break
            seen_urls = {c.url for c in candidates}
            new = [c for c in got if c.url and c.url not in seen_urls]
            candidates.extend(new)
            used.append(name)
            per[name] = len(new)
        except Exception as exc:
            logger.warning("[need_type_backends] %s failed (fail-open): %s", name, exc)
            per[name] = 0

    for adapter in adapters:
        _run(adapter.name, adapter.run)

    return NeedTypeBackendResult(
        needs=declared_needs,
        candidates=candidates,
        backends_used=used,
        per_backend_counts=per,
    )
