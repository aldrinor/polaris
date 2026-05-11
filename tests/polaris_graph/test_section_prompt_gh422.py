"""GH#422 I-gen-001: section prompt must carry policy-scope disambiguation rule.

After Tier-1 pilot Q5-T1-014 surfaced PBO-vs-Bill-C-64 scope conflation
(PR #421 / GH#420), SECTION_SYSTEM_PROMPT_TEMPLATE gained rule 13 in
multi_section_generator.py to explicitly require inline scope-attribution
when a paragraph names a narrow program (Bill C-64) but the cited source
is a broader-scope projection (PBO universal single-payer).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
)


def _format_template_for(title: str) -> str:
    """Render the section system prompt as the generator does."""
    return SECTION_SYSTEM_PROMPT_TEMPLATE.format(title=title, focus="test focus")


def test_section_prompt_contains_policy_scope_disambiguation_rule() -> None:
    """Rule 13 (M-NEW-1) must appear in every formatted section prompt."""
    formatted = _format_template_for("Regulatory")
    assert "Policy-scope disambiguation" in formatted, (
        "rule 13 'Policy-scope disambiguation' header missing"
    )
    assert "GH#422" in formatted, (
        "rule 13 must reference GH#422 for traceability"
    )


def test_section_prompt_names_bill_c64_example() -> None:
    """Rule 13 must call out the Bill C-64 / PBO conflation example."""
    formatted = _format_template_for("Regulatory")
    assert "Bill C-64" in formatted, "rule 13 example must name Bill C-64"
    assert "PBO" in formatted or "universal single-payer" in formatted, (
        "rule 13 must reference PBO universal single-payer scope"
    )


def test_section_prompt_requires_inline_scope_label() -> None:
    """Rule 13 must require an inline scope-attribution label."""
    formatted = _format_template_for("Regulatory")
    assert "EXPLICITLY label the scope-attribution INLINE" in formatted, (
        "rule 13 must demand inline scope-attribution"
    )


def test_section_prompt_rule_13_fires_across_sections() -> None:
    """Rule 13 generalizes; must appear regardless of section title."""
    for title in ("Efficacy", "Comparative", "Regulatory",
                  "Population Subgroups", "Long-term Outcomes",
                  "Mechanism", "Safety"):
        formatted = _format_template_for(title)
        assert "Policy-scope disambiguation" in formatted, (
            f"rule 13 should be present in section '{title}'"
        )


def test_section_prompt_rule_13_documents_bad_example() -> None:
    """Rule 13 must include the BAD example pattern to make the failure mode concrete."""
    formatted = _format_template_for("Regulatory")
    assert "BAD" in formatted and "Under Bill C-64" in formatted, (
        "rule 13 must include the BAD example showing PBO numbers folded into Bill C-64"
    )
