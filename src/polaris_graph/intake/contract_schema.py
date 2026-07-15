"""feat/intake-contract (2026-07-15) — the unified intake contract SCHEMA.

One universal envelope compiled once at query entry (design plan §1). It is
*metadata only*: it records what the prompt asked for; it enforces nothing and
touches no source. Composed from the three EXISTING deterministic extractors as
its non-droppable floor sub-blocks:

    * UserConstraints  (date window / language / journal-only-dormant)
    * ScopeConstraints (source-type / jurisdiction facets + named sources)
    * InstructionSlot  (comparison / enumeration / topic / structure)

plus the champion-missing fields the design plan adds (tone, audience, output
language, required sections, format, length, specific instructions, success
criteria, assumptions, warnings).

Each *explicit* normalized field carries the evidence that admitted it:
``value`` + ``verbatim_span`` + ``origin`` + ``strength`` (+ ``operator`` where
relevant). Empty-means-inert: an all-empty contract is the graceful-degradation
state that behaves byte-identically to a flags-off run.

SAFETY — the ``source_rules`` block is SCAFFOLDED ONLY. It may be populated, but
``source_rules_enforcement_disabled`` is hard-wired True and NOTHING in this repo
wires it to filter/mask the citeable corpus. journal-only stays DORMANT per the
operator veto; activation needs operator sign-off + a full-benchmark A/B. This
module imports no strict_verify / provenance / faithfulness path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Bump on ANY change to the schema shape OR the compiler's admission logic — it is
# part of the on-disk cache key so a loosened gate can never live on in the cache.
SCHEMA_VERSION = "intake-contract-v1"

# Vocabulary (documented, not enforced here).
_ORIGINS = ("user_explicit", "inferred_default", "profile_default", "unspecified")
_STRENGTHS = ("hard", "soft", "default")
_OPERATORS = ("allow_only", "forbid", "require_some", "prefer", "include", "exclude", "")


@dataclass
class ContractField:
    """One normalized explicit directive + the proof that admitted it.

    ``verbatim_span`` is the exact prompt substring that justifies the value; a
    HARD field with no span is a fabrication and the compiler demotes it to soft
    with a loud warning (design plan §2.5, §7.1).
    """

    value: Any = None
    verbatim_span: str = ""
    origin: str = "unspecified"     # one of _ORIGINS
    strength: str = "default"       # one of _STRENGTHS
    operator: str = ""              # one of _OPERATORS

    def is_set(self) -> bool:
        return self.value not in (None, "", [], {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "verbatim_span": self.verbatim_span,
            "origin": self.origin,
            "strength": self.strength,
            "operator": self.operator,
        }


@dataclass
class SourceRule:
    """A requested source-type rule. SCAFFOLD ONLY — never wired to filter.

    ``enforcement_disabled`` is hard-wired True: this record exists so the
    downstream (future, operator-signed-off) firewall has a contract field to
    read, but in this build it is inert disclosure metadata. journal-only stays
    dormant per the operator veto.
    """

    facet_id: str
    operator: str                   # allow_only | forbid | require_some | prefer | include | exclude
    strength: str                   # hard | soft
    verbatim_span: str = ""
    origin: str = "user_explicit"
    enforcement_disabled: bool = True   # ALWAYS True in this build (safety rule 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facet_id": self.facet_id,
            "operator": self.operator,
            "strength": self.strength,
            "verbatim_span": self.verbatim_span,
            "origin": self.origin,
            "enforcement_disabled": self.enforcement_disabled,
        }


@dataclass
class IntakeContract:
    """The unified intake contract (design plan §1). Metadata only."""

    schema_version: str = SCHEMA_VERSION

    # --- non-droppable FLOOR sub-blocks (verbatim from the existing extractors) ---
    user_constraints: dict[str, Any] = field(default_factory=dict)   # UserConstraints.to_dict()
    scope_constraints: dict[str, Any] = field(default_factory=dict)  # ScopeConstraints.to_dict()
    instruction_slots: list[dict[str, Any]] = field(default_factory=list)  # InstructionSlot.to_dict()

    # --- normalized explicit fields (floor-derived, LLM may enrich) ---
    date_window: ContractField = field(default_factory=ContractField)
    language: ContractField = field(default_factory=ContractField)     # source language
    required_sections: list[dict[str, Any]] = field(default_factory=list)  # from instruction_slots

    # --- source rules: SCAFFOLD ONLY, enforcement disabled (safety rule 3) ---
    source_rules: list[SourceRule] = field(default_factory=list)
    source_rules_enforcement_disabled: bool = True   # machine-readable dormancy marker

    # --- champion-missing fields (design plan §1.D/E — absent in champion today) ---
    tone: ContractField = field(default_factory=ContractField)
    audience: ContractField = field(default_factory=ContractField)
    output_language: ContractField = field(default_factory=ContractField)
    format: ContractField = field(default_factory=ContractField)
    length: ContractField = field(default_factory=ContractField)
    specific_instructions: list[dict[str, Any]] = field(default_factory=list)
    success_criteria: list[dict[str, Any]] = field(default_factory=list)

    # --- meta ---
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "floor"           # 'floor' (deterministic only) | 'enriched' (LLM ran)

    def is_empty(self) -> bool:
        """True when no directive was detected — the inert / graceful-degradation
        state that behaves like a flags-off run."""
        return not (
            self.user_constraints
            or self.scope_constraints
            or self.instruction_slots
            or self.date_window.is_set()
            or self.language.is_set()
            or self.required_sections
            or self.source_rules
            or self.tone.is_set()
            or self.audience.is_set()
            or self.output_language.is_set()
            or self.format.is_set()
            or self.length.is_set()
            or self.specific_instructions
            or self.success_criteria
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "user_constraints": dict(self.user_constraints),
            "scope_constraints": dict(self.scope_constraints),
            "instruction_slots": [dict(s) for s in self.instruction_slots],
            "date_window": self.date_window.to_dict(),
            "language": self.language.to_dict(),
            "required_sections": [dict(s) for s in self.required_sections],
            "source_rules": [r.to_dict() for r in self.source_rules],
            "source_rules_enforcement_disabled": self.source_rules_enforcement_disabled,
            "tone": self.tone.to_dict(),
            "audience": self.audience.to_dict(),
            "output_language": self.output_language.to_dict(),
            "format": self.format.to_dict(),
            "length": self.length.to_dict(),
            "specific_instructions": [dict(s) for s in self.specific_instructions],
            "success_criteria": [dict(s) for s in self.success_criteria],
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "source": self.source,
        }
