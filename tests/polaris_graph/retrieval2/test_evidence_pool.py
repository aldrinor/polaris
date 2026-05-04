"""Tests for polaris_graph.retrieval2.evidence_pool schemas."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    RetrievalError,
    Source,
    SourceTier,
)


# ---------- SourceTier ----------

def test_source_tier_enum_values():
    assert SourceTier.T1.value == "T1"
    assert SourceTier.T2.value == "T2"
    assert SourceTier.T3.value == "T3"


def test_source_tier_str_coercion():
    """Pydantic should accept string 'T1' and coerce to enum."""
    s = Source(
        url="https://www.cochrane.org/CD0000",
        domain="cochrane.org",
        tier="T1",
        title="example",
        snippet="example snippet",
    )
    assert s.tier is SourceTier.T1


# ---------- Source ----------

def test_source_minimal_construction():
    s = Source(
        url="https://pubmed.ncbi.nlm.nih.gov/123456/",
        domain="pubmed.ncbi.nlm.nih.gov",
        tier=SourceTier.T2,
        title="A randomized trial of aspirin",
        snippet="In this RCT we randomized 1,000 patients ...",
    )
    assert s.source_id  # uuid auto-populated
    assert s.fetched_at_utc.tzinfo is not None
    assert s.full_text is None
    assert s.full_text_available is False
    assert s.authors == []


def test_source_domain_lowercased():
    s = Source(
        url="https://NEJM.ORG/doi/abc",
        domain="NEJM.ORG",
        tier=SourceTier.T2,
        title="x",
        snippet="x",
    )
    assert s.domain == "nejm.org"


def test_source_rejects_blank_title():
    with pytest.raises(ValidationError):
        Source(
            url="https://nejm.org/doi/abc",
            domain="nejm.org",
            tier=SourceTier.T2,
            title="",
            snippet="x",
        )


def test_source_rejects_invalid_url():
    with pytest.raises(ValidationError):
        Source(
            url="not-a-url",
            domain="example.com",
            tier=SourceTier.T2,
            title="x",
            snippet="x",
        )


def test_source_strips_blank_authors():
    s = Source(
        url="https://nejm.org/doi/abc",
        domain="nejm.org",
        tier=SourceTier.T2,
        title="x",
        snippet="x",
        authors=["Jane Doe", "  ", "", "John Smith  "],
    )
    assert s.authors == ["Jane Doe", "John Smith"]


def test_source_with_publication_date():
    s = Source(
        url="https://nejm.org/doi/abc",
        domain="nejm.org",
        tier=SourceTier.T2,
        title="x",
        snippet="x",
        publication_date=date(2024, 1, 15),
    )
    assert s.publication_date == date(2024, 1, 15)


def test_source_provenance_arbitrary_dict():
    s = Source(
        url="https://nejm.org/doi/abc",
        domain="nejm.org",
        tier=SourceTier.T2,
        title="x",
        snippet="x",
        provenance={"query": "aspirin headache", "rank": 3},
    )
    assert s.provenance["query"] == "aspirin headache"


# ---------- AdequacyVerdict ----------

def test_adequacy_verdict_pass():
    v = AdequacyVerdict(
        is_adequate=True,
        sources_per_tier={SourceTier.T1: 2, SourceTier.T2: 5, SourceTier.T3: 2},
        min_required_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
    )
    assert v.is_adequate
    assert v.failure_reason is None


def test_adequacy_verdict_fail_requires_reason():
    with pytest.raises(ValidationError, match="failure_reason is required"):
        AdequacyVerdict(
            is_adequate=False,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 1, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
        )


def test_adequacy_verdict_pass_rejects_failure_reason():
    with pytest.raises(ValidationError, match="must be None when is_adequate=True"):
        AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
            min_required_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
            failure_reason="should not be allowed",
        )


def test_adequacy_verdict_fail_with_reason():
    v = AdequacyVerdict(
        is_adequate=False,
        sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 1, SourceTier.T3: 0},
        min_required_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
        failure_reason="not enough T1 sources (got 0, need 2)",
    )
    assert not v.is_adequate
    assert "T1" in v.failure_reason


# ---------- EvidencePool ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _adequate_verdict() -> AdequacyVerdict:
    return AdequacyVerdict(
        is_adequate=True,
        sources_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
        min_required_per_tier={SourceTier.T1: 2, SourceTier.T2: 4, SourceTier.T3: 2},
    )


def _make_source(tier: SourceTier = SourceTier.T2) -> Source:
    return Source(
        url="https://nejm.org/doi/abc",
        domain="nejm.org",
        tier=tier,
        title="example",
        snippet="example",
    )


def test_evidence_pool_minimal():
    started = _now()
    finished = started + timedelta(seconds=2)
    pool = EvidencePool(
        decision_id="dec-123",
        sources=[_make_source()],
        adequacy=_adequate_verdict(),
        queries_executed=["aspirin headache"],
        retrieval_started_at_utc=started,
        retrieval_finished_at_utc=finished,
        latency_ms=2000,
        cost_usd=0.0123,
    )
    assert pool.pool_id  # uuid auto-populated
    assert pool.decision_id == "dec-123"
    assert pool.latency_ms == 2000


def test_evidence_pool_finished_before_started_rejected():
    started = _now()
    finished = started - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="must be >= retrieval_started_at_utc"):
        EvidencePool(
            decision_id="dec-123",
            adequacy=_adequate_verdict(),
            retrieval_started_at_utc=started,
            retrieval_finished_at_utc=finished,
            latency_ms=0,
            cost_usd=0.0,
        )


def test_evidence_pool_negative_latency_rejected():
    started = _now()
    with pytest.raises(ValidationError):
        EvidencePool(
            decision_id="dec-123",
            adequacy=_adequate_verdict(),
            retrieval_started_at_utc=started,
            retrieval_finished_at_utc=started,
            latency_ms=-1,
            cost_usd=0.0,
        )


def test_evidence_pool_negative_cost_rejected():
    started = _now()
    with pytest.raises(ValidationError):
        EvidencePool(
            decision_id="dec-123",
            adequacy=_adequate_verdict(),
            retrieval_started_at_utc=started,
            retrieval_finished_at_utc=started,
            latency_ms=0,
            cost_usd=-0.01,
        )


def test_evidence_pool_blank_decision_id_rejected():
    started = _now()
    with pytest.raises(ValidationError):
        EvidencePool(
            decision_id="",
            adequacy=_adequate_verdict(),
            retrieval_started_at_utc=started,
            retrieval_finished_at_utc=started,
            latency_ms=0,
            cost_usd=0.0,
        )


def test_evidence_pool_sources_by_tier_filters():
    started = _now()
    pool = EvidencePool(
        decision_id="dec-123",
        sources=[
            _make_source(tier=SourceTier.T1),
            _make_source(tier=SourceTier.T2),
            _make_source(tier=SourceTier.T2),
            _make_source(tier=SourceTier.T3),
        ],
        adequacy=_adequate_verdict(),
        retrieval_started_at_utc=started,
        retrieval_finished_at_utc=started,
        latency_ms=0,
        cost_usd=0.0,
    )
    assert len(pool.sources_by_tier(SourceTier.T1)) == 1
    assert len(pool.sources_by_tier(SourceTier.T2)) == 2
    assert len(pool.sources_by_tier(SourceTier.T3)) == 1


def test_evidence_pool_round_trip_json():
    started = _now()
    pool = EvidencePool(
        decision_id="dec-123",
        sources=[_make_source()],
        adequacy=_adequate_verdict(),
        queries_executed=["q1", "q2"],
        retrieval_started_at_utc=started,
        retrieval_finished_at_utc=started,
        latency_ms=0,
        cost_usd=0.0,
    )
    payload = pool.model_dump(mode="json")
    assert isinstance(payload["pool_id"], str)
    assert payload["sources"][0]["tier"] == "T2"

    rehydrated = EvidencePool.model_validate(payload)
    assert rehydrated.pool_id == pool.pool_id
    assert rehydrated.sources[0].domain == "nejm.org"


# ---------- RetrievalError ----------

def test_retrieval_error_minimal():
    err = RetrievalError(
        code="wrong_status",
        message="ScopeDecision.status was 'out_of_scope', cannot retrieve",
    )
    assert err.error is True
    assert err.code == "wrong_status"
    assert err.decision_id is None


def test_retrieval_error_with_decision_id():
    err = RetrievalError(
        code="wrong_scope_class",
        message="scope_class must be clinical_*, got out_of_scope",
        decision_id="dec-456",
    )
    assert err.decision_id == "dec-456"
