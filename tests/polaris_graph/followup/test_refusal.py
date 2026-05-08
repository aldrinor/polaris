"""I-f11-004 — refusal handling tests."""

from __future__ import annotations

from polaris_graph.followup.agent import (
    ComposedQuery,
    FollowUpAgent,
    ParentRunContext,
)
from polaris_graph.followup.inheritance import compose_with_inheritance_or_refuse
from polaris_graph.followup.refusal import (
    RefusalDecision,
    compose_or_refuse,
    detect_out_of_scope,
)
from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan


def _ctx(template: str = "clinical_summary") -> ParentRunContext:
    return ParentRunContext(
        parent_run_id="run_42", template=template,
        parent_question="What is the efficacy of drug X?",
        known_evidence_ids=["ev_a"], parent_summary=None,
    )


def _contract(template: str = "clinical_summary") -> EvidenceContract:
    return EvidenceContract(
        run_id="run_42", template=template,
        question="What is the efficacy of drug X?",
        queued_at="2026-05-08T00:00:00Z", finished_at="2026-05-08T00:00:30Z",
        pipeline_status="success",
        evidence_pool=[SourceSpan(evidence_id="ev_a", source_url="https://example.test/a",
                                  source_tier="T1", span_start=0, span_end=5, span_text="alpha")],
        verified_sentences=[], frame_coverage=[], contradictions=[],
        cost_usd=0.0, generator_model="g", verifier_model="v",
        family_segregation_passed=True,
    )


def test_refuses_zero_overlap_specific_template() -> None:
    decision = detect_out_of_scope("clinical_summary", "Why is the sky blue?")
    assert decision.is_refused is True
    assert decision.reason is not None
    assert "clinical_summary" in decision.reason
    assert decision.template_keywords == ["clinical", "summary"]
    assert decision.question_overlap == []


def test_accepts_one_keyword_overlap() -> None:
    decision = detect_out_of_scope(
        "clinical_summary", "What about the summary statistics?"
    )
    assert decision.is_refused is False
    assert decision.question_overlap == ["summary"]


def test_general_template_never_refuses() -> None:
    decision = detect_out_of_scope("general", "random topic completely off")
    assert decision.is_refused is False


def test_compose_or_refuse_returns_composed_when_in_scope() -> None:
    result = compose_or_refuse(
        FollowUpAgent(), _ctx(), "Tell me more about the clinical efficacy"
    )
    assert isinstance(result, ComposedQuery)
    assert "clinical efficacy" in result.effective_question


def test_compose_or_refuse_returns_refusal_when_out_of_scope() -> None:
    result = compose_or_refuse(FollowUpAgent(), _ctx(), "Why is the sky blue?")
    assert isinstance(result, RefusalDecision)
    assert result.is_refused is True
    assert result.reason is not None


def test_adversarial_punctuation_and_case() -> None:
    decision = detect_out_of_scope("clinical_summary", "WHAT ABOUT THE SUMMARY?!")
    assert decision.is_refused is False
    assert decision.question_overlap == ["summary"]


def test_compose_with_inheritance_or_refuse_routes_refusal() -> None:
    refused, spans = compose_with_inheritance_or_refuse(
        FollowUpAgent(), _contract(), "Why is the sky blue?"
    )
    assert isinstance(refused, RefusalDecision)
    assert refused.is_refused is True
    assert spans == []

    composed, inherited = compose_with_inheritance_or_refuse(
        FollowUpAgent(), _contract(), "Tell me more about the clinical findings"
    )
    assert isinstance(composed, ComposedQuery)
    assert len(inherited) == 1
    assert inherited[0].evidence_id == "ev_a"
