"""Tests for the Evidence Contract gate (I-ecg-002)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.evidence_contract import (
    ContractRequiredError,
    EvidenceContract,
    ExpectedClaim,
    ExpectedEntity,
    ExpectedSourceCoverage,
    Jurisdiction,
    assert_generation_has_contract,
    evaluate_contract,
)
from polaris_graph.clinical_generator.verified_report import (
    Section,
    VerifiedReport,
    VerifiedSentence,
)
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


def _src(source_id: str, tier: SourceTier, domain: str = "cochrane.org") -> Source:
    return Source(
        url=f"https://{domain}/x",
        domain=domain,
        tier=tier,
        title="t",
        snippet="s",
        full_text="ft",
        full_text_available=True,
        source_id=source_id,
        provenance={"legal_cleared": True},
    )


def _pool(sources: list[Source]) -> EvidencePool:
    return EvidencePool(
        pool_id="p1",
        decision_id="d1",
        sources=sources,
        adequacy=AdequacyVerdict(is_adequate=True),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _report(sentence_text: str = "aspirin reduces headache pain in adults",
            cited_source_id: str = "a") -> VerifiedReport:
    return VerifiedReport(
        report_id="r1",
        pool_id="p1",
        decision_id="d1",
        sections=[
            Section(
                section_id="s1",
                section_title="X",
                verified_sentences=[
                    VerifiedSentence(
                        section_id="s1",
                        sentence_text=sentence_text,
                        provenance_tokens=[f"[#ev:{cited_source_id}:0-3]"],
                        verifier_pass=True,
                    )
                ],
                section_verify_pass_rate=1.0,
                section_status="verified",
            )
        ],
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="m",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _contract(
    entity_name: str = "aspirin",
    statement: str = "aspirin reduces headache pain",
    jurs: list[Jurisdiction] | None = None,
    coverage: ExpectedSourceCoverage | None = None,
) -> EvidenceContract:
    jurs = jurs or [Jurisdiction.CA]
    return EvidenceContract(
        research_question="q",
        expected_entities=[ExpectedEntity(name=entity_name, entity_type="drug")],
        expected_claims=[
            ExpectedClaim(
                claim_id="c1",
                statement=statement,
                expected_entities=[entity_name],
                required_jurisdictions=jurs,
            )
        ],
        expected_source_coverage=coverage or ExpectedSourceCoverage(
            tier_t1_min=1, tier_t2_min=0, tier_t3_min=0
        ),
        jurisdictions=jurs,
        created_by="op",
    )


def test_assert_generation_has_contract_passes_with_contract():
    assert_generation_has_contract(_contract())


def test_assert_generation_has_contract_raises_without_contract():
    with pytest.raises(ContractRequiredError, match="Evidence Contract required"):
        assert_generation_has_contract(None)


def test_evaluate_contract_passes_when_report_covers_everything():
    v = evaluate_contract(_contract(), _pool([_src("a", SourceTier.T1)]), _report())
    assert v.passed
    assert v.failures == []


def test_evaluate_contract_fails_on_missing_entity_coverage():
    v = evaluate_contract(
        _contract(entity_name="ibuprofen", statement="ibuprofen reduces fever"),
        _pool([_src("a", SourceTier.T1)]),
        _report(),
    )
    assert not v.passed
    assert any(f.startswith("entity_not_covered:ibuprofen") for f in v.failures)


def test_evaluate_contract_fails_on_missing_claim_coverage():
    v = evaluate_contract(
        _contract(statement="aspirin cures cancer"),
        _pool([_src("a", SourceTier.T1)]),
        _report(),
    )
    assert not v.passed
    assert any(f.startswith("claim_not_covered:c1") for f in v.failures)


def test_evaluate_contract_fails_on_insufficient_t1_sources():
    v = evaluate_contract(
        _contract(coverage=ExpectedSourceCoverage(tier_t1_min=3, tier_t2_min=0, tier_t3_min=0)),
        _pool([_src("a", SourceTier.T1)]),
        _report(),
    )
    assert not v.passed
    assert any(f.startswith("insufficient_t1_sources:1<3") for f in v.failures)


def test_evaluate_contract_aggregates_multiple_failures():
    v = evaluate_contract(
        _contract(
            entity_name="ibuprofen",
            statement="ibuprofen cures cancer",
            coverage=ExpectedSourceCoverage(tier_t1_min=5, tier_t2_min=0, tier_t3_min=0),
        ),
        _pool([_src("a", SourceTier.T1)]),
        _report(),
    )
    assert not v.passed
    assert len(v.failures) >= 3


def test_evaluate_contract_fails_on_jurisdiction_not_covered():
    v = evaluate_contract(
        _contract(jurs=[Jurisdiction.US]),
        _pool([_src("a", SourceTier.T1, domain="cochrane.org")]),
        _report(),
    )
    assert not v.passed
    assert any(f.startswith("jurisdiction_not_covered:c1:US") for f in v.failures)


def test_evaluate_contract_passes_with_zero_min_coverage():
    v = evaluate_contract(
        _contract(coverage=ExpectedSourceCoverage(tier_t1_min=0, tier_t2_min=0, tier_t3_min=0)),
        _pool([_src("a", SourceTier.T1)]),
        _report(),
    )
    assert v.passed
