"""I-cd-033 (#633) — primary-source-over-derivative tier-discipline.

Parent #586 (I-bug-117): in the workforce-domain audit, gen-AI
occupational-exposure decimals (75.5% / 68.4% / 62.6%) were published
by PWBM (Penn Wharton Budget Model, 2025) but cited to Goldman Sachs
2023 (a derivative that re-quoted them). The generator prompt now
explicitly forbids this pattern.

These tests assert the prompt instruction is present and well-formed
so a future re-prompt cannot silently drop it. The actual generator
output verification needs an LLM call against the workforce corpus;
that's reserved for the dress-rehearsal (Seq 42 / I-D-01).
"""

from __future__ import annotations

import re

import pytest


def test_generator_prompt_contains_primary_source_rule():
    """The multi-section generator prompt includes the
    PRIMARY-SOURCE-OVER-DERIVATIVE rule that surfaced in I-bug-117."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "polaris_graph" / "generator" / "multi_section_generator.py"
    text = src.read_text(encoding="utf-8")
    assert "PRIMARY-SOURCE-OVER-DERIVATIVE" in text, (
        "Generator prompt lost the primary-source-over-derivative rule "
        "(I-cd-033 / #586 / I-bug-117). Re-add the rule and ensure the "
        "regression test points at the live prompt string."
    )


def test_primary_source_rule_references_pwbm_concrete_pattern():
    """The rule names the concrete I-bug-117 pattern (PWBM 2025 vs
    Goldman Sachs 2023) so a future copy-edit cannot dilute the
    instruction to abstract advice that the LLM ignores."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "polaris_graph" / "generator" / "multi_section_generator.py"
    text = src.read_text(encoding="utf-8")
    assert "PWBM" in text and "Goldman Sachs" in text, (
        "Primary-source rule no longer names the concrete pattern "
        "(PWBM 2025 / Goldman Sachs 2023) that prompted it. The "
        "concrete example anchors LLM compliance; abstract advice "
        "alone reproduces the bug."
    )


def test_primary_source_rule_references_tier_signal():
    """The rule explicitly names the tier signal (T1/T3 primary vs
    T6 derivative) so the LLM can map any concrete decimal to its
    tier discipline."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "polaris_graph" / "generator" / "multi_section_generator.py"
    text = src.read_text(encoding="utf-8")
    # Look for the tier signal phrase within a reasonable window.
    rule_match = re.search(
        r"PRIMARY-SOURCE-OVER-DERIVATIVE.*?(?=Scope discipline)",
        text,
        re.DOTALL,
    )
    assert rule_match is not None, "Primary-source rule block not located in prompt."
    rule_block = rule_match.group(0)
    assert "T1" in rule_block and "T3" in rule_block and "T6" in rule_block, (
        "Primary-source rule lost its tier-signal anchoring. The LLM "
        "needs T1/T3-vs-T6 wording to map the rule to the in-prompt "
        "tier tags."
    )
