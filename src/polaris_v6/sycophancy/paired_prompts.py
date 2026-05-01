"""Paired-prompt schema for sycophancy + refusal stress tests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PromptFraming = Literal["neutral", "leading_positive", "leading_negative", "opposite_frame"]


class PairedPrompt(BaseModel):
    """One paired-prompt set targeting a single underlying factual question.

    Per ELEPHANT methodology, the same factual question is reframed in 4
    ways. A non-sycophantic model returns near-identical factual content
    across all framings (with possibly different surface tone).
    """

    paired_id: str = Field(..., description="Stable id for this paired set.")
    underlying_question: str = Field(..., description="The neutral factual question.")
    expected_factual_anchor: str = Field(
        ...,
        description=(
            "A short text anchor that should appear in any responsible "
            "answer regardless of framing (e.g., '3.4% rise per CMHC')."
        ),
    )
    refusal_acceptable: bool = Field(
        default=False,
        description="If True, refusing all 4 framings is acceptable.",
    )
    prompts: dict[PromptFraming, str] = Field(
        ...,
        description="Map of framing → fully-rendered prompt for that framing.",
    )


class CandidateResponse(BaseModel):
    """A model's response to one framing."""

    framing: PromptFraming
    response_text: str
    refused: bool = False


class PairedPromptResult(BaseModel):
    """All four framings' responses for one paired set."""

    paired_id: str
    responses: list[CandidateResponse]
