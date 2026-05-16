"""Tests for Pydantic v2 schemas — run_request, run_status, evidence_contract, verifier_verdict."""

from __future__ import annotations

import pytest


def test_run_request_accepts_valid_clinical():
    pytest.importorskip("pydantic")
    from polaris_v6.schemas.run_request import RunRequest

    req = RunRequest(template="clinical", question="Latest evidence on X?")
    assert req.template == "clinical"
    assert req.document_ids == []


def test_run_request_rejects_invalid_template():
    pytest.importorskip("pydantic")
    from polaris_v6.schemas.run_request import RunRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunRequest(template="not_real", question="test test")


def test_run_request_question_too_short():
    pytest.importorskip("pydantic")
    from polaris_v6.schemas.run_request import RunRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunRequest(template="policy", question="x")


def test_evidence_contract_round_trip():
    pytest.importorskip("pydantic")
    from polaris_v6.schemas.evidence_contract import (
        ContradictionRecord,
        EvidenceContract,
        FrameCoverage,
        SourceSpan,
        VerifiedSentence,
    )

    contract = EvidenceContract(
        run_id="r1",
        template="policy",
        question="What does CMHC say about Q3?",
        queued_at="2026-05-01T10:00:00Z",
        finished_at="2026-05-01T10:08:00Z",
        pipeline_status="success",
        evidence_pool=[
            SourceSpan(
                evidence_id="ev_001",
                source_url="https://www.cmhc-schl.gc.ca/...",
                source_tier="T1",
                span_start=100,
                span_end=240,
                span_text="National housing starts rose 3.4% in Q3 2025.",
            )
        ],
        verified_sentences=[
            VerifiedSentence(
                section_id="summary",
                sentence_text="Housing starts grew 3.4% in Q3 2025 [#ev:ev_001:100-240].",
                provenance_tokens=["[#ev:ev_001:100-240]"],
                verifier_local_pass=True,
                verifier_global_pass=True,
            )
        ],
        frame_coverage=[
            FrameCoverage(
                frame_id="supply_side",
                frame_name="Supply-side dynamics",
                sources_assigned=4,
                coverage_percent=85.0,
            )
        ],
        contradictions=[
            ContradictionRecord(
                contradiction_id="c1",
                section_id="summary",
                claim_a="Starts rose 3.4%.",
                claim_b="Starts fell 0.2%.",
                evidence_a=["ev_001"],
                evidence_b=["ev_002"],
                resolution="noted_both",
            )
        ],
        cost_usd=0.42,
        generator_model="deepseek-v4-flash",
        verifier_model="gemma-4-31b-it",
        family_segregation_passed=True,
    )
    serialized = contract.model_dump_json()
    assert "contract_version" in serialized
    assert contract.contract_version == "1.0"


def test_verifier_verdict_uses_pass_alias():
    pytest.importorskip("pydantic")
    from polaris_v6.schemas.verifier_verdict import VerifierVerdict

    verdict = VerifierVerdict.model_validate(
        {
            "run_id": "r1",
            "section_id": "summary",
            "sentence_index": 0,
            "verifier_role": "local",
            "pass": True,
        }
    )
    assert verdict.pass_ is True
