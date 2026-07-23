"""Claim-frame prompt coverage after Batch 2b domain generalization."""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    select_advisory_prompt_text,
)


def _clinical_advisory() -> str:
    return select_advisory_prompt_text("empirical", "clinical")


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


class TestGeneralClaimFrameRule:
    def test_general_rule_is_present_without_legacy_label(self) -> None:
        assert "Claim-frame discipline" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "M-38" not in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_general_rule_names_domain_neutral_frame_elements(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        for element in (
            "population or sample size",
            "baseline value",
            "comparator or control condition",
            "primary endpoint",
            "timepoint",
        ):
            assert element in text

    def test_general_rule_forbids_inventing_missing_frame_details(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "use only evidence-supplied frame elements" in text
        assert "describe the study generically" in text
        assert "supplying missing details" in text

    def test_claim_frame_precedes_evidence_tier_discipline(self) -> None:
        frame_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.index("Claim-frame discipline")
        tier_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.index("EVIDENCE TIER DISCIPLINE")
        assert frame_idx < tier_idx


class TestClinicalDomainGating:
    def test_clinical_floor_lives_in_advisory_pack(self) -> None:
        text = _normalized(_clinical_advisory())
        assert "when naming a specific study, cohort, or trial" in text
        assert "at least three of" in text
        for element in (
            "sample size",
            "baseline value",
            "comparator arm",
            "dose",
            "primary",
            "endpoint",
            "timepoint",
        ):
            assert element in text

    def test_clinical_fallback_is_pack_owned(self) -> None:
        text = _normalized(_clinical_advisory())
        assert "phrase the sentence generically" in text
        assert "study short-name" in text

    def test_non_clinical_path_gets_no_clinical_advisory(self) -> None:
        for answer_type in ("general", "science", "policy", "economics"):
            assert select_advisory_prompt_text("empirical", answer_type) == ""


class TestPromptFormattability:
    def test_template_format_succeeds(self) -> None:
        prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            title="Measured Outcomes",
            focus="Compare supported estimates",
        )
        assert "Measured Outcomes" in prompt
        assert "Compare supported estimates" in prompt
        assert "Claim-frame discipline" in prompt
