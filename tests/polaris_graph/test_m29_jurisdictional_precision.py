"""Authority-precision prompt coverage after Batch 2b generalization."""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    select_advisory_prompt_text,
)


class TestGeneralAuthorityRule:
    def test_domain_neutral_rule_is_present(self) -> None:
        assert "11. **Authority precision and coverage**" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "Jurisdictional precision" not in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "M-29" not in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_each_assertion_is_bound_to_its_source_authority(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "attribute each specific assertion to the one authority" in text
        assert "whose source supports it" in text

    def test_shared_assertions_require_complete_authority_support(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "collapse authorities into a shared assertion only when" in text
        assert "every referenced authority supports it" in text

    def test_rule_names_multiple_authority_types(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        for authority_type in (
            "jurisdictions",
            "agencies",
            "standards bodies",
            "courts",
            "governance institutions",
        ):
            assert authority_type in text


class TestClinicalDomainGating:
    def test_specific_regulatory_wording_lives_in_clinical_advisory(self) -> None:
        clinical = select_advisory_prompt_text("empirical", "clinical").lower()
        assert "specific jurisdiction" in clinical
        assert "both agencies" in clinical
        assert "regulators generally" in clinical
        assert "citation from each" in clinical

    def test_non_clinical_paths_do_not_receive_clinical_advisory(self) -> None:
        for answer_type in ("general", "policy", "economics", "science"):
            assert select_advisory_prompt_text("empirical", answer_type) == ""


class TestRuleCoexistsWithOtherGeneralRules:
    def test_multi_source_rule_remains(self) -> None:
        assert "multiple evidence rows independently support" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rules_one_through_thirteen_remain_numbered(self) -> None:
        for number in range(1, 14):
            assert f"\n{number}." in SECTION_SYSTEM_PROMPT_TEMPLATE
