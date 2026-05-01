"""Evidence Contract Gate — Phase 1 Task 1.4 GREEN test.

Per docs/carney_delivery_plan_FINAL.md F15, every research run emits an
artifact JSON conforming to EvidenceContract v1.0. The Gate test
validates that:

1. Three hand-crafted golden artifacts (success / contradiction /
   abort) all parse against the schema.
2. CLAUDE.md §9.1 invariants are checkable from the artifact:
   - family_segregation_passed must be true for non-error runs
   - abort_no_verified_sections artifacts have empty verified_sentences
   - Each verified sentence's provenance token references an
     evidence_id present in the pool
3. The schema rejects malformed artifacts (wrong contract_version,
   negative cost, span_end <= span_start, etc).

This Gate is what blocks Phase 1 from declaring 1.4 complete.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence_contract_v1"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture
def evidence_contract_cls():
    pytest.importorskip("pydantic")
    from polaris_v6.schemas.evidence_contract import EvidenceContract

    return EvidenceContract


@pytest.mark.parametrize(
    "fixture_name",
    [
        "golden_run_clinical.json",
        "golden_run_with_contradiction.json",
        "golden_run_abort_no_verified.json",
    ],
)
def test_golden_artifact_parses(evidence_contract_cls, fixture_name):
    raw = _load_fixture(fixture_name)
    contract = evidence_contract_cls.model_validate(raw)
    assert contract.contract_version == "1.0"
    assert contract.run_id == raw["run_id"]


def test_family_segregation_invariant_holds(evidence_contract_cls):
    for fixture_name in [
        "golden_run_clinical.json",
        "golden_run_with_contradiction.json",
    ]:
        contract = evidence_contract_cls.model_validate(_load_fixture(fixture_name))
        assert contract.family_segregation_passed is True
        assert contract.generator_model.startswith("deepseek")
        assert contract.verifier_model.startswith("gemma")


def test_abort_no_verified_has_empty_sentences(evidence_contract_cls):
    contract = evidence_contract_cls.model_validate(
        _load_fixture("golden_run_abort_no_verified.json")
    )
    assert contract.pipeline_status == "abort_no_verified_sections"
    assert contract.verified_sentences == []


def test_provenance_tokens_reference_pool(evidence_contract_cls):
    contract = evidence_contract_cls.model_validate(
        _load_fixture("golden_run_clinical.json")
    )
    pool_ids = {span.evidence_id for span in contract.evidence_pool}
    for sentence in contract.verified_sentences:
        for token in sentence.provenance_tokens:
            assert token.startswith("[#ev:") and token.endswith("]")
            evidence_id = token.removeprefix("[#ev:").split(":", 1)[0]
            assert evidence_id in pool_ids, (
                f"Provenance token {token} references {evidence_id} "
                f"not present in evidence pool {pool_ids}"
            )


def test_contradiction_evidence_resolves_to_pool(evidence_contract_cls):
    contract = evidence_contract_cls.model_validate(
        _load_fixture("golden_run_with_contradiction.json")
    )
    assert len(contract.contradictions) == 1
    pool_ids = {span.evidence_id for span in contract.evidence_pool}
    for contradiction in contract.contradictions:
        for ev_id in contradiction.evidence_a + contradiction.evidence_b:
            assert ev_id in pool_ids


def test_negative_cost_rejected(evidence_contract_cls):
    raw = _load_fixture("golden_run_clinical.json")
    raw["cost_usd"] = -1.0
    pytest.importorskip("pydantic")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        evidence_contract_cls.model_validate(raw)


def test_invalid_span_bounds_rejected(evidence_contract_cls):
    raw = _load_fixture("golden_run_clinical.json")
    raw["evidence_pool"][0]["span_end"] = 0
    pytest.importorskip("pydantic")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        evidence_contract_cls.model_validate(raw)


def test_wrong_contract_version_rejected(evidence_contract_cls):
    raw = _load_fixture("golden_run_clinical.json")
    raw["contract_version"] = "0.9"
    pytest.importorskip("pydantic")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        evidence_contract_cls.model_validate(raw)
