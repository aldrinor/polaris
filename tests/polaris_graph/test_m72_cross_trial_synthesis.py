"""V33 — M-72 cross-trial synthesis layer tests.

Codex run-12 verdict: Narrative depth + Citations stayed LB even
after V31+V32 because Efficacy + Mechanism remain slot-stacked.
M-72 reads contract slot payloads + emits cross-trial inferences
(dose-response, comparator-class progression, safety class) that
the legacy section LLM integrates into the body narrative.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.cross_trial_synthesis import (
    CrossTrialSynthesisBlock,
    _aggregate_trial_frames,
    _detect_comparator_class_patterns,
    _detect_dose_response_patterns,
    _detect_safety_class_patterns,
    build_cross_trial_synthesis,
    render_cross_trial_synthesis_block,
)
from src.polaris_graph.generator.slot_fill import (
    SlotFieldFill, SlotFillPayload,
)


def _trial_payload(
    entity_id: str, fields: dict[str, str],
) -> SlotFillPayload:
    return SlotFillPayload(
        slot_id=f"slot_{entity_id}",
        entity_id=entity_id,
        subsection_title=entity_id,
        bound_ev_id=entity_id,
        fields=tuple(
            SlotFieldFill(
                field_name=k, status="extracted",
                value=v, bound_ev_id=entity_id,
                source_span=v,
            )
            for k, v in fields.items()
        ),
        provenance_class="open_access",
    )


# ─────────────────────────────────────────────────────────────────────
# (1) Aggregation
# ─────────────────────────────────────────────────────────────────────
class TestAggregation:
    def test_aggregates_trial_frames(self) -> None:
        payloads = [
            _trial_payload("surpass_2_primary", {
                "etd_with_uncertainty": "-0.45 percentage points",
                "comparator": "semaglutide 1 mg",
            }),
            _trial_payload("surpass_5_primary", {
                "comparator": "placebo",
                "baseline_hba1c": "8.31%",
            }),
        ]
        frames = _aggregate_trial_frames(payloads)
        assert len(frames) == 2
        anchors = {f.anchor for f in frames}
        assert any("SURPASS-2" in a for a in anchors)
        assert any("SURPASS-5" in a for a in anchors)

    def test_skips_regulatory_entities(self) -> None:
        """fda_mounjaro_label etc. don't match trial anchor pattern."""
        payloads = [
            _trial_payload("fda_mounjaro_label", {
                "indications": "T2DM",
            }),
            _trial_payload("nice_ta924_t2d", {
                "commercial_arrangement": "yes",
            }),
        ]
        frames = _aggregate_trial_frames(payloads)
        assert frames == []

    def test_skips_payload_without_extracted_fields(self) -> None:
        p = SlotFillPayload(
            slot_id="x", entity_id="surpass_2_primary",
            subsection_title="x", bound_ev_id="surpass_2_primary",
            fields=(
                SlotFieldFill(
                    field_name="N", status="not_extractable",
                    value=None, bound_ev_id="x", source_span=None,
                ),
            ),
            provenance_class="open_access",
        )
        frames = _aggregate_trial_frames([p])
        assert frames == []


# ─────────────────────────────────────────────────────────────────────
# (2) Pattern detection
# ─────────────────────────────────────────────────────────────────────
class TestDoseResponse:
    def test_detects_triple_dose_etd_pattern(self) -> None:
        """≥2 trials with explicit 5/10/15 mg ETDs → dose-response
        pattern emits."""
        payloads = [
            _trial_payload("surpass_2_primary", {
                "etd_with_uncertainty": (
                    "-0.15 (95% CI -0.28 to -0.03; P=0.02), "
                    "-0.39 (95% CI -0.51 to -0.26; P<0.001), and "
                    "-0.45 (95% CI -0.57 to -0.32; P<0.001) for "
                    "5 mg, 10 mg, and 15 mg"
                ),
            }),
            _trial_payload("surpass_5_primary", {
                "etd_with_uncertainty": (
                    "10 mg: -1.53; 15 mg: -1.47; 5 mg: -1.34"
                ),
            }),
        ]
        frames = _aggregate_trial_frames(payloads)
        patterns = _detect_dose_response_patterns(frames)
        assert len(patterns) == 1
        assert patterns[0].section == "Comparative"
        assert "dose-response" in patterns[0].summary.lower()

    def test_single_trial_no_pattern(self) -> None:
        payloads = [
            _trial_payload("surpass_2_primary", {
                "etd_with_uncertainty": (
                    "5 mg, 10 mg, 15 mg: -0.15, -0.39, -0.45"
                ),
            }),
        ]
        frames = _aggregate_trial_frames(payloads)
        patterns = _detect_dose_response_patterns(frames)
        assert patterns == []


class TestComparatorClass:
    def test_detects_three_class_progression(self) -> None:
        """Trials spanning placebo + semaglutide + insulin → class
        progression pattern emits."""
        payloads = [
            _trial_payload("surpass_1_primary", {
                "comparator": "placebo",
            }),
            _trial_payload("surpass_2_primary", {
                "comparator": "semaglutide 1 mg",
            }),
            _trial_payload("surpass_3_primary", {
                "comparator": "insulin degludec",
            }),
        ]
        frames = _aggregate_trial_frames(payloads)
        patterns = _detect_comparator_class_patterns(frames)
        assert len(patterns) == 1
        s = patterns[0].summary.lower()
        assert "placebo-controlled" in s
        assert "glp-1 ra" in s.lower()
        assert "insulin" in s

    def test_only_one_class_emits_nothing(self) -> None:
        payloads = [
            _trial_payload("surpass_1_primary", {"comparator": "placebo"}),
        ]
        frames = _aggregate_trial_frames(payloads)
        patterns = _detect_comparator_class_patterns(frames)
        assert patterns == []


class TestSafetyClass:
    def test_detects_safety_pattern_when_two_trials_have_signal(self) -> None:
        payloads = [
            _trial_payload("surpass_2_primary", {
                "safety_signal": "GI events most common.",
            }),
            _trial_payload("surpass_5_primary", {
                "safety_signal": "diarrhea 12-21%, nausea 13-18%",
            }),
        ]
        frames = _aggregate_trial_frames(payloads)
        patterns = _detect_safety_class_patterns(frames)
        assert len(patterns) == 1
        assert patterns[0].section == "Safety"
        assert "gastrointestinal" in patterns[0].summary.lower()


# ─────────────────────────────────────────────────────────────────────
# (3) Public entry point
# ─────────────────────────────────────────────────────────────────────
class TestBuildBlock:
    def test_empty_when_fewer_than_two_trials(self) -> None:
        block = build_cross_trial_synthesis([_trial_payload(
            "surpass_2_primary", {"etd_with_uncertainty": "x"}
        )])
        assert block.section_to_patterns == {}

    def test_section_keys_are_lowercased(self) -> None:
        payloads = [
            _trial_payload("surpass_1_primary", {"comparator": "placebo"}),
            _trial_payload("surpass_2_primary",
                           {"comparator": "semaglutide 1 mg"}),
        ]
        block = build_cross_trial_synthesis(payloads)
        # Section keys lower-cased for case-insensitive lookup
        assert "comparative" in block.section_to_patterns
        # Look-up uses the same lowercasing
        patterns = block.get_for_section("Comparative")
        assert len(patterns) >= 1

    def test_get_for_unknown_section_returns_empty(self) -> None:
        payloads = [
            _trial_payload("surpass_1_primary", {"comparator": "placebo"}),
            _trial_payload("surpass_2_primary",
                           {"comparator": "semaglutide 1 mg"}),
        ]
        block = build_cross_trial_synthesis(payloads)
        assert block.get_for_section("Methods") == []


# ─────────────────────────────────────────────────────────────────────
# (4) Render
# ─────────────────────────────────────────────────────────────────────
class TestRender:
    def test_render_includes_pattern_summary_and_citations(self) -> None:
        payloads = [
            _trial_payload("surpass_1_primary", {"comparator": "placebo"}),
            _trial_payload("surpass_2_primary",
                           {"comparator": "semaglutide 1 mg"}),
        ]
        block = build_cross_trial_synthesis(payloads)
        prose = render_cross_trial_synthesis_block(
            "Comparative", block,
        )
        assert "M-72" in prose
        assert "CROSS-TRIAL SYNTHESIS" in prose
        # Cited contributing evidence ids
        assert "[surpass_1_primary]" in prose
        assert "[surpass_2_primary]" in prose

    def test_render_empty_for_no_patterns(self) -> None:
        block = CrossTrialSynthesisBlock()
        assert render_cross_trial_synthesis_block(
            "Comparative", block,
        ) == ""

    def test_render_empty_for_unknown_section(self) -> None:
        payloads = [
            _trial_payload("surpass_1_primary", {"comparator": "placebo"}),
            _trial_payload("surpass_2_primary",
                           {"comparator": "semaglutide 1 mg"}),
        ]
        block = build_cross_trial_synthesis(payloads)
        # Methods has no patterns
        assert render_cross_trial_synthesis_block(
            "Methods", block,
        ) == ""
