"""Real Serper + Semantic Scholar fetcher behind FetchHttpFn protocol.

Per `.codex/slices/slice_002/architecture_proposal.md` §"Implementation order"
PR 7 row.

Two backends, fanned out per query:
  1. Serper (https://google.serper.dev/search) — Google-results proxy.
     Requires SERPER_API_KEY env var. Returns up to 10 hits per query.
  2. Semantic Scholar (https://api.semanticscholar.org/graph/v1/paper/search)
     — academic-paper graph. SEMANTIC_SCHOLAR_API_KEY optional but recommended.

Results from both backends merge into a single list[FetchResult] handed back
to the orchestrator, which then runs them through clinical_source_registry
to drop anything not on the T1/T2/T3 allowlist.

Fail-loud per LAW II:
- SERPER_API_KEY missing → RuntimeError at construction. No silent skip.
- Both backends down → RuntimeError. No silent empty list.
- Semantic Scholar without key → still runs (1 RPS unauthenticated tier),
  but logs the missing key for ops visibility.

Rate limiting:
- Serper: 1 request per query (no fan-out within Serper); httpx default
  timeout 10s.
- Semantic Scholar: bounded to 1 RPS unauthenticated, 5 RPS with key —
  enforced via simple sleep() between calls in the same fetcher instance.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

from polaris_graph.retrieval2.clinical_retriever import FetchResult

_LOG = logging.getLogger(__name__)

SERPER_ENDPOINT = "https://google.serper.dev/search"
S2_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"

DEFAULT_TIMEOUT_S = 10.0


@dataclass
class RealFetcherConfig:
    """Construction-time config for the real fetcher."""

    serper_api_key: str
    semantic_scholar_api_key: str | None = None
    serper_results_per_query: int = 10
    s2_results_per_query: int = 10
    s2_rate_limit_seconds: float = 1.05  # >1s for safety on the 1 RPS tier
    timeout_s: float = DEFAULT_TIMEOUT_S


def load_config_from_env() -> RealFetcherConfig:
    """Build a RealFetcherConfig from environment variables.

    Raises RuntimeError if SERPER_API_KEY is unset (fail loud per LAW II).
    SEMANTIC_SCHOLAR_API_KEY is optional; absence is logged at WARNING.
    """
    serper = os.environ.get("SERPER_API_KEY", "").strip()
    if not serper:
        raise RuntimeError(
            "SERPER_API_KEY is required for slice 002 real_fetcher. Set it "
            "in .env or environment before mounting the retrieval route. "
            "Per CLAUDE.md LAW II, this MUST fail loudly rather than "
            "silently skipping the Serper backend."
        )
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip() or None
    if not s2_key:
        _LOG.warning(
            "SEMANTIC_SCHOLAR_API_KEY unset; falling back to "
            "unauthenticated 1 RPS tier"
        )
    return RealFetcherConfig(
        serper_api_key=serper,
        semantic_scholar_api_key=s2_key,
    )


# ---------------------------------------------------------------------------
# Per-backend fetch primitives
# ---------------------------------------------------------------------------

def _fetch_serper(
    query: str,
    config: RealFetcherConfig,
    client: httpx.Client,
) -> list[FetchResult]:
    """Single Serper search call. Raises on persistent network failure."""
    payload = {"q": query, "num": config.serper_results_per_query}
    headers = {
        "X-API-KEY": config.serper_api_key,
        "Content-Type": "application/json",
    }
    response = client.post(
        SERPER_ENDPOINT,
        json=payload,
        headers=headers,
        timeout=config.timeout_s,
    )
    response.raise_for_status()
    data = response.json()
    organic = data.get("organic", [])
    results: list[FetchResult] = []
    for hit in organic:
        url = hit.get("link", "")
        if not url:
            continue
        results.append(
            FetchResult(
                url=url,
                title=hit.get("title", "") or "untitled",
                snippet=hit.get("snippet", "") or "",
            )
        )
    return results


def _fetch_semantic_scholar(
    query: str,
    config: RealFetcherConfig,
    client: httpx.Client,
) -> list[FetchResult]:
    """Single Semantic Scholar search call. Raises on persistent failure."""
    params = {
        "query": query,
        "limit": config.s2_results_per_query,
        "fields": "title,abstract,url,year,authors,externalIds",
    }
    headers = {}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key
    response = client.get(
        S2_ENDPOINT,
        params=params,
        headers=headers,
        timeout=config.timeout_s,
    )
    if response.status_code == 429:
        # Rate-limited; sleep + retry once. After that fail loud.
        time.sleep(config.s2_rate_limit_seconds * 2)
        response = client.get(
            S2_ENDPOINT,
            params=params,
            headers=headers,
            timeout=config.timeout_s,
        )
    response.raise_for_status()
    data = response.json()
    papers = data.get("data", []) or []
    results: list[FetchResult] = []
    for paper in papers:
        url = paper.get("url") or ""
        if not url:
            ext = paper.get("externalIds") or {}
            doi = ext.get("DOI")
            if doi:
                url = f"https://doi.org/{doi}"
        if not url:
            continue
        title = paper.get("title") or "untitled"
        abstract = paper.get("abstract") or ""
        snippet = abstract[:500] if abstract else ""
        results.append(
            FetchResult(
                url=url,
                title=title,
                snippet=snippet,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Combined fetcher (FetchHttpFn protocol implementation)
# ---------------------------------------------------------------------------

@dataclass
class RealFetcher:
    """Stateful FetchHttpFn impl that batches + rate-limits S2 calls."""

    config: RealFetcherConfig
    _last_s2_call_at: float = field(default=0.0, init=False, repr=False)

    def __call__(self, query: str) -> list[FetchResult]:
        results: list[FetchResult] = []
        with httpx.Client() as client:
            # Serper first (fast, paid; high-confidence allowlist hits).
            try:
                serper_hits = _fetch_serper(query, self.config, client)
                results.extend(serper_hits)
            except httpx.HTTPError as exc:
                _LOG.warning(
                    "Serper backend failed for query %r: %s. Continuing "
                    "with Semantic Scholar only.",
                    query,
                    exc,
                )

            # S2 with simple rate-limit gate.
            since = time.perf_counter() - self._last_s2_call_at
            if since < self.config.s2_rate_limit_seconds:
                time.sleep(self.config.s2_rate_limit_seconds - since)
            try:
                s2_hits = _fetch_semantic_scholar(query, self.config, client)
                results.extend(s2_hits)
            except httpx.HTTPError as exc:
                _LOG.warning(
                    "Semantic Scholar backend failed for query %r: %s. "
                    "Returning Serper-only results.",
                    query,
                    exc,
                )
            finally:
                self._last_s2_call_at = time.perf_counter()

        if not results:
            # Both backends returned nothing or failed. Per LAW II
            # ('Fail Loudly'), surface the failure rather than letting
            # the orchestrator silently produce an inadequate corpus.
            raise RuntimeError(
                f"both Serper and Semantic Scholar produced no results "
                f"or failed for query {query!r}; check API keys + network"
            )
        return results


def build_real_fetcher() -> RealFetcher:
    """Factory: read env, build a configured RealFetcher.

    Use this as the FastAPI Depends() injection point in production.
    """
    return RealFetcher(config=load_config_from_env())
