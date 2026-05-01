"""Pin schema — durable snapshot of a run for replay + drift detection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunPin(BaseModel):
    """A complete snapshot of a run's inputs + sealed outputs.

    Pins are append-only; once written, they are not mutated. Replays
    produce a new pin and a `PinDiff` between original and replay.
    """

    pin_id: str
    workspace_id: str
    run_id: str
    template: str
    question: str
    document_ids: list[str] = Field(default_factory=list)
    pinned_at: str
    generator_model: str
    verifier_model: str
    generator_seed: int | None = Field(
        default=None,
        description="If the generator supports seeded sampling; recorded for reproducibility.",
    )
    sealed_evidence_pool_ids: list[str] = Field(
        ...,
        description="The exact evidence_ids in the pool when this pin was taken.",
    )
    sealed_verified_sentence_count: int = Field(..., ge=0)
    sealed_pipeline_status: str
    sealed_cost_usd: float = Field(..., ge=0.0)
    notes: str | None = None


class PinDiffField(BaseModel):
    """One field-level change between an original pin and a replay."""

    field: str
    original: str
    replay: str
    severity: Literal["info", "warn", "regression"]


class PinDiff(BaseModel):
    """Diff between two pins — usually original vs replay."""

    original_pin_id: str
    replay_pin_id: str
    fields_changed: list[PinDiffField]
    evidence_pool_added: list[str] = Field(default_factory=list)
    evidence_pool_dropped: list[str] = Field(default_factory=list)
    verified_sentence_count_delta: int = 0
    pipeline_status_changed: bool = False
    is_regression: bool = Field(
        ...,
        description="True iff any fields_changed has severity='regression' or "
        "pipeline_status changed from success → abort_*.",
    )
