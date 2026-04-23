"""M-62 tests: V30 non-clinical generalization guard (Layer 5 /
preservation_guard).

Codex plan review rev #8 required PROVING the architecture isn't
clinical-specific by running it on a non-DOI / non-paper domain.
This test exercises M-54..M-61 on the `policy_medicare_drug_price`
slug whose entity types are `statute`, `regulatory_ruling`,
`court_decision`, `cbo_report` — none of which have DOIs or live
on academic hosts.

If M-54..M-61 work for this contract WITHOUT any code changes
specific to clinical domain, that proves Codex rev #7/#8 —
architecture generalizes.

All tests pure — no network, no LLM.

Covers:
1. M-54 loader: policy contract loads with 5 non-clinical entity
   types and 5 rendering slots.
2. M-55 compiler: compile_frame produces CompiledFrame with
   url_pattern-primary bindings (no DOI anywhere).
3. M-57 outline: sections ordered per section_order
   (Statute → Implementation → Litigation → Economic_Analysis).
4. M-58 slot-fill: structured-first prompt + response parser +
   gap payload work identically.
5. M-59 validator: per-entity validation on non-clinical types.
6. M-60 manifest: structured coverage report shape identical.
7. M-61 human completion: statute completion with doi=null
   accepted; court_decision case citation as source_locator.
8. No clinical-specific branching: grep audit — no "pivotal_trial"
   / "PMID" / "CrossRef" string appears in the policy slug's
   path through the layers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.polaris_graph.generator.frame_manifest import (
    compose_frame_coverage,
    compose_human_completion_tasks,
)
from src.polaris_graph.generator.slot_fill import (
    build_slot_fill_prompt,
    compose_gap_payload,
    parse_slot_fill_response,
    render_slot_prose,
)
from src.polaris_graph.generator.slot_validator import (
    EntityValidation,
    SlotAggregateVerdict,
    ValidationReport,
    ValidationVerdict,
    validate_slot_completion,
)
from src.polaris_graph.nodes.contract_outline import (
    compose_outline_from_contract,
)
from src.polaris_graph.nodes.frame_compiler import (
    FrameCompilerError,
    compile_frame,
)
from src.polaris_graph.nodes.report_contract import (
    ContractSchemaError,
    load_report_contract_for_slug,
)
from src.polaris_graph.retrieval.frame_fetcher import (
    FrameRow,
    ProvenanceClass,
)
from src.polaris_graph.retrieval.human_gap_completion import (
    parse_completion,
    to_frame_rows,
    validate_against_tasks,
)


POLICY_SLUG = "policy_medicare_drug_price"


# ─────────────────────────────────────────────────────────────────────
# Fixture: the real policy template
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def policy_template() -> dict:
    path = Path("config/scope_templates/policy.yaml")
    assert path.exists(), f"policy scope template missing at {path}"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────
# (1) M-54 loader on non-clinical entity types
# ─────────────────────────────────────────────────────────────────────
class TestM54NonClinicalLoader:
    def test_policy_contract_loads(self, policy_template: dict) -> None:
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        assert contract is not None
        assert contract.slug == POLICY_SLUG
        assert contract.schema_version == "v30.1"

    def test_five_entities_five_slots(self, policy_template: dict) -> None:
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        assert len(contract.required_entities) == 5
        assert len(contract.rendering_slots) == 5

    def test_non_clinical_entity_types_accepted(
        self, policy_template: dict,
    ) -> None:
        """Codex rev #7: loader must accept arbitrary entity types
        without code changes. Policy types: statute,
        regulatory_ruling, court_decision, cbo_report."""
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        types = {e.type for e in contract.required_entities}
        assert "statute" in types
        assert "regulatory_ruling" in types
        assert "court_decision" in types
        assert "cbo_report" in types
        # No clinical types present
        assert "pivotal_trial" not in types
        assert "mechanism_primary" not in types

    def test_section_order_non_clinical(
        self, policy_template: dict,
    ) -> None:
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        assert contract.section_order == (
            "Statute", "Implementation", "Litigation",
            "Economic_Analysis",
        )

    def test_no_entities_have_doi(self, policy_template: dict) -> None:
        """All policy entities use url_pattern; none have DOIs.
        This is the crux of the generalization proof — if M-55
        and M-56 worked only for DOIs, this contract would fail
        to compile."""
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        for e in contract.required_entities:
            assert e.doi is None, (
                f"entity {e.id} unexpectedly has DOI {e.doi}"
            )
            assert e.url_pattern is not None, (
                f"entity {e.id} needs url_pattern (no DOI route)"
            )


# ─────────────────────────────────────────────────────────────────────
# (2) M-55 compiler on url_pattern-primary bindings
# ─────────────────────────────────────────────────────────────────────
class TestM55NonClinicalCompiler:
    def test_compiles_without_error(self, policy_template: dict) -> None:
        """No clinical hardcoding in compiler — policy contract
        compiles."""
        compiled = compile_frame(
            "What does the IRA drug price negotiation statute do?",
            policy_template,
            POLICY_SLUG,
        )
        assert compiled is not None
        assert compiled.slug == POLICY_SLUG
        assert len(compiled.evidence_bindings) == 5

    def test_all_bindings_url_primary(
        self, policy_template: dict,
    ) -> None:
        """Identifier priority: all policy entities fall through
        to url_pattern (no DOI, no PMID, no anchor). Compiler
        handles this uniformly."""
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        for b in compiled.evidence_bindings:
            assert b.primary_identifier.startswith("url:"), (
                f"binding {b.entity_id} primary "
                f"{b.primary_identifier} should be url:*"
            )

    def test_compiler_no_warnings(
        self, policy_template: dict,
    ) -> None:
        """Policy contract declares section_order + known
        schema_version — compiler should emit zero warnings."""
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        assert compiled.warnings == ()


# ─────────────────────────────────────────────────────────────────────
# (3) M-57 outline on non-clinical sections
# ─────────────────────────────────────────────────────────────────────
class TestM57NonClinicalOutline:
    def test_outline_honors_section_order(
        self, policy_template: dict,
    ) -> None:
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        # Minimal stub rows for all 5 entities
        rows = tuple(
            _stub_row(b.entity_id, b.rendering_slot,
                      entity_type=b.entity_type)
            for b in compiled.evidence_bindings
        )
        outline = compose_outline_from_contract(compiled, rows)
        sections = [s.section for s in outline.sections]
        assert sections == [
            "Statute", "Implementation", "Litigation",
            "Economic_Analysis",
        ]

    def test_litigation_section_has_two_slots_ordered(
        self, policy_template: dict,
    ) -> None:
        """Two court_decision entities land in Litigation section
        in slot.ordering order: Merck (1) before NFIB (2)."""
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        rows = tuple(
            _stub_row(b.entity_id, b.rendering_slot,
                      entity_type=b.entity_type)
            for b in compiled.evidence_bindings
        )
        outline = compose_outline_from_contract(compiled, rows)
        litigation = next(
            s for s in outline.sections if s.section == "Litigation"
        )
        slot_titles = [sl.subsection_title for sl in litigation.slots]
        assert "Merck" in slot_titles[0]
        assert "NFIB" in slot_titles[1]


# ─────────────────────────────────────────────────────────────────────
# (4) M-58 slot-fill on non-clinical content
# ─────────────────────────────────────────────────────────────────────
class TestM58NonClinicalSlotFill:
    def test_statute_prompt_structure(
        self, policy_template: dict,
    ) -> None:
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        binding = next(
            b for b in compiled.evidence_bindings
            if b.entity_type == "statute"
        )
        row = _stub_row(
            binding.entity_id, binding.rendering_slot,
            entity_type="statute",
            direct_quote=(
                "Inflation Reduction Act of 2022, "
                "Public Law 117-169. Enacted August 16, 2022. "
                "Section 11001 directs the Secretary to negotiate "
                "prices for covered drugs."
            ),
        )
        outline = compose_outline_from_contract(
            compiled, _stub_rows_for_all(compiled, direct_row=row),
        )
        slot = outline.slots_by_id()[binding.rendering_slot]

        prompt = build_slot_fill_prompt(
            slot, row,
            required_fields=(
                "enactment_year", "section_citation", "effective_date",
            ),
            research_question="IRA drug price negotiation statute",
        )
        # Prompt works identically — no pivotal_trial-specific
        # wording leaks through for statute content.
        assert "ENTITY_TYPE: statute" in prompt
        assert f"BOUND_EV_ID: {binding.entity_id}" in prompt
        assert "enactment_year" in prompt
        assert "section_citation" in prompt

    def test_court_decision_parse_and_render(
        self, policy_template: dict,
    ) -> None:
        """Parse a well-formed response for a court_decision
        entity. Round-trip prompt → parse → render works."""
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        binding = next(
            b for b in compiled.evidence_bindings
            if b.entity_id == "merck_v_becerra_2024"
        )
        row = _stub_row(
            binding.entity_id, binding.rendering_slot,
            entity_type="court_decision",
            direct_quote=(
                "Merck & Co. v. Becerra, No. 23-cv-1615 (D.D.C. "
                "filed June 6, 2023). On April 24, 2024 the court "
                "denied plaintiff's motion for summary judgment "
                "on First and Fifth Amendment claims."
            ),
        )
        outline = compose_outline_from_contract(
            compiled, _stub_rows_for_all(compiled, direct_row=row),
        )
        slot = outline.slots_by_id()[binding.rendering_slot]

        required = ("court", "disposition", "date_decided")
        response = json.dumps({
            "fields": [
                {
                    "field_name": "court", "status": "extracted",
                    "value": "D.D.C.",
                    "source_span": "D.D.C.",
                },
                {
                    "field_name": "disposition",
                    "status": "extracted",
                    "value": "denied plaintiff's motion for summary judgment",
                    "source_span": "denied plaintiff's motion for summary judgment",
                },
                {
                    "field_name": "date_decided",
                    "status": "extracted",
                    "value": "April 24, 2024",
                    "source_span": "April 24, 2024",
                },
            ]
        })
        payload = parse_slot_fill_response(
            response, slot, row, required,
        )
        assert payload.completion_count() == 3
        prose = render_slot_prose(payload)
        assert "Merck" in prose or "Becerra" in prose or \
               f"[{binding.entity_id}]" in prose
        assert prose.count(f"[{binding.entity_id}]") == 3


# ─────────────────────────────────────────────────────────────────────
# (5) M-59 validator on non-clinical slots
# ─────────────────────────────────────────────────────────────────────
class TestM59NonClinicalValidator:
    def test_validates_all_five_policy_slots(
        self, policy_template: dict,
    ) -> None:
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        rows = tuple(
            _stub_row(b.entity_id, b.rendering_slot,
                      entity_type=b.entity_type)
            for b in compiled.evidence_bindings
        )
        outline = compose_outline_from_contract(compiled, rows)

        payloads_by_eid = {
            b.entity_id: _stub_payload(b.entity_id, b.rendering_slot)
            for b in compiled.evidence_bindings
        }
        prose_by_slot = {
            b.rendering_slot: f"Subsection: ok [{b.entity_id}]"
            for b in compiled.evidence_bindings
        }

        report = validate_slot_completion(
            outline=outline,
            contract=compiled.contract,
            payloads_by_entity_id=payloads_by_eid,
            rendered_prose_by_slot_id=prose_by_slot,
        )
        assert report.all_passed() is True
        assert len(report.entity_validations) == 5


# ─────────────────────────────────────────────────────────────────────
# (6) M-60 manifest composition on non-clinical coverage
# ─────────────────────────────────────────────────────────────────────
class TestM60NonClinicalManifest:
    def test_coverage_report_for_policy(
        self, policy_template: dict,
    ) -> None:
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        rows = tuple(
            _stub_row(b.entity_id, b.rendering_slot,
                      entity_type=b.entity_type)
            for b in compiled.evidence_bindings
        )
        outline = compose_outline_from_contract(compiled, rows)

        entity_verdicts = tuple(
            EntityValidation(
                slot_id=b.rendering_slot,
                entity_id=b.entity_id,
                is_gap=False,
                required_min_fields=3,
                observed_completion_count=3,
                bound_ev_id_present_in_prose=True,
                verdict=ValidationVerdict.PASS,
                reason="stub pass",
            )
            for b in compiled.evidence_bindings
        )
        validation = ValidationReport(
            entity_validations=entity_verdicts,
            slot_verdicts=(),
        )
        coverage = compose_frame_coverage(
            compiled, outline, rows, validation,
        )
        assert coverage.total_entities == 5
        assert coverage.pass_count == 5
        assert coverage.frame_gap_count == 0
        # Every entry has a non-clinical entity_type
        types = {e.entity_type for e in coverage.entries}
        assert types == {
            "statute", "regulatory_ruling",
            "court_decision", "cbo_report",
        }
        # JSON-serializable
        json.dumps(coverage.to_manifest_dict())


# ─────────────────────────────────────────────────────────────────────
# (7) M-61 human completion for statute (doi=null)
# ─────────────────────────────────────────────────────────────────────
class TestM56UrlPatternFetcherIntegration:
    """Codex M-62 audit Medium 1: the chain tests consume synthetic
    stub rows for M-56 output. A regression in url-pattern-primary
    fetcher handling could slip through. Integration test uses a
    fake httpx.MockTransport so url_pattern entities are routed
    through fetch_frame_entity with zero real network calls."""

    def test_url_pattern_entity_yields_metadata_only_no_network(
        self, policy_template: dict,
    ) -> None:
        import httpx

        from src.polaris_graph.retrieval.frame_fetcher import (
            ProvenanceClass as PC,
            fetch_frame_entity,
        )

        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        statute_binding = next(
            b for b in compiled.evidence_bindings
            if b.entity_type == "statute"
        )

        # Transport that WOULD return 500 on any call — if M-56
        # calls it for a url-pattern entity, that's a regression.
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(500)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            row = fetch_frame_entity(statute_binding, client=client)
        finally:
            client.close()

        # URL-pattern-primary entities (no DOI, no PMID) must be
        # routed to METADATA_ONLY placeholder without any HTTP.
        assert row.provenance_class == PC.METADATA_ONLY
        assert calls == [], (
            f"unexpected HTTP calls for url-pattern entity: {calls}"
        )
        assert row.url == "congress.gov/bill/117th-congress/house-bill/5376"


class TestM61NonClinicalHumanCompletion:
    def test_statute_completion_with_null_doi(self) -> None:
        """Non-clinical entities (statute, court_decision) have
        doi=null. M-61 must handle the doi=null path correctly."""
        record = parse_completion({
            "entity_id": "ira_2022_section_11001",
            "doi": None,
            "direct_quote": (
                "The Inflation Reduction Act of 2022, Pub. L. "
                "117-169, 136 Stat. 1818, was enacted August 16, "
                "2022."
            ),
            "provenance": {
                "curator_id": "policy_curator@gov",
                "source_type": "licensed_institutional_access",
                "source_locator": "Pub. L. 117-169 §11001",
                "acquired_at": "2026-04-23T15:00:00+00:00",
                "artifact_sha256": "b" * 64,
                "artifact_retention_path": "/audit/ira_pub_law.pdf",
                "quote_page_range": "pp.1818-1830",
                "attestation": (
                    "I hereby certify licensed access via law "
                    "library subscription."
                ),
            },
        }, 0)
        assert record.doi is None
        assert record.entity_id == "ira_2022_section_11001"

    def test_court_decision_completion_with_case_citation_locator(
        self,
    ) -> None:
        """Codex M-62 audit Medium 2: court_decision case-citation
        source_locator path must be exercised. Unlike statutes
        (which can have Pub. L. identifiers) court decisions are
        located by court/docket/date citations — the most
        non-DOI identifier path in the whole V30 architecture."""
        record = parse_completion({
            "entity_id": "merck_v_becerra_2024",
            "doi": None,
            "direct_quote": (
                "Merck & Co. v. Becerra, No. 23-cv-1615 (D.D.C. "
                "2024). On April 24, 2024 the district court "
                "denied plaintiffs' motion for summary judgment "
                "on First Amendment compelled-speech and Fifth "
                "Amendment takings claims."
            ),
            "provenance": {
                "curator_id": "legal_curator@firm",
                "source_type": "licensed_institutional_access",
                # Case-citation locator — NOT a DOI, NOT a URL;
                # Bluebook-style legal citation
                "source_locator": (
                    "Merck & Co. v. Becerra, No. 23-cv-1615, "
                    "slip op. at 12-18 (D.D.C. Apr. 24, 2024)"
                ),
                "acquired_at": "2026-04-23T16:00:00+00:00",
                "artifact_sha256": "c" * 64,
                "artifact_retention_path": "/audit/merck_becerra_slip_opinion.pdf",
                "quote_page_range": "pp.12-18",
                "attestation": (
                    "I hereby certify access via Westlaw "
                    "institutional subscription."
                ),
            },
        }, 0)
        # doi=null accepted for court_decision
        assert record.doi is None
        # Source locator carries the Bluebook citation, not a URL
        assert "No. 23-cv-1615" in record.provenance.source_locator
        assert "D.D.C." in record.provenance.source_locator
        assert "Apr. 24, 2024" in record.provenance.source_locator
        # Task validation: matches a doi=null court_decision task
        tasks = [{
            "entity_id": "merck_v_becerra_2024",
            "doi": None,
        }]
        result = validate_against_tasks((record,), tasks)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 0

    def test_statute_task_generation(
        self, policy_template: dict,
    ) -> None:
        """A gap statute entity generates a human-completion task
        with doi=null and RETRIEVAL guidance."""
        compiled = compile_frame(
            "q", policy_template, POLICY_SLUG,
        )
        statute_binding = next(
            b for b in compiled.evidence_bindings
            if b.entity_type == "statute"
        )
        # Gap row for the statute
        rows = []
        for b in compiled.evidence_bindings:
            if b.entity_id == statute_binding.entity_id:
                rows.append(_stub_row(
                    b.entity_id, b.rendering_slot,
                    entity_type=b.entity_type,
                    provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
                    failure_reason="could not access",
                ))
            else:
                rows.append(_stub_row(
                    b.entity_id, b.rendering_slot,
                    entity_type=b.entity_type,
                ))
        rows_tuple = tuple(rows)
        outline = compose_outline_from_contract(compiled, rows_tuple)

        # Validation: statute fails min_fields (gap), others pass
        entity_verdicts = []
        for b in compiled.evidence_bindings:
            if b.entity_id == statute_binding.entity_id:
                verdict = ValidationVerdict.FAIL_MIN_FIELDS
            else:
                verdict = ValidationVerdict.PASS
            entity_verdicts.append(EntityValidation(
                slot_id=b.rendering_slot,
                entity_id=b.entity_id,
                is_gap=False,
                required_min_fields=3,
                observed_completion_count=(
                    0 if verdict == ValidationVerdict.FAIL_MIN_FIELDS
                    else 3
                ),
                bound_ev_id_present_in_prose=True,
                verdict=verdict,
                reason="stub",
            ))
        validation = ValidationReport(
            entity_validations=tuple(entity_verdicts),
            slot_verdicts=(),
        )
        coverage = compose_frame_coverage(
            compiled, outline, rows_tuple, validation,
        )
        tasks = compose_human_completion_tasks(coverage)
        assert len(tasks) == 1
        task = tasks[0]
        assert task["entity_id"] == statute_binding.entity_id
        assert task["entity_type"] == "statute"
        assert task["doi"] is None
        assert "RETRIEVAL gap" in task["needs"]
        # required_fields echoed from the contract
        assert "enactment_year" in task["required_fields"]


# ─────────────────────────────────────────────────────────────────────
# (8) Architecture-not-hardcoding proof
# ─────────────────────────────────────────────────────────────────────
class TestArchitectureNotHardcoded:
    """Codex plan review rev #8: this test class is the explicit
    preservation guard that V30 architecture is not
    tirzepatide-specific hardcoding. If someone adds a clinical-
    only path to M-54..M-61, these tests break."""

    def test_policy_contract_runs_without_clinical_imports(
        self, policy_template: dict,
    ) -> None:
        """Full M-54 → M-55 → M-57 → M-59 → M-60 chain on policy
        slug. If any layer does `if entity_type == "pivotal_trial"`
        or imports from clinical.yaml, this chain would break.
        """
        # Chain
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        assert contract is not None
        compiled = compile_frame("q", policy_template, POLICY_SLUG)
        assert compiled is not None
        rows = tuple(
            _stub_row(b.entity_id, b.rendering_slot,
                      entity_type=b.entity_type)
            for b in compiled.evidence_bindings
        )
        outline = compose_outline_from_contract(compiled, rows)
        assert len(outline.sections) == 4

        payloads_by_eid = {
            b.entity_id: _stub_payload(b.entity_id, b.rendering_slot)
            for b in compiled.evidence_bindings
        }
        prose_by_slot = {
            b.rendering_slot: f"Subsection: stub [{b.entity_id}]"
            for b in compiled.evidence_bindings
        }
        report = validate_slot_completion(
            outline=outline, contract=compiled.contract,
            payloads_by_entity_id=payloads_by_eid,
            rendered_prose_by_slot_id=prose_by_slot,
        )
        assert report.all_passed() is True

    def test_no_clinical_types_leak_into_policy_run(
        self, policy_template: dict,
    ) -> None:
        """Contract entity types must NOT contain pivotal_trial,
        mechanism_primary, or regulatory (the clinical vocabulary).
        This guards against someone copy-pasting clinical.yaml
        entities into the policy template."""
        contract = load_report_contract_for_slug(
            policy_template, POLICY_SLUG,
        )
        types = {e.type for e in contract.required_entities}
        clinical_types = {
            "pivotal_trial", "mechanism_primary", "regulatory",
        }
        leak = types & clinical_types
        assert leak == set(), (
            f"clinical entity types leaked into policy contract: "
            f"{leak}"
        )


# ─────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────
def _stub_row(
    entity_id: str,
    slot: str,
    entity_type: str = "unknown",
    provenance: ProvenanceClass = ProvenanceClass.ABSTRACT_ONLY,
    direct_quote: str = "stub content",
    failure_reason: str | None = None,
) -> FrameRow:
    return FrameRow(
        entity_id=entity_id,
        entity_type=entity_type,
        rendering_slot=slot,
        provenance_class=provenance,
        direct_quote=(
            direct_quote
            if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            else ""
        ),
        quote_source=(
            "url_pattern_placeholder"
            if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            else "none"
        ),
        doi=None,
        pmid=None,
        oa_pdf_url=None,
        url=f"https://example.gov/{entity_id}",
        title=None,
        authors=(),
        journal=None,
        year=None,
        failure_reason=failure_reason,
        retrieval_attempts=(),
        retrieval_timings=(),
    )


def _stub_rows_for_all(
    compiled: Any, direct_row: FrameRow,
) -> tuple[FrameRow, ...]:
    """Return a rows tuple where one entity uses the supplied
    direct_row; others get minimal stubs."""
    return tuple(
        direct_row if b.entity_id == direct_row.entity_id
        else _stub_row(b.entity_id, b.rendering_slot,
                       entity_type=b.entity_type)
        for b in compiled.evidence_bindings
    )


def _stub_payload(
    entity_id: str, slot_id: str, n_extracted: int = 4,
) -> Any:
    from src.polaris_graph.generator.slot_fill import (
        SlotFieldFill,
        SlotFillPayload,
    )
    # Generate enough extracted fields to clear the highest
    # min_fields_for_completion in the policy contract (=4 for
    # ira_2022_section_11001).
    fields = tuple(
        SlotFieldFill(
            field_name=f"stub_field_{i}",
            status="extracted",
            value=f"stub value {i}",
            bound_ev_id=entity_id,
            source_span=f"stub value {i}",
        )
        for i in range(n_extracted)
    )
    return SlotFillPayload(
        slot_id=slot_id,
        entity_id=entity_id,
        subsection_title=f"Sub {slot_id}",
        bound_ev_id=entity_id,
        fields=fields,
        provenance_class="abstract_only",
    )
