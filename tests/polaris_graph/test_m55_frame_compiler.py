"""M-55 tests: V30 frame compiler (research_question + template +
slug -> CompiledFrame).

Layer 2a of V30 Report Contract Architecture. Codex plan pass-1
CONDITIONAL-no-blockers; M-55 was root_cause_approved_with_revision
(Codex rev #1/#7: compiler tests must prove arbitrary entity types
and slot types compile without code changes).

Covers:
1. Well-formed template compiles to CompiledFrame.
2. Missing slug → None (backwards-compat).
3. Identifier priority order (DOI > PMID > url_pattern > anchor).
4. Entity with no identifier raises FrameCompilerError.
5. Schema-version forward-compat: unknown version → warning, not error.
6. Entity-type-agnostic per Codex rev #7: statute/dft_primary/etc.
7. Deterministic ordering: (section, slot.ordering, entity.id).
8. Integration test on real clinical.yaml contract.
9. Determinism: same inputs → byte-identical CompiledFrame.
10. bindings_by_entity_id() / bindings_by_slot() helpers.
11. research_question pass-through.
12. Non-string research_question raises.

All tests pure (no network, no LLM, no I/O). Fixture-based.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.polaris_graph.nodes.frame_compiler import (
    CompiledFrame,
    EvidenceBinding,
    FrameCompilerError,
    compile_frame,
    get_identifier_priority_order,
)
from src.polaris_graph.nodes.report_contract import ContractSchemaError


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _entity(
    eid: str = "e1",
    etype: str = "pivotal_trial",
    slot: str = "s1",
    doi: str | None = None,
    pmid: int | str | None = None,
    url_pattern: str | None = None,
    anchor: str | None = None,
    required_fields: list[str] | None = None,
    min_fields: int = 1,
) -> dict:
    out: dict = {
        "id": eid,
        "type": etype,
        "required_fields": required_fields or ["N", "primary_endpoint"],
        "min_fields_for_completion": min_fields,
        "rendering_slot": slot,
    }
    if doi is not None:
        out["doi"] = doi
    if pmid is not None:
        out["pmid"] = pmid
    if url_pattern is not None:
        out["url_pattern"] = url_pattern
    if anchor is not None:
        out["anchor"] = anchor
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
    schema_version: str = "v30.1",
    slug: str = "test_slug",
    section_order: list[str] | None = None,
) -> dict:
    body: dict = {
        "schema_version": schema_version,
        "required_entities": entities,
        "rendering_slots": slots,
    }
    if section_order is not None:
        body["section_order"] = section_order
    return {"per_query_report_contract": {slug: body}}


# ─────────────────────────────────────────────────────────────────────
# (1) Well-formed compilation
# ─────────────────────────────────────────────────────────────────────
class TestWellFormedCompilation:
    def test_single_entity_compiles(self) -> None:
        template = _template(
            [_entity(doi="10.1056/NEJMoa2107519")],
            {"s1": _slot()},
        )
        cf = compile_frame("what is the evidence for X?", template, "test_slug")

        assert isinstance(cf, CompiledFrame)
        assert cf.slug == "test_slug"
        assert cf.schema_version == "v30.1"
        assert cf.research_question == "what is the evidence for X?"
        assert len(cf.evidence_bindings) == 1

        b = cf.evidence_bindings[0]
        assert isinstance(b, EvidenceBinding)
        assert b.entity_id == "e1"
        assert b.entity_type == "pivotal_trial"
        assert b.primary_identifier == "doi:10.1056/NEJMoa2107519"
        assert b.rendering_slot == "s1"

    def test_warnings_empty_on_known_version_and_explicit_section_order(
        self,
    ) -> None:
        template = _template(
            [_entity(doi="10.1056/NEJMoa2107519")],
            {"s1": _slot(section="Efficacy")},
            section_order=["Efficacy"],
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.warnings == ()

    def test_research_question_passthrough(self) -> None:
        template = _template(
            [_entity(doi="10.1056/NEJMoa2107519")],
            {"s1": _slot()},
        )
        cf = compile_frame("arbitrary text", template, "test_slug")
        assert cf.research_question == "arbitrary text"


# ─────────────────────────────────────────────────────────────────────
# (2) Backwards compatibility
# ─────────────────────────────────────────────────────────────────────
class TestBackwardsCompat:
    def test_missing_slug_returns_none(self) -> None:
        template = _template(
            [_entity(doi="10.1/foo")],
            {"s1": _slot()},
            slug="existing_slug",
        )
        assert compile_frame("q", template, "other_slug") is None

    def test_missing_contract_block_returns_none(self) -> None:
        template = {"other_fields": 1}
        assert compile_frame("q", template, "anything") is None

    def test_none_template_returns_none(self) -> None:
        assert compile_frame("q", None, "test_slug") is None


# ─────────────────────────────────────────────────────────────────────
# (3) Identifier priority order
# ─────────────────────────────────────────────────────────────────────
class TestIdentifierPriority:
    def test_doi_wins(self) -> None:
        template = _template(
            [_entity(
                doi="10.1/foo", pmid=12345,
                url_pattern="example.com", anchor="TRIAL-1",
            )],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        b = cf.evidence_bindings[0]
        assert b.primary_identifier == "doi:10.1/foo"
        # Secondaries in priority order minus the primary
        assert b.secondary_identifiers == (
            "pmid:12345", "url:example.com", "anchor:TRIAL-1",
        )

    def test_pmid_wins_without_doi(self) -> None:
        template = _template(
            [_entity(pmid=12345, url_pattern="example.com", anchor="T")],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        b = cf.evidence_bindings[0]
        assert b.primary_identifier == "pmid:12345"
        assert b.secondary_identifiers == ("url:example.com", "anchor:T")

    def test_url_wins_without_doi_pmid(self) -> None:
        template = _template(
            [_entity(url_pattern="accessdata.fda.gov", anchor="T")],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        b = cf.evidence_bindings[0]
        assert b.primary_identifier == "url:accessdata.fda.gov"

    def test_anchor_last_resort(self) -> None:
        template = _template(
            [_entity(anchor="SURPASS-CVOT")],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        b = cf.evidence_bindings[0]
        assert b.primary_identifier == "anchor:SURPASS-CVOT"
        assert b.secondary_identifiers == ()

    def test_pmid_string_accepted(self) -> None:
        """PMID field accepts int or str (see RequiredEntity type)."""
        template = _template(
            [_entity(pmid="34010531")],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.evidence_bindings[0].primary_identifier == "pmid:34010531"

    def test_pmid_zero_is_not_identifier(self) -> None:
        """pmid=0 is treated as non-identifier (sentinel value)."""
        template = _template(
            [_entity(pmid=0, anchor="TRIAL")],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.evidence_bindings[0].primary_identifier == "anchor:TRIAL"

    def test_priority_order_accessor(self) -> None:
        assert get_identifier_priority_order() == (
            "doi", "pmid", "url_pattern", "anchor",
        )


# ─────────────────────────────────────────────────────────────────────
# (4) No-identifier rejection
# ─────────────────────────────────────────────────────────────────────
class TestNoIdentifierRejection:
    def test_no_identifier_raises(self) -> None:
        template = _template(
            [_entity()],  # no doi/pmid/url_pattern/anchor
            {"s1": _slot()},
        )
        with pytest.raises(FrameCompilerError) as exc:
            compile_frame("q", template, "test_slug")
        assert exc.value.entity_id == "e1"
        assert "no identifier" in exc.value.reason.lower()

    def test_error_names_entity(self) -> None:
        template = _template(
            [
                _entity(eid="good_one", doi="10.1/ok", slot="s1"),
                _entity(eid="bad_one", slot="s1"),
            ],
            {"s1": _slot()},
        )
        with pytest.raises(FrameCompilerError) as exc:
            compile_frame("q", template, "test_slug")
        assert exc.value.entity_id == "bad_one"
        assert "bad_one" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────
# (5) Schema version forward-compat
# ─────────────────────────────────────────────────────────────────────
class TestSchemaVersionWarnings:
    def test_known_version_no_warnings(self) -> None:
        template = _template(
            [_entity(doi="10.1/x")],
            {"s1": _slot(section="Efficacy")},
            schema_version="v30.1",
            section_order=["Efficacy"],
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.warnings == ()

    def test_unknown_version_emits_warning(self) -> None:
        template = _template(
            [_entity(doi="10.1/x")],
            {"s1": _slot(section="Efficacy")},
            schema_version="v99.7",
            section_order=["Efficacy"],
        )
        cf = compile_frame("q", template, "test_slug")
        # exactly 1 warning: schema-version; no section_order fallback
        assert len(cf.warnings) == 1
        assert "v99.7" in cf.warnings[0]
        assert "unknown" in cf.warnings[0].lower()

    def test_unknown_version_still_compiles(self) -> None:
        """Warning, not error."""
        template = _template(
            [_entity(doi="10.1/x")],
            {"s1": _slot()},
            schema_version="v99.7",
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf is not None
        assert cf.schema_version == "v99.7"


# ─────────────────────────────────────────────────────────────────────
# (6) Entity-type-agnostic (Codex rev #7)
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    """Codex M-55 plan review revision #7: compiler must prove
    arbitrary entity types plus arbitrary slot ids / sections /
    orderings compile without code changes. (The schema has no
    slot-TYPE field — that was stale plan wording; the actual
    contract is shape-agnostic over ids/sections/orderings.)
    Protects M-62 non-clinical generalization guard."""

    def test_compiles_policy_entity_type(self) -> None:
        template = _template(
            [_entity(etype="statute", url_pattern="uscode.house.gov/title42")],
            {"s1": _slot(section="Statute")},
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.evidence_bindings[0].entity_type == "statute"

    def test_compiles_materials_entity_type(self) -> None:
        template = _template(
            [_entity(etype="dft_primary", doi="10.1/materials.123")],
            {"s1": _slot(section="Computation")},
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.evidence_bindings[0].entity_type == "dft_primary"

    def test_compiles_completely_novel_type(self) -> None:
        template = _template(
            [_entity(etype="unknown_xyz_2099", doi="10.1/x")],
            {"s1": _slot()},
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.evidence_bindings[0].entity_type == "unknown_xyz_2099"

    def test_mixed_types_compile_together(self) -> None:
        """Multi-domain template with statute + dft_primary +
        pivotal_trial + regulatory mixed in one slug."""
        template = _template(
            [
                _entity(eid="e1", etype="pivotal_trial",
                        doi="10.1/trial", slot="s1"),
                _entity(eid="e2", etype="statute",
                        url_pattern="uscode.house.gov", slot="s2"),
                _entity(eid="e3", etype="dft_primary",
                        doi="10.1/dft", slot="s3"),
                _entity(eid="e4", etype="regulatory",
                        url_pattern="accessdata.fda.gov", slot="s4"),
            ],
            {
                "s1": _slot(section="A", ordering=1),
                "s2": _slot(section="B", ordering=1),
                "s3": _slot(section="C", ordering=1),
                "s4": _slot(section="D", ordering=1),
            },
        )
        cf = compile_frame("q", template, "test_slug")
        types = {b.entity_type for b in cf.evidence_bindings}
        assert types == {
            "pivotal_trial", "statute", "dft_primary", "regulatory"
        }


# ─────────────────────────────────────────────────────────────────────
# (7) Deterministic ordering
# ─────────────────────────────────────────────────────────────────────
class TestSectionOrder:
    """Codex M-55 audit Medium: cross-section rendering order is
    now template-declared via `section_order:` instead of being
    fragile alphabetic-by-label. M-55 compiler uses section_order
    when present; falls back to alphabetic with a warning when
    absent."""

    def test_explicit_section_order_wins(self) -> None:
        """Non-alphabetic explicit order — `Z_section` first
        even though alphabetic would place it last."""
        template = _template(
            [
                _entity(eid="e1_in_z", doi="10.1/z", slot="s_z"),
                _entity(eid="e2_in_a", doi="10.1/a", slot="s_a"),
            ],
            {
                "s_z": _slot(section="Z_section", ordering=1),
                "s_a": _slot(section="A_section", ordering=1),
            },
            section_order=["Z_section", "A_section"],
        )
        cf = compile_frame("q", template, "test_slug")
        assert cf.ordered_entity_ids == ("e1_in_z", "e2_in_a")
        # No warning because section_order is declared
        assert cf.warnings == ()

    def test_absent_section_order_emits_warning(self) -> None:
        template = _template(
            [_entity(doi="10.1/x")],
            {"s1": _slot(section="Efficacy")},
        )
        cf = compile_frame("q", template, "test_slug")
        assert any(
            "section_order" in w and "alphabetic" in w
            for w in cf.warnings
        ), f"expected section_order-missing warning, got {cf.warnings}"

    def test_section_order_missing_section_raises_at_loader(self) -> None:
        """A slot references a section not in section_order → raise
        at M-54 load (so error surfaces before compiler runs)."""
        template = _template(
            [_entity(doi="10.1/x", slot="s1")],
            {
                "s1": _slot(section="Efficacy"),
                "s2": _slot(section="Regulatory"),  # declared but unused
            },
            section_order=["Efficacy"],  # Regulatory missing
        )
        # Need an entity in s2 to make section referenced
        template["per_query_report_contract"]["test_slug"][
            "required_entities"
        ].append(_entity(eid="e2", doi="10.1/y", slot="s2"))
        with pytest.raises(ContractSchemaError) as exc:
            compile_frame("q", template, "test_slug")
        assert "section_order" in exc.value.path
        assert "Regulatory" in exc.value.reason

    def test_section_order_duplicates_raise(self) -> None:
        template = _template(
            [_entity(doi="10.1/x", slot="s1")],
            {"s1": _slot(section="Efficacy")},
            section_order=["Efficacy", "Efficacy"],
        )
        with pytest.raises(ContractSchemaError) as exc:
            compile_frame("q", template, "test_slug")
        assert "section_order" in exc.value.path

    def test_section_order_non_list_raises(self) -> None:
        template = _template(
            [_entity(doi="10.1/x", slot="s1")],
            {"s1": _slot(section="Efficacy")},
        )
        template["per_query_report_contract"]["test_slug"][
            "section_order"
        ] = "Efficacy"  # str not list
        with pytest.raises(ContractSchemaError):
            compile_frame("q", template, "test_slug")

    def test_section_order_empty_string_element_raises(self) -> None:
        template = _template(
            [_entity(doi="10.1/x", slot="s1")],
            {"s1": _slot(section="Efficacy")},
            section_order=["Efficacy", ""],
        )
        with pytest.raises(ContractSchemaError):
            compile_frame("q", template, "test_slug")


class TestDeterministicOrdering:
    def test_ordered_by_section_then_ordering_then_id(self) -> None:
        template = _template(
            [
                # Intentionally declared out of canonical order
                _entity(eid="z_last", slot="s_mech"),
                _entity(eid="c_eff_2", slot="s_eff_2"),
                _entity(eid="a_eff_1b", slot="s_eff_1"),
                _entity(eid="a_eff_1a", slot="s_eff_1"),  # same slot
            ],
            {
                "s_eff_1": _slot(section="Efficacy", ordering=1),
                "s_eff_2": _slot(section="Efficacy", ordering=2),
                "s_mech":  _slot(section="Mechanism", ordering=1),
            },
        )
        # All need an identifier, add a dummy DOI to each
        for e in template["per_query_report_contract"]["test_slug"][
            "required_entities"
        ]:
            e["doi"] = f"10.1/{e['id']}"
        cf = compile_frame("q", template, "test_slug")

        # Expected order: Efficacy/ord=1 (a_eff_1a, a_eff_1b by id),
        # then Efficacy/ord=2 (c_eff_2), then Mechanism/ord=1 (z_last)
        assert cf.ordered_entity_ids == (
            "a_eff_1a", "a_eff_1b", "c_eff_2", "z_last",
        )

    def test_determinism_same_inputs_same_output(self) -> None:
        template = _template(
            [
                _entity(eid="b", doi="10.1/b", slot="s2"),
                _entity(eid="a", doi="10.1/a", slot="s1"),
            ],
            {
                "s1": _slot(section="Efficacy", ordering=1),
                "s2": _slot(section="Efficacy", ordering=2),
            },
        )
        cf1 = compile_frame("q1", template, "test_slug")
        cf2 = compile_frame("q1", template, "test_slug")
        assert cf1.ordered_entity_ids == cf2.ordered_entity_ids
        assert cf1.evidence_bindings == cf2.evidence_bindings
        assert cf1.schema_version == cf2.schema_version


# ─────────────────────────────────────────────────────────────────────
# (8) research_question validation
# ─────────────────────────────────────────────────────────────────────
class TestResearchQuestionValidation:
    def test_empty_string_accepted(self) -> None:
        """Empty is permitted — compilation is about structure, not
        semantic question validation."""
        template = _template(
            [_entity(doi="10.1/x")], {"s1": _slot()},
        )
        cf = compile_frame("", template, "test_slug")
        assert cf is not None
        assert cf.research_question == ""

    def test_non_string_raises(self) -> None:
        template = _template(
            [_entity(doi="10.1/x")], {"s1": _slot()},
        )
        with pytest.raises(FrameCompilerError) as exc:
            compile_frame(42, template, "test_slug")  # type: ignore
        assert "research_question" in exc.value.reason


# ─────────────────────────────────────────────────────────────────────
# (9) Helper methods
# ─────────────────────────────────────────────────────────────────────
class TestCompiledFrameHelpers:
    def test_bindings_by_entity_id(self) -> None:
        template = _template(
            [
                _entity(eid="e1", doi="10.1/a", slot="s1"),
                _entity(eid="e2", doi="10.1/b", slot="s2"),
            ],
            {"s1": _slot(ordering=1), "s2": _slot(ordering=2)},
        )
        cf = compile_frame("q", template, "test_slug")
        by_id = cf.bindings_by_entity_id()
        assert set(by_id) == {"e1", "e2"}
        assert by_id["e1"].primary_identifier == "doi:10.1/a"

    def test_bindings_by_slot_multi_entity(self) -> None:
        template = _template(
            [
                _entity(eid="e1", doi="10.1/a", slot="s1"),
                _entity(eid="e2", doi="10.1/b", slot="s1"),  # same slot
                _entity(eid="e3", doi="10.1/c", slot="s2"),
            ],
            {"s1": _slot(ordering=1), "s2": _slot(ordering=2)},
        )
        cf = compile_frame("q", template, "test_slug")
        by_slot = cf.bindings_by_slot()
        assert {b.entity_id for b in by_slot["s1"]} == {"e1", "e2"}
        assert {b.entity_id for b in by_slot["s2"]} == {"e3"}


# ─────────────────────────────────────────────────────────────────────
# (10) YAML-shape errors propagate from M-54 loader
# ─────────────────────────────────────────────────────────────────────
class TestSchemaErrorsPropagate:
    def test_malformed_template_raises_contract_schema_error(self) -> None:
        """Compiler does NOT swallow M-54 shape errors — they
        propagate so caller sees the real diagnostic."""
        template = _template(
            [_entity(doi="10.1/x", slot="nonexistent_slot")],
            {"s1": _slot()},
        )
        with pytest.raises(ContractSchemaError):
            compile_frame("q", template, "test_slug")


# ─────────────────────────────────────────────────────────────────────
# (11) Integration: real clinical.yaml contract
# ─────────────────────────────────────────────────────────────────────
class TestRealClinicalYaml:
    @pytest.fixture(scope="class")
    def clinical_template(self) -> dict:
        path = Path("config/scope_templates/clinical.yaml")
        assert path.exists(), f"real contract missing at {path}"
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_clinical_compiles(self, clinical_template: dict) -> None:
        cf = compile_frame(
            "What is the evidence base for tirzepatide in T2D?",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        assert cf is not None
        assert cf.slug == "clinical_tirzepatide_t2dm"
        assert len(cf.evidence_bindings) == 15

    def test_clinical_no_warnings(self, clinical_template: dict) -> None:
        cf = compile_frame(
            "q", clinical_template, "clinical_tirzepatide_t2dm"
        )
        assert cf.warnings == ()

    def test_clinical_all_entities_have_identifier(
        self, clinical_template: dict
    ) -> None:
        """Regression guard: every entity in the real clinical
        contract must have at least one identifier (no
        FrameCompilerError)."""
        cf = compile_frame(
            "q", clinical_template, "clinical_tirzepatide_t2dm"
        )
        for b in cf.evidence_bindings:
            assert b.primary_identifier, (
                f"entity {b.entity_id} has no primary identifier"
            )

    def test_clinical_surpass_2_is_doi(
        self, clinical_template: dict
    ) -> None:
        cf = compile_frame(
            "q", clinical_template, "clinical_tirzepatide_t2dm"
        )
        by_id = cf.bindings_by_entity_id()
        b = by_id["surpass_2_primary"]
        assert b.primary_identifier == "doi:10.1056/NEJMoa2107519"
        # V30 Phase-2 run-1 root-cause fix (commit bcedd57):
        # PMID corrected 34010531 (SPRINT) → 34170647 (Frias).
        assert "pmid:34170647" in b.secondary_identifiers

    def test_clinical_fda_mounjaro_uses_url(
        self, clinical_template: dict
    ) -> None:
        """Regulatory entities without DOI fall through to
        url_pattern identifier."""
        cf = compile_frame(
            "q", clinical_template, "clinical_tirzepatide_t2dm"
        )
        by_id = cf.bindings_by_entity_id()
        b = by_id["fda_mounjaro_label"]
        assert b.primary_identifier == "url:accessdata.fda.gov"

    def test_clinical_efficacy_section_ordered(
        self, clinical_template: dict
    ) -> None:
        """Efficacy section entities must come out in slot.ordering
        order (SURPASS-1, 2, 3, 4, 5, 6, CVOT, SURMOUNT-2)."""
        cf = compile_frame(
            "q", clinical_template, "clinical_tirzepatide_t2dm"
        )
        contract = cf.contract
        slot_by_id = contract.slots_by_id()
        efficacy_ids = [
            eid for eid in cf.ordered_entity_ids
            if slot_by_id[
                contract.entities_by_id()[eid].rendering_slot
            ].section == "Efficacy"
        ]
        assert efficacy_ids == [
            "surpass_1_primary",
            "surpass_2_primary",
            "surpass_3_primary",
            "surpass_4_primary",
            "surpass_5_primary",
            "surpass_6_primary",
            "surpass_cvot_primary",
            "surmount_2_primary",
        ]
