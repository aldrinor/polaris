"""M-59 (2026-04-23): V30 slot-completion validator (Layer 4b).

Replaces V29 M-44 soft injection. Codex plan review #2 required
validator to consume structured payloads, not prose heuristics.

Given:
  - ReportContract (authoritative per-entity min_fields)
  - ContractOutline (per-slot structure from M-57)
  - SlotFillPayloads keyed by entity_id (from M-58)
  - rendered prose per slot (from M-58 render_slot_prose)

Emit:
  - ValidationReport with per-slot + per-entity verdicts
  - aggregate all_passed() gate for build decisions

## Checks per entity

1. Payload exists (M-58 produced a fill).
2. For non-gap entities:
   a. payload.completion_count() >= entity.min_fields_for_completion
   b. rendered prose contains [entity_id] citation
3. For gap entities:
   a. rendered prose contains M-60 gap-language marker
   b. rendered prose contains [entity_id] citation

## Slot-level verdict

A slot PASSes iff ALL its entities pass. Partial slots fail at the
entity that misses the threshold — each failing entity produces
its own EntityValidation record so M-60 manifest can report
granular coverage.

## Entity-type-agnostic (Codex rev #7)

No branching on entity_type. Works for pivotal_trial, mechanism
primary, regulatory, statute, dft_primary — any contract entity
with a `min_fields_for_completion` threshold.

## Pure function

No LLM, no network, no wall-clock. Deterministic output given
same inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..nodes.contract_outline import ContractOutline
from ..nodes.report_contract import ReportContract, RequiredEntity
from .slot_fill import GAP_PROSE_MARKER, SlotFillPayload


class ValidationVerdict(str, Enum):
    """Per-entity outcome. Slot-level verdict is an aggregation."""

    PASS = "pass"
    FAIL_MISSING_PAYLOAD = "fail_missing_payload"
    FAIL_UNBOUND_CITATION = "fail_unbound_citation"
    FAIL_MIN_FIELDS = "fail_min_fields"
    FAIL_GAP_NO_LANGUAGE = "fail_gap_no_language"
    FAIL_PAYLOAD_MISMATCH = "fail_payload_mismatch"


@dataclass(frozen=True)
class EntityValidation:
    """Verdict for one required entity within a slot."""

    slot_id: str
    entity_id: str
    is_gap: bool
    required_min_fields: int
    observed_completion_count: int
    bound_ev_id_present_in_prose: bool
    verdict: ValidationVerdict
    reason: str


@dataclass(frozen=True)
class SlotAggregateVerdict:
    """Slot-level verdict: aggregated from per-entity verdicts."""

    slot_id: str
    entity_verdicts: tuple[EntityValidation, ...]
    overall: ValidationVerdict
    reason: str


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate M-59 report. The build gate consumes
    `.all_passed()`; the M-60 manifest consumes per-slot and per-
    entity records for structured gap rendering."""

    entity_validations: tuple[EntityValidation, ...]
    slot_verdicts: tuple[SlotAggregateVerdict, ...]

    def all_passed(self) -> bool:
        return all(
            e.verdict == ValidationVerdict.PASS
            for e in self.entity_validations
        )

    def failed_entities(self) -> tuple[EntityValidation, ...]:
        return tuple(
            e for e in self.entity_validations
            if e.verdict != ValidationVerdict.PASS
        )

    def failed_slots(self) -> tuple[SlotAggregateVerdict, ...]:
        return tuple(
            s for s in self.slot_verdicts
            if s.overall != ValidationVerdict.PASS
        )

    def by_verdict(self) -> dict[ValidationVerdict, int]:
        out: dict[ValidationVerdict, int] = {}
        for e in self.entity_validations:
            out[e.verdict] = out.get(e.verdict, 0) + 1
        return out


# Codex M-59 audit Nit fix: import the gap marker from slot_fill
# (single source of truth) instead of duplicating the English
# phrase here. If M-60 later overrides the template, it must
# update slot_fill.GAP_PROSE_MARKER and M-59 picks up the change.
_GAP_MARKER = GAP_PROSE_MARKER


def validate_slot_completion(
    outline: ContractOutline,
    contract: ReportContract,
    payloads_by_entity_id: dict[str, SlotFillPayload],
    rendered_prose_by_slot_id: dict[str, str],
) -> ValidationReport:
    """M-59 public entrypoint.

    Args:
        outline: M-57 ContractOutline (authoritative slot set +
            ordering).
        contract: M-54 ReportContract (per-entity min_fields source
            of truth).
        payloads_by_entity_id: map of entity_id -> SlotFillPayload
            from M-58. Absence → FAIL_MISSING_PAYLOAD.
        rendered_prose_by_slot_id: map of slot_id -> rendered prose
            from M-58. Used for citation + gap-marker check. If a
            slot_id is missing, that's effectively "empty prose"
            and will surface as FAIL_UNBOUND_CITATION /
            FAIL_GAP_NO_LANGUAGE depending on gap status.

    Returns:
        ValidationReport with per-entity + slot-aggregate verdicts.
    """
    entities_by_id = contract.entities_by_id()
    entity_validations: list[EntityValidation] = []
    slot_verdicts: list[SlotAggregateVerdict] = []

    for section in outline.sections:
        for slot_plan in section.slots:
            slot_prose = rendered_prose_by_slot_id.get(
                slot_plan.slot_id, ""
            )
            per_entity: list[EntityValidation] = []
            for entity_id in slot_plan.entity_ids:
                entity = entities_by_id.get(entity_id)
                payload = payloads_by_entity_id.get(entity_id)
                per_entity.append(_validate_one_entity(
                    slot_id=slot_plan.slot_id,
                    entity_id=entity_id,
                    entity=entity,
                    payload=payload,
                    slot_prose=slot_prose,
                ))

            entity_validations.extend(per_entity)
            slot_verdicts.append(
                _aggregate_slot_verdict(slot_plan.slot_id, tuple(per_entity))
            )

    return ValidationReport(
        entity_validations=tuple(entity_validations),
        slot_verdicts=tuple(slot_verdicts),
    )


def _validate_one_entity(
    slot_id: str,
    entity_id: str,
    entity: RequiredEntity | None,
    payload: SlotFillPayload | None,
    slot_prose: str,
) -> EntityValidation:
    # Entity not found in contract — defensive. Outline should only
    # reference contract entities, but guard explicitly.
    if entity is None:
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=False,
            required_min_fields=0,
            observed_completion_count=0,
            bound_ev_id_present_in_prose=False,
            verdict=ValidationVerdict.FAIL_PAYLOAD_MISMATCH,
            reason=(
                f"entity_id={entity_id!r} referenced by outline "
                f"but not present in contract.entities_by_id()"
            ),
        )

    required_min = entity.min_fields_for_completion

    if payload is None:
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=False,
            required_min_fields=required_min,
            observed_completion_count=0,
            bound_ev_id_present_in_prose=False,
            verdict=ValidationVerdict.FAIL_MISSING_PAYLOAD,
            reason=(
                f"no SlotFillPayload produced for entity_id="
                f"{entity_id!r} — M-58 never ran or failed silently"
            ),
        )

    # Payload slot_id sanity
    if payload.slot_id != slot_id:
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=False,
            required_min_fields=required_min,
            observed_completion_count=payload.completion_count(),
            bound_ev_id_present_in_prose=False,
            verdict=ValidationVerdict.FAIL_PAYLOAD_MISMATCH,
            reason=(
                f"payload.slot_id={payload.slot_id!r} does not "
                f"match expected slot_id={slot_id!r} — pipeline "
                f"crossed wires"
            ),
        )
    if payload.entity_id != entity_id:
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=False,
            required_min_fields=required_min,
            observed_completion_count=payload.completion_count(),
            bound_ev_id_present_in_prose=False,
            verdict=ValidationVerdict.FAIL_PAYLOAD_MISMATCH,
            reason=(
                f"payload.entity_id={payload.entity_id!r} does "
                f"not match expected entity_id={entity_id!r}"
            ),
        )

    ev_cited = f"[{entity_id}]" in slot_prose
    observed = payload.completion_count()

    # Gap entity path — only FRAME_GAP_UNRECOVERABLE counts as
    # gap. HUMAN_CURATED is NOT a gap (content exists, curator-
    # supplied), and neither are ABSTRACT_ONLY / OPEN_ACCESS /
    # METADATA_ONLY.
    if payload.provenance_class == "frame_gap_unrecoverable":
        if _GAP_MARKER not in slot_prose:
            return EntityValidation(
                slot_id=slot_id,
                entity_id=entity_id,
                is_gap=True,
                required_min_fields=0,
                observed_completion_count=0,
                bound_ev_id_present_in_prose=ev_cited,
                verdict=ValidationVerdict.FAIL_GAP_NO_LANGUAGE,
                reason=(
                    f"gap entity {entity_id!r} prose lacks M-60 "
                    f"gap marker {_GAP_MARKER!r}"
                ),
            )
        if not ev_cited:
            return EntityValidation(
                slot_id=slot_id,
                entity_id=entity_id,
                is_gap=True,
                required_min_fields=0,
                observed_completion_count=0,
                bound_ev_id_present_in_prose=False,
                verdict=ValidationVerdict.FAIL_UNBOUND_CITATION,
                reason=(
                    f"gap entity {entity_id!r} prose has gap "
                    f"language but no [{entity_id}] citation"
                ),
            )
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=True,
            required_min_fields=0,
            observed_completion_count=0,
            bound_ev_id_present_in_prose=True,
            verdict=ValidationVerdict.PASS,
            reason=(
                f"gap entity — M-60 gap language + [{entity_id}] "
                f"citation present"
            ),
        )

    # Non-gap path
    if not ev_cited:
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=False,
            required_min_fields=required_min,
            observed_completion_count=observed,
            bound_ev_id_present_in_prose=False,
            verdict=ValidationVerdict.FAIL_UNBOUND_CITATION,
            reason=(
                f"entity {entity_id!r} rendered prose is missing "
                f"[{entity_id}] citation"
            ),
        )
    if observed < required_min:
        return EntityValidation(
            slot_id=slot_id,
            entity_id=entity_id,
            is_gap=False,
            required_min_fields=required_min,
            observed_completion_count=observed,
            bound_ev_id_present_in_prose=True,
            verdict=ValidationVerdict.FAIL_MIN_FIELDS,
            reason=(
                f"entity {entity_id!r} filled {observed} of required "
                f"{required_min} min_fields_for_completion"
            ),
        )

    return EntityValidation(
        slot_id=slot_id,
        entity_id=entity_id,
        is_gap=False,
        required_min_fields=required_min,
        observed_completion_count=observed,
        bound_ev_id_present_in_prose=True,
        verdict=ValidationVerdict.PASS,
        reason=(
            f"entity {entity_id!r} extracted {observed} of "
            f"{required_min} required min_fields with bound citation"
        ),
    )


def _aggregate_slot_verdict(
    slot_id: str, per_entity: tuple[EntityValidation, ...],
) -> SlotAggregateVerdict:
    """Slot passes iff ALL entities pass. Otherwise the slot takes
    the verdict of the first failing entity (deterministic; fits
    M-60 manifest rendering which shows the first problem)."""
    if not per_entity:
        return SlotAggregateVerdict(
            slot_id=slot_id,
            entity_verdicts=per_entity,
            overall=ValidationVerdict.FAIL_MISSING_PAYLOAD,
            reason=f"slot {slot_id!r} has no entity validations",
        )
    first_fail = next(
        (e for e in per_entity if e.verdict != ValidationVerdict.PASS),
        None,
    )
    if first_fail is None:
        return SlotAggregateVerdict(
            slot_id=slot_id,
            entity_verdicts=per_entity,
            overall=ValidationVerdict.PASS,
            reason=f"all {len(per_entity)} entity(ies) passed",
        )
    return SlotAggregateVerdict(
        slot_id=slot_id,
        entity_verdicts=per_entity,
        overall=first_fail.verdict,
        reason=(
            f"slot failed on entity {first_fail.entity_id!r}: "
            f"{first_fail.reason}"
        ),
    )
