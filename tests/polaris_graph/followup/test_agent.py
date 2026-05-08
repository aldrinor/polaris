"""Tests for FollowUpAgent (I-f11-001)."""

from __future__ import annotations

import pytest

from polaris_graph.followup.agent import (
    ComposedQuery,
    FollowUpAgent,
    ParentRunContext,
)


def _ctx(
    *,
    parent_run_id: str = "run-parent-1",
    template: str = "clinical",
    parent_question: str = "Tirzepatide vs semaglutide cardiovascular outcomes?",
    known_evidence_ids: list[str] | None = None,
    parent_summary: str | None = "Parent summary text.",
) -> ParentRunContext:
    return ParentRunContext(
        parent_run_id=parent_run_id,
        template=template,
        parent_question=parent_question,
        known_evidence_ids=known_evidence_ids or [],
        parent_summary=parent_summary,
    )


def test_compose_preserves_parent_template():
    agent = FollowUpAgent()
    composed = agent.compose(_ctx(template="trade"), "What about CETA?")
    assert composed.inherited_template == "trade"


def test_compose_preserves_parent_run_id():
    agent = FollowUpAgent()
    composed = agent.compose(_ctx(parent_run_id="run-x"), "Any updates?")
    assert composed.parent_run_id == "run-x"


def test_compose_inherits_known_evidence_ids_deduped():
    agent = FollowUpAgent()
    composed = agent.compose(
        _ctx(known_evidence_ids=["A", "B", "A", "C", "B"]), "details please"
    )
    assert composed.inherited_evidence_ids == ["A", "B", "C"]


def test_compose_returns_fresh_list_not_aliased():
    agent = FollowUpAgent()
    parent = _ctx(known_evidence_ids=["A", "B"])
    composed = agent.compose(parent, "more")
    assert composed.inherited_evidence_ids is not parent.known_evidence_ids


def test_compose_effective_question_format():
    agent = FollowUpAgent()
    composed = agent.compose(
        _ctx(parent_question="What is BPEI?"), "Why does it matter?"
    )
    assert "What is BPEI?" in composed.effective_question
    assert "Why does it matter?" in composed.effective_question
    assert composed.effective_question.startswith("Follow-up to '")


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_compose_rejects_blank_follow_up(blank: str):
    agent = FollowUpAgent()
    with pytest.raises(ValueError, match="non-blank"):
        agent.compose(_ctx(), blank)


def test_compose_handles_no_parent_summary():
    agent = FollowUpAgent()
    composed = agent.compose(_ctx(parent_summary=None), "more")
    assert isinstance(composed, ComposedQuery)
    assert composed.effective_question.endswith("more")
