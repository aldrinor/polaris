"""Verifier verdict event schema — streamed via SSE during a run."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DropReason = Literal[
    "evidence_id_not_in_pool",
    "span_oob",
    "numeric_mismatch",
    "content_word_overlap_lt_2",
    "numeric_consistency_violation",
    "frame_imbalance",
    "contradiction_unresolved",
]


class VerifierVerdict(BaseModel):
    """A single verifier verdict for one generated sentence."""

    run_id: str
    section_id: str
    sentence_index: int = Field(..., ge=0)
    verifier_role: Literal["local", "global"]
    pass_: bool = Field(..., alias="pass")
    drop_reason: DropReason | None = None
