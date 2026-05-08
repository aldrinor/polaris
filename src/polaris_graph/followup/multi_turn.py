"""Multi-turn follow-up driver (I-f11-005).

Runs N follow-ups against the SAME parent contract. Each turn flows
through `compose_with_inheritance_or_refuse`: out-of-scope → typed
RefusalDecision; in-scope → ComposedQuery + inherited spans. Refusal
does NOT short-circuit; subsequent turns still execute. Chained-context
follow-ups (turn-2 inheriting from turn-1) are post-MVP — call
run_multi_turn again with a new contract to chain.
"""

from __future__ import annotations

from dataclasses import dataclass

from polaris_graph.followup.agent import ComposedQuery, FollowUpAgent
from polaris_graph.followup.inheritance import compose_with_inheritance_or_refuse
from polaris_graph.followup.refusal import RefusalDecision
from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan


@dataclass(frozen=True)
class TurnResult:
    turn_index: int
    follow_up: str
    composed: ComposedQuery | None
    refusal: RefusalDecision | None
    inherited_spans: list[SourceSpan]


def run_multi_turn(
    agent: FollowUpAgent,
    parent_contract: EvidenceContract,
    follow_ups: list[str],
) -> list[TurnResult]:
    results: list[TurnResult] = []
    for i, fu in enumerate(follow_ups):
        decision, spans = compose_with_inheritance_or_refuse(
            agent, parent_contract, fu
        )
        if isinstance(decision, RefusalDecision):
            results.append(
                TurnResult(
                    turn_index=i, follow_up=fu, composed=None,
                    refusal=decision, inherited_spans=spans,
                )
            )
        else:
            results.append(
                TurnResult(
                    turn_index=i, follow_up=fu, composed=decision,
                    refusal=None, inherited_spans=spans,
                )
            )
    return results
