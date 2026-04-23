"""M-59 tests: V30 slot-completion validator (Layer 4b).

Consumes M-57 ContractOutline + M-54 ReportContract + M-58
SlotFillPayloads + rendered prose. Emits ValidationReport with
per-entity and per-slot verdicts.

All tests pure — no LLM, no network. M-58 payloads and rendered
prose are provided as fixtures.

Covers:
1. All-pass happy path.
2. Missing-payload detection.
3. Unbound-citation detection (prose lacks [ev_id]).
4. Min-fields threshold failure.
5. Gap-slot with M-60 language + citation = PASS.
6. Gap-slot without M-60 language = FAIL_GAP_NO_LANGUAGE.
7. Gap-slot with language but no citation = FAIL_UNBOUND_CITATION.
8. Payload slot_id/entity_id mismatch = FAIL_PAYLOAD_MISMATCH.
9. Slot-level aggregation: multi-entity slot, all-pass → PASS;
   partial-entity-fail → FAIL on first-failing entity.
10. Entity-type-agnostic.
11. Deterministic.
12. Report helpers: all_passed(), failed_entities(), by_verdict().
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.slot_fill import (
    SlotFieldFill,
    SlotFillPayload,
)
from src.polaris_graph.generator.slot_validator import (
    EntityValidation,
    SlotAggregateVerdict,
    ValidationReport,
    ValidationVerdict,
    validate_slot_completion,
)
from src.polaris_graph.nodes.contract_outline import (
    ContractOutline,
    ContractSectionPlan,
    ContractSlotPlan,
)
from src.polaris_graph.nodes.report_contract import (
    ReportContract,
    RenderingSlot,
    RequiredEntity,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture builders
# ─────────────────────────────────────────────────────────────────────
def _entity(
    id: str = "e1",
    type: str = "pivotal_trial",
    required_fields: tuple[str, ...] = ("N", "primary_endpoint"),
    min_fields: int = 1,
    rendering_slot: str = "s1",
) -> RequiredEntity:
    return RequiredEntity(
        id=id,
        type=type,
        required_fields=required_fields,
        min_fields_for_completion=min_fields,
        rendering_slot=rendering_slot,
    )


def _contract(entities: tuple[RequiredEntity, ...]) -> ReportContract:
    # Derive rendering_slots from the entity rendering_slot refs
    slot_ids = sorted({e.rendering_slot for e in entities})
    slots = tuple(
        RenderingSlot(
            id=sid, section="Efficacy",
            subsection_title=f"Subsection {sid}",
            ordering=i + 1, required=True,
        )
        for i, sid in enumerate(slot_ids)
    )
    return ReportContract(
        slug="test_slug",
        schema_version="v30.1",
        required_entities=entities,
        rendering_slots=slots,
        section_order=("Efficacy",),
    )


def _outline(contract: ReportContract) -> ContractOutline:
    """Build a minimal outline directly from contract — mirrors
    what M-57 compose_outline_from_contract would produce for the
    test fixtures. Avoids a full compile_frame + fetch_compiled_frame
    dance in M-59 tests."""
    by_slot: dict[str, list[RequiredEntity]] = {}
    for e in contract.required_entities:
        by_slot.setdefault(e.rendering_slot, []).append(e)

    slots: list[ContractSlotPlan] = []
    for slot in contract.rendering_slots:
        eids = tuple(sorted(
            e.id for e in by_slot.get(slot.id, [])
        ))
        slots.append(ContractSlotPlan(
            slot_id=slot.id,
            section=slot.section,
            subsection_title=slot.subsection_title,
            ordering=slot.ordering,
            entity_ids=eids,
            provenance_classes=tuple(
                "abstract_only" for _ in eids
            ),
            is_gap=False,
            is_partial=False,
        ))

    sec = ContractSectionPlan(
        section="Efficacy",
        section_ordering_index=0,
        slots=tuple(sorted(slots, key=lambda s: s.ordering)),
        focus="test",
    )
    return ContractOutline(
        research_question="q",
        schema_version=contract.schema_version,
        sections=(sec,),
    )


def _fill(
    slot_id: str = "s1",
    entity_id: str = "e1",
    extracted: tuple[str, ...] = ("N", "primary_endpoint"),
    not_extractable: tuple[str, ...] = (),
    provenance: str = "abstract_only",
) -> SlotFillPayload:
    fields = [
        SlotFieldFill(
            field_name=f,
            status="extracted",
            value="verbatim text",
            bound_ev_id=entity_id,
            source_span="verbatim text",
        )
        for f in extracted
    ] + [
        SlotFieldFill(
            field_name=f,
            status="not_extractable",
            value=None,
            bound_ev_id=entity_id,
            source_span=None,
        )
        for f in not_extractable
    ]
    return SlotFillPayload(
        slot_id=slot_id,
        entity_id=entity_id,
        subsection_title=f"Subsection {slot_id}",
        bound_ev_id=entity_id,
        fields=tuple(fields),
        provenance_class=provenance,
    )


def _gap_fill(
    slot_id: str = "s1",
    entity_id: str = "e1",
    required_fields: tuple[str, ...] = ("N", "primary_endpoint"),
) -> SlotFillPayload:
    fields = tuple(
        SlotFieldFill(
            field_name=f,
            status="gap_unrecoverable",
            value=None,
            bound_ev_id=entity_id,
            source_span=None,
        )
        for f in required_fields
    )
    return SlotFillPayload(
        slot_id=slot_id,
        entity_id=entity_id,
        subsection_title=f"Subsection {slot_id}",
        bound_ev_id=entity_id,
        fields=fields,
        provenance_class="frame_gap_unrecoverable",
    )


def _prose(entity_id: str, extra: str = "") -> str:
    """Minimal prose that contains the entity's bound citation."""
    return f"Subsection: some content here. [{entity_id}]{extra}"


def _gap_prose(entity_id: str) -> str:
    return (
        f"Subsection: Primary publication was not retrievable from "
        f"open-access, abstract, or metadata sources. [{entity_id}]"
    )


# ─────────────────────────────────────────────────────────────────────
# (1) All-pass happy path
# ─────────────────────────────────────────────────────────────────────
class TestAllPass:
    def test_single_entity_passes(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": _fill()},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        assert report.all_passed() is True
        assert len(report.entity_validations) == 1
        assert report.entity_validations[0].verdict == ValidationVerdict.PASS

    def test_two_slots_both_pass(self) -> None:
        contract = _contract((
            _entity(id="e1", rendering_slot="s1"),
            _entity(id="e2", rendering_slot="s2"),
        ))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={
                "e1": _fill(slot_id="s1", entity_id="e1"),
                "e2": _fill(slot_id="s2", entity_id="e2"),
            },
            rendered_prose_by_slot_id={
                "s1": _prose("e1"),
                "s2": _prose("e2"),
            },
        )
        assert report.all_passed() is True
        assert len(report.slot_verdicts) == 2


# ─────────────────────────────────────────────────────────────────────
# (2) Missing payload
# ─────────────────────────────────────────────────────────────────────
class TestMissingPayload:
    def test_entity_without_payload_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={},  # no payloads
            rendered_prose_by_slot_id={"s1": "some prose"},
        )
        assert report.all_passed() is False
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_MISSING_PAYLOAD
        assert "M-58 never ran" in v.reason


# ─────────────────────────────────────────────────────────────────────
# (3) Unbound citation
# ─────────────────────────────────────────────────────────────────────
class TestUnboundCitation:
    def test_prose_missing_citation_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        # Prose has content but no [e1] citation
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": _fill()},
            rendered_prose_by_slot_id={"s1": "some prose without tag"},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_UNBOUND_CITATION
        assert v.bound_ev_id_present_in_prose is False

    def test_prose_empty_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": _fill()},
            rendered_prose_by_slot_id={},  # no prose map entry
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_UNBOUND_CITATION


# ─────────────────────────────────────────────────────────────────────
# (4) Min-fields threshold
# ─────────────────────────────────────────────────────────────────────
class TestMinFieldsThreshold:
    def test_completion_below_threshold_fails(self) -> None:
        # min_fields=3 but only 1 extracted
        contract = _contract((
            _entity(
                required_fields=("a", "b", "c"),
                min_fields=3,
            ),
        ))
        outline = _outline(contract)
        fill = _fill(extracted=("a",), not_extractable=("b", "c"))
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": fill},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_MIN_FIELDS
        assert v.observed_completion_count == 1
        assert v.required_min_fields == 3

    def test_at_threshold_passes(self) -> None:
        contract = _contract((
            _entity(
                required_fields=("a", "b", "c"),
                min_fields=2,
            ),
        ))
        outline = _outline(contract)
        fill = _fill(extracted=("a", "b"), not_extractable=("c",))
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": fill},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        assert report.all_passed() is True


# ─────────────────────────────────────────────────────────────────────
# (5-7) Gap-slot handling
# ─────────────────────────────────────────────────────────────────────
class TestGapSlots:
    def test_gap_with_m60_language_and_citation_passes(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": _gap_fill()},
            rendered_prose_by_slot_id={"s1": _gap_prose("e1")},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.PASS
        assert v.is_gap is True

    def test_gap_without_m60_language_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        # Prose is non-empty but lacks the marker
        bad_prose = f"Subsection: data unavailable. [e1]"
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": _gap_fill()},
            rendered_prose_by_slot_id={"s1": bad_prose},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_GAP_NO_LANGUAGE

    def test_gap_with_language_no_citation_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        bad_prose = (
            "Subsection: Primary publication was not retrievable."
        )
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": _gap_fill()},
            rendered_prose_by_slot_id={"s1": bad_prose},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_UNBOUND_CITATION


# ─────────────────────────────────────────────────────────────────────
# (8) Payload mismatch
# ─────────────────────────────────────────────────────────────────────
class TestPayloadMismatch:
    def test_mismatched_slot_id_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        # Payload claims slot_id = 'WRONG' but outline expects 's1'
        bad_fill = _fill(slot_id="WRONG", entity_id="e1")
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": bad_fill},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_PAYLOAD_MISMATCH
        assert "crossed wires" in v.reason

    def test_mismatched_entity_id_fails(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        bad_fill = _fill(slot_id="s1", entity_id="WRONG")
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={"e1": bad_fill},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        v = report.entity_validations[0]
        assert v.verdict == ValidationVerdict.FAIL_PAYLOAD_MISMATCH


# ─────────────────────────────────────────────────────────────────────
# (9) Slot-level aggregation on multi-entity slot
# ─────────────────────────────────────────────────────────────────────
class TestMultiEntitySlot:
    def test_multi_entity_all_pass(self) -> None:
        contract = _contract((
            _entity(id="e1", rendering_slot="s_multi"),
            _entity(id="e2", rendering_slot="s_multi"),
        ))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={
                "e1": _fill(slot_id="s_multi", entity_id="e1"),
                "e2": _fill(slot_id="s_multi", entity_id="e2"),
            },
            rendered_prose_by_slot_id={
                "s_multi": f"[e1] and [e2] both present."
            },
        )
        assert report.all_passed() is True
        assert len(report.slot_verdicts) == 1
        assert report.slot_verdicts[0].overall == ValidationVerdict.PASS
        assert len(report.slot_verdicts[0].entity_verdicts) == 2

    def test_multi_entity_partial_fail(self) -> None:
        contract = _contract((
            _entity(id="e1", rendering_slot="s_multi"),
            _entity(id="e2", rendering_slot="s_multi"),
        ))
        outline = _outline(contract)
        # e2 has no payload
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={
                "e1": _fill(slot_id="s_multi", entity_id="e1"),
            },
            rendered_prose_by_slot_id={
                "s_multi": "[e1] and [e2] both present."
            },
        )
        assert report.all_passed() is False
        slot = report.slot_verdicts[0]
        assert slot.overall == ValidationVerdict.FAIL_MISSING_PAYLOAD
        # First-failing entity's verdict surfaces at slot level
        assert "e2" in slot.reason


# ─────────────────────────────────────────────────────────────────────
# (10) Entity-type-agnostic
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    def test_statute_dft_types_validate(self) -> None:
        contract = _contract((
            _entity(id="stat1", type="statute", rendering_slot="s1"),
            _entity(id="dft1", type="dft_primary", rendering_slot="s2"),
        ))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline,
            contract=contract,
            payloads_by_entity_id={
                "stat1": _fill(slot_id="s1", entity_id="stat1"),
                "dft1":  _fill(slot_id="s2", entity_id="dft1"),
            },
            rendered_prose_by_slot_id={
                "s1": _prose("stat1"),
                "s2": _prose("dft1"),
            },
        )
        assert report.all_passed() is True


# ─────────────────────────────────────────────────────────────────────
# (11) Deterministic
# ─────────────────────────────────────────────────────────────────────
class TestDeterministic:
    def test_same_inputs_yield_same_report(self) -> None:
        contract = _contract((_entity(),))
        outline = _outline(contract)
        r1 = validate_slot_completion(
            outline=outline, contract=contract,
            payloads_by_entity_id={"e1": _fill()},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        r2 = validate_slot_completion(
            outline=outline, contract=contract,
            payloads_by_entity_id={"e1": _fill()},
            rendered_prose_by_slot_id={"s1": _prose("e1")},
        )
        assert r1 == r2


# ─────────────────────────────────────────────────────────────────────
# (12) Report helpers
# ─────────────────────────────────────────────────────────────────────
class TestReportHelpers:
    def test_by_verdict_counts(self) -> None:
        contract = _contract((
            _entity(id="e1", rendering_slot="s1"),
            _entity(id="e2", rendering_slot="s2"),
            _entity(id="e3", rendering_slot="s3"),
        ))
        outline = _outline(contract)
        # e1 passes, e2 fails (no citation), e3 fails (no payload)
        report = validate_slot_completion(
            outline=outline, contract=contract,
            payloads_by_entity_id={
                "e1": _fill(slot_id="s1", entity_id="e1"),
                "e2": _fill(slot_id="s2", entity_id="e2"),
            },
            rendered_prose_by_slot_id={
                "s1": _prose("e1"),
                "s2": "no citation here",
                # s3 prose missing entirely
            },
        )
        counts = report.by_verdict()
        assert counts[ValidationVerdict.PASS] == 1
        assert counts[ValidationVerdict.FAIL_UNBOUND_CITATION] == 1
        assert counts[ValidationVerdict.FAIL_MISSING_PAYLOAD] == 1

    def test_failed_entities_and_slots(self) -> None:
        contract = _contract((
            _entity(id="e1", rendering_slot="s1"),
            _entity(id="e2", rendering_slot="s2"),
        ))
        outline = _outline(contract)
        report = validate_slot_completion(
            outline=outline, contract=contract,
            payloads_by_entity_id={
                "e1": _fill(slot_id="s1", entity_id="e1"),
            },
            rendered_prose_by_slot_id={
                "s1": _prose("e1"),
                "s2": _prose("e2"),
            },
        )
        failed_entities = report.failed_entities()
        assert len(failed_entities) == 1
        assert failed_entities[0].entity_id == "e2"
        failed_slots = report.failed_slots()
        assert len(failed_slots) == 1
        assert failed_slots[0].slot_id == "s2"
