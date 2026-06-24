"""search_discovery bake-off — candidate search providers + recall@k scorer + ranked-results.

I-ret-002 (#1294), layer 1 of 7. Holds IterResearch/Tongyi queries FIXED; varies ONLY the
search backend at the ``_serper_search`` seam. Scores the RANKED URL list PRE-FETCH against the
gold SOURCE-SET fixture (``build_fixture.finding_recall``): per-required-finding gold-source
recall@k, identity match (DOI/PMID or canonical page identity), NOT exact URL.

Candidates (the brief): Serper (baseline), Exa, Semantic Scholar /paper/search, Firecrawl
search, SearXNG (self-host). no_key (registered-but-skipped, NEVER faked): Tavily, Parallel,
Brave.

Honest flags:
  - no_key candidates are registered and SKIPPED (recorded as skipped, no score), never faked.
  - SearXNG needs the self-host container up (needs_service); gated behind a runtime check.
  - A candidate DECLARED runnable that returns keyless/stub/empty FAILS LOUD in GATE-0 liveness
    (gate0.py) — never a believable-low score (the drb_72 guard).

Provider interface (the abstraction the brief names): ``SearchProvider.search(query) -> list``
of ranked ``{"url","title","snippet"}``. Each candidate is one adapter. ALL network/SDK clients
are constructed lazily inside ``search`` so this module imports with no network/keys, and the
smoke + GATE-0 can inject synthetic/stub providers (full offline testability).
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from scripts.dr_benchmark.gate0_lineage import (
    DEFAULT_TASKS_PATH,
    SLUG_TO_IDX,
    canonical_question_for_slug,
)
from scripts.dr_benchmark.retrieval_bakeoff.search_discovery.build_fixture import (
    finding_recall,
    gold_set_for_row,
    load_fixture,
)

# Held-identical per-query result budget k (the POLARIS default surface; overridable by env,
# never hard-coded as a magic literal — LAW VI).
DEFAULT_RANK_K = int(os.getenv("PG_BAKEOFF_SEARCH_RANK_K", "20"))


@runtime_checkable
class SearchProvider(Protocol):
    """A search backend under test. Its ONLY job: return a ranked URL list for a held query."""

    name: str
    runnable: str  # "yes" | "no_key" | "needs_service"

    def search(self, query: str) -> list[dict[str, str]]:
        """Return ranked results [{"url","title","snippet"}] for the FIXED query. No fetch."""
        ...


# ---------------------------------------------------------------------------
# Candidate adapters. Lazy client construction => importable + mockable offline.
# ---------------------------------------------------------------------------


@dataclass
class SerperProvider:
    """Baseline: the current POLARIS search backend (reuses src/search/serper_client.py)."""

    name: str = "serper_baseline"
    runnable: str = "yes"
    max_results: int = DEFAULT_RANK_K

    def search(self, query: str) -> list[dict[str, str]]:
        import asyncio

        from src.search.serper_client import SerperClient

        client = SerperClient()
        if not client.enabled:
            raise RuntimeError("serper: SERPER_API_KEY not configured (declared runnable)")
        results = asyncio.run(client.search(query, max_results=self.max_results))
        return [{"url": r.url, "title": r.title, "snippet": r.snippet} for r in results]


@dataclass
class ExaProvider:
    """Exa neural search. use_autoprompt=False so Exa cannot rewrite the held-fixed query.

    HONEST FLAG (recorded in run output): Exa deprecated ``use_autoprompt`` in API responses
    (2026 SDK). To honor the ISOLATION holding-condition (query held VERBATIM, no expansion) we
    pin ``type='neural'`` (the embedding mode, NOT 'auto'/'deep' which expand) AND pass
    ``use_autoprompt=False`` defensively. The residual API-surface uncertainty is surfaced as a
    run flag, not papered over.
    """

    name: str = "exa"
    runnable: str = "yes"
    num_results: int = DEFAULT_RANK_K
    api_surface_flag: str = (
        "exa use_autoprompt deprecated in 2026 responses; pinned type=neural (no query "
        "expansion) + use_autoprompt=False; verify no rewrite on live run"
    )

    def search(self, query: str) -> list[dict[str, str]]:
        from exa_py import Exa

        key = os.getenv("EXA_API_KEY")
        if not key:
            raise RuntimeError("exa: EXA_API_KEY not configured (declared runnable)")
        exa = Exa(key)
        resp = exa.search(
            query, num_results=self.num_results, type="neural", use_autoprompt=False
        )
        out: list[dict[str, str]] = []
        for r in getattr(resp, "results", []) or []:
            out.append({
                "url": getattr(r, "url", "") or "",
                "title": getattr(r, "title", "") or "",
                "snippet": getattr(r, "text", "") or "",
            })
        return out


@dataclass
class SemanticScholarProvider:
    """Semantic Scholar /paper/search — relevance-RANKED papers (a justified ranking candidate).

    Returns ranked DOI/openAccessPdf URLs. Academic-only recall (strong on named-study findings,
    weak on gov/news — that contrast is the signal).
    """

    name: str = "semantic_scholar"
    runnable: str = "yes"
    limit: int = DEFAULT_RANK_K

    def search(self, query: str) -> list[dict[str, str]]:
        import httpx

        headers = {}
        key = os.getenv("S2_API_KEY")
        if key:
            headers["x-api-key"] = key
        params = {
            "query": query,
            "limit": self.limit,
            "fields": "title,externalIds,openAccessPdf,url",
        }
        with httpx.Client(timeout=30.0, headers=headers) as client:
            r = client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search", params=params
            )
            r.raise_for_status()
            data = r.json()
        out: list[dict[str, str]] = []
        for p in data.get("data", []) or []:
            ext = p.get("externalIds") or {}
            doi = ext.get("DOI")
            url = ""
            if doi:
                url = f"https://doi.org/{doi}"
            elif (p.get("openAccessPdf") or {}).get("url"):
                url = p["openAccessPdf"]["url"]
            elif p.get("url"):
                url = p["url"]
            if url:
                out.append({"url": url, "title": p.get("title", "") or "", "snippet": ""})
        return out


@dataclass
class FirecrawlSearchProvider:
    """Firecrawl agent-search API, scrapeOptions DISABLED (search-only, score URL ranking)."""

    name: str = "firecrawl_search"
    runnable: str = "yes"
    limit: int = DEFAULT_RANK_K

    def search(self, query: str) -> list[dict[str, str]]:
        from firecrawl import Firecrawl

        key = os.getenv("FIRECRAWL_API_KEY")
        if not key:
            raise RuntimeError("firecrawl: FIRECRAWL_API_KEY not configured (declared runnable)")
        app = Firecrawl(api_key=key)
        resp = app.search(query, limit=self.limit)
        out: list[dict[str, str]] = []
        items = resp.get("data") if isinstance(resp, dict) else getattr(resp, "web", resp)
        for it in (items or []):
            d = it if isinstance(it, dict) else getattr(it, "__dict__", {})
            url = d.get("url") or ""
            if url:
                out.append({
                    "url": url, "title": d.get("title", "") or "",
                    "snippet": d.get("description", "") or "",
                })
        return out


@dataclass
class SearxngProvider:
    """SearXNG self-host metasearch (the only sovereign candidate). Needs the container up."""

    name: str = "searxng"
    runnable: str = "needs_service"
    base_url: str = field(default_factory=lambda: os.getenv("SEARXNG_URL", "http://127.0.0.1:8080"))
    limit: int = DEFAULT_RANK_K

    def search(self, query: str) -> list[dict[str, str]]:
        import httpx

        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base_url}/search", params={"q": query, "format": "json"}
            )
            r.raise_for_status()
            data = r.json()
        out: list[dict[str, str]] = []
        for it in (data.get("results") or [])[: self.limit]:
            url = it.get("url") or ""
            if url:
                out.append({
                    "url": url, "title": it.get("title", "") or "",
                    "snippet": it.get("content", "") or "",
                })
        return out


# no_key candidates: REGISTERED but never invoked here (no key held). Recorded, never faked.
NO_KEY_CANDIDATES: tuple[dict[str, str], ...] = (
    {"name": "tavily", "reason": "TAVILY_API_KEY not held", "license": "proprietary"},
    {"name": "parallel", "reason": "PARALLEL_API_KEY not held", "license": "proprietary"},
    {"name": "brave", "reason": "BRAVE_API_KEY not held (non-sovereign yardstick)",
     "license": "proprietary"},
)


def default_providers() -> list[SearchProvider]:
    """The runnable/known candidate set (no_key ones are in NO_KEY_CANDIDATES, not here)."""
    return [
        SerperProvider(),
        ExaProvider(),
        SemanticScholarProvider(),
        FirecrawlSearchProvider(),
        SearxngProvider(),
    ]


# ---------------------------------------------------------------------------
# Scoring: per-finding gold-source recall over the union of ranked URLs for a slug.
# ---------------------------------------------------------------------------


def score_provider_on_slug(
    provider: SearchProvider,
    slug: str,
    queries: list[str],
    gold_rows: list[dict[str, Any]],
    rank_k: int = DEFAULT_RANK_K,
) -> dict[str, Any]:
    """Run the FIXED queries through one provider, collect the rank-k URL union, score recall.

    Only rows that carry a confirmed gold SET are scored (rows flagged needs_confirm with no gold
    are excluded from the denominator and reported separately — never a silent fake 0/1).
    Returns a per-slug result dict with per-finding verdicts (full §-1.1 audit trail).
    """
    ranked_urls: list[str] = []
    seen: set[str] = set()
    for q in queries:
        for item in provider.search(q)[:rank_k]:
            u = (item.get("url") or "").strip()
            if u and u not in seen:
                seen.add(u)
                ranked_urls.append(u)

    scorable = [r for r in gold_rows if r.get("gold_sources")]
    skipped = [r for r in gold_rows if not r.get("gold_sources")]

    per_finding: list[dict[str, Any]] = []
    covered = 0
    for row in scorable:
        gold_set = gold_set_for_row(row)
        hit = finding_recall(ranked_urls, gold_set)
        covered += hit
        per_finding.append({
            "finding_index": row.get("finding_index"),
            "title": row.get("title"),
            "confirmation_status": row.get("confirmation_status"),
            "recall": hit,
            "finding_preview": (row.get("finding") or "")[:160],
        })

    total = len(scorable)
    return {
        "provider": provider.name,
        "slug": slug,
        "idx": SLUG_TO_IDX.get(slug),
        "recall_at_k": (covered / total) if total else 0.0,
        "covered": covered,
        "total_scorable": total,
        "n_skipped_needs_confirm": len(skipped),
        "n_ranked_urls": len(ranked_urls),
        "rank_k": rank_k,
        "per_finding": per_finding,
    }


def run_bakeoff(
    fixture_path: str,
    queries_by_slug: dict[str, list[str]],
    providers: list[SearchProvider] | None = None,
    rank_k: int = DEFAULT_RANK_K,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> dict[str, Any]:
    """Score every runnable provider on every slug; record no_key skips honestly.

    queries_by_slug holds the FIXED IterResearch query set per slug (identical for every
    provider). Returns the ranked results structure for the results JSON.
    """
    providers = providers if providers is not None else default_providers()
    gold_by_idx = load_fixture(fixture_path)

    results: list[dict[str, Any]] = []
    skipped_providers: list[dict[str, Any]] = []
    for provider in providers:
        if provider.runnable == "no_key":
            skipped_providers.append({"provider": provider.name, "reason": "no_key"})
            continue
        for slug, queries in queries_by_slug.items():
            idx = SLUG_TO_IDX.get(slug)
            gold_rows = gold_by_idx.get(idx, [])
            if not gold_rows:
                continue
            results.append(
                score_provider_on_slug(provider, slug, queries, gold_rows, rank_k)
            )

    # Aggregate per provider (mean recall over slugs) for a ranked board.
    board: dict[str, list[float]] = {}
    for r in results:
        board.setdefault(r["provider"], []).append(r["recall_at_k"])
    ranked_board = sorted(
        (
            {"provider": p, "mean_recall_at_k": sum(v) / len(v), "n_slugs": len(v)}
            for p, v in board.items()
        ),
        key=lambda d: d["mean_recall_at_k"],
        reverse=True,
    )

    return {
        "layer": "search_discovery",
        "metric": "gold_source_set_recall_at_k",
        "rank_k": rank_k,
        "fixture_path": fixture_path,
        "ranked_board": ranked_board,
        "per_slug_results": results,
        "skipped_no_key": list(NO_KEY_CANDIDATES) + skipped_providers,
    }


def _load_queries_arg(path: str | None) -> dict[str, list[str]]:
    """Load the FIXED per-slug IterResearch queries from a JSON file, or fail loud."""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            f"queries file required (the held-fixed IterResearch query set per slug): {path}"
        )
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the search_discovery bake-off")
    parser.add_argument(
        "--fixture", default="tests/fixtures/retrieval_bakeoff/drb_gold_sources.jsonl"
    )
    parser.add_argument(
        "--queries", required=True,
        help="JSON file: {slug: [held IterResearch query, ...]}",
    )
    parser.add_argument("--rank-k", type=int, default=DEFAULT_RANK_K)
    parser.add_argument("--out", default="outputs/retrieval_bakeoff/search_discovery_results.json")
    args = parser.parse_args(argv)

    queries_by_slug = _load_queries_arg(args.queries)
    out = run_bakeoff(args.fixture, queries_by_slug, rank_k=args.rank_k)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)
    print(json.dumps(out["ranked_board"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
