"""M-57 (2026-04-23): V30 contract-driven outline composer.

V30 Report Contract Architecture Layer 3.

Replaces LLM-emergent outline planning with CONTRACT-DETERMINED
outline structure. Given a CompiledFrame (M-55) and the retrieved
FrameRows (M-56), emit a ContractOutline where:

  - Sections come from `contract.section_order` (explicit; no
    alphabetic-by-label fragility — Codex M-55 audit Medium fix).
  - Subsections come from `contract.rendering_slots`, sorted by
    `slot.ordering` within each section.
  - Each slot's `entity_ids` come from `contract.entities_by_slot()`
    in compiler-deterministic order.
  - Each slot carries its frame rows' provenance_classes so M-58
    prompt assembly + M-60 manifest rendering know at a glance
    whether the slot is gap vs OA vs abstract-only.

## Design principles

1. **Pure function.** No LLM, no network, no wall-clock. Same
   inputs → byte-identical ContractOutline.
2. **Gap-slot preservation.** Slots whose frame rows ALL classify
   as FRAME_GAP_UNRECOVERABLE still appear in the outline with
   `is_gap=True`. M-60 renders explicit gap content; silent
   omission is forbidden (Codex plan review #4).
3. **Entity-type-agnostic.** No per-type branching. Works for
   pivotal_trial + mechanism_primary + regulatory today, and
   for statute / dft_primary / whatever else later without code
   changes (Codex review #7, M-62 generalization proof).
4. **Stable identifiers through the pipeline.** `ContractSlotPlan.entity_ids`
   holds the contract-side entity ids (e.g. `surpass_2_primary`).
   M-58/M-59/M-60 consume these; no reliance on opaque ev_xxx
   rewriting.
5. **Intra-slot ordering inherited, not re-asserted.** Within-slot
   entity order is READ from `CompiledFrame.ordered_entity_ids`
   (M-55), not re-sorted by M-57. If the compiler ordering policy
   evolves (e.g. per-entity priority key), M-57 picks up the new
   order for free. Codex M-57 audit Medium fix.

## What M-57 does NOT do

- Does NOT call the LLM outline planner. Enrichment sections
  (Contradictions / Limitations) stay with the existing
  LLM planner — M-57 covers only contract-slot sections.
- Does NOT touch `multi_section_generator.py`. That integration
  is M-58's responsibility (slot-bound prompts consume this
  outline). Keeping M-57 standalone avoids churn in the 2500-line
  generator module.
- Does NOT fetch content. M-56 did that. M-57 only arranges.

## Relationship to existing `SectionPlan`

`ContractOutline.to_section_plan_dicts()` produces a list of
`{"title", "focus", "ev_ids"}` dicts — the legacy SectionPlan
payload shape — so existing generator code can consume the
flattened view while M-58 consumes the structured view. The
actual `SectionPlan` dataclass lives in
`generator/multi_section_generator.py`; M-57 stays free of
generator imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .frame_compiler import CompiledFrame
from ..retrieval.frame_fetcher import FrameRow, ProvenanceClass


@dataclass(frozen=True)
class ContractSlotPlan:
    """One rendering slot's plan within a section.

    Represents a subsection in the rendered report: header from
    `subsection_title`, content from `entity_ids` resolved against
    FrameRows.
    """

    slot_id: str
    section: str
    subsection_title: str
    ordering: int
    entity_ids: tuple[str, ...]
    # M-56 frame row snapshot per entity, parallel to entity_ids.
    provenance_classes: tuple[str, ...]
    # True iff every frame row for this slot is gap-unrecoverable.
    # M-60 renders explicit gap content for is_gap=True slots.
    is_gap: bool
    # Did M-56 retrieve ANY resolvable content? Used for "partial"
    # reporting when a multi-entity slot has one gap + one fill.
    is_partial: bool


@dataclass(frozen=True)
class ContractSectionPlan:
    """One section, composed of rendering slots in slot.ordering
    order. `focus` is a one-line deterministic summary for the
    section-level prompt header (used as-is in the legacy
    SectionPlan adapter; M-58 uses the structured slots instead).
    """

    section: str
    section_ordering_index: int
    slots: tuple[ContractSlotPlan, ...]
    focus: str


@dataclass(frozen=True)
class ContractOutline:
    """Full contract-driven outline. M-57 output."""

    research_question: str
    schema_version: str
    sections: tuple[ContractSectionPlan, ...]

    def slots_by_id(self) -> dict[str, ContractSlotPlan]:
        out: dict[str, ContractSlotPlan] = {}
        for sec in self.sections:
            for slot in sec.slots:
                out[slot.slot_id] = slot
        return out

    def sections_by_name(self) -> dict[str, ContractSectionPlan]:
        return {s.section: s for s in self.sections}

    def all_entity_ids(self) -> tuple[str, ...]:
        """Flattened entity ids across every slot across every
        section, in contract rendering order."""
        out: list[str] = []
        for sec in self.sections:
            for slot in sec.slots:
                out.extend(slot.entity_ids)
        return tuple(out)

    def gap_slot_ids(self) -> tuple[str, ...]:
        """Slot ids where all frame rows are gap-unrecoverable.
        M-60 manifest consumption."""
        return tuple(
            slot.slot_id
            for sec in self.sections
            for slot in sec.slots
            if slot.is_gap
        )

    def to_section_plan_dicts(self) -> list[dict[str, Any]]:
        """Legacy-compatible flattened view: one dict per section
        in `{"title", "focus", "ev_ids"}` shape. ev_ids are the
        contract entity ids (e.g. `surpass_2_primary`); the
        existing generator pipeline adapts those to its own
        evidence-pool ids as needed."""
        return [
            {
                "title": sec.section,
                "focus": sec.focus,
                "ev_ids": [
                    eid
                    for slot in sec.slots
                    for eid in slot.entity_ids
                ],
            }
            for sec in self.sections
        ]


# ─────────────────────────────────────────────────────────────────────
# Compose
# ─────────────────────────────────────────────────────────────────────
def compose_outline_from_contract(
    compiled_frame: CompiledFrame,
    frame_rows: tuple[FrameRow, ...],
) -> ContractOutline:
    """M-57 public entrypoint.

    Args:
        compiled_frame: output of M-55 compile_frame(...).
        frame_rows: output of M-56 fetch_compiled_frame(...). Must
            be a tuple parallel to `compiled_frame.evidence_bindings`
            (same length, same order) — M-56's documented contract.

    Returns:
        ContractOutline with sections in contract.section_order
        (or alphabetic when section_order is None) and slots in
        slot.ordering within each section.

    Raises:
        ValueError: when `frame_rows` is not parallel to
            `compiled_frame.evidence_bindings`, or a frame row's
            entity_id doesn't match the binding at the same index.
    """
    _validate_frame_rows_parallel(compiled_frame, frame_rows)

    # Build a fast entity_id → FrameRow lookup.
    rows_by_eid: dict[str, FrameRow] = {
        r.entity_id: r for r in frame_rows
    }

    contract = compiled_frame.contract
    section_order = _resolve_section_order(contract)

    # Codex M-57 audit Medium fix: within-slot entity ordering is
    # INHERITED from M-55 compiler, not re-sorted by M-57. The
    # compiler's ordered_entity_ids tuple is the single source of
    # truth for entity rendering order — M-57 only projects that
    # order onto slots.
    compiler_entity_rank = {
        eid: i for i, eid in enumerate(compiled_frame.ordered_entity_ids)
    }

    # Group slots by section
    slots_by_section: dict[str, list[Any]] = {}
    for slot in contract.rendering_slots:
        slots_by_section.setdefault(slot.section, []).append(slot)

    # Compose per-section
    section_plans: list[ContractSectionPlan] = []
    entities_by_slot = contract.entities_by_slot()
    for sec_idx, section_name in enumerate(section_order):
        raw_slots = slots_by_section.get(section_name, [])
        # Sort slots within section by ordering (then id for tiebreak)
        sorted_slots = sorted(raw_slots, key=lambda s: (s.ordering, s.id))

        slot_plans: list[ContractSlotPlan] = []
        for slot in sorted_slots:
            entities = entities_by_slot.get(slot.id, [])
            # Inherit compiler-determined entity order. An entity
            # not present in the compiler ordering (defensive;
            # should not happen on a well-formed CompiledFrame)
            # sorts to the end by id.
            max_rank = len(compiler_entity_rank)
            entities_ordered = sorted(
                entities,
                key=lambda e: (
                    compiler_entity_rank.get(e.id, max_rank),
                    e.id,
                ),
            )
            eids = tuple(e.id for e in entities_ordered)

            provenance_classes: list[str] = []
            gap_count = 0
            for eid in eids:
                row = rows_by_eid.get(eid)
                if row is None:
                    # Defensive: M-56 should have produced a row
                    # for every binding. Treat as gap.
                    provenance_classes.append(
                        ProvenanceClass.FRAME_GAP_UNRECOVERABLE.value
                    )
                    gap_count += 1
                    continue
                provenance_classes.append(row.provenance_class.value)
                if row.is_gap():
                    gap_count += 1

            is_gap = len(eids) > 0 and gap_count == len(eids)
            is_partial = 0 < gap_count < len(eids)

            slot_plans.append(ContractSlotPlan(
                slot_id=slot.id,
                section=section_name,
                subsection_title=slot.subsection_title,
                ordering=slot.ordering,
                entity_ids=eids,
                provenance_classes=tuple(provenance_classes),
                is_gap=is_gap,
                is_partial=is_partial,
            ))

        focus = _compose_section_focus(section_name, slot_plans)
        section_plans.append(ContractSectionPlan(
            section=section_name,
            section_ordering_index=sec_idx,
            slots=tuple(slot_plans),
            focus=focus,
        ))

    return ContractOutline(
        research_question=compiled_frame.research_question,
        schema_version=compiled_frame.schema_version,
        sections=tuple(section_plans),
    )


def _validate_frame_rows_parallel(
    compiled_frame: CompiledFrame,
    frame_rows: tuple[FrameRow, ...],
) -> None:
    bindings = compiled_frame.evidence_bindings
    if len(frame_rows) != len(bindings):
        raise ValueError(
            f"frame_rows length {len(frame_rows)} does not match "
            f"evidence_bindings length {len(bindings)}; M-56 "
            f"fetch_compiled_frame must return rows parallel to "
            f"bindings"
        )
    for i, (b, r) in enumerate(zip(bindings, frame_rows)):
        if b.entity_id != r.entity_id:
            raise ValueError(
                f"frame_rows[{i}].entity_id={r.entity_id!r} does "
                f"not match bindings[{i}].entity_id={b.entity_id!r}; "
                f"M-56 ordering contract violated"
            )


def _resolve_section_order(contract: Any) -> tuple[str, ...]:
    """When contract declares section_order, honor it. Otherwise
    fall back to alphabetic-by-label.

    NOTE: This policy is DUPLICATED in M-55 `_ordered_entities()`
    (src/polaris_graph/nodes/frame_compiler.py). Keep them in sync
    if the contract evolves (e.g. add a per-section priority key).
    A cross-layer integration test covers both behaviors on the
    real clinical.yaml, so drift shows up as test breakage.

    The fallback is quiet here; M-55 already emitted the
    alphabetic-fallback warning at compile time, so M-57 would be
    redundant to re-emit it.
    """
    if contract.section_order is not None:
        return contract.section_order
    sections = sorted({s.section for s in contract.rendering_slots})
    return tuple(sections)


def _compose_section_focus(
    section_name: str, slot_plans: list[ContractSlotPlan],
) -> str:
    """Deterministic one-line focus for section-level prompt. Lists
    subsection titles and flags gaps.

    Format examples:
      - "3 subsections: SURPASS-1, SURPASS-2, SURPASS-3"
      - "2 subsections with 1 gap: Thomas clamp, mechanism TBD"

    Entity-type-agnostic: no special-casing per section name. Works
    for novel sections in a non-clinical slug."""
    n = len(slot_plans)
    if n == 0:
        return f"{section_name}: no contract-bound subsections"

    gap_count = sum(1 for s in slot_plans if s.is_gap)
    partial_count = sum(1 for s in slot_plans if s.is_partial)
    titles = [s.subsection_title for s in slot_plans]

    # Cap title list for one-line readability
    title_list = ", ".join(titles[:6])
    if len(titles) > 6:
        title_list = f"{title_list}, ... (+{len(titles) - 6} more)"

    suffix = ""
    if gap_count:
        suffix += f"; {gap_count} gap"
        if gap_count > 1:
            suffix += "s"
    if partial_count:
        suffix += f"; {partial_count} partial"

    return (
        f"{n} subsection{'s' if n > 1 else ''}: {title_list}{suffix}"
    )
