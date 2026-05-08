"""I-f11-005 — multi-turn follow-up tests."""

from __future__ import annotations

from polaris_graph.followup.agent import ComposedQuery, FollowUpAgent
from polaris_graph.followup.multi_turn import TurnResult, run_multi_turn
from polaris_graph.followup.refusal import RefusalDecision
from polaris_v6.adapters.evidence_pool_merger import merge_evidence_pool
from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan


def _span(eid: str, text: str) -> SourceSpan:
    return SourceSpan(
        evidence_id=eid, source_url=f"https://x.test/{eid}",
        source_tier="T1", span_start=0, span_end=len(text), span_text=text,
    )


def _contract(spans: list[SourceSpan] | None = None) -> EvidenceContract:
    return EvidenceContract(
        run_id="run_p", template="clinical_summary",
        question="Drug X efficacy?",
        queued_at="2026-05-08T00:00:00Z", finished_at="2026-05-08T00:00:30Z",
        pipeline_status="success",
        evidence_pool=spans if spans is not None else [_span("ev_a", "alpha"), _span("ev_b", "beta")],
        verified_sentences=[], frame_coverage=[], contradictions=[],
        cost_usd=0.0, generator_model="g", verifier_model="v",
        family_segregation_passed=True,
    )


def test_five_sequential_follow_ups_all_grounded() -> None:
    contract = _contract()
    follow_ups = [
        "Tell me about the clinical methodology",
        "What about secondary clinical endpoints?",
        "Summarize the clinical adverse events",
        "What clinical biomarkers were measured?",
        "How does the clinical dose schedule work?",
    ]
    results = run_multi_turn(FollowUpAgent(), contract, follow_ups)
    assert len(results) == 5
    for i, r in enumerate(results):
        assert r.turn_index == i
        assert isinstance(r.composed, ComposedQuery)
        assert r.refusal is None
        assert r.composed.parent_run_id == "run_p"
        assert r.composed.inherited_template == "clinical_summary"
        assert r.composed.inherited_evidence_ids == ["ev_a", "ev_b"]
        assert len(r.inherited_spans) == 2


def test_mix_in_scope_and_refusal() -> None:
    contract = _contract()
    follow_ups = [
        "Tell me about the clinical methodology",
        "Why is the sky blue?",
        "What about clinical safety?",
        "Random topic about cars",
        "Summarize clinical findings",
    ]
    results = run_multi_turn(FollowUpAgent(), contract, follow_ups)
    accepted = [r for r in results if r.composed is not None]
    refused = [r for r in results if r.refusal is not None]
    assert len(accepted) == 3
    assert len(refused) == 2
    for r in refused:
        assert r.refusal is not None and r.refusal.is_refused is True
        assert r.inherited_spans == []


def test_turn_index_preserved() -> None:
    results = run_multi_turn(
        FollowUpAgent(), _contract(),
        ["clinical a", "clinical b", "clinical c"],
    )
    assert [r.turn_index for r in results] == [0, 1, 2]


def test_inherited_spans_pass_through_to_merger_per_turn() -> None:
    parent_spans = [_span("ev_a", "alpha"), _span("ev_b", "beta")]
    results = run_multi_turn(
        FollowUpAgent(), _contract(parent_spans),
        ["clinical findings 1", "clinical findings 2"],
    )
    for r in results:
        assert r.composed is not None
        merged = merge_evidence_pool(
            retrieval_spans=r.inherited_spans, uploaded_chunks=[], memory_summaries=[]
        )
        assert len(merged) == len(parent_spans)
        for parent, out in zip(parent_spans, merged, strict=True):
            assert out.span_text == parent.span_text
            assert out.source_url == parent.source_url


def test_empty_follow_ups_returns_empty() -> None:
    assert run_multi_turn(FollowUpAgent(), _contract(), []) == []
