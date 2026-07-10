"""I-deepfix-006 SYNTHESIS-RENDER + NUMERIC-GUARANTEE lane (C4 / C5 / PT11).

Offline, no-network unit tests for the three sub-fixes in this lane:
  - C5  PG_SYNTH_RENDER_CLEAN            (analyst_synthesis._render_clean_synthesis)
  - C4  PG_SYNTH_BODY_LEAD              (multi_section_generator._reorder_synthesis_body_lead)
  - PT11 PG_COMPOSE_NUMERIC_CITE_GUARANTEE (multi_section_generator._suppress_uncited_decimal_sentences)

Every flag is default-ON with a byte-identical OFF path; each test asserts both directions.
The frozen faithfulness engine (strict_verify / numeric / NLI / provenance / D8) is never touched.
"""

from __future__ import annotations

import importlib

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# C5 — clean analyst-synthesis render (PG_SYNTH_RENDER_CLEAN)
# ─────────────────────────────────────────────────────────────────────────────
def _analyst_mod():
    return importlib.import_module("src.polaris_graph.generator.analyst_synthesis")


def test_c5_disclosure_not_doubled(monkeypatch):
    """The in-text disclosure copy is removed (renderer supplies the canonical preamble)."""
    monkeypatch.setenv("PG_SYNTH_RENDER_CLEAN", "1")
    mod = _analyst_mod()
    disc = mod.ANALYST_SYNTHESIS_DISCLOSURE
    text = f"{disc}\n\n### Mechanism\n\nThe evidence suggests X [1]."
    out = mod._render_clean_synthesis(text)
    assert disc not in out, "in-text disclosure copy must be stripped so the render is not doubled"
    assert "### Mechanism" in out and "The evidence suggests X [1]." in out


def test_c5_confidence_tags_moved_to_note(monkeypatch):
    """Per-sentence [confidence:…] markers leave the prose and become one compact per-section note."""
    monkeypatch.setenv("PG_SYNTH_RENDER_CLEAN", "1")
    mod = _analyst_mod()
    text = (
        "### Clinical implications\n\n"
        "Drug A lowers risk [1]. [confidence: moderate — moderate confidence — verified against the cited source]\n"
        "Drug B may help [2]. [confidence: low — NOT confirmed by the cited source; treat as unverified]\n"
        "A broader trend is plausible. [confidence: no-source-found — no grounded source was found for this statement; shown unverified]"
    )
    out = mod._render_clean_synthesis(text)
    assert "[confidence:" not in out, "inline per-sentence confidence markers must be lifted out of prose"
    assert "Confidence labels for this interpretive section:" in out
    assert "1 moderate" in out and "1 low" in out and "1 no-source-found" in out
    # the actual claims survive (nothing dropped, render-only)
    assert "Drug A lowers risk [1]." in out
    assert "Drug B may help [2]." in out


def test_c5_off_is_byte_identical(monkeypatch):
    """OFF => the text is returned unchanged (doubled disclosure + inline markers preserved)."""
    monkeypatch.setenv("PG_SYNTH_RENDER_CLEAN", "0")
    mod = _analyst_mod()
    disc = mod.ANALYST_SYNTHESIS_DISCLOSURE
    text = f"{disc}\n\nClaim [1]. [confidence: low — NOT confirmed by the cited source; treat as unverified]"
    assert mod._render_clean_synthesis(text) == text


def test_c5_clean_input_unchanged_when_on(monkeypatch):
    """ON but nothing to clean (no in-text disclosure, no markers) => byte-identical."""
    monkeypatch.setenv("PG_SYNTH_RENDER_CLEAN", "1")
    mod = _analyst_mod()
    text = "### Mechanism\n\nThe verified data show X [1]; clinically this is interpreted as Y [2]."
    assert mod._render_clean_synthesis(text) == text


# ─────────────────────────────────────────────────────────────────────────────
# C4 — synthesized body leads; verbatim Evidence base -> supporting appendix
# ─────────────────────────────────────────────────────────────────────────────
def _msg_mod():
    return importlib.import_module("src.polaris_graph.generator.multi_section_generator")


def _mk_section(mod, title):
    return mod.SectionResult(
        title=title,
        focus="",
        ev_ids_assigned=[],
        raw_draft="",
        rewritten_draft="",
        verified_text=f"body of {title} [1].",
        biblio_slice=[],
        sentences_verified=1,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=False,
    )


def test_c4_evidence_base_moves_to_appendix(monkeypatch):
    """ON => analytical sections lead; the Evidence base + Low-relevance ledger trail as appendix."""
    monkeypatch.setenv("PG_SYNTH_BODY_LEAD", "1")
    mod = _msg_mod()
    from src.polaris_graph.generator.weighted_enrichment import (
        _EVIDENCE_BASE_TITLE,
        _LOW_RELEVANCE_LEDGER_TITLE,
    )
    sections = [
        _mk_section(mod, "Efficacy"),
        _mk_section(mod, _EVIDENCE_BASE_TITLE),
        _mk_section(mod, "Safety"),
        _mk_section(mod, _LOW_RELEVANCE_LEDGER_TITLE),
        _mk_section(mod, "Comparative"),
    ]
    out = mod._reorder_synthesis_body_lead(sections)
    titles = [s.title for s in out]
    assert titles == [
        "Efficacy", "Safety", "Comparative",
        _EVIDENCE_BASE_TITLE, _LOW_RELEVANCE_LEDGER_TITLE,
    ], "analytical sections lead in original order; supporting sections trail in original order"


def test_c4_off_is_byte_identical(monkeypatch):
    """OFF => the section order is returned unchanged."""
    monkeypatch.setenv("PG_SYNTH_BODY_LEAD", "0")
    mod = _msg_mod()
    from src.polaris_graph.generator.weighted_enrichment import _EVIDENCE_BASE_TITLE
    sections = [
        _mk_section(mod, "Efficacy"),
        _mk_section(mod, _EVIDENCE_BASE_TITLE),
        _mk_section(mod, "Safety"),
    ]
    out = mod._reorder_synthesis_body_lead(sections)
    assert [s.title for s in out] == ["Efficacy", _EVIDENCE_BASE_TITLE, "Safety"]


# ─────────────────────────────────────────────────────────────────────────────
# PT11 — compose-time numeric-citation guarantee (PG_COMPOSE_NUMERIC_CITE_GUARANTEE)
# ─────────────────────────────────────────────────────────────────────────────
def test_pt11_uncited_decimal_sentence_removed_and_disclosed(monkeypatch):
    """A decimal-bearing sentence with no [N]/[#ev:] is removed; cited decimal sentences survive."""
    monkeypatch.setenv("PG_COMPOSE_NUMERIC_CITE_GUARANTEE", "1")
    mod = _msg_mod()
    text = (
        "Risk fell by 12.5 percent [1]. "
        "A stray 4.8 percent figure has no citation here. "
        "Mortality dropped 3.2 percent [#ev:ev_9:0-10]."
    )
    cleaned, removed = mod._suppress_uncited_decimal_sentences(text)
    assert removed, "the uncited-decimal sentence must be recorded as removed"
    assert "4.8 percent figure has no citation" not in cleaned
    assert "12.5 percent [1]." in cleaned
    assert "3.2 percent [#ev:ev_9:0-10]." in cleaned


def test_pt11_cited_and_integer_only_survive(monkeypatch):
    """Integer-only sentences and cited-decimal sentences are never removed (no false positives)."""
    monkeypatch.setenv("PG_COMPOSE_NUMERIC_CITE_GUARANTEE", "1")
    mod = _msg_mod()
    text = "Week 68 outcomes were recorded. Efficacy was 15.3 percent [2]."
    cleaned, removed = mod._suppress_uncited_decimal_sentences(text)
    assert removed == []
    assert cleaned == text


def test_pt11_off_is_byte_identical(monkeypatch):
    """OFF => the text is returned unchanged even with an uncited decimal present."""
    monkeypatch.setenv("PG_COMPOSE_NUMERIC_CITE_GUARANTEE", "0")
    mod = _msg_mod()
    text = "An uncited 9.9 percent value sits here. Cited 1.1 percent [1]."
    cleaned, removed = mod._suppress_uncited_decimal_sentences(text)
    assert removed == []
    assert cleaned == text


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
