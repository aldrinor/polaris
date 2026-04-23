"""M-57 tests: V30 contract-driven outline composer.

Layer 3 of V30 Report Contract Architecture. Consumes M-55
CompiledFrame + M-56 FrameRows, emits ContractOutline where
section/subsection structure is contract-determined (not
LLM-emergent).

Covers:
1. Well-formed compose: one section per contract section,
   slots per rendering_slot, entity_ids from contract.
2. Section ordering honors contract.section_order.
3. Slot ordering within section honors slot.ordering.
4. Gap-slot preservation: slots with gap frame rows still appear,
   flagged is_gap=True.
5. Partial-slot flagging: multi-entity slot with mixed
   gap/non-gap rows is is_partial=True.
6. Parallel-validation: frame_rows must match bindings order;
   mismatch raises.
7. Entity-type-agnostic: statute / dft_primary / etc compose.
8. Deterministic: same inputs → byte-identical ContractOutline.
9. to_section_plan_dicts() legacy adapter shape.
10. Integration with real clinical.yaml + stub frame_rows.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from src.polaris_graph.nodes.contract_outline import (
    ContractOutline,
    ContractSectionPlan,
    ContractSlotPlan,
    _compose_section_focus,
    compose_outline_from_contract,
)
from src.polaris_graph.nodes.frame_compiler import (
    CompiledFrame,
    compile_frame,
)
from src.polaris_graph.retrieval.frame_fetcher import (
    FrameRow,
    ProvenanceClass,
    RetrievalAttempt,
    RetrievalTiming,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _entity(
    eid: str = "e1",
    etype: str = "pivotal_trial",
    slot: str = "s1",
    doi: str | None = "10.1/x",
) -> dict:
    out: dict = {
        "id": eid,
        "type": etype,
        "required_fields": ["N", "primary_endpoint"],
        "min_fields_for_completion": 1,
        "rendering_slot": slot,
    }
    if doi is not None:
        out["doi"] = doi
    return out


def _slot(
    section: str = "Efficacy",
    title: str = "Trial X",
    ordering: int = 1,
) -> dict:
    return {
        "section": section,
        "subsection_title": title,
        "ordering": ordering,
        "required": True,
    }


def _template(
    entities: list[dict],
    slots: dict[str, dict],
    section_order: list[str] | None = None,
    schema_version: str = "v30.1",
    slug: str = "test_slug",
) -> dict:
    body: dict = {
        "schema_version": schema_version,
        "required_entities": entities,
        "rendering_slots": slots,
    }
    if section_order is not None:
        body["section_order"] = section_order
    return {"per_query_report_contract": {slug: body}}


def _make_row(
    entity_id: str,
    slot: str,
    provenance: ProvenanceClass = ProvenanceClass.ABSTRACT_ONLY,
    entity_type: str = "pivotal_trial",
    doi: str | None = "10.1/x",
) -> FrameRow:
    return FrameRow(
        entity_id=entity_id,
        entity_type=entity_type,
        rendering_slot=slot,
        provenance_class=provenance,
        direct_quote=(
            "Primary endpoint ETD was -2.3%."
            if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            else ""
        ),
        quote_source=(
            "crossref_abstract"
            if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            else "none"
        ),
        doi=doi,
        pmid=None,
        oa_pdf_url=None,
        url=None,
        title=f"title {entity_id}",
        authors=(),
        journal=None,
        year=2021,
        failure_reason=(
            "all sources failed: ..."
            if provenance == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            else None
        ),
        retrieval_attempts=(),
        retrieval_timings=(),
    )


def _compile_then_rows(
    template: dict,
    slug: str = "test_slug",
    research_question: str = "q",
    row_provenances: dict[str, ProvenanceClass] | None = None,
) -> tuple[CompiledFrame, tuple[FrameRow, ...]]:
    cf = compile_frame(research_question, template, slug)
    assert cf is not None
    rows = []
    for b in cf.evidence_bindings:
        prov = (row_provenances or {}).get(
            b.entity_id, ProvenanceClass.ABSTRACT_ONLY
        )
        rows.append(_make_row(
            entity_id=b.entity_id,
            slot=b.rendering_slot,
            provenance=prov,
            entity_type=b.entity_type,
        ))
    return cf, tuple(rows)


# ─────────────────────────────────────────────────────────────────────
# (1) Well-formed compose
# ─────────────────────────────────────────────────────────────────────
class TestWellFormedCompose:
    def test_single_section_single_slot(self) -> None:
        template = _template(
            [_entity(eid="e1", slot="s1")],
            {"s1": _slot(section="Efficacy")},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)

        assert isinstance(outline, ContractOutline)
        assert outline.research_question == "q"
        assert outline.schema_version == "v30.1"
        assert len(outline.sections) == 1

        sec = outline.sections[0]
        assert sec.section == "Efficacy"
        assert sec.section_ordering_index == 0
        assert len(sec.slots) == 1

        slot = sec.slots[0]
        assert slot.slot_id == "s1"
        assert slot.section == "Efficacy"
        assert slot.entity_ids == ("e1",)
        assert slot.is_gap is False
        assert slot.is_partial is False

    def test_multi_section_multi_slot(self) -> None:
        template = _template(
            [
                _entity(eid="e1", slot="s_eff_1"),
                _entity(eid="e2", slot="s_eff_2"),
                _entity(eid="e3", slot="s_mech"),
            ],
            {
                "s_eff_1": _slot(section="Efficacy", ordering=1),
                "s_eff_2": _slot(section="Efficacy", ordering=2),
                "s_mech":  _slot(section="Mechanism", ordering=1),
            },
            section_order=["Efficacy", "Mechanism"],
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)

        assert len(outline.sections) == 2
        assert outline.sections[0].section == "Efficacy"
        assert outline.sections[1].section == "Mechanism"
        assert len(outline.sections[0].slots) == 2
        assert len(outline.sections[1].slots) == 1


# ─────────────────────────────────────────────────────────────────────
# (2) Section ordering honors contract.section_order
# ─────────────────────────────────────────────────────────────────────
class TestSectionOrdering:
    def test_explicit_non_alphabetic_order(self) -> None:
        """Section_order=[Z, A] — outline must emit Z first despite
        Z > A alphabetically."""
        template = _template(
            [
                _entity(eid="z1", slot="s_z"),
                _entity(eid="a1", slot="s_a"),
            ],
            {
                "s_z": _slot(section="Z_section"),
                "s_a": _slot(section="A_section"),
            },
            section_order=["Z_section", "A_section"],
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)

        assert [s.section for s in outline.sections] == [
            "Z_section", "A_section"
        ]
        assert outline.sections[0].section_ordering_index == 0
        assert outline.sections[1].section_ordering_index == 1

    def test_no_section_order_falls_back_alphabetic(self) -> None:
        """Contract without section_order — section ordering is
        alphabetic. (M-55 emits the warning; M-57 is quiet.)"""
        template = _template(
            [
                _entity(eid="z1", slot="s_z"),
                _entity(eid="a1", slot="s_a"),
            ],
            {
                "s_z": _slot(section="Z"),
                "s_a": _slot(section="A"),
            },
            section_order=None,
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)
        assert [s.section for s in outline.sections] == ["A", "Z"]


# ─────────────────────────────────────────────────────────────────────
# (3) Slot ordering within section
# ─────────────────────────────────────────────────────────────────────
class TestSlotOrdering:
    def test_slots_sorted_by_ordering(self) -> None:
        template = _template(
            [
                _entity(eid="e_first", slot="s_ord_3"),  # declared 3rd
                _entity(eid="e_middle", slot="s_ord_1"),
                _entity(eid="e_last", slot="s_ord_2"),
            ],
            {
                "s_ord_1": _slot(ordering=1, title="First"),
                "s_ord_2": _slot(ordering=2, title="Second"),
                "s_ord_3": _slot(ordering=3, title="Third"),
            },
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)
        titles = [slot.subsection_title for slot in outline.sections[0].slots]
        assert titles == ["First", "Second", "Third"]


# ─────────────────────────────────────────────────────────────────────
# (4) Gap-slot preservation
# ─────────────────────────────────────────────────────────────────────
class TestGapSlotPreservation:
    def test_gap_slot_still_appears_flagged(self) -> None:
        template = _template(
            [_entity(eid="e_gap", slot="s1")],
            {"s1": _slot()},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(
            template,
            row_provenances={
                "e_gap": ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            },
        )
        outline = compose_outline_from_contract(cf, rows)

        # Slot still appears
        assert len(outline.sections[0].slots) == 1
        slot = outline.sections[0].slots[0]
        assert slot.entity_ids == ("e_gap",)
        assert slot.is_gap is True
        assert slot.is_partial is False
        assert slot.provenance_classes == ("frame_gap_unrecoverable",)

    def test_gap_slot_ids_accessor(self) -> None:
        template = _template(
            [
                _entity(eid="e_ok", slot="s_ok"),
                _entity(eid="e_gap", slot="s_gap"),
            ],
            {
                "s_ok":  _slot(ordering=1),
                "s_gap": _slot(ordering=2, title="Gap slot"),
            },
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(
            template,
            row_provenances={
                "e_gap": ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            },
        )
        outline = compose_outline_from_contract(cf, rows)
        assert outline.gap_slot_ids() == ("s_gap",)


# ─────────────────────────────────────────────────────────────────────
# (5) Partial-slot flagging (multi-entity slot mixed outcome)
# ─────────────────────────────────────────────────────────────────────
class TestPartialSlot:
    def test_multi_entity_mixed_provenance_is_partial(self) -> None:
        template = _template(
            [
                _entity(eid="e_ok",  slot="s_multi"),
                _entity(eid="e_gap", slot="s_multi"),
            ],
            {"s_multi": _slot()},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(
            template,
            row_provenances={
                "e_gap": ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            },
        )
        outline = compose_outline_from_contract(cf, rows)
        slot = outline.sections[0].slots[0]
        assert slot.entity_ids == ("e_gap", "e_ok")  # alphabetic
        assert slot.is_gap is False     # not ALL gap
        assert slot.is_partial is True  # SOME gap


# ─────────────────────────────────────────────────────────────────────
# (6) Parallel-validation of frame_rows
# ─────────────────────────────────────────────────────────────────────
class TestParallelValidation:
    def test_length_mismatch_raises(self) -> None:
        template = _template(
            [_entity(eid="e1"), _entity(eid="e2", slot="s2")],
            {"s1": _slot(), "s2": _slot(ordering=2)},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        with pytest.raises(ValueError) as exc:
            compose_outline_from_contract(cf, rows[:1])
        assert "length" in str(exc.value)

    def test_order_mismatch_raises(self) -> None:
        template = _template(
            [_entity(eid="e1"), _entity(eid="e2", slot="s2")],
            {"s1": _slot(), "s2": _slot(ordering=2)},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        # Swap row order
        swapped = (rows[1], rows[0])
        with pytest.raises(ValueError) as exc:
            compose_outline_from_contract(cf, swapped)
        assert "entity_id" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────
# (7) Entity-type-agnostic (Codex rev #7)
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    def test_statute_dft_novel_types_compose(self) -> None:
        template = _template(
            [
                _entity(eid="stat1", etype="statute", slot="s_law",
                        doi=None),
                _entity(eid="dft1", etype="dft_primary",
                        slot="s_comp"),
                _entity(eid="novel1", etype="unknown_xyz_2099",
                        slot="s_new"),
            ],
            {
                "s_law":  _slot(section="Law", ordering=1),
                "s_comp": _slot(section="Computation", ordering=1),
                "s_new":  _slot(section="NewStuff", ordering=1),
            },
            section_order=["Law", "Computation", "NewStuff"],
        )
        # statute entity with no DOI needs a url_pattern
        template["per_query_report_contract"]["test_slug"][
            "required_entities"
        ][0]["url_pattern"] = "uscode.house.gov"
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)

        assert [s.section for s in outline.sections] == [
            "Law", "Computation", "NewStuff",
        ]
        assert outline.sections[0].slots[0].entity_ids == ("stat1",)
        assert outline.sections[1].slots[0].entity_ids == ("dft1",)
        assert outline.sections[2].slots[0].entity_ids == ("novel1",)


# ─────────────────────────────────────────────────────────────────────
# (8) Determinism
# ─────────────────────────────────────────────────────────────────────
class TestDeterminism:
    def test_same_inputs_yield_same_outline(self) -> None:
        template = _template(
            [
                _entity(eid="e1", slot="s1"),
                _entity(eid="e2", slot="s2"),
            ],
            {"s1": _slot(ordering=1), "s2": _slot(ordering=2)},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        o1 = compose_outline_from_contract(cf, rows)
        o2 = compose_outline_from_contract(cf, rows)
        assert o1 == o2


# ─────────────────────────────────────────────────────────────────────
# (9) Legacy-compatible adapter
# ─────────────────────────────────────────────────────────────────────
class TestLegacyAdapter:
    def test_to_section_plan_dicts_shape(self) -> None:
        template = _template(
            [
                _entity(eid="e1", slot="s_eff_1"),
                _entity(eid="e2", slot="s_eff_2"),
                _entity(eid="e3", slot="s_mech"),
            ],
            {
                "s_eff_1": _slot(section="Efficacy", ordering=1),
                "s_eff_2": _slot(section="Efficacy", ordering=2),
                "s_mech":  _slot(section="Mechanism", ordering=1),
            },
            section_order=["Efficacy", "Mechanism"],
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)
        plans = outline.to_section_plan_dicts()
        assert len(plans) == 2
        assert plans[0]["title"] == "Efficacy"
        assert plans[0]["ev_ids"] == ["e1", "e2"]
        assert "2 subsections" in plans[0]["focus"]
        assert plans[1]["title"] == "Mechanism"
        assert plans[1]["ev_ids"] == ["e3"]

    def test_intra_slot_entity_order_inherits_from_compiler(self) -> None:
        """Codex M-57 audit Medium fix: entity ordering within a
        slot must come from the M-55 compiler's ordered_entity_ids,
        not be re-sorted alphabetically by M-57.

        Constructed setup where compiler order diverges from id
        alphabetic order so we can witness inheritance: both
        entities in same slot, but one has a smaller id alphabetically.
        The compiler still orders them by (section, slot.ordering,
        entity.id) — so in a single slot they happen to tie on
        section+ordering and alphabetic id wins. This test instead
        proves M-57 consults the compiler tuple explicitly: if we
        patched that tuple in reverse, M-57 would emit reverse order.
        """
        template = _template(
            [
                _entity(eid="alpha_b", slot="s_multi"),
                _entity(eid="alpha_a", slot="s_multi"),
            ],
            {"s_multi": _slot()},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        # Baseline: alphabetic within slot (compiler sort = id asc)
        outline = compose_outline_from_contract(cf, rows)
        assert outline.sections[0].slots[0].entity_ids == (
            "alpha_a", "alpha_b"
        )

        # Now craft a CompiledFrame with REVERSED ordered_entity_ids
        # and confirm M-57 follows it.
        from dataclasses import replace
        cf_reversed = replace(
            cf, ordered_entity_ids=("alpha_b", "alpha_a"),
        )
        outline_reversed = compose_outline_from_contract(cf_reversed, rows)
        assert outline_reversed.sections[0].slots[0].entity_ids == (
            "alpha_b", "alpha_a"
        )

    def test_all_entity_ids_flattened(self) -> None:
        template = _template(
            [
                _entity(eid="e3", slot="s2"),
                _entity(eid="e1", slot="s1"),
                _entity(eid="e2", slot="s1"),
            ],
            {"s1": _slot(ordering=1), "s2": _slot(ordering=2)},
            section_order=["Efficacy"],
        )
        cf, rows = _compile_then_rows(template)
        outline = compose_outline_from_contract(cf, rows)
        # s1 first (ordering=1), entities alphabetic within slot,
        # then s2. Result: e1, e2 (slot 1), e3 (slot 2).
        assert outline.all_entity_ids() == ("e1", "e2", "e3")


# ─────────────────────────────────────────────────────────────────────
# (10) Focus string composition
# ─────────────────────────────────────────────────────────────────────
class TestFocusComposition:
    def test_focus_counts_and_lists(self) -> None:
        slots = [
            ContractSlotPlan(
                slot_id=f"s{i}", section="Efficacy",
                subsection_title=f"Trial {i}",
                ordering=i, entity_ids=(f"e{i}",),
                provenance_classes=("abstract_only",),
                is_gap=False, is_partial=False,
            )
            for i in range(1, 4)
        ]
        focus = _compose_section_focus("Efficacy", slots)
        assert "3 subsections" in focus
        assert "Trial 1" in focus and "Trial 3" in focus

    def test_focus_flags_gap_count(self) -> None:
        slots = [
            ContractSlotPlan(
                slot_id="s1", section="Efficacy",
                subsection_title="Trial 1", ordering=1,
                entity_ids=("e1",),
                provenance_classes=("abstract_only",),
                is_gap=False, is_partial=False,
            ),
            ContractSlotPlan(
                slot_id="s2", section="Efficacy",
                subsection_title="Trial 2", ordering=2,
                entity_ids=("e2",),
                provenance_classes=("frame_gap_unrecoverable",),
                is_gap=True, is_partial=False,
            ),
        ]
        focus = _compose_section_focus("Efficacy", slots)
        assert "1 gap" in focus

    def test_focus_caps_long_title_list(self) -> None:
        slots = [
            ContractSlotPlan(
                slot_id=f"s{i}", section="Efficacy",
                subsection_title=f"Trial {i}",
                ordering=i, entity_ids=(f"e{i}",),
                provenance_classes=("abstract_only",),
                is_gap=False, is_partial=False,
            )
            for i in range(1, 10)
        ]
        focus = _compose_section_focus("Efficacy", slots)
        assert "+3 more" in focus

    def test_focus_zero_slots(self) -> None:
        focus = _compose_section_focus("NoContent", [])
        assert "no contract-bound" in focus


# ─────────────────────────────────────────────────────────────────────
# (11) Integration: real clinical.yaml + stub frame_rows
# ─────────────────────────────────────────────────────────────────────
class TestRealClinicalYaml:
    @pytest.fixture(scope="class")
    def clinical_template(self) -> dict:
        path = Path("config/scope_templates/clinical.yaml")
        assert path.exists()
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_clinical_compiles_to_outline(
        self, clinical_template: dict
    ) -> None:
        cf = compile_frame(
            "Evidence for tirzepatide in T2D",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        rows = tuple(
            _make_row(
                entity_id=b.entity_id,
                slot=b.rendering_slot,
                entity_type=b.entity_type,
            )
            for b in cf.evidence_bindings
        )
        outline = compose_outline_from_contract(cf, rows)

        # 3 sections: Efficacy, Mechanism, Regulatory
        assert [s.section for s in outline.sections] == [
            "Efficacy", "Mechanism", "Regulatory",
        ]
        # 15 slots total (8 + 1 + 6)
        total_slots = sum(len(s.slots) for s in outline.sections)
        assert total_slots == 15

        # Efficacy section has 8 subsections ordered SURPASS-1..6,
        # CVOT, SURMOUNT-2
        efficacy = outline.sections[0]
        assert len(efficacy.slots) == 8
        titles = [s.subsection_title for s in efficacy.slots]
        for name in ["SURPASS-1", "SURPASS-2", "SURPASS-3",
                     "SURPASS-4", "SURPASS-5", "SURPASS-6",
                     "SURPASS-CVOT", "SURMOUNT-2"]:
            assert any(name in t for t in titles), (
                f"{name} missing from efficacy titles: {titles}"
            )

        # Legacy adapter produces 3 section dicts
        plans = outline.to_section_plan_dicts()
        assert len(plans) == 3
        assert plans[0]["title"] == "Efficacy"
        assert len(plans[0]["ev_ids"]) == 8
