"""M-55 (2026-04-23): V30 frame compiler (query → CompiledFrame).

V30 Report Contract Architecture Layer 2a. Codex V30 plan pass-1
CONDITIONAL-no-blockers; M-55 was root_cause_approved_with_revision
(Codex revision #1/#7: "compiler tests must prove arbitrary entity
types and slot types compile without code changes").

## Role in the architecture

M-54 provides the static YAML-shape validator. M-55 is the
compilation stage: given `(research_question, template, slug)` it
emits a `CompiledFrame` that carries:

- The resolved `ReportContract` (from M-54 loader).
- Per-entity `EvidenceBinding` — how to retrieve and bind evidence
  for each required entity (DOI / PMID / url_pattern / anchor
  selected in priority order).
- Compilation warnings (e.g. schema-version forward-compat notice).
- The research_question text that drove compilation.
- A deterministic rendering order (by section, ordering, entity id).

M-56 (deterministic DOI/PMID/Unpaywall retriever) consumes
`CompiledFrame.evidence_bindings`. M-57 (outline instantiation)
consumes `CompiledFrame.contract.rendering_slots`. M-58 (slot-bound
generation) consumes both bindings and slots.

## Codex review revisions woven in

- **#7 (M-62 generalization)**: compiler is entity-type-agnostic.
  `statute`, `dft_primary`, `court_decision` all compile without
  code changes. Only two universal contracts enforced:
    1. Entity must have at least one identifier (doi/pmid/url_pattern/anchor).
    2. Schema-version unknowns become warnings, not errors.
- **#1/#7**: no per-type hardcoding of required_fields vocabulary.
  The compiler propagates whatever the template declares.

## Non-determinism guard (Codex plan review note)

Same input → same output. The compiler does not call networks,
does not use wall-clock time, does not depend on dict iteration
order. Ordering is sorted explicitly.

## Descoped at M-55

**Domain-inheritance / contract composition** (V30 plan §M-55 test
coverage "domain-inheritance works"): not implemented. Rationale:
V30 ships exactly one slug (`clinical_tirzepatide_t2dm`). There is
no second slug yet that would benefit from `extends:` composition,
and implementing a template-inheritance resolver before the second
concrete use-case would be speculative abstraction.

When a second slug lands (e.g. `clinical_tirzepatide_hfpef` sharing
most entities with T2DM but overriding SURPASS-6), inheritance
resolution can be added here with the concrete requirements known.
Until then, per-slug contracts remain self-contained — the M-62
non-clinical generalization guard will exercise a fresh slug, not
an inherited one.

This descope supersedes the M-54 report_contract.py docstring's
prospective "belongs in M-55" note.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .report_contract import (
    ContractSchemaError,
    ReportContract,
    RequiredEntity,
    get_known_schema_versions,
    load_report_contract_for_slug,
)


class FrameCompilerError(ValueError):
    """Raised when a contract is structurally valid (passes M-54)
    but cannot be compiled into a frame (e.g. entity has no
    identifier). Separate from ContractSchemaError to let callers
    distinguish YAML-shape failures from compilation-stage failures."""

    def __init__(self, *, entity_id: str | None, reason: str) -> None:
        loc = f"entity_id={entity_id!r}" if entity_id else "compiler"
        super().__init__(f"frame compiler error at {loc}: {reason}")
        self.entity_id = entity_id
        self.reason = reason


@dataclass(frozen=True)
class EvidenceBinding:
    """Per-entity compiled binding: how retrieval (M-56) should
    resolve the entity, and how the slot-fill stage (M-58) should
    account for it.

    `primary_identifier` is the best locator per priority order
    (doi > pmid > url_pattern > anchor). `secondary_identifiers`
    carries the remainder, so M-56 can fall back deterministically
    without re-consulting the contract.
    """

    entity_id: str
    entity_type: str
    primary_identifier: str
    secondary_identifiers: tuple[str, ...]
    rendering_slot: str
    required_fields: tuple[str, ...]
    min_fields_for_completion: int


@dataclass(frozen=True)
class CompiledFrame:
    """Output of M-55 frame compiler.

    Carries the resolved contract plus compilation-time data needed
    by M-56 / M-57 / M-58. Pure value object: no mutation, no I/O.
    """

    slug: str
    schema_version: str
    research_question: str
    contract: ReportContract
    evidence_bindings: tuple[EvidenceBinding, ...]
    ordered_entity_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    def bindings_by_entity_id(self) -> dict[str, EvidenceBinding]:
        return {b.entity_id: b for b in self.evidence_bindings}

    def bindings_by_slot(self) -> dict[str, list[EvidenceBinding]]:
        out: dict[str, list[EvidenceBinding]] = {}
        for b in self.evidence_bindings:
            out.setdefault(b.rendering_slot, []).append(b)
        return out


# ─────────────────────────────────────────────────────────────────────
# Identifier priority order.
# Same priority used by M-56 retriever fallback chain so compiler
# and retriever agree on which locator is "primary".
# ─────────────────────────────────────────────────────────────────────
_IDENTIFIER_PRIORITY: tuple[str, ...] = ("doi", "pmid", "url_pattern", "anchor")


def compile_frame(
    research_question: str,
    template: dict[str, Any] | None,
    slug: str,
) -> CompiledFrame | None:
    """M-55 public accessor: compile a per-query frame for one
    research-question slug.

    Args:
        research_question: The raw user question text. Pass-through;
            retained in CompiledFrame for downstream prompt grounding.
        template: Loaded scope template dict (yaml.safe_load output).
        slug: Research-question slug (e.g. 'clinical_tirzepatide_t2dm').

    Returns:
        CompiledFrame when the template has a contract for this slug.
        None when no contract exists (backwards-compat with V28/V29
        slugs that have not yet been migrated to V30 contracts).

    Raises:
        ContractSchemaError: propagated from M-54 loader on YAML
            shape malformation.
        FrameCompilerError: raised at compile stage when a structurally
            valid contract entity has no identifier (no doi, pmid,
            url_pattern, or anchor).

    Determinism: same `(research_question, template, slug)` inputs
    always produce the same CompiledFrame (no I/O, no wall-clock,
    explicit sort on all iteration).
    """
    if not isinstance(research_question, str):
        raise FrameCompilerError(
            entity_id=None,
            reason=(
                f"research_question must be str, got "
                f"{type(research_question).__name__}"
            ),
        )

    contract = load_report_contract_for_slug(template, slug)
    if contract is None:
        return None

    warnings: list[str] = []

    # ── Schema-version forward-compat check ──────────────────────
    # M-54 accepts unknown schema_version at loader level; M-55 is
    # where the warning surfaces so downstream consumers can decide
    # whether to proceed or abort.
    if contract.schema_version not in get_known_schema_versions():
        warnings.append(
            f"schema_version {contract.schema_version!r} unknown to "
            f"runtime; known versions: "
            f"{sorted(get_known_schema_versions())}. "
            f"Compiler will proceed — downstream consumers should "
            f"treat field semantics as best-effort."
        )

    # ── Deterministic entity ordering ────────────────────────────
    ordered = _ordered_entities(contract)

    # ── Compile bindings (entity-type-agnostic per Codex rev #7) ─
    bindings: list[EvidenceBinding] = []
    for e in ordered:
        bindings.append(_compile_binding(e))

    return CompiledFrame(
        slug=contract.slug,
        schema_version=contract.schema_version,
        research_question=research_question,
        contract=contract,
        evidence_bindings=tuple(bindings),
        ordered_entity_ids=tuple(e.id for e in ordered),
        warnings=tuple(warnings),
    )


def _ordered_entities(contract: ReportContract) -> list[RequiredEntity]:
    """Deterministic rendering order: (section, slot.ordering,
    entity.id). Section names compare as strings; ties within a
    section break by slot.ordering; ties within a slot break by
    entity id. All three are stable attributes of the contract.
    """
    slot_by_id = contract.slots_by_id()

    def sort_key(e: RequiredEntity) -> tuple[str, int, str]:
        slot = slot_by_id[e.rendering_slot]
        return (slot.section, slot.ordering, e.id)

    return sorted(contract.required_entities, key=sort_key)


def _compile_binding(entity: RequiredEntity) -> EvidenceBinding:
    """Entity-type-AGNOSTIC binding compilation (Codex rev #7).

    Identifier priority (stable across all entity types):
      1. DOI  — most universal stable identifier
      2. PMID — stable for medical literature
      3. url_pattern — for regulatory / web-hosted sources
      4. anchor — for unpublished or not-yet-assigned-DOI trials

    At least one identifier must resolve. No identifier → raise
    FrameCompilerError (M-54 permits missing all identifiers at
    shape level because some edge cases may declare identifier
    inline in required_fields; M-55 is where "must be retrievable"
    becomes enforced).
    """
    candidates: list[str] = []
    if entity.doi:
        candidates.append(f"doi:{entity.doi}")
    if entity.pmid is not None and entity.pmid != "" and entity.pmid != 0:
        # Accept int or str PMID; reject 0/empty as non-identifier.
        candidates.append(f"pmid:{entity.pmid}")
    if entity.url_pattern:
        candidates.append(f"url:{entity.url_pattern}")
    if entity.anchor:
        candidates.append(f"anchor:{entity.anchor}")

    if not candidates:
        raise FrameCompilerError(
            entity_id=entity.id,
            reason=(
                "entity has no identifier (no doi, pmid, "
                "url_pattern, or anchor). M-56 retriever cannot "
                "resolve this entity. Add at least one identifier "
                "to the contract YAML."
            ),
        )

    return EvidenceBinding(
        entity_id=entity.id,
        entity_type=entity.type,
        primary_identifier=candidates[0],
        secondary_identifiers=tuple(candidates[1:]),
        rendering_slot=entity.rendering_slot,
        required_fields=entity.required_fields,
        min_fields_for_completion=entity.min_fields_for_completion,
    )


def get_identifier_priority_order() -> tuple[str, ...]:
    """Expose identifier priority for M-56 retriever to consult.
    Returns (doi, pmid, url_pattern, anchor) — the order compiler
    uses for primary_identifier selection."""
    return _IDENTIFIER_PRIORITY
