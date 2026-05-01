"""Tests for F11 report-scoped follow-up agent (Phase 3 Task 3.1 substrate)."""

from __future__ import annotations

from polaris_v6.followup.agent import answer_followup
from polaris_v6.schemas.evidence_contract import (
    EvidenceContract,
    SourceSpan,
)


def _parent_with_pool(spans: list[SourceSpan]) -> EvidenceContract:
    return EvidenceContract(
        contract_version="1.0",
        run_id="run_001",
        template="clinical",
        question="Initial question",
        queued_at="2026-05-01T10:00:00Z",
        finished_at="2026-05-01T10:08:00Z",
        pipeline_status="success",
        evidence_pool=spans,
        verified_sentences=[],
        frame_coverage=[],
        contradictions=[],
        cost_usd=0.42,
        generator_model="deepseek-v4-flash",
        verifier_model="gemma-4-31b-it",
        family_segregation_passed=True,
    )


def _span(eid: str, text: str, start: int = 0) -> SourceSpan:
    return SourceSpan(
        evidence_id=eid,
        source_url="https://example.gc.ca",
        source_tier="T1",
        span_start=start,
        span_end=start + len(text),
        span_text=text,
    )


def test_answer_with_overlap_returns_answered():
    parent = _parent_with_pool(
        [
            _span("ev1", "Semaglutide reduces cardiovascular events by 22% in SELECT"),
            _span("ev2", "Major adverse cardiovascular outcomes data from FDA labelling 2025"),
            _span("ev3", "Unrelated content about housing markets in Q3"),
        ]
    )
    result = answer_followup(
        parent=parent, question="What does the data show on cardiovascular events?"
    )
    assert result.status == "answered"
    assert "ev1" in result.used_evidence_ids or "ev2" in result.used_evidence_ids
    assert any(t.startswith("[#ev:") for t in result.provenance_tokens)


def test_answer_out_of_scope_when_no_overlap():
    parent = _parent_with_pool(
        [_span("ev1", "Cardiovascular outcomes in SELECT trial")]
    )
    result = answer_followup(
        parent=parent, question="Tell me about Renaissance painting techniques"
    )
    assert result.status == "out_of_scope"
    assert result.used_evidence_ids == []


def test_answer_evidence_insufficient_for_no_content_tokens():
    parent = _parent_with_pool([_span("ev1", "Some content")])
    # Question has only short stop-style tokens (filtered by len > 2 rule)
    result = answer_followup(parent=parent, question="?! a b c")
    assert result.status == "evidence_insufficient"


def test_answer_caps_to_top_three_evidence():
    parent = _parent_with_pool(
        [
            _span(f"ev{i}", "Cardiovascular outcomes data analysis", start=i * 100)
            for i in range(10)
        ]
    )
    result = answer_followup(
        parent=parent, question="What does cardiovascular outcomes data show?"
    )
    assert result.status == "answered"
    assert len(result.used_evidence_ids) <= 3


def test_provenance_tokens_match_used_evidence():
    parent = _parent_with_pool(
        [
            _span("ev_alpha", "Cardiovascular event reduction observed in trial"),
            _span("ev_beta", "Cardiovascular adverse events tracked"),
        ]
    )
    result = answer_followup(
        parent=parent, question="What about cardiovascular events?"
    )
    for ev_id in result.used_evidence_ids:
        assert any(ev_id in tok for tok in result.provenance_tokens)
