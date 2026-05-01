"""Tests for F12 side-by-side compare (Phase 3 Task 3.2 substrate)."""

from __future__ import annotations

import pytest

from polaris_v6.compare.differ import compare_reports
from polaris_v6.schemas.evidence_contract import (
    EvidenceContract,
    FrameCoverage,
    SourceSpan,
)


def _bundle(
    run_id: str,
    *,
    template: str = "clinical",
    question: str = "Initial question text exceeds the minimum",
    evidence_ids: list[str] | None = None,
    frame_ids: list[str] | None = None,
    status: str = "success",
    family_pass: bool = True,
    contradictions: list = None,
) -> EvidenceContract:
    return EvidenceContract(
        contract_version="1.0",
        run_id=run_id,
        template=template,
        question=question,
        queued_at="2026-05-01T10:00:00Z",
        finished_at="2026-05-01T10:08:00Z",
        pipeline_status=status,
        evidence_pool=[
            SourceSpan(
                evidence_id=eid,
                source_url="https://example.gc.ca",
                source_tier="T1",
                span_start=0,
                span_end=10,
                span_text="lorem.....",
            )
            for eid in (evidence_ids or [])
        ],
        verified_sentences=[],
        frame_coverage=[
            FrameCoverage(
                frame_id=fid,
                frame_name=fid,
                sources_assigned=1,
                coverage_percent=100.0,
            )
            for fid in (frame_ids or [])
        ],
        contradictions=contradictions or [],
        cost_usd=0.42,
        generator_model="deepseek-v4-flash",
        verifier_model="gemma-4-31b-it",
        family_segregation_passed=family_pass,
    )


def test_same_run_id_raises():
    a = _bundle("r1")
    with pytest.raises(ValueError):
        compare_reports(a, a)


def test_evidence_overlap_calculation():
    a = _bundle("r1", evidence_ids=["ev_a", "ev_b", "ev_c"])
    b = _bundle("r2", evidence_ids=["ev_b", "ev_c", "ev_d"])
    cmp = compare_reports(a, b)
    assert cmp.shared_evidence_ids == ["ev_b", "ev_c"]
    assert cmp.only_left_evidence_ids == ["ev_a"]
    assert cmp.only_right_evidence_ids == ["ev_d"]
    assert cmp.shared_evidence_pct == pytest.approx(0.5)


def test_disjoint_evidence_pools():
    a = _bundle("r1", evidence_ids=["ev_a"])
    b = _bundle("r2", evidence_ids=["ev_b"])
    cmp = compare_reports(a, b)
    assert cmp.shared_evidence_ids == []
    assert cmp.shared_evidence_pct == 0.0


def test_template_and_question_flags():
    a = _bundle("r1", template="clinical", question="A question that is long enough")
    b = _bundle("r2", template="trade", question="A different question altogether")
    cmp = compare_reports(a, b)
    assert cmp.same_template is False
    assert cmp.same_question is False


def test_frame_overlap():
    a = _bundle("r1", frame_ids=["efficacy", "safety"])
    b = _bundle("r2", frame_ids=["safety", "cost"])
    cmp = compare_reports(a, b)
    assert cmp.frame_coverage_overlap == ["safety"]
    assert cmp.only_left_frames == ["efficacy"]
    assert cmp.only_right_frames == ["cost"]


def test_pipeline_status_match():
    a = _bundle("r1", status="success")
    b = _bundle("r2", status="abort_no_verified_sections")
    cmp = compare_reports(a, b)
    assert cmp.pipeline_status_match is False


def test_family_segregation_both_pass_only_when_both_true():
    a = _bundle("r1", family_pass=True)
    b = _bundle("r2", family_pass=False)
    cmp = compare_reports(a, b)
    assert cmp.family_segregation_both_pass is False
