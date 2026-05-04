"""Clinical retriever orchestrator — slice 002 main entry.

Per `.codex/slices/slice_002/architecture_proposal.md` §"clinical_retriever".

Pipeline:
    ScopeDecision (slice 001 in_scope clinical_*)
        ↓
    plan_queries()                    -> list[str]
        ↓
    fetch_fn(query) for each query    -> list[FetchResult]
        ↓
    classify_url() drops + tiers      -> list[Source]
        ↓
    de-duplicate by canonical URL     -> list[Source]
        ↓
    template_for_scope_class()        -> ClinicalTemplate
        ↓
    assess()                          -> AdequacyVerdict
        ↓
    EvidencePool

Network-free by design: callers inject fetch_fn (FetchHttpFn protocol)
that returns deterministic FetchResults. The default fetcher raises
NotImplementedError so unit tests + golden tests cannot accidentally
make network calls. PR 7 will ship a real Serper + Semantic Scholar
backed fetch_fn behind the same Protocol.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

from polaris_graph.retrieval2.clinical_source_registry import classify_url
from polaris_graph.retrieval2.corpus_adequacy_gate import (
    ClinicalTemplate,
    assess,
    template_for_scope_class,
)
from polaris_graph.retrieval2.evidence_pool import (
    EvidencePool,
    RetrievalError,
    Source,
    SourceTier,
)
from polaris_graph.retrieval2.query_planner import plan_queries
from polaris_graph.scope.scope_decision import ScopeDecision


# ---------------------------------------------------------------------------
# Protocols + raw fetch result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FetchResult:
    """Raw fetch output. Must be classifiable by clinical_source_registry."""

    url: str
    title: str
    snippet: str
    domain: str | None = None  # if None, derived from URL by orchestrator


class FetchHttpFn(Protocol):
    """Network adapter contract.

    Implementations must be deterministic-given-input enough to test, and
    must raise on persistent network failure (don't silently downgrade).
    """

    def __call__(self, query: str) -> list[FetchResult]: ...


def _default_fetch_fn(query: str) -> list[FetchResult]:
    """Sentinel fetcher that refuses to run.

    PR 6 ships the orchestrator with NO real network adapter; callers
    must inject one explicitly. This guards against accidental
    network calls in unit tests + slice 002 golden tests.
    """
    raise NotImplementedError(
        "no fetch_fn injected. slice 002 PR 7 ships the real "
        "Serper+Semantic-Scholar backed fetcher; for unit tests inject "
        "a stub fetch_fn."
    )


# ---------------------------------------------------------------------------
# Validation: which ScopeDecisions are eligible for clinical retrieval
# ---------------------------------------------------------------------------

_CLINICAL_SCOPE_CLASSES: frozenset[str] = frozenset({
    "clinical_efficacy",
    "clinical_safety",
    "clinical_diagnosis",
    "clinical_prognosis",
})


def _validate_decision(decision: ScopeDecision) -> RetrievalError | None:
    if decision.status != "in_scope":
        return RetrievalError(
            code="wrong_status",
            message=(
                f"clinical retrieval requires status='in_scope', got "
                f"{decision.status!r}; upstream pipeline aborted"
            ),
            decision_id=decision.decision_id,
        )
    if decision.scope_class not in _CLINICAL_SCOPE_CLASSES:
        return RetrievalError(
            code="wrong_scope_class",
            message=(
                f"clinical retrieval requires a clinical_* scope_class, "
                f"got {decision.scope_class!r}"
            ),
            decision_id=decision.decision_id,
        )
    return None


# ---------------------------------------------------------------------------
# Sources extraction + deduplication
# ---------------------------------------------------------------------------

def _fetch_result_to_source(
    result: FetchResult,
    tier: SourceTier,
    query: str,
) -> Source:
    return Source(
        url=result.url,
        domain=result.domain or _domain_from_url(result.url),
        tier=tier,
        title=result.title,
        snippet=result.snippet,
        full_text_available=False,
        full_text=None,
        provenance={"query": query},
    )


def _domain_from_url(url: str) -> str:
    """Extract hostname from URL; deferred from urllib for one-line clarity."""
    from urllib.parse import urlparse
    try:
        return (urlparse(url).hostname or "unknown").lower()
    except (ValueError, AttributeError):
        return "unknown"


def _canonical_url(url: str) -> str:
    """Normalize URL for de-dup: lowercase host, strip fragment + trailing /."""
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").rstrip("/")
        return urlunparse(
            (parsed.scheme.lower(), host, path, parsed.params, parsed.query, "")
        )
    except (ValueError, AttributeError):
        return url


def _dedupe_by_url(sources: Iterable[Source]) -> list[Source]:
    """Drop sources whose canonical URL already appeared. Order-preserving."""
    seen: set[str] = set()
    kept: list[Source] = []
    for s in sources:
        canon = _canonical_url(str(s.url))
        if canon in seen:
            continue
        seen.add(canon)
        kept.append(s)
    return kept


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

def process_retrieval(
    decision: ScopeDecision,
    fetch_fn: FetchHttpFn = _default_fetch_fn,
    template: ClinicalTemplate | None = None,
) -> EvidencePool | RetrievalError:
    """Run a slice 001 ScopeDecision through clinical retrieval.

    Returns:
        EvidencePool when retrieval ran (regardless of adequacy verdict).
            Caller inspects pool.adequacy.is_adequate to decide whether
            to flow to slice 003 generation.
        RetrievalError when the decision is structurally ineligible
            (wrong status, wrong scope_class, or fetch backend fails).
    """
    err = _validate_decision(decision)
    if err is not None:
        return err

    started = datetime.now(timezone.utc)
    t_start = time.perf_counter()

    queries = plan_queries(decision)

    # Run each query, classify each fetch result, keep only allowed-tier sources
    raw_sources: list[Source] = []
    for query in queries:
        try:
            results = fetch_fn(query)
        except NotImplementedError:
            return RetrievalError(
                code="fetch_backend_unavailable",
                message=(
                    "fetch_fn is the sentinel default; inject a real "
                    "fetcher (PR 7) or a test stub"
                ),
                decision_id=decision.decision_id,
            )
        except Exception as exc:  # noqa: BLE001 - propagate as RetrievalError
            return RetrievalError(
                code="fetch_backend_unavailable",
                message=f"fetch_fn raised {type(exc).__name__}: {exc}",
                decision_id=decision.decision_id,
            )

        for result in results:
            tier = classify_url(result.url)
            if tier is None:
                continue  # not on the allowlist; skip
            raw_sources.append(_fetch_result_to_source(result, tier, query))

    sources = _dedupe_by_url(raw_sources)

    chosen_template = template or template_for_scope_class(decision.scope_class)
    adequacy = assess(sources, chosen_template)

    finished = datetime.now(timezone.utc)
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    return EvidencePool(
        decision_id=decision.decision_id,
        sources=sources,
        adequacy=adequacy,
        queries_executed=queries,
        retrieval_started_at_utc=started,
        retrieval_finished_at_utc=finished,
        latency_ms=elapsed_ms,
        cost_usd=0.0,  # PR 7 will accumulate real fetch cost
    )
