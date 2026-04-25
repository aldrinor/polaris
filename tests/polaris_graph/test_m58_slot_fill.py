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
    """Simulate an LLM response per the pass-5 prompt contract:
    `value` and `source_span` must be IDENTICAL verbatim substrings
    of direct_quote. No field-level truncation or rewriting."""
    field_to_extract = {
        "N": "N=1879",
        "population": "T2D",
        "primary_endpoint": "change in HbA1c at 40 weeks",
        "etd_with_uncertainty": (
            "-0.47% (95% CI -0.59 to -0.35)"
        ),
    }
    fields = []
    for fname in required_fields:
        if fname in field_to_extract:
            text = field_to_extract[fname]
            fields.append({
                "field_name": fname,
                "status": "extracted",
                "value": text,
                "source_span": text,
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
        # Pass-5: value == source_span verbatim substring contract
        assert by_name["N"].value == "N=1879"
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

    def test_source_span_not_in_quote_degrades_to_not_extractable(self) -> None:
        """Anti-fabrication preserved: LLM source_span not in
        direct_quote → field downgraded to not_extractable
        (M-69 Fix #5)."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "99999",
                 "source_span": "this phrase is not in the quote"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), ("N",),
        )
        f = payload.fields_by_name()["N"]
        assert f.status == "not_extractable"
        assert f.value is None

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

    def test_fabricated_value_with_real_span_degrades_to_not_extractable(self) -> None:
        """Codex M-58 audit Blocker: anti-fabrication check 2.
        Fabricated value with real source_span downgrades to
        not_extractable (M-69 Fix #5) — anti-fabrication preserved
        because the fabricated value never lands in payload."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1880",  # fabricated
                 "source_span": "N=1879"},  # real span
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), ("N",),
        )
        f = payload.fields_by_name()["N"]
        assert f.status == "not_extractable"
        assert f.value is None  # 1880 never made it through

    def test_value_substring_of_span_degrades_to_not_extractable(self) -> None:
        """Pass-5 contract: value and source_span must be IDENTICAL.
        Subset drift downgrades to not_extractable (M-69 Fix #5)."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1879",  # subset of span
                 "source_span": "N=1879"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), ("N",),
        )
        assert payload.fields_by_name()["N"].status == "not_extractable"

    def test_value_case_mismatch_degrades_to_not_extractable(self) -> None:
        """Pass-3: case drift between value and source_span fails.
        M-69 Fix #5 downgrade preserves anti-fabrication."""
        quote = "Baseline HbA1c was 8.3%."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "marker", "status": "extracted",
                 "value": "hba1c",  # lowercase drift
                 "source_span": "HbA1c"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("marker",),
        )
        assert payload.fields_by_name()["marker"].status == "not_extractable"

    def test_m69_fix5_one_bad_field_does_not_kill_siblings(self) -> None:
        """V30 Phase-2 M-69 Fix #5 (Codex run-10 audit — SURMOUNT-2
        regression): when ONE field fails anti-fabrication, the
        remaining VALID fields must still extract. Pre-fix
        behaviour raised SlotFillParseError → caller fell back to
        all-not_extractable payload, killing 9 valid fields."""
        quote = (
            "SURPASS-2 enrolled N=1879 participants. Primary "
            "endpoint: HbA1c at 40 weeks."
        )
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                # Valid: source_span and value both verbatim
                {"field_name": "N", "status": "extracted",
                 "value": "N=1879", "source_span": "N=1879"},
                # Invalid: value not in source_span (subset drift)
                {"field_name": "primary_endpoint", "status": "extracted",
                 "value": "HbA1c at 40 weeks",
                 "source_span": "Primary endpoint: HbA1c at 40 weeks"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row,
            ("N", "primary_endpoint"),
        )
        # Sibling field survives
        n_field = payload.fields_by_name()["N"]
        assert n_field.status == "extracted"
        assert n_field.value == "N=1879"
        # Broken field downgraded
        pe_field = payload.fields_by_name()["primary_endpoint"]
        assert pe_field.status == "not_extractable"
        assert pe_field.value is None

    def test_molarity_meter_case_degrades_to_not_extractable(self) -> None:
        """Codex M-58 pass-3 exact exploit repro: span='5 M' (molar
        concentration) with value='5 m' (meter) are semantically
        distinct units. Pass-3 whitespace-only normalization rejects
        the semantic mismatch, but M-69 Fix #5 (Codex run-10 audit)
        downgrades single-field anti-fabrication failures to
        not_extractable instead of raising — preserving anti-
        fabrication while letting the rest of the payload survive."""
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
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("concentration",),
        )
        # Anti-fabrication preserved: the broken field is NOT
        # rendered as extracted; downgraded to not_extractable.
        f = payload.fields_by_name()["concentration"]
        assert f.status == "not_extractable"
        assert f.value is None
        assert f.source_span is None

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

    def test_partial_number_substring_degrades_to_not_extractable(self) -> None:
        """Codex M-58 pass-4: span='1879' value='879' is a truncation
        exploit. M-69 Fix #5 downgrades the single bad field to
        not_extractable instead of raising — preserves anti-
        fabrication, lets sibling fields survive."""
        quote = "N was 1879 at baseline."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "879",  # truncation exploit
                 "source_span": "1879"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("N",),
        )
        f = payload.fields_by_name()["N"]
        assert f.status == "not_extractable"
        assert f.value is None

    def test_partial_dose_unit_substring_degrades_to_not_extractable(self) -> None:
        """Pass-4: span='15 mg' value='5 mg' truncation exploit.
        M-69 Fix #5 downgrade."""
        quote = "Dose escalated to 15 mg weekly."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "dose", "status": "extracted",
                 "value": "5 mg",
                 "source_span": "15 mg"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("dose",),
        )
        assert payload.fields_by_name()["dose"].status == "not_extractable"

    def test_punctuation_drift_degrades_to_not_extractable(self) -> None:
        """Pass-5: span='(5 mg)' with value='5 mg' drops punctuation.
        M-69 Fix #5 downgrade."""
        quote = "Initial dose (5 mg) weekly."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "dose", "status": "extracted",
                 "value": "5 mg",
                 "source_span": "(5 mg)"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("dose",),
        )
        assert payload.fields_by_name()["dose"].status == "not_extractable"

    def test_value_equal_to_span_accepted(self) -> None:
        """The ONE accepted form under pass-5: value == source_span,
        with both being a verbatim substring of direct_quote."""
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "N=1879",
                 "source_span": "N=1879"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), _frame_row(), ("N",),
        )
        assert payload.fields_by_name()["N"].value == "N=1879"
        assert payload.fields_by_name()["N"].source_span == "N=1879"

    def test_bare_value_equal_to_bare_span_accepted(self) -> None:
        """Alternative: quote just the bare number for BOTH fields."""
        quote = "Enrolled 1879 participants. HbA1c 8.3% baseline."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "1879",
                 "source_span": "1879"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("N",),
        )
        assert payload.fields_by_name()["N"].value == "1879"

    def test_whitespace_only_drift_accepted(self) -> None:
        """The one tolerated LLM drift: whitespace collapse.
        direct_quote has 'N=1879  participants' (double space).
        LLM emits source_span='N=1879  participants' (verbatim,
        check 1 passes) and value='N=1879 participants' (single
        space) — whitespace_collapse normalizes both sides to
        'N=1879 participants', so value_matches_span returns True."""
        quote = "SURPASS-2 enrolled N=1879  participants with T2D."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "N", "status": "extracted",
                 "value": "N=1879 participants",   # one space
                 "source_span": "N=1879  participants"},  # two spaces
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("N",),
        )
        # Value stored as the LLM emitted it; normalization only
        # affects the MATCHING check, not the stored payload.
        assert payload.fields_by_name()["N"].value == "N=1879 participants"

    def test_sign_truncation_degrades_to_not_extractable(self) -> None:
        """Pass-5: value='0.47%' from span='-0.47%' drops sign.
        M-69 Fix #5 downgrade."""
        quote = "ETD vs semaglutide 1mg was -0.47% (95% CI)."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "etd", "status": "extracted",
                 "value": "0.47%",
                 "source_span": "-0.47%"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("etd",),
        )
        assert payload.fields_by_name()["etd"].status == "not_extractable"

    def test_ionic_state_truncation_degrades_to_not_extractable(self) -> None:
        """Pass-5: value='Ca2' from span='Ca2+' drops ionic charge.
        M-69 Fix #5 downgrade."""
        quote = "Ca2+ signaling was upregulated."
        row = _frame_row(quote=quote)
        response = json.dumps({
            "fields": [
                {"field_name": "ion", "status": "extracted",
                 "value": "Ca2",
                 "source_span": "Ca2+"},
            ]
        })
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("ion",),
        )
        assert payload.fields_by_name()["ion"].status == "not_extractable"

    def test_value_misbound_to_wrong_span_degrades_to_not_extractable(self) -> None:
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
        payload = parse_slot_fill_response(
            response, _slot_plan(), row, ("initial_dose",),
        )
        # M-69 Fix #5 surgical degrade — broken field
        # downgraded, not raised.
        f = payload.fields_by_name()["initial_dose"]
        assert f.status == "not_extractable"
        assert f.value is None

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
        # Phase-2 change: body-only prose — subsection title
        # no longer prefixed. The `### {subsection_title}`
        # heading is emitted separately by _run_contract_section
        # at M-63 integration time.
        assert "SURPASS-2" not in prose
        # Pass-5 fixture now uses value='N=1879'
        assert "N: N=1879" in prose
        # Phase-2 change: field_name rendered Title Cased with
        # underscore→space for sentence-splitter compatibility.
        assert "Primary endpoint:" in prose
        # Phase-2 citation format: `[id].` (period AFTER
        # citation inside sentence)
        assert "[surpass_2_primary]." in prose
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
        # Phase-2: field names Title Cased with underscore→space
        assert "Baseline hba1c" in prose

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
        # Pass-5: value == source_span verbatim
        response = json.dumps({
            "fields": [
                {"field_name": "enactment_year", "status": "extracted",
                 "value": "Enacted 1871",
                 "source_span": "Enacted 1871"},
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
        assert "Band gap: 1.42 eV" in prose


# ─────────────────────────────────────────────────────────────────────
# (6b) V30 Phase-2 M-66a-R whitespace-tolerant verbatim check
# ─────────────────────────────────────────────────────────────────────
class TestWhitespaceTolerantSubstring:
    """V30 Phase-2 M-66a-R regression coverage. Codex pass-1 of M-66
    predicted this fix would become data-indicated after M-66b-T
    brought full-text OA content into M-58's direct_quote. Run-5
    confirmed: 5 of 6 regulatory + 1 mechanism entity parse-failed
    because the LLM echoed source_span with collapsed whitespace
    against a direct_quote containing newlines.

    The relaxation must BOTH let whitespace-differing matches
    through AND still reject fabricated content.
    """

    def test_whitespace_difference_now_accepted(self) -> None:
        """LLM echoes `Indications: adjunct to diet` but the
        source has `Indications:\\n\\nadjunct to diet` — used to
        fail, now passes."""
        slot = _slot_plan()
        row = _frame_row(
            quote=(
                "HIGHLIGHTS OF PRESCRIBING INFORMATION\n\n"
                "Indications:\n\nadjunct to diet and exercise to "
                "improve glycemic control in adults with T2D.\n\n"
                "WARNING: thyroid C-cell tumors."
            ),
            entity_id="fda_mounjaro_label",
            entity_type="regulatory",
        )
        response = json.dumps({
            "fields": [{
                "field_name": "indications",
                "status": "extracted",
                # Single-space, no newlines
                "value": "adjunct to diet and exercise to improve "
                         "glycemic control in adults with T2D",
                "source_span": "adjunct to diet and exercise to improve "
                              "glycemic control in adults with T2D",
            }],
        })
        payload = parse_slot_fill_response(
            response, slot, row, ("indications",),
        )
        assert payload.fields[0].status == "extracted"

    def test_fabricated_content_still_rejected_via_degrade(self) -> None:
        """Anti-fabrication preserved: text NOT in the source
        still fails regardless of whitespace handling. M-69 Fix #5
        downgrades the broken field to not_extractable instead
        of raising — the fabricated content does NOT make it
        into the rendered payload (anti-fabrication intact)."""
        slot = _slot_plan()
        row = _frame_row(
            quote=(
                "Indications: adjunct to diet and exercise for T2D."
            ),
            entity_id="fda_mounjaro_label",
            entity_type="regulatory",
        )
        response = json.dumps({
            "fields": [{
                "field_name": "indications",
                "status": "extracted",
                # Content NOT in source quote
                "value": "cure for all diabetes including type 1",
                "source_span": "cure for all diabetes including type 1",
            }],
        })
        payload = parse_slot_fill_response(
            response, slot, row, ("indications",),
        )
        f = payload.fields_by_name()["indications"]
        assert f.status == "not_extractable"
        assert f.value is None
        assert "cure for all diabetes" not in (f.value or "")

    def test_case_change_still_rejected_via_degrade(self) -> None:
        """Case-sensitivity preserved — `ADJUNCT` should not
        match `adjunct`. M-69 Fix #5 downgrade applies."""
        slot = _slot_plan()
        row = _frame_row(
            quote="Indications: adjunct to diet for T2D.",
            entity_id="fda_mounjaro_label",
            entity_type="regulatory",
        )
        response = json.dumps({
            "fields": [{
                "field_name": "indications",
                "status": "extracted",
                "value": "ADJUNCT TO DIET FOR T2D",
                "source_span": "ADJUNCT TO DIET FOR T2D",
            }],
        })
        payload = parse_slot_fill_response(
            response, slot, row, ("indications",),
        )
        assert payload.fields_by_name()["indications"].status == "not_extractable"

    def test_helper_directly(self) -> None:
        """Direct-call coverage of the helper."""
        from src.polaris_graph.generator.slot_fill import (
            _whitespace_tolerant_substring,
        )
        # Exact match
        assert _whitespace_tolerant_substring("foo", "the foo bar") is True
        # Whitespace difference
        assert _whitespace_tolerant_substring(
            "foo bar", "the foo\n\n  bar baz",
        ) is True
        # Content difference
        assert _whitespace_tolerant_substring(
            "qux", "the foo bar",
        ) is False
        # Case difference
        assert _whitespace_tolerant_substring(
            "FOO", "the foo bar",
        ) is False
        # Empty
        assert _whitespace_tolerant_substring("", "anything") is False
        assert _whitespace_tolerant_substring("foo", "") is False


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
        # Render (Phase-2 body-only format)
        prose = render_slot_prose(payload)
        assert "SURPASS-2" not in prose  # subsection title not in body
        assert prose.count("[surpass_2_primary]") == 4
        assert prose.count("[surpass_2_primary].") == 4  # citation-inside-sentence
