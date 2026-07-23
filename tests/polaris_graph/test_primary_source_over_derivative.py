"""Primary-source-over-derivative tier discipline stays field-neutral."""

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


def test_primary_source_rule_does_not_embed_task_entities():
    """The general rule must not depend on one benchmark's named sources."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "polaris_graph" / "generator" / "multi_section_generator.py"
    text = src.read_text(encoding="utf-8")
    assert "PWBM" not in text
    assert "Goldman Sachs" not in text


def test_primary_source_rule_is_adjacent_to_general_tier_discipline():
    """The rule remains coupled to the prompt's general tier semantics."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "polaris_graph" / "generator" / "multi_section_generator.py"
    text = src.read_text(encoding="utf-8")
    rule_match = re.search(
        r"EVIDENCE TIER DISCIPLINE.*?PRIMARY-SOURCE-OVER-DERIVATIVE"
        r".*?(?=Scope discipline)",
        text,
        re.DOTALL,
    )
    assert rule_match is not None, "Tier discipline and primary-source rule not located."
    rule_block = rule_match.group(0)
    assert "[T1]" in rule_block
    assert "[T3]" in rule_block
    assert "[T4]-[T7]" in rule_block
    assert "primary source that originated it" in rule_block
