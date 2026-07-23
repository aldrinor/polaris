"""Mechanism-section prompt coverage after Batch 2b generalization."""
from __future__ import annotations

import inspect
import re

from src.polaris_graph.generator import multi_section_generator as msg
from src.polaris_graph.generator.multi_section_generator import (
    OUTLINE_SYSTEM_PROMPT,
    OUTLINE_SYSTEM_PROMPT_GENERIC,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    _select_outline_system_prompt,
)


class TestGeneralMechanismCapability:
    def test_section_prompt_has_domain_neutral_process_rule(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "MECHANISM OR CAUSAL-PROCESS RULE" in text
        assert "inputs or conditions through intermediate processes to outcomes" in text
        assert "fixed domain vocabulary" in text
        assert "M-40" not in text

    def test_rule_is_evidence_driven(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "concepts and" in text
        assert "measures that recur in that section's evidence" in text
        assert "only when the cited evidence supplies them" in text


class TestDomainGatedOutline:
    def test_clinical_pack_exposes_mechanism_section(self) -> None:
        selected = _select_outline_system_prompt("clinical")
        assert selected == OUTLINE_SYSTEM_PROMPT
        assert "'Mechanism'" in selected

    def test_general_pack_does_not_inherit_clinical_section_menu(self, monkeypatch) -> None:
        monkeypatch.delenv("PG_FACET_OUTLINE", raising=False)
        selected = _select_outline_system_prompt("general")
        assert selected == OUTLINE_SYSTEM_PROMPT_GENERIC
        assert "'Mechanism'" not in selected
        assert selected != _select_outline_system_prompt("clinical")

    def test_non_clinical_pack_can_own_a_domain_appropriate_mechanism_title(self, monkeypatch) -> None:
        monkeypatch.delenv("PG_FACET_OUTLINE", raising=False)
        science = _select_outline_system_prompt("science")
        policy = _select_outline_system_prompt("policy")
        assert "'Mechanism'" in science
        assert "'Policy Mechanism'" in policy

    def test_legacy_labeled_rule_is_absent_from_outline_templates(self) -> None:
        assert "M-40" not in OUTLINE_SYSTEM_PROMPT
        assert "M-40" not in OUTLINE_SYSTEM_PROMPT_GENERIC


class TestOutlineSummaryIncludesTitle:
    def test_outline_summary_reads_and_exposes_title(self) -> None:
        source = inspect.getsource(msg._call_outline)
        assert 'ev.get("title"' in source or "ev.get('title'" in source
        assert "title:" in source or "title_clean" in source


class TestOutlinePromptIntegrity:
    def test_tier_hierarchy_and_output_contract_remain(self) -> None:
        assert "EVIDENCE QUALITY HIERARCHY" in OUTLINE_SYSTEM_PROMPT
        assert "[T1]" in OUTLINE_SYSTEM_PROMPT
        assert "OUTPUT FORMAT" in OUTLINE_SYSTEM_PROMPT

    def test_outline_prompt_has_no_unescaped_placeholders(self) -> None:
        suspicious = re.findall(
            r"\{([A-Za-z_][A-Za-z_0-9]*)\}", OUTLINE_SYSTEM_PROMPT,
        )
        assert not suspicious
