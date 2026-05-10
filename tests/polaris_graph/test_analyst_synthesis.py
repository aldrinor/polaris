"""Tests for I-bug-105 — Analyst Synthesis (two-layer report).

Codex iter-1 brief verdict required:
  - Output scrub guardrail removes [#ev:...] tokens (not just test)
  - Synthesis section omitted entirely when empty (no empty disclosure)
  - Bibliography [N] citation requirement in prompt
  - Manifest distinguishes verified_words from analyst_synthesis_words

These tests pin those invariants.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.analyst_synthesis import (
    ANALYST_SYNTHESIS_DISCLOSURE,
    ANALYST_SYNTHESIS_SYSTEM_PROMPT,
    _format_bibliography_for_prompt,
    _format_evidence_pool_for_prompt,
    _scrub_ev_tokens,
    _scrub_invalid_n_markers,
)


# ---------- Invalid [N] marker scrub (I-bug-108 P0) ----------

def test_scrub_invalid_n_markers_drops_out_of_range():
    text = "Result A [1]. Result B [3]. Result C [19]. Result D [2]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert n == 1
    assert "[19]" not in cleaned
    assert "[1]" in cleaned
    assert "[2]" in cleaned
    assert "[3]" in cleaned


def test_scrub_invalid_n_markers_preserves_in_range():
    text = "Result [1] and [2] and [5]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert n == 0
    assert cleaned == text


def test_scrub_invalid_n_markers_drops_zero_and_negative():
    """Markers like [0] and [-1] are invalid — bibliography indices start at 1.

    Codex iter-1 P0 hardening: regex now matches both `[N]` and `[-N]` so
    both forms get scrubbed. Bibliography emits "[1]" not "[0]" or "[-1]".
    """
    text = "Result [0] [1] [-1] [2]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert "[0]" not in cleaned
    assert "[-1]" not in cleaned, "negative markers must be scrubbed (Codex iter-1 P0)"
    assert "[1]" in cleaned
    assert "[2]" in cleaned
    assert n >= 2  # [0] and [-1]


def test_scrub_invalid_n_markers_drops_padded_forms():
    """Whitespace-padded markers like [ 5 ] don't match the canonical
    bibliography format `[5]` and are scrubbed (parser-fragile).
    """
    text = "Result [ 5 ] and [5]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert "[ 5 ]" not in cleaned
    assert "[5]" in cleaned
    assert n == 1


def test_scrub_invalid_n_markers_drops_leading_zero_forms():
    """`[01]` parses as 1 but raw form differs from canonical `[1]`."""
    text = "Result [01] and [1]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert "[01]" not in cleaned
    assert "[1]" in cleaned
    assert n == 1


def test_scrub_invalid_n_markers_logs_warning(caplog):
    text = "Result [99]."
    with caplog.at_level("WARNING"):
        _scrub_invalid_n_markers(text, biblio_size=5)
    assert any("invalid [N]" in r.message for r in caplog.records)


def test_scrub_invalid_n_markers_no_warning_on_clean(caplog):
    text = "Result [1] [2]."
    with caplog.at_level("WARNING"):
        _scrub_invalid_n_markers(text, biblio_size=5)
    assert not any("invalid [N]" in r.message for r in caplog.records)


def test_scrub_invalid_n_markers_handles_mass_hallucination():
    """Real-world failure mode: synthesis LLM emitted [18] [19] when
    biblio had 17 entries. Scrub fixes both.
    """
    text = "Result [18] and [19] and [3]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=17)
    assert n == 2
    assert "[18]" not in cleaned
    assert "[19]" not in cleaned
    assert "[3]" in cleaned


# ---------- Scrub guardrail (Codex iter-1 P0) ----------

def test_scrub_removes_single_ev_token():
    text = "The drug reduced HbA1c by 1.5% [#ev:ev_001:0-50] in adults."
    cleaned = _scrub_ev_tokens(text)
    assert "[#ev:" not in cleaned
    assert "1.5%" in cleaned


def test_scrub_removes_multiple_ev_tokens():
    text = "First [#ev:ev_a:0-10] then [#ev:ev_b:5-20] always [#ev:ev_c:1-2]."
    cleaned = _scrub_ev_tokens(text)
    assert "[#ev:" not in cleaned
    # Counts preserved minus ev tokens (whitespace/format may shift)
    assert "First" in cleaned and "then" in cleaned and "always" in cleaned


def test_scrub_preserves_n_bibliography_markers():
    """[N] citation markers MUST survive — they are the legitimate
    synthesis citation format. Scrub MUST NOT touch them.
    """
    text = "Results consistent with [1] and [2], extending [3]."
    cleaned = _scrub_ev_tokens(text)
    assert "[1]" in cleaned
    assert "[2]" in cleaned
    assert "[3]" in cleaned


def test_scrub_logs_warning_when_tokens_present(caplog):
    text = "Drug worked [#ev:ev_x:0-5]."
    with caplog.at_level("WARNING"):
        _scrub_ev_tokens(text)
    assert any(
        "scrubbed" in r.message and "synthesis" in r.message
        for r in caplog.records
    )


def test_scrub_no_warning_on_clean_text(caplog):
    text = "Drug worked according to [1]."
    with caplog.at_level("WARNING"):
        _scrub_ev_tokens(text)
    assert not any("scrubbed" in r.message for r in caplog.records)


def test_scrub_handles_empty_string():
    assert _scrub_ev_tokens("") == ""


# ---------- Bibliography rendering ----------

def test_bibliography_renders_numbered():
    bib = [
        {"title": "Trial A", "url": "https://a.example", "tier": "T1"},
        {"title": "Review B", "url": "https://b.example", "tier": "T2"},
    ]
    rendered = _format_bibliography_for_prompt(bib)
    assert "[1]" in rendered
    assert "[2]" in rendered
    assert "Trial A" in rendered
    assert "Review B" in rendered


def test_bibliography_includes_tier_when_present():
    bib = [{"title": "X", "url": "https://x", "tier": "T1"}]
    rendered = _format_bibliography_for_prompt(bib)
    assert "(tier T1)" in rendered


def test_bibliography_handles_missing_url():
    bib = [{"title": "Y"}]
    rendered = _format_bibliography_for_prompt(bib)
    assert "[1] Y" in rendered


def test_bibliography_handles_empty_list():
    assert _format_bibliography_for_prompt([]) == ""


# ---------- Evidence pool rendering ----------

def test_evidence_pool_renders_blocks():
    rows = [
        {"evidence_id": "ev_1", "direct_quote": "Result one"},
        {"evidence_id": "ev_2", "direct_quote": "Result two"},
    ]
    rendered = _format_evidence_pool_for_prompt(rows)
    assert "<<<evidence:ev_1>>>" in rendered
    assert "<<<evidence:ev_2>>>" in rendered
    assert "Result one" in rendered
    assert "Result two" in rendered


def test_evidence_pool_caps_at_max_rows():
    rows = [
        {"evidence_id": f"ev_{i}", "direct_quote": f"row{i}"}
        for i in range(50)
    ]
    rendered = _format_evidence_pool_for_prompt(rows, max_rows=5)
    # Only first 5 rendered
    for i in range(5):
        assert f"ev_{i}" in rendered
    for i in range(5, 50):
        assert f"ev_{i}" not in rendered


def test_evidence_pool_truncates_long_quotes():
    long_quote = "x" * 5000
    rows = [{"evidence_id": "ev_x", "direct_quote": long_quote}]
    rendered = _format_evidence_pool_for_prompt(rows)
    # Quote truncated to 1200 chars in our impl
    assert len([line for line in rendered.split("\n") if "x" * 1200 in line]) == 1


# ---------- Disclosure preamble ----------

def test_disclosure_preamble_mentions_not_span_verified():
    """The disclosure MUST tell readers these sentences are NOT
    individually span-verified — that's the whole two-layer contract.
    """
    assert "not individually span-verified" in ANALYST_SYNTHESIS_DISCLOSURE.lower() \
        or "are not individually span-verified" in ANALYST_SYNTHESIS_DISCLOSURE


def test_disclosure_preamble_mentions_audit_grade_distinction():
    """Reader must understand verified core ≠ synthesis."""
    assert "audit-grade" in ANALYST_SYNTHESIS_DISCLOSURE.lower()


def test_disclosure_preamble_references_verified_findings():
    """The synthesis must point back at the audit core."""
    assert "Verified Findings" in ANALYST_SYNTHESIS_DISCLOSURE


# ---------- System prompt invariants ----------

def test_prompt_forbids_ev_tokens():
    """The prompt MUST tell the LLM to not use [#ev:...] tokens.
    This is the upstream half of the two-layer contract; the scrub
    guardrail is the downstream backstop.
    """
    assert "NEVER by [#ev:...]" in ANALYST_SYNTHESIS_SYSTEM_PROMPT or \
        "no [#ev:...] tokens" in ANALYST_SYNTHESIS_SYSTEM_PROMPT


def test_prompt_requires_bibliography_n_citations():
    """Codex iter-1 P0: prompt should require [N] citations where
    concrete evidence is discussed.
    """
    assert "[N]" in ANALYST_SYNTHESIS_SYSTEM_PROMPT
    assert "bibliography" in ANALYST_SYNTHESIS_SYSTEM_PROMPT.lower()


def test_prompt_requires_hedge_phrasing():
    """The prompt MUST instruct the LLM to hedge interpretive claims
    so readers know which sentences are interpretive vs audit-grade.
    """
    prompt_lower = ANALYST_SYNTHESIS_SYSTEM_PROMPT.lower()
    assert "hedge" in prompt_lower
    # At least one of the standard hedge phrases
    assert (
        "consistent with" in prompt_lower
        or "literature broadly suggests" in prompt_lower
        or "typically interpreted" in prompt_lower
    )


def test_prompt_requires_subsections():
    """Per Codex iter-1: sub_section_structure: yes.

    I-bug-106: subheadings must be ### (not ##) so the synthesis
    renders under a parent ## heading without breaking markdown
    hierarchy.
    """
    prompt_lower = ANALYST_SYNTHESIS_SYSTEM_PROMPT.lower()
    assert "sub-section" in prompt_lower or "subsection" in prompt_lower
    # I-bug-106: prompt MUST request ### (3-hash) subheadings.
    assert "###" in ANALYST_SYNTHESIS_SYSTEM_PROMPT


def test_prompt_forbids_double_hash_subheadings():
    """I-bug-106: prompt must explicitly forbid ## headers in synthesis
    output (those are reserved for the parent section that wraps the
    synthesis block).
    """
    prompt_lower = ANALYST_SYNTHESIS_SYSTEM_PROMPT.lower()
    # The prompt should explicitly mention "not ##" or "do not emit ##"
    assert "not ##" in prompt_lower or "do not emit ##" in prompt_lower
