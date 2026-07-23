"""Batch 2 (structure): the PG_SECTION_STRUCTURE section-prompt transform.

The lever flips the section writer's rule 7 from flat-paragraph-only to a directive that organizes
the body with ### sub-headings, markdown comparison tables, and bullet lists — while KEEPING the
[ev_XXX]-marker-per-unit citation contract. Default OFF => byte-identical section prompt.
"""
import pytest

import src.polaris_graph.generator.multi_section_generator as m


def _off(monkeypatch):
    monkeypatch.delenv("PG_SECTION_STRUCTURE", raising=False)
    monkeypatch.setenv("PG_RENDER_BLOCKS", "0")
    monkeypatch.setenv("PG_BASKET_SYNTHESIS", "0")


def _on(monkeypatch):
    monkeypatch.setenv("PG_SECTION_STRUCTURE", "1")
    monkeypatch.setenv("PG_RENDER_BLOCKS", "0")
    monkeypatch.setenv("PG_BASKET_SYNTHESIS", "0")


@pytest.mark.parametrize("anti_verbosity", [False, True])
@pytest.mark.parametrize("field_agnostic", [False, True])
def test_off_is_byte_identical(monkeypatch, anti_verbosity, field_agnostic):
    _off(monkeypatch)
    got = m._select_section_system_prompt(field_agnostic, anti_verbosity=anti_verbosity)
    # OFF returns the SAME object identity as the pre-existing selector (byte-identical).
    if anti_verbosity:
        want = (
            m.SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC_CONCISE
            if field_agnostic else m.SECTION_SYSTEM_PROMPT_TEMPLATE_CONCISE
        )
    else:
        want = (
            m.SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC
            if field_agnostic else m.SECTION_SYSTEM_PROMPT_TEMPLATE
        )
    assert got is want
    assert "Do not write a section heading" in got and "### sub-heading" not in got


@pytest.mark.parametrize("anti_verbosity", [False, True])
def test_on_enables_structure_keeps_citation_contract(monkeypatch, anti_verbosity):
    _on(monkeypatch)
    got = m._select_section_system_prompt(True, anti_verbosity=anti_verbosity)
    assert "Do not write a section heading" not in got          # flat rule 7 gone
    assert "`###` subheadings" in got                          # subsection directive
    assert "Markdown table" in got                              # comparison-table directive
    assert "bulleted list" in got                               # bullet directive
    assert "[ev_XXX] marker" in got                             # citation contract preserved
    # composes with anti-verbosity (front-loading directive still present when on)
    if anti_verbosity:
        assert "FRONT-LOADING" in got


def test_build_structured_variant_fails_loud_on_anchor_drift():
    with pytest.raises(RuntimeError, match="anchor drifted"):
        m._build_structured_variant("a template with no rule 7 anchor at all")


def test_structure_composes_on_both_base_templates():
    # The transform must anchor on rule 7 in BOTH the plain and concise field-agnostic templates.
    for base in (
        m.SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
        m.SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC_CONCISE,
    ):
        out = m._build_structured_variant(base)
        assert "`###` subheadings" in out and "[ev_XXX] marker" in out
