"""Evidence Contract — Phase 1 Task 1.4 canonical JSON schema.

Per docs/carney_delivery_plan_v6_2.md F15 (audit bundle export with
embedded source spans), every research run emits a single canonical
artifact described by this schema. Phase 1 milestone 1.4 (Evidence
Contract Gate) ships:

1. This schema (durable contract for run artifact JSON).
2. A golden corpus (5 hand-curated runs that conform to this schema).
3. A sample artifact (one full real run validated against the schema).

Schema is versioned; v1 is what we deliver to Carney's office. Future
versions track via the `contract_version` field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceSpan(BaseModel):
    """A verbatim span lifted from a cited source document."""

    evidence_id: str = Field(..., description="Stable id for this evidence pool member.")
    source_url: str = Field(..., description="Canonical URL to the source.")
    source_tier: Literal["T1", "T2", "T3"] = Field(
        ...,
        description="Source admissibility tier per CLAUDE.md §9 corpus adequacy gate.",
    )
    span_start: int = Field(..., ge=0, description="Inclusive char offset within source body.")
    span_end: int = Field(..., gt=0, description="Exclusive char offset within source body.")
    span_text: str = Field(..., min_length=1, description="Verbatim span text.")


class VerifiedSentence(BaseModel):
    """A generator sentence that passed strict_verify Local + Global."""

    section_id: str
    sentence_text: str
    provenance_tokens: list[str] = Field(
        ...,
        description=(
            "List of [#ev:<evidence_id>:<start>-<end>] tokens per CLAUDE.md "
            "§9.1 invariant 2."
        ),
    )
    verifier_local_pass: bool
    verifier_global_pass: bool
    drop_reason: str | None = Field(
        default=None,
        description=(
            "Null if sentence shipped. Otherwise one of "
            "evidence_id_not_in_pool | span_oob | numeric_mismatch | "
            "content_word_overlap_lt_2 | numeric_consistency_violation | "
            "frame_imbalance | contradiction_unresolved."
        ),
    )


class FrameCoverage(BaseModel):
    """Frame-coverage panel data — F7 above-the-fold UI surface."""

    frame_id: str
    frame_name: str
    sources_assigned: int
    coverage_percent: float = Field(..., ge=0.0, le=100.0)


class ContradictionRecord(BaseModel):
    """A claim-level contradiction surfaced by audit_ir."""

    contradiction_id: str
    section_id: str
    claim_a: str
    claim_b: str
    evidence_a: list[str]
    evidence_b: list[str]
    resolution: Literal["unresolved", "claim_a_preferred", "claim_b_preferred", "noted_both"]


class EvidenceContract(BaseModel):
    """The canonical run artifact JSON, contract version 1."""

    contract_version: Literal["1.0"] = "1.0"
    run_id: str
    template: str
    question: str
    queued_at: str
    finished_at: str
    pipeline_status: str = Field(
        ...,
        description="One of CLAUDE.md §9.3 statuses (success | abort_* | error_*).",
    )
    evidence_pool: list[SourceSpan]
    verified_sentences: list[VerifiedSentence]
    frame_coverage: list[FrameCoverage]
    contradictions: list[ContradictionRecord]
    cost_usd: float = Field(..., ge=0.0)
    generator_model: str
    verifier_model: str
    family_segregation_passed: bool = Field(
        ...,
        description="CLAUDE.md §9.1 invariant 1 cross-check at run time.",
    )
