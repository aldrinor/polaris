"""Tests for the EvidenceContract pre-generation schema (I-ecg-001)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from polaris_graph.evidence_contract import (
    EvidenceContract,
    ExpectedClaim,
    ExpectedEntity,
    ExpectedSourceCoverage,
    Jurisdiction,
)


def _entity(name: str = "aspirin") -> ExpectedEntity:
    return ExpectedEntity(name=name, entity_type="drug")


def _claim(claim_id: str = "c1", entity: str = "aspirin",
           jurs: list[Jurisdiction] | None = None) -> ExpectedClaim:
    return ExpectedClaim(
        claim_id=claim_id,
        statement="aspirin reduces headache pain in adults",
        expected_entities=[entity],
        required_jurisdictions=jurs or [Jurisdiction.CA],
    )


def _coverage() -> ExpectedSourceCoverage:
    return ExpectedSourceCoverage(tier_t1_min=1, tier_t2_min=2, tier_t3_min=0)


def _contract(**overrides) -> EvidenceContract:
    return EvidenceContract(
        research_question=overrides.pop("research_question", "Does aspirin reduce headache in adults?"),
        expected_entities=overrides.pop("expected_entities", [_entity()]),
        expected_claims=overrides.pop("expected_claims", [_claim()]),
        expected_source_coverage=overrides.pop("expected_source_coverage", _coverage()),
        jurisdictions=overrides.pop("jurisdictions", [Jurisdiction.CA]),
        created_by=overrides.pop("created_by", "operator-1"),
        **overrides,
    )


def test_minimal_valid_contract():
    c = _contract()
    assert c.contract_version == "1.0"
    assert c.contract_id


def test_jurisdiction_enum_values():
    for j in [Jurisdiction.CA, Jurisdiction.US, Jurisdiction.EU, Jurisdiction.UK, Jurisdiction.GLOBAL]:
        c = _contract(jurisdictions=[j], expected_claims=[_claim(jurs=[j])])
        assert j in c.jurisdictions


def test_expected_source_coverage_zero_min_allowed():
    cov = ExpectedSourceCoverage(tier_t1_min=0, tier_t2_min=0, tier_t3_min=0)
    assert cov.tier_t1_min == 0


def test_undeclared_entity_in_claim_rejected():
    with pytest.raises(ValidationError, match="undeclared entity"):
        _contract(expected_claims=[_claim(entity="ghost")])


def test_empty_expected_entities_rejected():
    with pytest.raises(ValidationError):
        _contract(expected_entities=[])


def test_empty_expected_claims_rejected():
    with pytest.raises(ValidationError):
        _contract(expected_claims=[])


def test_contract_version_pinned():
    with pytest.raises(ValidationError):
        EvidenceContract(
            contract_version="2.0",  # type: ignore[arg-type]
            research_question="q",
            expected_entities=[_entity()],
            expected_claims=[_claim()],
            expected_source_coverage=_coverage(),
            jurisdictions=[Jurisdiction.CA],
            created_by="op",
        )


def test_contract_round_trip_json():
    c1 = _contract()
    raw = c1.model_dump_json()
    c2 = EvidenceContract.model_validate_json(raw)
    assert c1 == c2


def test_duplicate_entity_name_rejected():
    with pytest.raises(ValidationError, match="duplicate entity name"):
        _contract(expected_entities=[_entity("aspirin"), _entity("aspirin")])


def test_duplicate_claim_id_rejected():
    with pytest.raises(ValidationError, match="duplicate claim_id"):
        _contract(expected_claims=[_claim("c1"), _claim("c1")])


def test_claim_jurisdiction_must_be_in_contract_jurisdictions():
    with pytest.raises(ValidationError, match="not in contract jurisdictions"):
        _contract(
            jurisdictions=[Jurisdiction.CA],
            expected_claims=[_claim(jurs=[Jurisdiction.US])],
        )
