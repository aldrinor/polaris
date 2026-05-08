"""Evidence Contract inheritance for follow-up runs (I-f11-003).

Pure deterministic functions. NO retrieval / network calls — the parent
run's accepted source pool is reused via deep copy, satisfying the
acceptance "no re-retrieval of parent" guarantee at the module level
(verified by tests).
"""

from __future__ import annotations

from polaris_graph.followup.agent import (
    ComposedQuery,
    FollowUpAgent,
    ParentRunContext,
)
from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan


def inherit_evidence_pool(parent_contract: EvidenceContract) -> list[SourceSpan]:
    """Return a fresh list of the parent run's accepted source spans."""
    return list(parent_contract.evidence_pool)


def compose_with_inheritance(
    agent: FollowUpAgent,
    parent_contract: EvidenceContract,
    follow_up: str,
) -> tuple[ComposedQuery, list[SourceSpan]]:
    """Compose a follow-up question that inherits the parent's evidence pool.

    Returns the ComposedQuery (with evidence_id list inherited from the
    parent's evidence_pool) and a fresh copy of the parent's source spans
    suitable for direct passthrough to the merger.
    """
    parent = ParentRunContext(
        parent_run_id=parent_contract.run_id,
        template=parent_contract.template,
        parent_question=parent_contract.question,
        known_evidence_ids=[s.evidence_id for s in parent_contract.evidence_pool],
        parent_summary=None,
    )
    composed = agent.compose(parent, follow_up)
    inherited = inherit_evidence_pool(parent_contract)
    return composed, inherited
