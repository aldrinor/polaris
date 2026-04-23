"""M-58 tests: V30 slot-bound generator (structured-first).

Layer 4a of V30 Report Contract Architecture. Codex plan rev #1
required structured-first over prose-first: each slot emits a
machine-readable field payload (extracted | not_extractable |
gap_unrecoverable) before prose is rendered.

All tests pure — no LLM calls, no network. LLM response text is
provided as fixtures simulating what a well-behaved model would
return per the prompt contract.

Covers:
1. build_slot_fill_prompt — deterministic prompt structure.
2. parse_slot_fill_response — happy paths (extracted + not_extractable).
3. parse_slot_fill_response — failure paths (missing field,
   extra field, bad status, source_span not substring, bad types).
4. compose_gap_payload — gap row → all-gap payload, no LLM.
5. render_slot_prose — deterministic prose output.
6. Entity-type-agnostic: statute / dft_primary / novel types
   produce structured fills unchanged.
7. Integration: round-trip prompt → simulated LLM JSON → parse →
   render on a real clinical slot.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator.slot_fill import (
    SlotFieldFill,
    SlotFillParseError,
    SlotFillPayload,
    build_slot_fill_prompt,
    compose_gap_payload,
    parse_slot_fill_response,
    render_slot_prose,
)
from src.polaris_graph.nodes.contract_outline import ContractSlotPlan
from src.polaris_graph.retrieval.frame_fetcher import (
    FrameRow,
    ProvenanceClass,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _slot_plan(
    slot_id: str = "efficacy_surpass_2",
    section: str = "Efficacy",
    subsection: str = "SURPASS-2 (Frias et al., NEJM 2021)",
    entity_ids: tuple[str, ...] = ("surpass_2_primary",),
) -> ContractSlotPlan:
    return ContractSlotPlan(
        slot_id=slot_id,
        section=section,
        subsection_title=subsection,
        ordering=2,
        entity_ids=entity_ids,
        provenance_classes=("abstract_only",),
        is_gap=False,
        is_partial=False,
    )


def _frame_row(
    entity_id: str = "surpass_2_primary",
    provenance: ProvenanceClass = ProvenanceClass.ABSTRACT_ONLY,
    quote: str = (
        "SURPASS-2 enrolled N=1879 participants with T2D. "
        "Primary endpoint: change in HbA1c at 40 weeks. "
        "ETD vs semaglutide 1mg was -0.47% (95% CI -0.59 to -0.35). "
        "Safety: GI events more common with tirzepatide."
    ),
    entity_type: str = "pivotal_trial",
) -> FrameRow:
    return FrameRow(
        entity_id=entity_id,
        entity_type=entity_type,
        rendering_slot="efficacy_surpass_2",
        provenance_class=provenance,
        direct_quote=quote if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE else "",
        quote_source="crossref_abstract" if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE else "none",
        doi="10.1056/NEJMoa2107519",
        pmid="34010531",
        oa_pdf_url=None,
        url=None,
        title="Tirzepatide versus Semaglutide Once Weekly",
        authors=("Frias JP", "Davies MJ"),
        journal="NEJM",
        year=2021,
        failure_reason=None if provenance != ProvenanceClass.FRAME_GAP_UNRECOVERABLE else "all sources failed",
        retrieval_attempts=(),
        retrieval_timings=(),
    )


def _well_formed_response(required_fields: tuple[str, ...]) -> str:
    """Simulate an LLM response per the prompt contract. All fields
    are extracted with source_spans that ARE substrings of the
    fixture quote."""
    field_to_extract = {
        "N": ("1879", "N=1879"),
        "population": ("T2D", "T2D"),
        "primary_endpoint": (
            "change in HbA1c at 40 weeks",
            "change in HbA1c at 40 weeks",
        ),
        "etd_with_uncertainty": (
            "-0.47% (95% CI -0.59 to -0.35)",
            "-0.47% (95% CI -0.59 to -0.35)",
        ),
    }
    fields = []
    for fname in required_fields:
        if fname in field_to_extract:
            val, span = field_to_extract[fname]
            fields.append({
                "field_name": fname,
                "status": "extracted",
                "value": val,
                "source_span": span,
            })
        else:
            fields.append({
                "field_name": fname,
                "status": "not_extractable",
                "value": None,
                "source_span": None,
            })
    return json.dumps({"fields": fields})


# ─────────────────────────────────────────────────────────────────────
# (1) Prompt construction
# ─────────────────────────────────────────────────────────────────────
class TestBuildPrompt:
    def test_basic_prompt_structure(self) -> None:
        slot = _slot_plan()
        row = _frame_row()
        prompt = build_slot_fill_prompt(
            slot, row,
            required_fields=("N", "primary_endpoint"),
            research_question="Is tirzepatide effective for T2D?",
        )
        # Structural markers
        assert "BOUND_EV_ID: surpass_2_primary" in prompt
        assert "SUBSECTION: SURPASS-2" in prompt
        assert "SECTION: Efficacy" in prompt
        assert "PROVENANCE: abstract_only" in prompt
        assert "DIRECT_QUOTE:" in prompt
        assert "SURPASS-2 enrolled" in prompt  # quote embedded
        # Required fields bullet list
        assert "- N" in prompt
        assert "- primary_endpoint" in prompt
        # JSON schema present
        assert '"field_name"' in prompt
        assert "extracted | not_extractable" in prompt
        # Anti-fabrication rules
        assert "status=not_extractable" in prompt
        assert "Do NOT guess" in prompt

    def test_prompt_deterministic(self) -> None:
        slot = _slot_plan()
        row = _frame_row()
        p1 = build_slot_fill_prompt(
            slot, row, ("N",), "q",
        )
        p2 = build_slot_fill_prompt(
            slot, row, ("N",), "q",
        )
        assert p1 == p2

    def test_gap_row_raises(self) -> None:
        slot = _slot_plan()
        row = _frame_row(provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE)
        with pytest.raises(ValueError) as exc:
            build_slot_fill_prompt(slot, row, ("N",), "q")
        assert "gap" in str(exc.value).lower()

    def test_empty_required_fields_raises(self) -> None:
        with pytest.raises(ValueError):
            build_slot_fill_prompt(_slot_plan(), _frame_row(), (), "q")


# ─────────────────────────────────────────────────────────────────────
# (2) Response parsing — happy paths
# ─────────────────────────────────────────────────────────────────────
class TestParseHappy:
    def test_all_extracted(self) -> None:
        required = ("N", "primary_endpoint")
        response = _well_formed_response(required)
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), required,
        )

        assert isinstance(payload, SlotFillPayload)
        assert payload.slot_id == "efficacy_surpass_2"
        assert payload.bound_ev_id == "surpass_2_primary"
        assert payload.provenance_class == "abstract_only"
        assert len(payload.fields) == 2
        assert payload.completion_count() == 2

        by_name = payload.fields_by_name()
        assert by_name["N"].status == "extracted"
        assert by_name["N"].value == "1879"
        assert by_name["N"].source_span == "N=1879"
        assert by_name["N"].bound_ev_id == "surpass_2_primary"

    def test_mixed_extracted_and_not_extractable(self) -> None:
        required = ("N", "population", "baseline_hba1c")
        # fixture quote mentions N and T2D but NOT baseline_hba1c
        response = _well_formed_response(required)
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), required,
        )
        by_name = payload.fields_by_name()
        assert by_name["N"].status == "extracted"
        assert by_name["population"].status == "extracted"
        assert by_name["baseline_hba1c"].status == "not_extractable"
        assert by_name["baseline_hba1c"].value is None
        assert by_name["baseline_hba1c"].source_span is None
        assert payload.completion_count() == 2

    def test_fenced_json_unwraps(self) -> None:
        required = ("N",)
        inner = _well_formed_response(required)
        fenced = f"```json\n{inner}\n```"
        payload = parse_slot_fill_response(
            fenced, _slot_plan(), _frame_row(), required,
        )
        assert payload.completion_count() == 1

    def test_plain_fenced_json_unwraps(self) -> None:
        required = ("N",)
        fenced = f"```\n{_well_formed_response(required)}\n```"
        payload = parse_slot_fill_response(
            fenced, _slot_plan(), _frame_row(), required,
        )
        assert payload.completion_count() == 1


# ─────────────────────────────────────────────────────────────────────
# (3) Response parsing — failure paths
# ─────────────────────────────────────────────────────────────────────
class TestParseFailures:
    def test_invalid_json_raises(self) -> None:
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                "not JSON", _slot_plan(), _frame_row(), ("N",),
            )
        assert "invalid JSON" in str(exc.value)

    def test_root_not_object_raises(self) -> None:
        with pytest.raises(SlotFillParseError):
            parse_slot_fill_response(
                '["a", "b"]', _slot_plan(), _frame_row(), ("N",),
            )

    def test_missing_fields_key_raises(self) -> None:
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                '{}', _slot_plan(), _frame_row(), ("N",),
            )
        assert "fields" in str(exc.value)

    def test_missing_required_field_raises(self) -> None:
        # Response emits only N; required list includes population
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1879", "source_span": "N=1879"},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(),
                ("N", "population"),
            )
        assert "population" in str(exc.value)

    def test_extra_field_raises(self) -> None:
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1879", "source_span": "N=1879"},
                {"field_name": "bonus_invented",
                 "status": "extracted",
                 "value": "oops", "source_span": "SURPASS-2"},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )
        assert "bonus_invented" in str(exc.value)

    def test_invalid_status_raises(self) -> None:
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "guessed",
                 "value": "1879", "source_span": "N=1879"},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )
        assert "status" in str(exc.value)

    def test_source_span_not_in_quote_raises(self) -> None:
        """Anti-fabrication guard: LLM claimed to extract but
        source_span is not actually in direct_quote."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "99999",
                 "source_span": "this phrase is not in the quote"},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )
        assert "substring" in str(exc.value).lower()

    def test_extracted_empty_value_raises(self) -> None:
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "", "source_span": "N=1879"},
            ]
        })
        with pytest.raises(SlotFillParseError):
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )

    def test_not_extractable_with_value_raises(self) -> None:
        """Status=not_extractable MUST have value=null + source_span=null."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "not_extractable",
                 "value": "1879", "source_span": None},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )
        assert "must be null" in str(exc.value)

    def test_fabricated_value_with_real_span_raises(self) -> None:
        """Codex M-58 audit Blocker: anti-fabrication check 2.

        LLM can claim to extract `value="1880"` while citing a real
        `source_span="N=1879"` (the span IS in direct_quote, but the
        value is fabricated). Without check 2 this passed; now it
        must raise SlotFillParseError."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1880",  # fabricated
                 "source_span": "N=1879"},  # real span
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )
        msg = str(exc.value).lower()
        assert "not supported" in msg or "anti-fabrication" in msg
        assert "1880" in str(exc.value)

    def test_value_whitespace_normalization_accepted(self) -> None:
        """value='1879' with source_span='N=1879' passes via
        normalized-substring check: 'n=1879' contains '1879' after
        whitespace/case collapse."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1879",
                 "source_span": "N=1879"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), ("N",),
        )
        assert payload.fields_by_name()["N"].value == "1879"

    def test_value_case_mismatch_raises(self) -> None:
        """Codex M-58 pass-3 regression: lowercasing in
        normalization conflates case-sensitive scientific tokens.
        span='HbA1c' with value='hba1c' must RAISE now — the LLM
        must emit the verbatim casing from direct_quote. Case drift
        is a contract violation, not a tolerable LLM quirk."""
        quote = "Baseline HbA1c was 8.3%."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "marker", "status": "extracted",
                 "value": "hba1c",  # lowercase drift
                 "source_span": "HbA1c"},
            ]
        })
        with pytest.raises(SlotFillParseError):
            parse_slot_fill_response(
                response, _slot_plan(), row, ("marker",),
            )

    def test_molarity_meter_case_raises(self) -> None:
        """Codex M-58 pass-3 exact exploit repro: span='5 M' (molar
        concentration) with value='5 m' (meter) are semantically
        distinct units. The pass-2 lowercase normalization accepted
        this; pass-3 whitespace-only normalization rejects it."""
        quote = "The compound was prepared at 5 M concentration."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "concentration",
                 "status": "extracted",
                 "value": "5 m",  # WRONG — that's meters, not molar
                 "source_span": "5 M"},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), row, ("concentration",),
            )
        assert "not supported" in str(exc.value).lower()

    def test_whitespace_only_normalization_still_accepted(self) -> None:
        """Whitespace variation is the ONE form pass-3 still accepts.
        span='5\\tmg' (tab) with value='5 mg' (space) passes."""
        quote = "Administered 5\tmg weekly."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "dose", "status": "extracted",
                 "value": "5 mg",
                 "source_span": "5\tmg"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("dose",),
        )
        assert payload.fields_by_name()["dose"].value == "5 mg"

    def test_value_misbound_to_wrong_span_raises(self) -> None:
        """Codex M-58 pass-2 regression: value '10 mg' with
        source_span='5 mg' must be rejected even though '10 mg' IS
        in direct_quote elsewhere AND shares token 'mg' with the
        span. The pass-1 fallback (value ∈ direct_quote + token
        overlap) let this through; pass-2 tightens to normalized-
        substring-of-span only, which correctly rejects it."""
        quote = (
            "Dose: 5 mg daily for 4 weeks, then escalated to 10 mg "
            "for weeks 5-40."
        )
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "initial_dose", "status": "extracted",
                 "value": "10 mg",  # fabricated binding
                 "source_span": "5 mg"},  # real span, wrong value
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), row, ("initial_dose",),
            )
        msg = str(exc.value).lower()
        assert "not supported" in msg or "anti-fabrication" in msg

    def test_duplicate_field_raises(self) -> None:
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1879", "source_span": "N=1879"},
                {"field_name": "N", "status": "extracted",
                 "value": "99", "source_span": "N=1879"},
            ]
        })
        with pytest.raises(SlotFillParseError) as exc:
            parse_slot_fill_response(
                response, _slot_plan(), _frame_row(), ("N",),
            )
        assert "duplicated" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────
# (4) Gap payload
# ─────────────────────────────────────────────────────────────────────
class TestComposeGapPayload:
    def test_non_gap_row_raises(self) -> None:
        """Codex M-58 audit Medium: symmetric guard — gap composer
        must reject non-gap rows so routing bugs surface rather
        than silently erasing evidence."""
        row = _frame_row(provenance=ProvenanceClass.ABSTRACT_ONLY)
        with pytest.raises(ValueError) as exc:
            compose_gap_payload(_slot_plan(), row, ("N",))
        assert "non-gap" in str(exc.value).lower()

    def test_open_access_row_raises(self) -> None:
        row = _frame_row(provenance=ProvenanceClass.OPEN_ACCESS)
        with pytest.raises(ValueError):
            compose_gap_payload(_slot_plan(), row, ("N",))

    def test_metadata_only_row_raises(self) -> None:
        row = _frame_row(provenance=ProvenanceClass.METADATA_ONLY)
        with pytest.raises(ValueError):
            compose_gap_payload(_slot_plan(), row, ("N",))

    def test_gap_row_produces_all_gap_fields(self) -> None:
        required = ("N", "primary_endpoint", "etd_with_uncertainty")
        row = _frame_row(
            provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE
        )
        payload = compose_gap_payload(_slot_plan(), row, required)
        assert payload.provenance_class == "frame_gap_unrecoverable"
        assert len(payload.fields) == 3
        for f in payload.fields:
            assert f.status == "gap_unrecoverable"
            assert f.value is None
            assert f.source_span is None
            assert f.bound_ev_id == "surpass_2_primary"
        assert payload.completion_count() == 0


# ─────────────────────────────────────────────────────────────────────
# (5) Prose rendering — deterministic
# ─────────────────────────────────────────────────────────────────────
class TestRenderSlotProse:
    def test_extracted_fields_prose(self) -> None:
        required = ("N", "primary_endpoint")
        response = _well_formed_response(required)
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), required,
        )
        prose = render_slot_prose(payload)
        assert "SURPASS-2" in prose
        assert "N: 1879" in prose
        assert "primary_endpoint:" in prose
        assert "[surpass_2_primary]" in prose
        # Every extracted field has a citation
        assert prose.count("[surpass_2_primary]") == 2

    def test_not_extractable_phrasing(self) -> None:
        required = ("N", "baseline_hba1c")
        response = _well_formed_response(required)  # baseline missing
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), required,
        )
        prose = render_slot_prose(payload)
        assert "not extractable from available primary content" in prose
        assert "baseline_hba1c" in prose

    def test_gap_payload_prose(self) -> None:
        payload = compose_gap_payload(
            _slot_plan(),
            _frame_row(provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE),
            ("N", "primary_endpoint"),
        )
        prose = render_slot_prose(payload)
        assert "Primary publication was not retrievable" in prose
        assert "[surpass_2_primary]" in prose

    def test_render_deterministic(self) -> None:
        payload = compose_gap_payload(
            _slot_plan(),
            _frame_row(provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE),
            ("N",),
        )
        assert render_slot_prose(payload) == render_slot_prose(payload)

    def test_every_sentence_has_ev_citation(self) -> None:
        """Invariant: every emitted sentence carries [bound_ev_id].
        No silent claim without provenance."""
        required = ("N", "population", "baseline_hba1c")
        response = _well_formed_response(required)
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), required,
        )
        prose = render_slot_prose(payload)
        sentences = [s for s in prose.split(". ") if s.strip()]
        for s in sentences[1:]:  # skip header prefix
            assert "[surpass_2_primary]" in s, (
                f"sentence missing ev_id citation: {s!r}"
            )


# ─────────────────────────────────────────────────────────────────────
# (6) Entity-type-agnostic (Codex rev #7)
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    def test_statute_slot_fills(self) -> None:
        slot = _slot_plan(
            slot_id="statute_42usc_health",
            section="Law",
            subsection="42 USC Sec 1983",
        )
        row = _frame_row(
            entity_id="statute_42_usc_1983",
            entity_type="statute",
            quote=(
                "42 U.S.C. § 1983 provides a civil remedy. "
                "Enacted 1871. Standing requirement: personal injury."
            ),
        )
        required = ("enactment_year", "remedy_type", "standing")
        response = json.dumps({
            "fields": [
                {"field_name": "enactment_year", "status": "extracted",
                 "value": "1871", "source_span": "Enacted 1871"},
                {"field_name": "remedy_type", "status": "extracted",
                 "value": "civil remedy",
                 "source_span": "civil remedy"},
                {"field_name": "standing", "status": "extracted",
                 "value": "personal injury",
                 "source_span": "personal injury"},
            ]
        })
        payload = parse_slot_fill_response(
            response, slot, row, required,
        )
        assert payload.completion_count() == 3
        assert payload.bound_ev_id == "statute_42_usc_1983"
        prose = render_slot_prose(payload)
        assert "[statute_42_usc_1983]" in prose

    def test_dft_slot_fills(self) -> None:
        slot = _slot_plan(
            slot_id="dft_perovskite",
            section="Computation",
            subsection="DFT calculation (Smith et al., 2024)",
        )
        row = _frame_row(
            entity_id="dft_smith_2024",
            entity_type="dft_primary",
            quote=(
                "Band gap was calculated as 1.42 eV using PBE "
                "functional. Lattice constant 3.9 Å."
            ),
        )
        required = ("band_gap", "functional", "lattice_constant")
        response = json.dumps({
            "fields": [
                {"field_name": "band_gap", "status": "extracted",
                 "value": "1.42 eV", "source_span": "1.42 eV"},
                {"field_name": "functional", "status": "extracted",
                 "value": "PBE", "source_span": "PBE"},
                {"field_name": "lattice_constant", "status": "extracted",
                 "value": "3.9 Å", "source_span": "3.9 Å"},
            ]
        })
        payload = parse_slot_fill_response(
            response, slot, row, required,
        )
        assert payload.completion_count() == 3
        prose = render_slot_prose(payload)
        assert "band_gap: 1.42 eV" in prose


# ─────────────────────────────────────────────────────────────────────
# (7) End-to-end round trip
# ─────────────────────────────────────────────────────────────────────
class TestRoundTrip:
    def test_prompt_parse_render_chain(self) -> None:
        slot = _slot_plan()
        row = _frame_row()
        required = ("N", "population", "primary_endpoint",
                    "etd_with_uncertainty")
        # Prompt is deterministic
        prompt = build_slot_fill_prompt(slot, row, required, "q")
        assert "BOUND_EV_ID" in prompt
        # Simulated LLM response
        response = _well_formed_response(required)
        # Parse
        payload = parse_slot_fill_response(response, slot, row, required)
        assert payload.completion_count() == 4
        # Render
        prose = render_slot_prose(payload)
        assert "SURPASS-2" in prose
        assert prose.count("[surpass_2_primary]") == 4
