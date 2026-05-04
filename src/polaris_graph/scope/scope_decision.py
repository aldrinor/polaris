"""Scope decision schema + assembly.

Per slice 001 architecture proposal §"Data shapes". Defines the canonical
Pydantic types that flow through the front half of the BPEI spine:

    NormalizedQuestion (intake)
        ↓
    ScopeClass + AmbiguityAxes (classifier + detector — later PRs)
        ↓
    ScopeDecision (assembled here)

The schemas exactly match the golden test bundle's expected_scope_decision
shape (polaris-controls/golden/slice_001/test_*.json) so CI can deep-equal.

Pure-types module: no I/O, no network, no LLM calls. Validation only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Type literals
# ---------------------------------------------------------------------------

PicoAxis = Literal["population", "intervention", "outcome"]
"""The three PICO axes used by slice 001's ambiguity detector. Comparator
is intentionally excluded — it's a slice-2+ retrieval concern."""

ScopeClassValue = Literal[
    "clinical_efficacy",
    "clinical_safety",
    "clinical_diagnosis",
    "clinical_prognosis",
    "out_of_scope",
    "uncertain",
]
"""Coarse-grained classification of a question's scope. Slice 001 emits
one of these per question; downstream slices may refine or extend."""

ScopeStatus = Literal[
    "in_scope",
    "out_of_scope",
    "ambiguous_needs_clarification",
    "refused",
]
"""Final disposition surfaced to the UI. Discriminated-union shape forces
explicit handling of all four cases (rather than booleans + flags). The
golden test suite asserts exactly one of these as expected_scope_decision.status."""


# ---------------------------------------------------------------------------
# Component schemas
# ---------------------------------------------------------------------------

class ScopeClass(BaseModel):
    """Output of the classifier layer."""

    value: ScopeClassValue = Field(description="Coarse-grained scope class")
    confidence: float = Field(
        description="Classifier confidence in [0.0, 1.0]; regex hit = 1.0",
        ge=0.0, le=1.0,
    )
    provenance: Literal["regex", "llm_fallback"] = Field(
        description="Which classifier layer produced this verdict"
    )
    matched_pattern: str | None = Field(
        default=None,
        description="For regex hits, the pattern name. Null for LLM fallback.",
    )


class AmbiguityAxis(BaseModel):
    """One PICO axis's ambiguity assessment."""

    axis: PicoAxis = Field(description="Which PICO axis")
    plausible_interpretations: list[str] = Field(
        description="Distinct interpretations the question could plausibly mean"
    )
    needs_clarification: bool = Field(
        description="True iff len(plausible_interpretations) > 1"
    )

    @field_validator("plausible_interpretations")
    @classmethod
    def _validate_interpretations_nonempty(cls, v: list[str]) -> list[str]:
        # Empty list is invalid — even a clear axis has 1 interpretation
        if not v:
            raise ValueError("plausible_interpretations must have at least 1 entry")
        # Cap at 5 to keep the modal UI reasonable per architecture proposal
        if len(v) > 5:
            raise ValueError(
                f"plausible_interpretations capped at 5; got {len(v)}"
            )
        return v


class AmbiguityAxes(BaseModel):
    """Per-PICO ambiguity. Slice 001 uses three axes (P/I/O); Comparator
    is a slice-2+ retrieval concern."""

    population: AmbiguityAxis
    intervention: AmbiguityAxis
    outcome: AmbiguityAxis
    is_ambiguous: bool = Field(
        description="True iff any axis has needs_clarification=True"
    )

    @field_validator("population", "intervention", "outcome")
    @classmethod
    def _validate_axis_matches_field(cls, v: AmbiguityAxis, info) -> AmbiguityAxis:
        if v.axis != info.field_name:
            raise ValueError(
                f"AmbiguityAxes.{info.field_name} must have axis='{info.field_name}', got '{v.axis}'"
            )
        return v


# ---------------------------------------------------------------------------
# Top-level decision
# ---------------------------------------------------------------------------

class ScopeDecision(BaseModel):
    """Final assembled output of slice 001's front-half pipeline.

    Shape matches polaris-controls/golden/slice_001/test_*.json
    expected_scope_decision exactly so CI can deep-equal compare.
    """

    status: ScopeStatus = Field(description="Final disposition for UI")
    scope_class: ScopeClassValue | None = Field(
        default=None,
        description="None when status == 'out_of_scope' or 'refused'",
    )
    ambiguity_axes: list[AmbiguityAxis] = Field(
        default_factory=list,
        description="Ordered P/I/O axes; empty when out_of_scope/refused",
    )
    clarifications_needed: list[str] = Field(
        default_factory=list,
        description="Human-readable strings shown in the AmbiguityModal",
    )
    provenance: dict[str, str] = Field(
        default_factory=dict,
        description="Layer-trace dict: classifier_layer, ambiguity_detector_layer, etc.",
    )
    decision_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique ID for this decision; used in logging/audit-bundle",
    )
    decided_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp at decision time",
    )
    latency_ms: int = Field(
        default=0,
        ge=0,
        description="Wall-clock time intake → decision in milliseconds",
    )


# ---------------------------------------------------------------------------
# Assembly helper
# ---------------------------------------------------------------------------

def assemble_scope_decision(
    scope_class: ScopeClass | None,
    ambiguity: AmbiguityAxes | None,
    *,
    refused: bool = False,
    refusal_reason: str | None = None,
    latency_ms: int = 0,
) -> ScopeDecision:
    """Combine classifier output + ambiguity output into final decision.

    Logic (per architecture proposal):
        - If refused=True → status='refused', no class, no axes
        - If scope_class.value == 'out_of_scope' → status='out_of_scope'
        - Elif ambiguity.is_ambiguous → status='ambiguous_needs_clarification'
        - Else → status='in_scope'
    """
    if refused:
        return ScopeDecision(
            status="refused",
            scope_class=None,
            ambiguity_axes=[],
            clarifications_needed=[],
            provenance={"refusal_reason": refusal_reason or "instruction_override_attempt"},
            latency_ms=latency_ms,
        )

    if scope_class is None:
        # Defensive — caller should always supply scope_class except in refused path
        raise ValueError("scope_class is required when not refused")

    if scope_class.value == "out_of_scope":
        return ScopeDecision(
            status="out_of_scope",
            scope_class="out_of_scope",
            ambiguity_axes=[],
            clarifications_needed=[],
            provenance={
                "classifier_layer": scope_class.provenance,
                "out_of_scope_reason": "no_clinical_pico_pattern_matched",
            },
            latency_ms=latency_ms,
        )

    if ambiguity is None:
        raise ValueError("ambiguity is required when scope_class is in-scope")

    axes = [ambiguity.population, ambiguity.intervention, ambiguity.outcome]
    clarifications = [
        f"Which {ax.axis}: {', '.join(ax.plausible_interpretations)}?"
        for ax in axes if ax.needs_clarification
    ]

    status: ScopeStatus = (
        "ambiguous_needs_clarification"
        if ambiguity.is_ambiguous
        else "in_scope"
    )

    return ScopeDecision(
        status=status,
        scope_class=scope_class.value,
        ambiguity_axes=axes,
        clarifications_needed=clarifications,
        provenance={
            "classifier_layer": scope_class.provenance,
            "ambiguity_detector_layer": "pico_axes_v1",
        },
        latency_ms=latency_ms,
    )
