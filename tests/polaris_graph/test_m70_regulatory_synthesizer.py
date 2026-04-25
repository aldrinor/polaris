"""V31 — M-70 regulatory_synthesizer tests.

Codex strategic review (2026-04-25): regulatory entities (FDA / EMA
/ NICE / HC) need PROSE synthesis from segmented page sections, not
M-58 field-level verbatim extraction. This module's tests cover:

  1. Heading segmentation — given a fetched regulatory page,
     return field_name → segment chunks via jurisdiction-specific
     heading patterns.
  2. Synthesis prompt — composes a prose-grade prompt asking for
     2-4 sentences per field with verbatim phrase grounding.
  3. Response parsing + verification — whitespace-tolerant
     verbatim check on source_span against the matched segment
     (NOT against the whole 25K-char direct_quote).
  4. Surgical degrade — failed verification on a single field
     downgrades that field, not the whole payload.
  5. Render path — extracted fields render as multi-sentence
     paragraphs prefixed by Title-cased field labels.
  6. Dispatch helper — `is_regulatory_entity` correctly routes
     `type=regulatory` entities through M-70.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.polaris_graph.generator.regulatory_synthesizer import (
    RegulatorySynthesisError,
    _segment_regulatory_text,
    build_regulatory_synthesis_prompt,
    is_regulatory_entity,
    parse_regulatory_synthesis_response,
    render_regulatory_prose,
)
from src.polaris_graph.nodes.contract_outline import ContractSlotPlan
from src.polaris_graph.retrieval.frame_fetcher import (
    FrameRow, ProvenanceClass,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def clinical_template() -> dict:
    with Path("config/scope_templates/clinical.yaml").open(
        "r", encoding="utf-8",
    ) as f:
        return yaml.safe_load(f)


def _slot_plan(
    slot_id: str = "regulatory_fda_t2d",
    subsection_title: str = "US FDA (Mounjaro for T2D)",
) -> ContractSlotPlan:
    return ContractSlotPlan(
        slot_id=slot_id,
        section="Regulatory",
        subsection_title=subsection_title,
        ordering=1,
        entity_ids=("fda_mounjaro_label",),
        provenance_classes=("open_access",),
        is_gap=False,
        is_partial=False,
    )


def _frame_row(
    quote: str,
    entity_id: str = "fda_mounjaro_label",
) -> FrameRow:
    return FrameRow(
        entity_id=entity_id,
        entity_type="regulatory",
        rendering_slot="regulatory_fda_t2d",
        provenance_class=ProvenanceClass.OPEN_ACCESS,
        direct_quote=quote,
        quote_source="url_pattern_fetch",
        doi=None, pmid=None, oa_pdf_url=None,
        url="https://dailymed.nlm.nih.gov/.../mounjaro",
        title=None, authors=(), journal=None, year=None,
        failure_reason=None,
        retrieval_attempts=(), retrieval_timings=(),
    )


def _fda_mounjaro_entity(clinical_template: dict):
    from src.polaris_graph.nodes.report_contract import (
        load_report_contract_for_slug,
    )
    contract = load_report_contract_for_slug(
        clinical_template, "clinical_tirzepatide_t2dm",
    )
    return contract.entities_by_id()["fda_mounjaro_label"]


# ─────────────────────────────────────────────────────────────────────
# (1) Heading segmentation
# ─────────────────────────────────────────────────────────────────────
class TestSegmentation:
    def test_fda_label_segments_indications_and_boxed_warning(self) -> None:
        """A typical FDA label header structure produces segments
        for `indications` + `boxed_warning`."""
        quote = (
            "HIGHLIGHTS OF PRESCRIBING INFORMATION\n\n"
            "WARNING: RISK OF THYROID C-CELL TUMORS\n"
            "Tirzepatide causes thyroid C-cell tumors in rats.\n"
            "It is unknown whether MOUNJARO causes thyroid C-cell tumors.\n\n"
            "1 INDICATIONS AND USAGE\n"
            "MOUNJARO is indicated as an adjunct to diet and exercise to "
            "improve glycemic control in adults with type 2 diabetes mellitus.\n\n"
            "4 CONTRAINDICATIONS\n"
            "MOUNJARO is contraindicated in patients with a personal or "
            "family history of medullary thyroid carcinoma.\n"
        )
        segments = _segment_regulatory_text(
            quote,
            (
                "indications", "boxed_warning",
                "contraindications", "warnings_and_precautions",
                "dosing",
            ),
            "FDA",
        )
        assert "indications" in segments
        assert "MOUNJARO is indicated" in segments["indications"].text
        assert "boxed_warning" in segments
        assert "thyroid C-cell tumors" in segments["boxed_warning"].text
        assert "contraindications" in segments
        assert "medullary thyroid carcinoma" in segments["contraindications"].text

    def test_ema_epar_segments_indications(self) -> None:
        """EMA-style heading variants match."""
        quote = (
            "Mounjaro\n"
            "Therapeutic indications\n"
            "Mounjaro is indicated for the treatment of insufficiently controlled "
            "type 2 diabetes mellitus in adults.\n\n"
            "4.3 Contraindications\n"
            "Hypersensitivity to the active substance or to any of the excipients.\n"
        )
        segments = _segment_regulatory_text(
            quote, ("indications", "contraindications"), "EMA",
        )
        assert "indications" in segments
        assert "type 2 diabetes" in segments["indications"].text
        assert "contraindications" in segments

    def test_no_jurisdiction_returns_empty(self) -> None:
        segments = _segment_regulatory_text(
            "some prose", ("indications",), None,
        )
        assert segments == {}

    def test_unknown_jurisdiction_returns_empty(self) -> None:
        segments = _segment_regulatory_text(
            "some prose", ("indications",), "AUS",
        )
        assert segments == {}

    def test_field_with_no_matching_heading_excluded(self) -> None:
        """If a required field's heading patterns don't match,
        that field is OMITTED from segments dict (caller treats
        as not_extractable)."""
        quote = "1 INDICATIONS AND USAGE\nadjunct to diet."
        segments = _segment_regulatory_text(
            quote, ("indications", "boxed_warning"), "FDA",
        )
        assert "indications" in segments
        assert "boxed_warning" not in segments

    def test_segment_capped_at_max_chars(self) -> None:
        """Long sections are truncated at max_chars_per_segment."""
        long_body = "x" * 5000
        quote = f"1 INDICATIONS AND USAGE\n{long_body}"
        segments = _segment_regulatory_text(
            quote, ("indications",), "FDA",
            max_chars_per_segment=1000,
        )
        assert len(segments["indications"].text) <= 1000


# ─────────────────────────────────────────────────────────────────────
# (2) Prompt construction
# ─────────────────────────────────────────────────────────────────────
class TestPromptBuild:
    def test_prompt_has_required_structure(self, clinical_template) -> None:
        entity = _fda_mounjaro_entity(clinical_template)
        slot = _slot_plan()
        row = _frame_row(
            "1 INDICATIONS AND USAGE\nMOUNJARO is indicated for T2DM."
        )
        segments = _segment_regulatory_text(
            row.direct_quote, entity.required_fields, "FDA",
        )
        prompt = build_regulatory_synthesis_prompt(
            slot, row, entity, segments, "research question?",
        )
        assert "BOUND_EV_ID: fda_mounjaro_label" in prompt
        assert "FDA" in prompt
        assert "Mounjaro" in prompt
        assert "research question?" in prompt
        assert "JSON" in prompt
        assert "field_name" in prompt
        # Each segment block included
        assert "--- field=indications ---" in prompt
        assert "MOUNJARO is indicated" in prompt


# ─────────────────────────────────────────────────────────────────────
# (3) Response parsing + verification
# ─────────────────────────────────────────────────────────────────────
class TestParseAndVerify:
    def test_happy_path_extracted_field_kept(self) -> None:
        slot = _slot_plan()
        row = _frame_row(
            "1 INDICATIONS AND USAGE\n"
            "MOUNJARO is indicated as an adjunct to diet and exercise."
        )
        segments = {
            "indications": _make_segment(
                "indications",
                "MOUNJARO is indicated as an adjunct to diet and exercise.",
            ),
        }
        response = json.dumps({
            "fields": [{
                "field_name": "indications",
                "status": "extracted",
                "value": (
                    "The label states that MOUNJARO is indicated as an "
                    "adjunct to diet and exercise. This applies to adults "
                    "with type 2 diabetes."
                ),
                "source_span": "MOUNJARO is indicated as an adjunct to diet and exercise",
            }],
        })
        payload = parse_regulatory_synthesis_response(
            response, slot, row, ("indications",), segments,
        )
        f = payload.fields[0]
        assert f.status == "extracted"
        assert "MOUNJARO is indicated" in f.value

    def test_source_span_not_in_segment_degrades(self) -> None:
        """Source span outside segment → field downgraded
        (anti-fabrication)."""
        slot = _slot_plan()
        row = _frame_row("Indications: T2DM")
        segments = {
            "indications": _make_segment(
                "indications", "Indications: T2DM",
            ),
        }
        response = json.dumps({
            "fields": [{
                "field_name": "indications",
                "status": "extracted",
                "value": "fabricated content",
                "source_span": "fabricated content not in segment",
            }],
        })
        payload = parse_regulatory_synthesis_response(
            response, slot, row, ("indications",), segments,
        )
        assert payload.fields[0].status == "not_extractable"

    def test_missing_field_in_response_becomes_not_extractable(self) -> None:
        """Required field absent from LLM response → not_extractable."""
        slot = _slot_plan()
        row = _frame_row("Indications: T2DM")
        segments = {
            "indications": _make_segment("indications", "Indications: T2DM"),
        }
        response = json.dumps({"fields": []})
        payload = parse_regulatory_synthesis_response(
            response, slot, row, ("indications", "boxed_warning"),
            segments,
        )
        assert all(f.status == "not_extractable" for f in payload.fields)

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(RegulatorySynthesisError):
            parse_regulatory_synthesis_response(
                "not JSON", _slot_plan(), _frame_row("x"),
                ("indications",), {},
            )

    def test_one_bad_field_does_not_kill_siblings(self) -> None:
        """V31 surgical degrade — one field fails verification,
        siblings survive."""
        slot = _slot_plan()
        row = _frame_row(
            "1 INDICATIONS AND USAGE\n"
            "MOUNJARO is indicated for T2DM.\n"
            "WARNING: RISK OF THYROID C-CELL TUMORS\n"
            "Tirzepatide causes thyroid C-cell tumors in rats."
        )
        segments = {
            "indications": _make_segment(
                "indications", "MOUNJARO is indicated for T2DM.",
            ),
            "boxed_warning": _make_segment(
                "boxed_warning",
                "WARNING: RISK OF THYROID C-CELL TUMORS",
            ),
        }
        response = json.dumps({
            "fields": [
                {  # GOOD: source_span is in segment
                    "field_name": "indications",
                    "status": "extracted",
                    "value": "Indicated for T2DM.",
                    "source_span": "MOUNJARO is indicated for T2DM",
                },
                {  # BAD: fabricated
                    "field_name": "boxed_warning",
                    "status": "extracted",
                    "value": "fabricated warning",
                    "source_span": "fabricated content not in segment",
                },
            ],
        })
        payload = parse_regulatory_synthesis_response(
            response, slot, row, ("indications", "boxed_warning"),
            segments,
        )
        by_name = {f.field_name: f for f in payload.fields}
        assert by_name["indications"].status == "extracted"
        assert by_name["boxed_warning"].status == "not_extractable"


# ─────────────────────────────────────────────────────────────────────
# (4) Render
# ─────────────────────────────────────────────────────────────────────
class TestRender:
    def test_render_produces_field_paragraphs(self) -> None:
        from src.polaris_graph.generator.slot_fill import (
            SlotFieldFill, SlotFillPayload,
        )
        payload = SlotFillPayload(
            slot_id="regulatory_fda_t2d",
            entity_id="fda_mounjaro_label",
            subsection_title="US FDA",
            bound_ev_id="fda_mounjaro_label",
            fields=(
                SlotFieldFill(
                    field_name="indications", status="extracted",
                    value=(
                        "The label states that MOUNJARO is indicated as an "
                        "adjunct to diet and exercise."
                    ),
                    bound_ev_id="fda_mounjaro_label",
                    source_span="MOUNJARO is indicated as an adjunct to diet",
                ),
                SlotFieldFill(
                    field_name="boxed_warning", status="not_extractable",
                    value=None,
                    bound_ev_id="fda_mounjaro_label",
                    source_span=None,
                ),
            ),
            provenance_class="open_access",
        )
        prose = render_regulatory_prose(payload)
        assert "Indications" in prose
        assert "MOUNJARO is indicated" in prose
        assert "[fda_mounjaro_label]" in prose
        # Not-extractable fields are SKIPPED in prose render
        # (gap-disclosure fallback at section level handles them)
        assert "Boxed warning" not in prose

    def test_render_all_not_extractable_returns_empty(self) -> None:
        from src.polaris_graph.generator.slot_fill import (
            SlotFieldFill, SlotFillPayload,
        )
        payload = SlotFillPayload(
            slot_id="x", entity_id="x", subsection_title="x",
            bound_ev_id="x",
            fields=(SlotFieldFill(
                field_name="indications", status="not_extractable",
                value=None, bound_ev_id="x", source_span=None,
            ),),
            provenance_class="open_access",
        )
        assert render_regulatory_prose(payload) == ""


# ─────────────────────────────────────────────────────────────────────
# (5) Dispatch helper
# ─────────────────────────────────────────────────────────────────────
class TestDispatch:
    def test_regulatory_entity_routed_to_m70(self, clinical_template) -> None:
        entity = _fda_mounjaro_entity(clinical_template)
        assert is_regulatory_entity(entity) is True

    def test_pivotal_trial_not_routed_to_m70(self, clinical_template) -> None:
        from src.polaris_graph.nodes.report_contract import (
            load_report_contract_for_slug,
        )
        contract = load_report_contract_for_slug(
            clinical_template, "clinical_tirzepatide_t2dm",
        )
        e = contract.entities_by_id()["surpass_2_primary"]
        assert is_regulatory_entity(e) is False


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _make_segment(field_name: str, text: str):
    from src.polaris_graph.generator.regulatory_synthesizer import _Segment
    return _Segment(field_name=field_name, text=text)
