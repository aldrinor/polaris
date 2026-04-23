"""M-54 tests: V30 Report Contract YAML schema + loader.

Layer 1 of V30 (Report Contract Architecture). Codex plan pass-1
CONDITIONAL-no-blockers at
`outputs/codex_findings/v30_fix_plan_review_pass1/findings.md`.

Covers:
1. Well-formed contract loads to ReportContract runtime type.
2. Missing required keys raise ContractSchemaError with precise path.
3. Unknown entity types are ACCEPTED at loader level (Codex rev #7:
   compiler and renderers must handle arbitrary entity types; M-54
   is entity-type-agnostic to support M-62 generalization guard).
4. min_fields_for_completion bound-check raises.
5. Referential integrity: entity.rendering_slot must resolve to a
   declared slot.
6. Unknown schema_version accepted (forward-compat warning at M-55).
7. Missing slug returns None (backwards-compat — V28/V29 continue
   to work without a contract).
8. Real clinical.yaml loads with 15 entities + 15 slots.

All tests pure (no network, no LLM). Fixture-based.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.polaris_graph.nodes.report_contract import (
    ContractSchemaError,
    RenderingSlot,
    ReportContract,
    RequiredEntity,
    get_known_schema_versions,
    load_report_contract_for_slug,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _minimal_entity(
    eid: str = "e1",
    etype: str = "pivotal_trial",
    slot: str = "s1",
    required_fields: list[str] | None = None,
    min_fields: int = 1,
) -> dict:
    return {
        "id": eid,
        "type": etype,
        "required_fields": required_fields or ["N", "primary_endpoint"],
        "min_fields_for_completion": min_fields,
        "rendering_slot": slot,
    }


def _minimal_slot(
    section: str = "Efficacy",
    subsection_title: str = "Trial X",
    ordering: int = 1,
    required: bool = True,
) -> dict:
    return {
        "section": section,
        "subsection_title": subsection_title,
        "ordering": ordering,
        "required": required,
    }


def _template_with_contract(contract: dict) -> dict:
    """Simulate a full scope template with only the contract block."""
    return {"per_query_report_contract": contract}


def _single_entity_contract() -> dict:
    return {
        "test_slug": {
            "schema_version": "v30.1",
            "required_entities": [_minimal_entity()],
            "rendering_slots": {"s1": _minimal_slot()},
        }
    }


# ─────────────────────────────────────────────────────────────────────
# (1) Well-formed contract loads
# ─────────────────────────────────────────────────────────────────────
class TestWellFormedContract:
    def test_single_entity_single_slot_loads(self) -> None:
        template = _template_with_contract(_single_entity_contract())
        contract = load_report_contract_for_slug(template, "test_slug")

        assert isinstance(contract, ReportContract)
        assert contract.slug == "test_slug"
        assert contract.schema_version == "v30.1"
        assert len(contract.required_entities) == 1
        assert len(contract.rendering_slots) == 1

        e = contract.required_entities[0]
        assert isinstance(e, RequiredEntity)
        assert e.id == "e1"
        assert e.type == "pivotal_trial"
        assert e.required_fields == ("N", "primary_endpoint")
        assert e.min_fields_for_completion == 1
        assert e.rendering_slot == "s1"

        s = contract.rendering_slots[0]
        assert isinstance(s, RenderingSlot)
        assert s.id == "s1"
        assert s.section == "Efficacy"
        assert s.ordering == 1
        assert s.required is True

    def test_optional_fields_pass_through(self) -> None:
        contract_raw = {
            "test_slug": {
                "schema_version": "v30.1",
                "required_entities": [{
                    **_minimal_entity(),
                    "doi": "10.1056/NEJMoa2107519",
                    "pmid": 34010531,
                    "anchor": "SURPASS-2",
                    "journal": "NEJM",
                    "year": 2021,
                    "population_scope": "direct",
                }],
                "rendering_slots": {"s1": _minimal_slot()},
            }
        }
        template = _template_with_contract(contract_raw)
        contract = load_report_contract_for_slug(template, "test_slug")
        e = contract.required_entities[0]
        assert e.doi == "10.1056/NEJMoa2107519"
        assert e.pmid == 34010531
        assert e.anchor == "SURPASS-2"
        assert e.journal == "NEJM"
        assert e.year == 2021
        assert e.population_scope == "direct"

    def test_regulatory_optional_fields_pass_through(self) -> None:
        contract_raw = {
            "test_slug": {
                "schema_version": "v30.1",
                "required_entities": [{
                    **_minimal_entity(etype="regulatory"),
                    "jurisdiction": "FDA",
                    "label_name": "Mounjaro",
                    "url_pattern": "accessdata.fda.gov",
                }],
                "rendering_slots": {"s1": _minimal_slot()},
            }
        }
        template = _template_with_contract(contract_raw)
        contract = load_report_contract_for_slug(template, "test_slug")
        e = contract.required_entities[0]
        assert e.type == "regulatory"
        assert e.jurisdiction == "FDA"
        assert e.label_name == "Mounjaro"
        assert e.url_pattern == "accessdata.fda.gov"

    def test_helper_methods(self) -> None:
        contract_raw = {
            "test_slug": {
                "schema_version": "v30.1",
                "required_entities": [
                    _minimal_entity(eid="e1", slot="s1"),
                    _minimal_entity(eid="e2", slot="s2"),
                    _minimal_entity(eid="e3", slot="s1"),  # multi per slot
                ],
                "rendering_slots": {
                    "s1": _minimal_slot(ordering=1),
                    "s2": _minimal_slot(ordering=2),
                },
            }
        }
        template = _template_with_contract(contract_raw)
        contract = load_report_contract_for_slug(template, "test_slug")

        by_id = contract.entities_by_id()
        assert set(by_id) == {"e1", "e2", "e3"}

        slots_by_id = contract.slots_by_id()
        assert set(slots_by_id) == {"s1", "s2"}

        by_slot = contract.entities_by_slot()
        assert {e.id for e in by_slot["s1"]} == {"e1", "e3"}
        assert {e.id for e in by_slot["s2"]} == {"e2"}


# ─────────────────────────────────────────────────────────────────────
# (2) Missing required keys raise with precise path
# ─────────────────────────────────────────────────────────────────────
class TestMissingRequiredFields:
    def test_missing_schema_version_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["schema_version"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "schema_version" in exc.value.path
        assert "missing" in exc.value.reason.lower()

    def test_missing_required_entities_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["required_entities"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_entities" in exc.value.path

    def test_missing_rendering_slots_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["rendering_slots"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slots" in exc.value.path

    def test_entity_missing_id_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["required_entities"][0]["id"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_entities[0]" in exc.value.path
        assert "id" in exc.value.reason

    def test_entity_missing_type_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["required_entities"][0]["type"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_entities[0]" in exc.value.path
        assert "type" in exc.value.reason

    def test_entity_missing_required_fields_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["required_entities"][0]["required_fields"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_entities[0]" in exc.value.path
        assert "required_fields" in exc.value.reason

    def test_slot_missing_section_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["rendering_slots"]["s1"]["section"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slots.s1" in exc.value.path
        assert "section" in exc.value.reason

    def test_slot_missing_ordering_raises(self) -> None:
        contract = _single_entity_contract()
        del contract["test_slug"]["rendering_slots"]["s1"]["ordering"]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slots.s1" in exc.value.path
        assert "ordering" in exc.value.reason


# ─────────────────────────────────────────────────────────────────────
# (3) Unknown entity types ACCEPTED — Codex rev #7, M-62 generalization
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    """Codex review #7: the loader MUST accept arbitrary entity types
    without code changes. Type-specific handling belongs to M-55
    compiler + downstream renderers. This test protects the M-62
    non-clinical generalization guard."""

    def test_accepts_policy_entity_type(self) -> None:
        """A policy-domain slug uses entity types like 'statute',
        'regulatory_ruling', 'court_decision' — not in the clinical
        vocabulary."""
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["type"] = "statute"
        template = _template_with_contract(contract)
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert result.required_entities[0].type == "statute"

    def test_accepts_materials_entity_type(self) -> None:
        """A materials slug may declare entity types like 'dft_primary',
        'characterization_primary' — loader must accept."""
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["type"] = "dft_primary"
        template = _template_with_contract(contract)
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert result.required_entities[0].type == "dft_primary"

    def test_accepts_completely_novel_type(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["type"] = "unknown_xyz_2099"
        template = _template_with_contract(contract)
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert result.required_entities[0].type == "unknown_xyz_2099"

    def test_empty_type_still_raises(self) -> None:
        """Permissive on vocab, strict on non-empty."""
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["type"] = ""
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "type" in exc.value.path


# ─────────────────────────────────────────────────────────────────────
# (4) min_fields_for_completion bounds
# ─────────────────────────────────────────────────────────────────────
class TestMinFieldsBounds:
    def test_zero_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0][
            "min_fields_for_completion"
        ] = 0
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "min_fields_for_completion" in exc.value.path

    def test_negative_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0][
            "min_fields_for_completion"
        ] = -1
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError):
            load_report_contract_for_slug(template, "test_slug")

    def test_exceeds_required_fields_len_raises(self) -> None:
        contract = _single_entity_contract()
        # required_fields has 2 entries; min=3 should fail
        contract["test_slug"]["required_entities"][0][
            "min_fields_for_completion"
        ] = 3
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "min_fields_for_completion" in exc.value.path

    def test_equals_required_fields_len_accepted(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0][
            "min_fields_for_completion"
        ] = 2
        template = _template_with_contract(contract)
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert result.required_entities[0].min_fields_for_completion == 2

    def test_non_int_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0][
            "min_fields_for_completion"
        ] = "2"
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError):
            load_report_contract_for_slug(template, "test_slug")


# ─────────────────────────────────────────────────────────────────────
# (5) Referential integrity
# ─────────────────────────────────────────────────────────────────────
class TestReferentialIntegrity:
    def test_entity_references_undeclared_slot_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0][
            "rendering_slot"
        ] = "unknown_slot"
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slot" in exc.value.path
        assert "unknown_slot" in exc.value.reason

    def test_all_slots_must_be_referenced_is_NOT_required(self) -> None:
        """Declaring extra slots without entities is allowed — the
        schema supports future expansion. Only the reverse (entity
        referencing missing slot) is an error."""
        contract_raw = {
            "test_slug": {
                "schema_version": "v30.1",
                "required_entities": [_minimal_entity(slot="s1")],
                "rendering_slots": {
                    "s1": _minimal_slot(ordering=1),
                    "s2": _minimal_slot(ordering=2),  # unreferenced
                },
            }
        }
        template = _template_with_contract(contract_raw)
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert len(result.rendering_slots) == 2

    def test_duplicate_entity_id_raises(self) -> None:
        contract_raw = {
            "test_slug": {
                "schema_version": "v30.1",
                "required_entities": [
                    _minimal_entity(eid="e1"),
                    _minimal_entity(eid="e1"),  # duplicate
                ],
                "rendering_slots": {"s1": _minimal_slot()},
            }
        }
        template = _template_with_contract(contract_raw)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "duplicate" in exc.value.reason.lower()


# ─────────────────────────────────────────────────────────────────────
# (6) Schema version forward-compat
# ─────────────────────────────────────────────────────────────────────
class TestSchemaVersion:
    def test_known_version_loads(self) -> None:
        template = _template_with_contract(_single_entity_contract())
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert result.schema_version == "v30.1"

    def test_unknown_future_version_accepted(self) -> None:
        """Forward-compat: loader accepts unknown version; M-55
        compiler is responsible for emitting a warning."""
        contract = _single_entity_contract()
        contract["test_slug"]["schema_version"] = "v99.7"
        template = _template_with_contract(contract)
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is not None
        assert result.schema_version == "v99.7"

    def test_known_schema_versions_accessor(self) -> None:
        versions = get_known_schema_versions()
        assert "v30.1" in versions
        assert isinstance(versions, frozenset)

    def test_non_string_schema_version_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["schema_version"] = 30.1  # float not str
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "schema_version" in exc.value.path


# ─────────────────────────────────────────────────────────────────────
# (7) Backwards compatibility — missing slug / missing block
# ─────────────────────────────────────────────────────────────────────
class TestBackwardsCompat:
    def test_missing_slug_returns_none(self) -> None:
        template = _template_with_contract(_single_entity_contract())
        result = load_report_contract_for_slug(template, "nonexistent_slug")
        assert result is None

    def test_missing_contract_block_returns_none(self) -> None:
        """Scope template without per_query_report_contract — V28/V29
        continue working."""
        template = {"other_fields": {"anything": 1}}
        result = load_report_contract_for_slug(template, "test_slug")
        assert result is None

    def test_none_template_returns_none(self) -> None:
        assert load_report_contract_for_slug(None, "test_slug") is None

    def test_empty_slug_returns_none(self) -> None:
        template = _template_with_contract(_single_entity_contract())
        assert load_report_contract_for_slug(template, "") is None
        assert load_report_contract_for_slug(template, "   ") is None

    def test_non_string_slug_returns_none(self) -> None:
        template = _template_with_contract(_single_entity_contract())
        assert load_report_contract_for_slug(template, 42) is None  # type: ignore
        assert load_report_contract_for_slug(template, None) is None  # type: ignore


# ─────────────────────────────────────────────────────────────────────
# (8) Malformed top-level shapes
# ─────────────────────────────────────────────────────────────────────
class TestMalformedShapes:
    def test_contract_block_not_dict_raises(self) -> None:
        template = {"per_query_report_contract": ["not", "a", "dict"]}
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "per_query_report_contract" in exc.value.path

    def test_slug_block_not_dict_raises(self) -> None:
        template = {
            "per_query_report_contract": {
                "test_slug": "not a dict",
            }
        }
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "test_slug" in exc.value.path

    def test_entities_not_list_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"] = {"not": "list"}
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_entities" in exc.value.path

    def test_empty_entities_list_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"] = []
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError):
            load_report_contract_for_slug(template, "test_slug")

    def test_slots_not_dict_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["rendering_slots"] = []
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slots" in exc.value.path

    def test_empty_slots_dict_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["rendering_slots"] = {}
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError):
            load_report_contract_for_slug(template, "test_slug")

    def test_required_fields_with_empty_string_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["required_fields"] = [
            "valid", "", "also_valid"
        ]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_fields" in exc.value.path

    def test_empty_required_fields_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["required_fields"] = []
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError):
            load_report_contract_for_slug(template, "test_slug")

    def test_required_fields_with_non_string_element_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["required_entities"][0]["required_fields"] = [
            "N", 42, "primary_endpoint"
        ]
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "required_fields" in exc.value.path

    def test_slot_required_non_bool_raises(self) -> None:
        """Reject non-bool `required:` to keep slot-gating semantics
        unambiguous."""
        contract = _single_entity_contract()
        contract["test_slug"]["rendering_slots"]["s1"]["required"] = "yes"
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slots.s1.required" in exc.value.path

    def test_slot_ordering_non_int_raises(self) -> None:
        contract = _single_entity_contract()
        contract["test_slug"]["rendering_slots"]["s1"]["ordering"] = "1"
        template = _template_with_contract(contract)
        with pytest.raises(ContractSchemaError) as exc:
            load_report_contract_for_slug(template, "test_slug")
        assert "rendering_slots.s1.ordering" in exc.value.path


# ─────────────────────────────────────────────────────────────────────
# (9) Integration: load the REAL clinical.yaml contract
# ─────────────────────────────────────────────────────────────────────
class TestRealClinicalYaml:
    """Load the real `config/scope_templates/clinical.yaml` contract
    (15 pivotal trials + mechanism + regulatories). Guards against
    schema-drift in the actual shipped contract."""

    @pytest.fixture(scope="class")
    def clinical_template(self) -> dict:
        path = Path("config/scope_templates/clinical.yaml")
        assert path.exists(), f"real contract missing at {path}"
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_clinical_tirzepatide_t2dm_loads(
        self, clinical_template: dict
    ) -> None:
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        assert contract is not None
        assert contract.slug == "clinical_tirzepatide_t2dm"
        assert contract.schema_version == "v30.1"

    def test_clinical_has_15_entities(
        self, clinical_template: dict
    ) -> None:
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        assert len(contract.required_entities) == 15

    def test_clinical_has_15_slots(self, clinical_template: dict) -> None:
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        assert len(contract.rendering_slots) == 15

    def test_clinical_surpass_trials_present(
        self, clinical_template: dict
    ) -> None:
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        by_id = contract.entities_by_id()
        for tid in [
            "surpass_1_primary", "surpass_2_primary", "surpass_3_primary",
            "surpass_4_primary", "surpass_5_primary", "surpass_6_primary",
            "surpass_cvot_primary", "surmount_2_primary",
        ]:
            assert tid in by_id, f"missing trial {tid}"
            assert by_id[tid].type == "pivotal_trial"

    def test_clinical_surpass_2_doi_correct(
        self, clinical_template: dict
    ) -> None:
        """Anchor: Frías et al., NEJM 2021."""
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        e = contract.entities_by_id()["surpass_2_primary"]
        assert e.doi == "10.1056/NEJMoa2107519"
        assert e.pmid == 34010531
        assert e.journal == "NEJM"
        assert e.anchor == "SURPASS-2"

    def test_clinical_mechanism_clamp_present(
        self, clinical_template: dict
    ) -> None:
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        by_id = contract.entities_by_id()
        assert "thomas_clamp_2022" in by_id
        e = by_id["thomas_clamp_2022"]
        assert e.type == "mechanism_primary"
        assert e.doi == "10.1016/S2213-8587(22)00041-1"

    def test_clinical_regulatory_entities_present(
        self, clinical_template: dict
    ) -> None:
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        by_id = contract.entities_by_id()
        expected = [
            "fda_mounjaro_label", "fda_zepbound_label", "ema_mounjaro_epar",
            "nice_ta924_t2d", "nice_ta1026_obesity", "hc_mounjaro_monograph",
        ]
        for rid in expected:
            assert rid in by_id, f"missing regulatory {rid}"
            assert by_id[rid].type == "regulatory"

    def test_clinical_all_entities_have_valid_slot(
        self, clinical_template: dict
    ) -> None:
        """Ref-integrity guard on the real contract: loader already
        enforces this, but confirm that clinical.yaml actually
        passes (no dangling rendering_slot pointers)."""
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        slot_ids = {s.id for s in contract.rendering_slots}
        for e in contract.required_entities:
            assert e.rendering_slot in slot_ids, (
                f"entity {e.id} references unknown slot {e.rendering_slot!r}"
            )

    def test_clinical_slot_ordering_unique_within_section(
        self, clinical_template: dict
    ) -> None:
        """Sanity: within a section, orderings should be distinct.
        (Not required by M-54 loader, but if violated, M-57 planner
        will render slots non-deterministically.)"""
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm"
        )
        by_section: dict[str, list[int]] = {}
        for s in contract.rendering_slots:
            by_section.setdefault(s.section, []).append(s.ordering)
        for section, orderings in by_section.items():
            assert len(orderings) == len(set(orderings)), (
                f"duplicate ordering in section {section!r}: {orderings}"
            )
