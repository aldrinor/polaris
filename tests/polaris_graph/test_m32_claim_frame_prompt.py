"""Domain-neutral claim-frame prompt contract."""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    select_advisory_prompt_text,
)


class TestClaimFrameRule:
    def test_rule_is_present_without_historical_label(self) -> None:
        assert "12. **Claim-frame discipline**" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "Primary-study framing" not in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "(M-32" not in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_requires_supported_frame_components(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "population or sample size" in text
        assert "baseline value" in text
        assert "comparator or control condition" in text
        assert "primary endpoint with its timepoint" in text

    def test_rule_is_closed_world(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "when the evidence supplies them" in text
        assert "use only evidence-supplied frame elements" in text
        assert "supplying missing details" in text

    def test_rule_uses_general_study_language(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "specific named study" in text
        assert "describe the study generically" in text


class TestDomainSpecificEnrichment:
    def test_clinical_details_are_selected_only_by_answer_type(self) -> None:
        clinical = select_advisory_prompt_text("empirical", "clinical").lower()
        assert "comparator/control arm" in clinical
        assert "effect size" in clinical
        assert "uncertainty" in clinical
        assert select_advisory_prompt_text("empirical", "general") == ""


class TestPromptNonRegression:
    def test_authority_and_scope_rules_remain(self) -> None:
        assert "11. **Authority precision and coverage**" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "13. **Scope disambiguation**" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rules_one_through_thirteen_are_numbered(self) -> None:
        for number in range(1, 14):
            assert f"{number}." in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_template_formats_title_and_focus(self) -> None:
        rendered = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            title="Comparison",
            focus="Compare the supported measurements",
        )
        assert "Comparison" in rendered
        assert "Compare the supported measurements" in rendered
