"""Pin snapshot schema — I-cd-017 (#627).

Per-run synthesized quality snapshot keyed by completed_at ISO date.
Synthesized from `manifest.json` + run_store fields; NO separate
pin-write path in the v6 actor (Option B accepted by Codex
scope-consult 2026-05-20 — full B writes a new actor path; iter-2 P1
clarified manifest top-level uses `status` not `pipeline_status`).

`PinSnapshot` is the contract consumed by `web/lib/pin_replay_client.ts`.
`extra="forbid"` mirrors the BundleManifest v1.0 schema-freeze discipline
landed in I-cd-012.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PinSnapshot(BaseModel):
    """Per-run quality snapshot for pin-replay timeseries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(..., description="Source run_id (multiple runs may share pin_date).")
    pin_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="ISO date of run completion.")
    query: str = Field(..., description="Research question.")
    verdict: str = Field(..., description="success | abort_no_verified_sections (partial_* collapsed to success).")
    section_count_kept: int = Field(..., ge=0)
    section_count_dropped: int = Field(..., ge=0)
    verified_sentence_count: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    retracted_source_ids: list[str] | None = Field(
        default=None,
        description="Not captured today — placeholder for future source-retraction logging.",
    )
