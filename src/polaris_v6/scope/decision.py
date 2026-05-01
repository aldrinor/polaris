"""ScopeDecision — what the scope gate decided about a question.

Phase 0/1 stub: deterministic rule-based scoper. Phase 1 swap to the
existing scope_eligibility_classifier (LLM-augmented) once the cluster
is live and OpenRouter is wired.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScopeVerdict = Literal["accepted", "needs_clarification", "rejected"]
RefusalReason = Literal[
    "clinical_treatment_recommendation",
    "individual_legal_advice",
    "individual_financial_advice",
    "personal_political_endorsement",
    "out_of_template_scope",
]


class ScopeDecision(BaseModel):
    verdict: ScopeVerdict
    template: str
    question: str
    rationale: str = Field(..., min_length=8)
    refusals: list[RefusalReason] = Field(
        default_factory=list,
        description=(
            "What the gate will refuse if asked downstream. Surfaced in "
            "F1 panel so the user knows the boundary before any cost."
        ),
    )
    intended_source_tiers: list[Literal["T1", "T2", "T3"]] = Field(
        ...,
        description="Which tiers of source the run will draw from.",
    )


_REFUSAL_PATTERNS: dict[str, RefusalReason] = {
    " should i take ": "clinical_treatment_recommendation",
    " is this drug right for me": "clinical_treatment_recommendation",
    " can i sue ": "individual_legal_advice",
    " should i invest ": "individual_financial_advice",
    " who should i vote ": "personal_political_endorsement",
}


def classify_scope(template: str, question: str) -> ScopeDecision:
    """Phase 0/1 deterministic scoper — to be replaced by LLM classifier."""
    normalized = f" {question.strip().lower()} "

    refusals: list[RefusalReason] = []
    for pattern, reason in _REFUSAL_PATTERNS.items():
        if pattern in normalized:
            refusals.append(reason)

    if refusals:
        return ScopeDecision(
            verdict="rejected",
            template=template,
            question=question,
            rationale=(
                "Question reads as a personal recommendation request; "
                "POLARIS is a research-synthesis system, not a "
                "personal-advice service."
            ),
            refusals=refusals,
            intended_source_tiers=[],
        )

    if len(question.strip()) < 12:
        return ScopeDecision(
            verdict="needs_clarification",
            template=template,
            question=question,
            rationale=(
                "Question is too short to fix scope. Please add the "
                "specific timeframe, jurisdiction, or sub-topic you want."
            ),
            refusals=[],
            intended_source_tiers=["T1", "T2"],
        )

    return ScopeDecision(
        verdict="accepted",
        template=template,
        question=question,
        rationale=(
            f"Question fits the {template} template. POLARIS will draw "
            "from primary-source government and academic data."
        ),
        refusals=[],
        intended_source_tiers=["T1", "T2", "T3"],
    )
