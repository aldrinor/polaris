"""Tests for clinical_retriever orchestrator (network-free)."""

from __future__ import annotations

from typing import Callable

import pytest

from polaris_graph.retrieval2.clinical_retriever import (
    FetchResult,
    process_retrieval,
)
from polaris_graph.retrieval2.corpus_adequacy_gate import (
    CLINICAL_DEFAULT,
    ClinicalTemplate,
)
from polaris_graph.retrieval2.evidence_pool import (
    EvidencePool,
    RetrievalError,
    SourceTier,
)
from polaris_graph.scope.scope_decision import (
    AmbiguityAxis,
    ScopeDecision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _decision(
    *,
    status: str = "in_scope",
    scope_class: str | None = "clinical_efficacy",
    population: list[str] | None = None,
    intervention: list[str] | None = None,
    outcome: list[str] | None = None,
) -> ScopeDecision:
    axes = []
    if population:
        axes.append(
            AmbiguityAxis(
                axis="population",
                plausible_interpretations=population,
                needs_clarification=len(population) > 1,
            )
        )
    if intervention:
        axes.append(
            AmbiguityAxis(
                axis="intervention",
                plausible_interpretations=intervention,
                needs_clarification=len(intervention) > 1,
            )
        )
    if outcome:
        axes.append(
            AmbiguityAxis(
                axis="outcome",
                plausible_interpretations=outcome,
                needs_clarification=len(outcome) > 1,
            )
        )
    return ScopeDecision(
        status=status,  # type: ignore[arg-type]
        scope_class=scope_class,  # type: ignore[arg-type]
        ambiguity_axes=axes,
    )


def _result(url: str, title: str = "title") -> FetchResult:
    return FetchResult(url=url, title=title, snippet="snippet")


def _stub_fetcher(
    results_per_query: list[list[FetchResult]],
) -> Callable[[str], list[FetchResult]]:
    """Build a stub fetch_fn that returns the i-th list on the i-th call."""
    state = {"i": 0}

    def fetcher(_query: str) -> list[FetchResult]:
        i = state["i"]
        state["i"] = i + 1
        if i < len(results_per_query):
            return results_per_query[i]
        return []

    return fetcher


def _all_queries_return(results: list[FetchResult]):
    """Stub that returns the same list for every query."""

    def fetcher(_query: str) -> list[FetchResult]:
        return list(results)

    return fetcher


# ---------------------------------------------------------------------------
# Validation: ineligible decisions return RetrievalError
# ---------------------------------------------------------------------------

def test_out_of_scope_returns_wrong_status_error():
    decision = _decision(status="out_of_scope", scope_class=None)
    result = process_retrieval(decision)
    assert isinstance(result, RetrievalError)
    assert result.code == "wrong_status"


def test_refused_returns_wrong_status_error():
    decision = _decision(status="refused", scope_class=None)
    result = process_retrieval(decision)
    assert isinstance(result, RetrievalError)
    assert result.code == "wrong_status"


def test_ambiguous_returns_wrong_status_error():
    """Ambiguous decisions must NOT proceed to retrieval — slice 002 only
    runs after the user has resolved ambiguity."""
    decision = _decision(
        status="ambiguous_needs_clarification",
        scope_class="clinical_efficacy",
        population=["a"],
    )
    result = process_retrieval(decision)
    assert isinstance(result, RetrievalError)
    assert result.code == "wrong_status"


def test_non_clinical_scope_class_returns_error():
    decision = _decision(scope_class="out_of_scope", population=["a"])
    result = process_retrieval(decision)
    assert isinstance(result, RetrievalError)
    assert result.code == "wrong_scope_class"


def test_default_fetcher_raises_via_error_path():
    """No fetch_fn injected -> RetrievalError fetch_backend_unavailable."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    result = process_retrieval(decision)
    assert isinstance(result, RetrievalError)
    assert result.code == "fetch_backend_unavailable"


def test_fetch_fn_exception_returns_error():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )

    def boom(_q: str) -> list[FetchResult]:
        raise ConnectionError("simulated network failure")

    result = process_retrieval(decision, fetch_fn=boom)
    assert isinstance(result, RetrievalError)
    assert result.code == "fetch_backend_unavailable"
    assert "ConnectionError" in result.message


# ---------------------------------------------------------------------------
# Happy path: produces EvidencePool
# ---------------------------------------------------------------------------

def test_in_scope_efficacy_returns_evidence_pool():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return(
        [
            _result("https://www.cochrane.org/CD001"),
            _result("https://www.nejm.org/doi/abc"),
            _result("https://clinicaltrials.gov/study/NCT001"),
        ]
    )
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert result.decision_id == decision.decision_id


def test_pool_includes_classified_sources_only():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return(
        [
            _result("https://en.wikipedia.org/wiki/Aspirin"),  # denied
            _result("https://random-blog.com/post"),  # unclassified
            _result("https://www.cochrane.org/CD001"),  # T1
            _result("https://www.nejm.org/doi/abc"),  # T2
        ]
    )
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    domains = {s.domain for s in result.sources}
    # Allowed sources kept
    assert any("cochrane" in d for d in domains)
    assert any("nejm" in d for d in domains)
    # Denied / unknown dropped
    assert not any("wikipedia" in d for d in domains)
    assert not any("random-blog" in d for d in domains)


def test_pool_dedupes_repeated_urls_across_queries():
    """Same URL surfaced by multiple queries appears once."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    duplicate = _result("https://www.nejm.org/doi/abc")
    fetcher = _all_queries_return([duplicate, duplicate])
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    nejm_count = sum(1 for s in result.sources if "nejm" in s.domain)
    assert nejm_count == 1


def test_pool_canonical_url_dedup_strips_trailing_slash():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )

    # Same URL with/without trailing slash, different fragment
    def fetcher(_q: str) -> list[FetchResult]:
        return [
            _result("https://www.nejm.org/doi/abc/"),
            _result("https://www.nejm.org/doi/abc"),
            _result("https://www.nejm.org/doi/abc#section-1"),
        ]

    # Only fire once (one query) so we assert dedup, not query count
    decision_minimal = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    result = process_retrieval(decision_minimal, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    nejm = [s for s in result.sources if "nejm" in s.domain]
    # All three URLs canonicalize to the same canonical form
    assert len(nejm) == 1


def test_pool_carries_query_provenance():
    """Each source.provenance should contain the query that surfaced it."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )

    def fetcher(query: str) -> list[FetchResult]:
        # Tag the URL by query so we can introspect what surfaced what
        if "randomized" in query:
            return [_result("https://www.cochrane.org/CD001")]
        return []

    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    for source in result.sources:
        assert "query" in source.provenance


def test_pool_queries_executed_populated():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return([_result("https://www.cochrane.org/CD001")])
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert len(result.queries_executed) > 0


def test_pool_no_sources_yields_inadequate_verdict():
    """Fetcher returns nothing -> pool exists but adequacy fails."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return([])
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert not result.adequacy.is_adequate
    assert "T1" in result.adequacy.failure_reason


def test_pool_meeting_threshold_marks_adequate():
    """Build a fetcher that produces >= clinical_default thresholds."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    # clinical_efficacy template: T1>=2, T2>=5, T3>=1
    sources = [
        # T1
        _result("https://www.cochrane.org/CD001"),
        _result("https://www.cochrane.org/CD002"),
        # T2 — five distinct journals
        _result("https://www.nejm.org/doi/a1"),
        _result("https://www.thelancet.com/article/a2"),
        _result("https://jamanetwork.com/journals/jama/a3"),
        _result("https://www.bmj.com/content/a4"),
        _result("https://journals.plos.org/plosmedicine/article?id=a5"),
        # T3
        _result("https://clinicaltrials.gov/study/NCT001"),
    ]
    # Inject all on first query, empty on subsequent — ensures dedup works
    state = {"i": 0}

    def fetcher(_q: str) -> list[FetchResult]:
        if state["i"] == 0:
            state["i"] = 1
            return list(sources)
        return []

    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert result.adequacy.is_adequate, result.adequacy.failure_reason


# ---------------------------------------------------------------------------
# Latency / cost / timestamps
# ---------------------------------------------------------------------------

def test_pool_latency_non_negative():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return([])
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert result.latency_ms >= 0


def test_pool_cost_zero_in_pr6():
    """PR 6 ships orchestrator with stubbed fetcher; cost is always 0
    until PR 7 wires real backend metering."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return([_result("https://www.nejm.org/doi/a")])
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert result.cost_usd == 0.0


def test_pool_timestamps_ordered():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    fetcher = _all_queries_return([])
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert result.retrieval_finished_at_utc >= result.retrieval_started_at_utc


# ---------------------------------------------------------------------------
# Custom template override
# ---------------------------------------------------------------------------

def test_custom_template_used_when_passed():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    strict = ClinicalTemplate(
        template_id="strict_test_template",
        min_t1=10,
        min_t2=10,
        min_t3=10,
    )
    fetcher = _all_queries_return([_result("https://www.nejm.org/doi/a")])
    result = process_retrieval(decision, fetch_fn=fetcher, template=strict)
    assert isinstance(result, EvidencePool)
    assert not result.adequacy.is_adequate
    assert "strict_test_template" in result.adequacy.failure_reason


def test_default_template_routes_by_scope_class():
    """When no template passed, scope_class determines which template
    is used. clinical_safety needs T1>=3."""
    decision = _decision(
        scope_class="clinical_safety",
        population=["older adults"],
        intervention=["metformin"],
        outcome=["adverse events"],
    )
    # Only 2 T1 sources — not enough for clinical_safety (needs 3)
    fetcher = _all_queries_return(
        [
            _result("https://www.cochrane.org/CD001"),
            _result("https://www.fda.gov/drugs/safety-info"),
            _result("https://www.nejm.org/doi/a"),
            _result("https://www.thelancet.com/article/a"),
            _result("https://clinicaltrials.gov/study/NCT001"),
        ]
    )
    result = process_retrieval(decision, fetch_fn=fetcher)
    assert isinstance(result, EvidencePool)
    assert not result.adequacy.is_adequate
    assert "clinical_safety" in result.adequacy.failure_reason
