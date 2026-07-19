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
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

import httpx

from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    SearchCandidate,
)
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.domain_backends")

PG_DOMAIN_MAX_HITS = int(resolve("PG_DOMAIN_MAX_HITS"))
HTTP_TIMEOUT = float(resolve("PG_DOMAIN_HTTP_TIMEOUT"))


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-001 W3 (#1310): bounded-parallel backend fan-out (gated by
# PG_SEARCH_FUSION_WRRF — same single kill-switch as the WRRF fusion it feeds).
# ─────────────────────────────────────────────────────────────────────────────
# The serial `_run` loop in each dispatcher mutates shared state (candidates /
# used / per) via `nonlocal`, so it is NOT thread-safe. Rather than make that
# thread-safe, the ON path uses a SEPARATE bounded fan-out where each backend
# returns ITS OWN list (no shared write); the dispatcher then reassembles the
# results in FIXED backend order (deterministic — NOT completion order, so the
# downstream WRRF tie-break stays reproducible per wiring_standard point 15) and
# applies the SAME intra-dispatcher URL-dedup. OFF (default) the serial `_run`
# loop runs byte-identically.


def _backend_fanout_enabled() -> bool:
    """True iff the W3 WRRF flag is ON (the parallel backend fan-out shares the
    SAME single kill-switch as the fusion it feeds — wiring_standard point 13).
    Default/unset => OFF => the serial `_run` loop runs byte-identically."""
    return resolve("PG_SEARCH_FUSION_WRRF").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _backend_workers() -> int:
    """Bounded backend fan-out cap (LAW VI). Default 6 per the execution graph
    (sized to avoid upstream-API 429s). Clamped >= 1."""
    try:
        return max(1, int(resolve("PG_RETRIEVAL_BACKEND_WORKERS")))
    except ValueError:
        return 6


def _run_backends_parallel(
    specs: list[tuple[str, Any]],
    queries: list[str],
    max_hits_per_backend: int,
    *,
    early_break: bool,
    log_prefix: str,
) -> tuple[
    list[SearchCandidate], list[str], dict[str, int],
    dict[str, list[SearchCandidate]],
]:
    """Run each (name, fn) backend in a bounded ThreadPoolExecutor.

    Each worker runs ALL queries for ITS backend and returns that backend's own
    hit list (intra-backend URL-dedup only). NO worker writes shared state, so
    there is no lock. Results are reassembled in the SAME order as ``specs``
    (declared backend order) so the output is deterministic regardless of which
    worker finished first. Cross-backend URL-dedup is applied here in declared
    order (mirrors the serial loop's first-seen-wins) so the merged candidate
    set is identical-by-set to the serial path; only the WRRF fuser downstream
    re-orders on rank. Each backend remains fail-open (an exception => 0 hits).

    Returns a 4-tuple ``(candidates, used, per, per_engine_lists)``:
      * ``candidates`` — the flat CROSS-DEDUPED list (legacy consumers + notes;
        a shared URL is credited once to the first declared backend).
      * ``used`` / ``per`` — backends-used + cross-deduped per-backend counts.
      * ``per_engine_lists`` (I-wire-001 W3 #1310 P1-3) — each backend's OWN
        intra-backend-deduped RANKED list, keyed by the declared backend NAME,
        BEFORE cross-dedup. A URL returned by TWO backends survives in BOTH
        lists with its DISTINCT per-engine rank, so the downstream ``wrrf_fuse``
        fuses on real per-engine ranks (the prior code cross-deduped first,
        collapsing duplicate ranks before they could reach the fuser). §-1.3:
        this is rank-preservation for the WEIGHT fusion, never a drop.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _one(name_fn: tuple[str, Any]) -> tuple[str, list[SearchCandidate]]:
        name, fn = name_fn
        try:
            got: list[SearchCandidate] = []
            for q in queries:
                got.extend(fn(q, limit=max_hits_per_backend))
                if early_break and len(got) >= max_hits_per_backend * 2:
                    break
            # Intra-backend dedup (preserve this backend's returned rank order).
            seen: set[str] = set()
            uniq: list[SearchCandidate] = []
            for c in got:
                if c.url and c.url not in seen:
                    seen.add(c.url)
                    uniq.append(c)
            return name, uniq
        except Exception as exc:
            logger.warning("[%s] %s failed (fail-open): %s", log_prefix, name, exc)
            return name, []

    workers = min(_backend_workers(), max(1, len(specs)))
    results_by_name: dict[str, list[SearchCandidate]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, uniq in pool.map(_one, specs):
            results_by_name[name] = uniq

    # Per-engine ranked lists in DECLARED backend order (P1-3): the
    # intra-backend-deduped list per backend, NOT cross-deduped — so a URL
    # returned by two backends keeps its rank in BOTH and reaches wrrf_fuse.
    per_engine_lists: dict[str, list[SearchCandidate]] = {}
    # Reassemble the flat CROSS-DEDUPED list in DECLARED order — deterministic.
    candidates: list[SearchCandidate] = []
    used: list[str] = []
    per: dict[str, int] = {}
    cross_seen: set[str] = set()
    for name, _fn in specs:
        uniq = results_by_name.get(name, [])
        per_engine_lists[name] = uniq          # P1-3: pre-cross-dedup ranks
        new = [c for c in uniq if c.url and c.url not in cross_seen]
        for c in new:
            cross_seen.add(c.url)
        candidates.extend(new)
        used.append(name)
        per[name] = len(new)
    return candidates, used, per, per_engine_lists


# ─────────────────────────────────────────────────────────────────────────────
# Shared httpx helper
# ─────────────────────────────────────────────────────────────────────────────


class OpenAlexHTTPError(RuntimeError):
    """OpenAlex ``/works`` request failed at the HTTP layer.

    U25 (I-deepfix-001): the 2026-02-13 OpenAlex policy makes anonymous ``search=``
    requests credit-capped (~$0.10/day); under load they return HTTP 503 with an
    "Anonymous search is temporarily rate-limited ..." body. The old fail-open
    swallowed that 503 as an empty result, so a rate-limited backend that returned
    ZERO candidates was still recorded as ``status='ok'`` and inflated discovery
    ``success_rate`` to 1.0 — a silent downgrade (LAW II).

    ``_http_get_json(strict=True)`` raises this on any non-200 / undecodable body /
    transport fault so ``openalex_search`` can FAIL LOUD to its caller, which then
    records the miss honestly (``status='fail'``) instead of masking it.
    """

    def __init__(
        self, message: str, *, status_code: int | None = None, body: str = ""
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _http_get_json(
    url: str, params: dict | None = None, *, strict: bool = False
) -> dict | None:
    """Shared JSON GET.

    ``strict=False`` (default) is byte-identical to the legacy fail-open helper:
    a non-200, an undecodable body, or a transport fault all return ``None``.

    ``strict=True`` FAILS LOUD (U25): a non-200 raises :class:`OpenAlexHTTPError`
    carrying the status code + a body snippet, and an undecodable body / transport
    fault re-raises as :class:`OpenAlexHTTPError`. This prevents a rate-limited
    backend (HTTP 503) from ever being masked as a genuine 0-result.
    """
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "POLARIS-honest-rebuild/1.0"},
        ) as c:
            r = c.get(url, params=params)
        if r.status_code != 200:
            if strict:
                raise OpenAlexHTTPError(
                    f"HTTP {r.status_code} from {url}",
                    status_code=r.status_code,
                    body=(r.text or "")[:500],
                )
            return None
        try:
            return r.json()
        except Exception:
            if strict:
                raise OpenAlexHTTPError(
                    f"undecodable JSON body from {url}",
                    status_code=r.status_code,
                )
            return None
    except OpenAlexHTTPError:
        # strict-mode fail-loud signal — never re-mask it as None.
        raise
    except Exception as exc:
        if strict:
            raise OpenAlexHTTPError(f"transport error for {url}: {exc}") from exc
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
# WORKFORCE / labour: Serper with site: filters for statistical / data agencies
# ─────────────────────────────────────────────────────────────────────────────
# The workforce/labour domain's authoritative PRIMARY evidence is national +
# international statistical / data agencies (BLS, OECD, ILO, StatCan, Eurostat,
# World Bank, IMF, US Census, Federal Reserve). config/scope_templates/workforce.yaml
# names them explicitly and requires T3 at 35-65%. But the workforce domain had NO
# domain backend (run_domain_backends selected specs == [] for it), so the generic
# Serper+S2 baseline under-reached the agencies — drb_72 fired a journal-publisher-only
# amplified set and got T3=4 (~4%) -> abort_corpus_approval_denied. This backend biases
# the SAME Serper budget toward those hosts via a `(site:bls.gov OR site:oecd.org OR ...)`
# OR-clause so the corpus REACHES the agencies. §-1.3 weight-not-filter: it ADDS
# agency-authoritative sources, never drops/caps/thins/filters, and hard-codes NO target
# count. It reuses the shared, jurisdiction-agnostic `site_scoped_serper` seam (no new HTTP
# literal). Default-OFF via the kill-switch: the workforce branch selects no backend unless
# PG_WORKFORCE_T3_TARGETING is truthy, so the workforce domain stays byte-identical
# (specs == []) when the switch is off.
_STATISTICAL_AGENCY_HOSTS = (
    "bls.gov",              # US Bureau of Labor Statistics
    "oecd.org",             # OECD Employment / Skills / Future-of-Work outlooks
    "ilo.org",              # International Labour Organization (+ ILOSTAT)
    "statcan.gc.ca",        # Statistics Canada
    "ec.europa.eu",         # Eurostat (ec.europa.eu/eurostat)
    "worldbank.org",        # World Bank Open Data
    "imf.org",              # International Monetary Fund
    "census.gov",           # US Census Bureau
    "federalreserve.gov",   # US Federal Reserve Board
)


def _workforce_t3_targeting_enabled() -> bool:
    """LAW VI kill-switch for the workforce statistical-agency retrieval backend
    (PG_WORKFORCE_T3_TARGETING). Default-OFF => the workforce domain selects no
    backend (specs == []), byte-identical to legacy."""
    return resolve("PG_WORKFORCE_T3_TARGETING").strip().lower() in (
        "1", "true", "yes", "on",
    )


def statistical_agency_serper(
    query: str, limit: int = PG_DOMAIN_MAX_HITS,
) -> list[SearchCandidate]:
    """Issue a Serper query scoped to national + international statistical / data
    agencies via a `(site:bls.gov OR site:oecd.org OR ...)` OR-clause.

    Thin wrapper over the shared `site_scoped_serper` seam (fail-open, path-B
    telemetry, no new HTTP literal). The workforce/labour domain's authoritative
    primary quantitative evidence lives on statistical-agency hosts; this ADDS those
    hits to the generic Serper+S2 corpus (§-1.3 weight-not-filter — never a drop)."""
    return site_scoped_serper(
        query,
        scopes=list(_STATISTICAL_AGENCY_HOSTS),
        source="serper_statistical_agency",
        limit=limit,
    )


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
# BB-003 (#1171): the OpenAlex API per_page hard maximum (docs.openalex.org paging).
_OPENALEX_PER_PAGE_MAX = 200


def _openalex_auth_params() -> dict[str, str]:
    """U25 (I-deepfix-001): config-driven OpenAlex auth/politeness query params.

    Per developers.openalex.org/api-reference/authentication (2026-02-13 policy):
    an API key is passed as the ``api_key`` QUERY param (NOT a header) and raises
    the anonymous ~$0.10/day search budget ~10x; ``mailto`` joins the polite pool.
    BOTH are read from the environment (LAW VI — no hard-coded credentials) and
    OMITTED entirely when unset, so an unconfigured run sends the EXACT legacy
    keyless params (byte-identical OFF). The key/contact are provisioned into the
    process env (``.env`` / ``PG_OPENALEX_API_KEY`` / ``PG_OPENALEX_MAILTO``);
    they are read at call time, never baked in.
    """
    params: dict[str, str] = {}
    api_key = os.getenv("PG_OPENALEX_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key
    mailto = resolve("PG_OPENALEX_MAILTO").strip()
    if mailto:
        params["mailto"] = mailto
    return params


def _openalex_per_page(limit: int) -> int:
    """BB-003 (#1171): per-page size for the OpenAlex /works search.

    Capped at the OpenAlex API maximum (200). DEFAULT 25 (PG_OPENALEX_PER_PAGE
    unset) = byte-identical to the legacy ``max(1, min(limit, 25))``. The Gate-B
    slate sets PG_OPENALEX_PER_PAGE=200 so one page covers up to 200 works.
    A bad value FAILS LOUD (LAW II) rather than silently throttling to a default.
    """
    raw = resolve("PG_OPENALEX_PER_PAGE").strip()
    try:
        cap = int(raw)
    except ValueError:
        raise ValueError(f"PG_OPENALEX_PER_PAGE={raw!r} is not an int")
    cap = max(1, min(cap, _OPENALEX_PER_PAGE_MAX))
    return max(1, min(limit, cap))


def _openalex_max_pages() -> int:
    """BB-003 (#1171): cursor-page count cap. DEFAULT 1 (PG_OPENALEX_MAX_PAGES
    unset) = single page = byte-identical OFF. The slate raises it to cover the
    requested ``limit``. A bad value FAILS LOUD."""
    raw = resolve("PG_OPENALEX_MAX_PAGES").strip()
    try:
        pages = int(raw)
    except ValueError:
        raise ValueError(f"PG_OPENALEX_MAX_PAGES={raw!r} is not an int")
    return max(1, pages)


def _openalex_date_filter(
    from_date: str | None, to_date: str | None
) -> str | None:
    """I-deepfix-001 Wave-3 (#1344): build the OpenAlex ``filter`` value for a publication-date window.

    Returns a comma-joined ``from_publication_date:YYYY-MM-DD,to_publication_date:YYYY-MM-DD`` string
    for whichever bounds are supplied (per developers.openalex.org filter reference), or ``None`` when
    BOTH are absent — so an unscoped call adds no ``filter`` param and is byte-identical to the legacy
    request. Pure string construction; no network. Dates are expected already-normalized to a full
    ISO ``YYYY-MM-DD`` by the caller (``UserConstraints`` bounds)."""
    parts: list[str] = []
    fd = (from_date or "").strip()
    td = (to_date or "").strip()
    if fd:
        parts.append(f"from_publication_date:{fd}")
    if td:
        parts.append(f"to_publication_date:{td}")
    return ",".join(parts) if parts else None


def openalex_search(
    query: str,
    limit: int = PG_DOMAIN_MAX_HITS,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[SearchCandidate]:
    """Keyword-SEARCH OpenAlex /works for primary-literature discovery.

    Emits a resolvable primary-literature URL per work in DOI -> OpenAlex-id
    priority; a work with neither is SKIPPED. Candidates flow through the SAME
    fetch / tier / strict_verify chokepoint as Serper/S2. Fail-open.

    I-deepfix-001 Wave-3 (#1344): the optional ``from_date`` / ``to_date`` (full ISO
    ``YYYY-MM-DD``) add an OpenAlex ``filter=from_publication_date:..,to_publication_date:..``
    so a caller with a stated publication window can issue an EXTRA date-scoped lane
    (``PG_OPENALEX_DATE_FILTER``) that surfaces in-window primaries a plain keyword
    search buries. BOTH unset (the default) => NO ``filter`` param => byte-identical to
    the legacy request. Strictly ADDITIVE at the caller (the un-scoped base call still
    runs); this only date-scopes the extra lane.

    BB-003 (#1171): per_page is raised to min(limit, PG_OPENALEX_PER_PAGE<=200)
    and the search CURSOR-PAGES (cursor=* -> meta.next_cursor) up to ``limit`` or
    PG_OPENALEX_MAX_PAGES — the legacy single page of 25 was the #3 breadth
    chokepoint (env limit=100 reached the adapter but min(limit,25) capped it at
    25/query). DEFAULT (per_page 25, max_pages 1) = byte-identical single page,
    no cursor key in the request. Discovery-breadth only; faithfulness-neutral.

    U25 (I-deepfix-001): merges the config-driven ``_openalex_auth_params`` (an
    ``api_key`` / ``mailto`` when provisioned — empty = keyless byte-identical) so
    the 2026-02-13 anonymous-search rate-limit is lifted, and uses the STRICT
    fetch so a non-200 (the 503 rate-limit) raises :class:`OpenAlexHTTPError` and
    is RE-RAISED to the caller instead of being swallowed as a 0-result. A genuine
    200-empty (no matching works) still returns ``[]`` — the caller distinguishes
    that honest zero from the rate-limited failure.
    """
    auth_params = _openalex_auth_params()
    # I-deepfix-001 Wave-3 (#1344): the publication-date window filter (None when
    # no bound supplied => byte-identical: no `filter` param is ever attached).
    date_filter = _openalex_date_filter(from_date, to_date)
    try:
        per_page = _openalex_per_page(limit)
        max_pages = _openalex_max_pages()
        out: list[SearchCandidate] = []
        seen_ids: set[str] = set()
        cursor = "*"
        for _page in range(max_pages):
            params: dict[str, Any] = {"search": query, "per_page": per_page}
            # BYTE-IDENTICAL OFF: only add the cursor param when paging is enabled
            # (max_pages > 1). A single-page run sends the exact legacy params.
            if max_pages > 1:
                params["cursor"] = cursor
            # I-deepfix-001 Wave-3: attach the date-window filter ONLY when supplied.
            if date_filter:
                params["filter"] = date_filter
            # U25: merge auth/politeness params LAST (never override search/per_page/
            # cursor); empty dict when unset => exact legacy keyless request.
            params.update(auth_params)
            # U25: STRICT — a non-200 (e.g. the anonymous-search 503) raises
            # OpenAlexHTTPError so a rate-limited backend can never be masked as [].
            data = _http_get_json(_OPENALEX_WORKS_SEARCH, params=params, strict=True)
            if not data:
                break
            results = data.get("results") or []
            if not results:
                break
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
                # Dedup across pages by the OpenAlex work id (or the url when absent).
                _dedup_key = oa_id or url
                if _dedup_key in seen_ids:
                    continue
                seen_ids.add(_dedup_key)
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
                    return out
            # Advance the cursor; stop when OpenAlex returns no next cursor.
            cursor = str((data.get("meta") or {}).get("next_cursor") or "").strip()
            if max_pages == 1 or not cursor:
                break
        return out
    except OpenAlexHTTPError:
        # U25: FAIL LOUD on an HTTP error (e.g. the 503 rate-limit) — do NOT
        # swallow it as []. Every caller wraps this in a fail-open (log + 0 hits),
        # but the failure is now VISIBLE so discovery success_rate reflects the
        # miss instead of masking a rate-limited backend as status='ok'.
        raise
    except Exception as exc:
        logger.warning("[domain_backends] openalex_search failed (fail-open): %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DomainBackendResult:
    """Merged output of running a domain's search backends.

    Carries the deduped ``candidates`` plus which ``backends_used`` produced
    them and ``per_backend_counts``. ``per_engine_lists`` holds the intra-backend
    ranked lists (empty on the serial/legacy path) so a caller can feed real
    per-engine ranks to fusion.
    """

    domain: str
    candidates: list[SearchCandidate]
    backends_used: list[str]
    per_backend_counts: dict[str, int]
    # I-wire-001 W3 (#1310) P1-3: per-backend RANKED lists (intra-backend dedup,
    # NOT cross-deduped) keyed by backend name, so the caller can feed real
    # per-engine ranks to wrrf_fuse. Empty on the serial/legacy (OFF) path =>
    # byte-identical default; the caller falls back to the flat `candidates`.
    per_engine_lists: dict[str, list[SearchCandidate]] = field(default_factory=dict)


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
    # I-wire-001 W3 (#1310) P1-3: per-backend ranked lists for wrrf_fuse. On the
    # serial path it is populated from each backend's own pre-cross-dedup list so
    # the WRRF fusion sees real per-engine ranks even without the parallel fanout.
    per_engine_lists: dict[str, list[SearchCandidate]] = {}

    def _run(name: str, fn) -> None:
        nonlocal candidates, used, per
        try:
            got: list[SearchCandidate] = []
            for q in queries:
                got.extend(fn(q, limit=max_hits_per_backend))
                if len(got) >= max_hits_per_backend * 2:
                    break
            # Intra-backend dedup (preserve this backend's returned rank order) —
            # this is the per-engine RANKED list (P1-3), captured BEFORE the
            # cross-backend dedup below so duplicate ranks survive to wrrf_fuse.
            _bseen: set[str] = set()
            _buniq: list[SearchCandidate] = []
            for c in got:
                if c.url and c.url not in _bseen:
                    _bseen.add(c.url)
                    _buniq.append(c)
            per_engine_lists[name] = _buniq
            # Cross-backend dedup for the flat legacy `candidates` list.
            seen_urls = {c.url for c in candidates}
            new = [c for c in _buniq if c.url not in seen_urls]
            candidates.extend(new)
            used.append(name)
            per[name] = len(new)
        except Exception as exc:
            logger.warning("[domain_backends] %s failed: %s", name, exc)
            per[name] = 0

    # Backend selection (same set for serial OFF + parallel ON paths).
    specs: list[tuple[str, Any]] = []
    if domain == "tech":
        specs = [("arxiv", arxiv_search), ("github", github_search_repos)]
    elif domain == "policy":
        specs = [("serper_policy", policy_targeted_serper)]
    elif domain == "due_diligence":
        specs = [("sec_edgar", sec_edgar_search)]
    elif domain == "clinical":
        # I-meta-002-q1d (#942-clinical): add Europe PMC primary-literature breadth on top of generic
        # Serper + S2. Keyless/free + fail-open; kill-switch PG_CLINICAL_EUROPE_PMC=0. (ClinicalTrials.gov
        # + openFDA/DailyMed are named fast-follows — CT.gov runtime 403, openFDA needs an allowlist change.)
        if resolve("PG_CLINICAL_EUROPE_PMC").strip() in ("1", "true", "True"):
            specs = [("europe_pmc", europe_pmc_search)]
    elif domain == "workforce":
        # T3 retrieval-targeting (PG_WORKFORCE_T3_TARGETING, default-OFF). The
        # workforce/labour domain had NO legacy backend, so the statistical agencies
        # it depends on (BLS / OECD / ILO / StatCan / Eurostat / World Bank / IMF) are
        # under-reached by the generic Serper+S2 baseline (drb_72 -> T3=4). When the
        # switch is ON, add the statistical-agency Serper backend so the SAME budget
        # reaches those authoritative hosts (§-1.3: ADD sources, never drop/cap/filter;
        # no hard-coded target count). OFF => specs stays [] => byte-identical to legacy
        # (no workforce backend fires).
        if _workforce_t3_targeting_enabled():
            specs = [("serper_statistical_agency", statistical_agency_serper)]

    # I-wire-001 W3 (#1310): ON => bounded-parallel fan-out (deterministic
    # declared-order reassembly). OFF (default) => the serial `_run` loop,
    # byte-identical. early_break=True keeps the legacy result-count cap.
    if _backend_fanout_enabled() and specs:
        candidates, used, per, per_engine_lists = _run_backends_parallel(
            specs, queries, max_hits_per_backend,
            early_break=True, log_prefix="domain_backends",
        )
    else:
        for _name, _fn in specs:
            _run(_name, _fn)

    return DomainBackendResult(
        domain=domain,
        candidates=candidates,
        backends_used=used,
        per_backend_counts=per,
        per_engine_lists=per_engine_lists,
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
    # I-wire-001 W3 (#1310) P1-3: per-backend RANKED lists (intra-backend dedup,
    # NOT cross-deduped) keyed by adapter name — real per-engine ranks for
    # wrrf_fuse. Empty on the serial/legacy (OFF) path => byte-identical.
    per_engine_lists: dict[str, list[SearchCandidate]] = field(default_factory=dict)


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
    # I-wire-001 W3 (#1310) P1-3: per-adapter ranked lists for wrrf_fuse (real
    # per-engine ranks, pre-cross-dedup).
    per_engine_lists: dict[str, list[SearchCandidate]] = {}

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
            # Intra-adapter dedup = this adapter's per-engine RANKED list (P1-3),
            # captured BEFORE the cross-adapter dedup so duplicate ranks survive.
            _aseen: set[str] = set()
            _auniq: list[SearchCandidate] = []
            for c in got:
                if c.url and c.url not in _aseen:
                    _aseen.add(c.url)
                    _auniq.append(c)
            per_engine_lists[name] = _auniq
            seen_urls = {c.url for c in candidates}
            new = [c for c in _auniq if c.url not in seen_urls]
            candidates.extend(new)
            used.append(name)
            per[name] = len(new)
        except Exception as exc:
            logger.warning("[need_type_backends] %s failed (fail-open): %s", name, exc)
            per[name] = 0

    # I-wire-001 W3 (#1310): ON => bounded-parallel fan-out over the adapters
    # (deterministic declared-order reassembly). OFF (default) => serial `_run`,
    # byte-identical. early_break=anchor_seed mirrors the serial cap (the gap
    # round anchor_seed=False fires ALL queries with no early break).
    if _backend_fanout_enabled() and adapters:
        specs = [(adapter.name, adapter.run) for adapter in adapters]
        candidates, used, per, per_engine_lists = _run_backends_parallel(
            specs, queries, max_hits_per_backend,
            early_break=anchor_seed, log_prefix="need_type_backends",
        )
    else:
        for adapter in adapters:
            _run(adapter.name, adapter.run)

    return NeedTypeBackendResult(
        needs=declared_needs,
        candidates=candidates,
        backends_used=used,
        per_backend_counts=per,
        per_engine_lists=per_engine_lists,
    )
