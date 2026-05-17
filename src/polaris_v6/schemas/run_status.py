"""Run-status response schema.

I-arch-001a (2026-05-12): split lifecycle (operational) from pipeline_status
(pipeline-A manifest verdict). Old `status` retained as computed alias for
tests/v6/ backcompat — populated from lifecycle_status.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

LifecycleStatus = Literal[
    "queued",
    "in_progress",
    "completed",
    "cancelled",
    "failed",
]

PipelineStatus = Literal[
    "success",
    "partial_outline_fallback",
    "partial_qwen_advisory",  # legacy alias (I-modref-004 #530) — historical manifests
    "partial_evaluator_advisory",
    "partial_thin_corpus",
    "partial_incomplete_corpus",
    "partial_rule_check_warnings",
    "abort_scope_rejected",
    "abort_corpus_inadequate",
    "abort_corpus_approval_denied",
    "abort_no_verified_sections",
    "abort_no_sources",
    "abort_evaluator_critical",
    "error_unexpected",
]

# Backcompat alias used by older code/tests (tests/v6/ asserts body['status']
# and record.status). Computed from lifecycle_status by the model.
RunStatus = LifecycleStatus


class RunStatusResponse(BaseModel):
    run_id: str = Field(..., description="Server-assigned UUID hex.")
    lifecycle_status: LifecycleStatus = Field(
        ...,
        description="Operational lifecycle: queued → in_progress → completed|failed|cancelled.",
    )
    pipeline_status: PipelineStatus | None = Field(
        default=None,
        description="Pipeline-A manifest verdict. NULL until run reaches a terminal pipeline state.",
    )
    template: str
    question: str
    queued_at: str = Field(..., description="ISO8601 UTC.")
    started_at: str | None = None
    finished_at: str | None = None
    result_json: str | None = None
    error_json: str | None = None
    # I-arch-001a new optional fields for UUID/slug/artifact_dir mapping.
    query_slug: str | None = None
    manifest_run_id: str | None = None
    artifact_dir: str | None = None
    cost_usd: float | None = None
    decision_id: str | None = None

    @computed_field  # serialized in JSON and readable as attr
    @property
    def status(self) -> LifecycleStatus:
        """Deprecated alias for lifecycle_status (kept for tests/v6/ backcompat).

        New code should use lifecycle_status. This computed field will be
        removed once tests/v6/ migrate (post-Carney-demo cleanup).
        """
        return self.lifecycle_status
