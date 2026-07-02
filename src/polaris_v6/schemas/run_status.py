"""Run-status response schema.

I-arch-001a (2026-05-12): split lifecycle (operational) from pipeline_status
(pipeline-A manifest verdict). Old `status` retained as computed alias for
tests/v6/ backcompat — populated from lifecycle_status.

I-rdy-011 (2026-05-16): `cancel_requested` surfaced so the UI can show a
cancel as in-flight in <5s, before an in-progress run reaches the next
pipeline stage boundary and transitions to terminal `cancelled`.
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
    # I-perm-001 (#1195): always-release RELEASED-with-disclosure terminals. The v6 actor loads
    # manifest.status into pipeline_status, so these MUST mirror UNIFIED_STATUS_VALUES or
    # RunStatusResponse 500s on a released_* run.
    "released_with_disclosed_gaps",
    "released_insufficient_safety_evidence",
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
    # I-ready-016 (#1086): sync the stale PipelineStatus mirror with UNIFIED_STATUS_VALUES — these
    # are real terminal manifest statuses the actor can load into pipeline_status, so omitting them
    # would 500 RunStatusResponse Pydantic validation on a real run.
    "partial_saturation",            # I-meta-005 Phase 4 (#988)
    "abort_budget_exceeded",         # I-meta-008 (#1015)
    "abort_verifier_degraded",       # I-ready-002 (#1071)
    "abort_discovery_degraded",      # FL-05 (#1124): force-enabled discovery feature did not fire (run-health backstop) — must mirror UNIFIED_STATUS_VALUES or the actor 500s RunStatusResponse on an FL-05 abort
    "abort_safety_refused",          # I-ready-007 (#1072): input harm-refusal before retrieval
    "abort_four_role_release_held",  # 4-role D8 held release
    "abort_role_transport_exhausted",  # I-beatboth-006 (#1283) Fix C.3: a force-closed role transport reached the D8 seam with PG_ROLE_TRANSPORT_DEGRADE OFF -> disclosed hard halt. The v6 actor loads manifest.status into pipeline_status, so omitting this 500s RunStatusResponse on a real run. Mirrors runner.UNIFIED_STATUS_VALUES (status-schema-parity gate).
    "abort_report_redaction_failed",  # I-beatboth-fix-000 (#1171): post-gate report.md reconciliation fail-closed — the v6 actor loads manifest.status into pipeline_status, so omitting this would 500 RunStatusResponse on a redaction-failure abort
    "abort_journal_only_contract_conflict",  # I-ready-017 (#1134): journal_only — required contract slot bound to a non-journal entity
    # I-arch-005 B23 (#1257): close the status-schema parity drift — these are real terminal manifest
    # statuses the v6 actor can load into pipeline_status, so omitting them 500s RunStatusResponse
    # Pydantic validation on a real run. Each mirrors runner.UNIFIED_STATUS_VALUES (status-schema-parity gate).
    "abort_excessive_gap",                   # F03 (A3): verified-section-fraction floor abort
    "abort_critical_topic_uncovered",        # F11 (A3): uncovered critical clinical topic hold
    "abort_credibility_coverage_gap",        # I-cred-008b (#1162): credibility-disclosure coverage gap
    "abort_conflict_judge_unavailable",      # I-arch-004 F07 (#1249/#1252): conflict-judge unavailable hold
    "abort_required_entity_ledger_failed",   # I-arch-004 F27 (#1213): RequiredEntityLedger raised under strict gates
    "abort_synthesis_did_not_fire",          # I-deepfix-001 U5 (#1344): synthesis-fires canary — multi-source baskets existed but composition rendered zero multi-cited sentences (span-dump regression); mirrors runner.UNIFIED_STATUS_VALUES (status-schema-parity gate)
    "cancelled",                     # user-cancel terminal (_abort_if_cancelled writes manifest.status)
    "error_unexpected",
    "error_journal_only_leak",       # I-ready-017 (#1134): journal_only fail-closed no-leak backstop
    "error_corpus_population_mismatch",  # I-ready-017 FX-06b (#1121): corpus-approval gate vs adequacy artifact score different populations (total_sources or tier_counts diverge); defensive fail-loud
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
    # I-rdy-011: True once a cancel has been requested. For a queued run the
    # request is applied atomically (lifecycle_status flips to 'cancelled');
    # for an in_progress run this stays True while lifecycle_status is still
    # 'in_progress', until the worker observes it at a stage boundary.
    cancel_requested: bool = Field(
        default=False,
        description="True iff cancellation has been requested for this run.",
    )

    @computed_field  # serialized in JSON and readable as attr
    @property
    def status(self) -> LifecycleStatus:
        """Deprecated alias for lifecycle_status (kept for tests/v6/ backcompat).

        New code should use lifecycle_status. This computed field will be
        removed once tests/v6/ migrate (post-Carney-demo cleanup).
        """
        return self.lifecycle_status
