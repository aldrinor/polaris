"""VerifiedReport schema for slice 003 (generator + strict-verify).

Per `.codex/slices/slice_003/architecture_proposal.md` §"verified_report.py".

Pure-types module. No I/O, no LLM, no network. Slice 003's
process_generation() consumes an EvidencePool (slice 002 output) and
produces a VerifiedReport, which slice 004 will export as an audit
bundle.

Lives in `polaris_graph.generator2` (note the `2`) to keep separation
from heritage `polaris_graph.generator` (multi_section, live_deepseek)
which serves the legacy honest-rebuild pipeline. Coexistence by design
per PLAN.md §4 Heritage Import.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Type literals
# ---------------------------------------------------------------------------

SectionStatus = Literal["verified", "regenerated", "dropped"]
"""Per-section outcome from strict_verify:

- "verified": original generation passed >=verifier_pass_threshold of
  sentences strict-verified
- "regenerated": original failed; regeneration attempt passed
- "dropped": both attempts failed; section excluded from final report
"""

PipelineVerdict = Literal["success", "abort_no_verified_sections"]
"""Top-level verdict per CLAUDE.md §9.1 invariant 4."""

AssertionSurface = Literal[
    "prose",
    "table",
    "summary_bullet",
    "limitation",
    "caption",
    "heading",
]
"""Render-surface kind of a verified assertion (I-f5-009).

Per Carney plan §F: every assertion-bearing surface in a verified report
must be gated-and-clickable through the Inspector OR explicitly marked
ungated. Today's generator emits only "prose"; future Issues populate
the other 5 surfaces as the generator learns to label table cells,
summary bullets, etc."""

DropReason = Literal[
    "invalid_token",       # token doesn't reference a known source_id
    "span_out_of_range",   # span_start > span_end or > len(full_text)
    "numeric_mismatch",    # decimal in sentence not present in cited span
    "overlap_too_low",     # < min_content_overlap shared content words
    "no_provenance_token", # sentence has no [#ev:...:start-end] tokens
]


# ---------------------------------------------------------------------------
# VerifiedSentence — atomic verified unit
# ---------------------------------------------------------------------------

class VerifiedSentence(BaseModel):
    """A single sentence emitted by the generator after strict-verify.

    Sentences that fail strict_verify are still represented here with
    `verifier_pass=False` and a `drop_reason`, so the audit bundle can
    surface "what got proposed and dropped" alongside "what shipped."
    """

    section_id: str = Field(min_length=1)
    sentence_text: str = Field(min_length=1)
    provenance_tokens: list[str] = Field(
        default_factory=list,
        description="Token strings of form '[#ev:<source_id>:<start>-<end>]'",
    )
    verifier_pass: bool
    drop_reason: DropReason | None = None
    evaluator_agrees: bool | None = Field(
        default=None,
        description=(
            "Two-family evaluator agreement per CLAUDE.md §9.1 invariant 1. "
            "True = evaluator confirms generator claim; False = evaluator "
            "disagrees; None = pending (no evaluator pass yet). At rule-based "
            "stage this mirrors verifier_pass; future Issue plugs in the "
            "real two-family LLM judge to populate this independently."
        ),
    )
    assertion_surface: AssertionSurface = Field(
        default="prose",
        description=(
            "Render-surface kind per I-f5-009. Default 'prose' preserves "
            "back-compat with all existing fixtures. Non-prose values are "
            "populated by future generator wiring (table cells, summary "
            "bullets, limitations, captions, headings); the Inspector gates "
            "all six surfaces equally."
        ),
    )
    contradiction: "ContradictionSignal | None" = Field(
        default=None,
        description=(
            "Optional contradiction signal (I-f8-001). When present, "
            "≥2 sources cited for this sentence disagree on the claim. "
            "Default None preserves back-compat. Future Issue (F8-002+) "
            "wires real detection into the generator."
        ),
    )
    is_synthesis_claim: bool = Field(
        default=False,
        description=(
            "True iff sentence is a synthesis claim (e.g., a discussion "
            "paragraph summarizing across sources without quoting any one). "
            "Synthesis claims have no provenance_tokens by definition; "
            "non-synthesis kept sentences MUST have ≥1 provenance token. "
            "Today's generator defaults to False; future Issue may wire the "
            "prompt template to label synthesis sentences explicitly."
        ),
    )

    @model_validator(mode="after")
    def _drop_reason_consistency(self) -> "VerifiedSentence":
        if self.verifier_pass is False and self.drop_reason is None:
            raise ValueError(
                "drop_reason is required when verifier_pass=False"
            )
        if self.verifier_pass is True and self.drop_reason is not None:
            raise ValueError(
                "drop_reason must be None when verifier_pass=True"
            )
        return self

    @model_validator(mode="after")
    def _evaluator_agreement_consistency(self) -> "VerifiedSentence":
        if self.verifier_pass is False and self.evaluator_agrees is True:
            raise ValueError(
                "evaluator_agrees=True is forbidden when verifier_pass=False "
                "(rule-based dropped the sentence; evaluator cannot pass it "
                "without contradicting strict-verify)"
            )
        return self

    @model_validator(mode="after")
    def _synthesis_claim_consistency(self) -> "VerifiedSentence":
        if self.is_synthesis_claim and self.verifier_pass is False:
            raise ValueError(
                "is_synthesis_claim=True requires verifier_pass=True "
                "(synthesis claims either ship or are dropped before reaching "
                "this record)"
            )
        if self.is_synthesis_claim and len(self.provenance_tokens) > 0:
            raise ValueError(
                "is_synthesis_claim=True requires provenance_tokens=[] "
                "(synthesis claims have no specific provenance — that's the "
                "definition)"
            )
        if (
            not self.is_synthesis_claim
            and self.verifier_pass is True
            and len(self.provenance_tokens) == 0
        ):
            raise ValueError(
                "kept non-synthesis sentence requires ≥1 provenance token; "
                "set is_synthesis_claim=True for prose without specific "
                "provenance"
            )
        return self


# ---------------------------------------------------------------------------
# FrameCoverage (I-f7-001)
# ---------------------------------------------------------------------------

class ContradictionSignal(BaseModel):
    """Inline contradiction annotation per sentence (I-f8-001).

    Indicates ≥2 cited sources disagree on the claim in the sentence.
    Future Issue (F8-002+) populates this from real conflict detection;
    today the field is the surface, not the producer."""

    disagreeing_source_count: int = Field(ge=2, le=20)
    summary: str = Field(min_length=1, max_length=500)


GapReason = Literal[
    "paywalled",
    "no_oa",
    "source_tier_ineligible",
    "language_unavailable",
    "retracted_only",
    "jurisdiction_outside",
    "not_indexed",
    "embargoed",
    "other",
]
"""Frozen taxonomy of frame-gap reasons (I-f7-002).

Replaces the free-text reason from I-f7-001. Forces consistent UI
labels and analytics aggregation. `other` is the escape hatch — paired
with `reason_detail` when it's used."""


class FrameGap(BaseModel):
    """A single uncovered entity in a frame coverage report."""

    entity_name: str = Field(min_length=1, max_length=200)
    reason: GapReason
    reason_detail: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional free-text supplement to the enum reason "
            "(I-f7-002). Renders as 'Label: detail' in the panel."
        ),
    )


class FrameCoverage(BaseModel):
    """Top-of-report frame coverage summary (I-f7-001).

    Surfaces "X of N entities covered" with explicit gap reasons. Consumed
    by the FrameCoveragePanel above the verified report. Optional on
    VerifiedReport; older payloads without coverage render no panel."""

    covered_entity_count: int = Field(ge=0)
    total_entity_count: int = Field(ge=0)
    gaps: list[FrameGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_consistency(self) -> "FrameCoverage":
        if self.covered_entity_count > self.total_entity_count:
            raise ValueError(
                "covered_entity_count cannot exceed total_entity_count"
            )
        if (
            self.covered_entity_count + len(self.gaps)
            != self.total_entity_count
        ):
            raise ValueError(
                "covered_entity_count + len(gaps) must equal total_entity_count"
            )
        return self


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class Section(BaseModel):
    """A report section (e.g. 'Population', 'Outcomes').

    `verified_sentences` includes both passed AND dropped sentences for
    audit completeness; UI filters by `verifier_pass` when rendering the
    user-facing report. `section_verify_pass_rate` is over all attempted
    sentences (not just kept ones).
    """

    section_id: str = Field(min_length=1)
    section_title: str = Field(min_length=1, max_length=200)
    verified_sentences: list[VerifiedSentence] = Field(default_factory=list)
    section_verify_pass_rate: float = Field(ge=0.0, le=1.0)
    section_status: SectionStatus

    def kept_sentences(self) -> list[VerifiedSentence]:
        """Filter to sentences that passed strict_verify."""
        return [s for s in self.verified_sentences if s.verifier_pass]


# ---------------------------------------------------------------------------
# VerifiedReport
# ---------------------------------------------------------------------------

class VerifiedReport(BaseModel):
    """The slice 003 output. Bound to a slice-002 pool via pool_id +
    a slice-001 decision via decision_id. Same pool can produce different
    reports across runs (LLM nondeterminism); report_id distinguishes them.
    """

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pool_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    sections: list[Section] = Field(default_factory=list)
    overall_verify_pass_rate: float = Field(ge=0.0, le=1.0)
    pipeline_verdict: PipelineVerdict
    generator_model: str = Field(min_length=1, max_length=200)
    evaluator_model: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Two-family evaluator identifier per CLAUDE.md §9.1 invariant 1. "
            "Rule-based stage value: 'strict_verify_v1'. When a real LLM "
            "judge wires in (separate Issue), this becomes the OpenRouter "
            "model id from a different training family than generator_model."
        ),
    )
    family_segregation_passed: bool = Field(
        default=True,
        description=(
            "True iff generator and evaluator are confirmed to be from "
            "different training lineages (rule-based always True; future "
            "two-family LLM judge invokes "
            "openrouter_client.check_family_segregation)."
        ),
    )
    verifier_pass_threshold: float = Field(ge=0.0, le=1.0)
    started_at_utc: datetime
    finished_at_utc: datetime
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    frame_coverage: FrameCoverage | None = Field(
        default=None,
        description=(
            "Optional top-of-report frame coverage summary (I-f7-001). "
            "When present, the Inspector renders a panel above-the-fold "
            "showing 'X of N entities covered' + each gap with reason. "
            "Default None preserves back-compat with older payloads."
        ),
    )

    @field_validator("finished_at_utc")
    @classmethod
    def _finished_after_started(cls, v: datetime, info) -> datetime:
        started = info.data.get("started_at_utc")
        if started is not None and v < started:
            raise ValueError(
                "finished_at_utc must be >= started_at_utc"
            )
        return v

    @model_validator(mode="after")
    def _verdict_consistency(self) -> "VerifiedReport":
        """If verdict=success, at least one section must be verified or
        regenerated. If verdict=abort_no_verified_sections, every section
        (if any) must be 'dropped' or sections may be empty."""
        if self.pipeline_verdict == "success":
            kept = [
                s for s in self.sections if s.section_status != "dropped"
            ]
            if not kept:
                raise ValueError(
                    "pipeline_verdict='success' requires at least one "
                    "non-dropped section"
                )
        else:  # abort_no_verified_sections
            for section in self.sections:
                if section.section_status != "dropped":
                    raise ValueError(
                        "pipeline_verdict='abort_no_verified_sections' "
                        "requires all sections (if any) to be dropped"
                    )
        return self

    def kept_sections(self) -> list[Section]:
        """Filter to non-dropped sections."""
        return [s for s in self.sections if s.section_status != "dropped"]


# ---------------------------------------------------------------------------
# GenerationError (parallel to slice 001 IntakeError + slice 002 RetrievalError)
# ---------------------------------------------------------------------------

class GenerationError(BaseModel):
    """Returned when generation cannot run (e.g. inadequate input pool)."""

    error: bool = True
    code: str  # 'inadequate_pool' | 'completion_backend_unavailable' | 'malformed_output'
    message: str
    pool_id: str | None = None
    decision_id: str | None = None
