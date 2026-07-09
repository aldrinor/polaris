"""Codex+Fable P1 gate-fix — the sentence splitter glued an UNCITED reformulation onto a FOLLOWING
cited line when the uncited line had NO terminal punctuation (bullets, GFM table rows, blockquotes,
numbered-list items, plain unterminated lines). The glued unit then carried the following line's
``[N]`` marker, so the whole unit was EXCLUDED as cited evidence and a real uncited reformulation
slipped through under ``PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY=1``.

The fix splits the body into UNITS on BOTH sentence terminals (``.!?``) AND newlines, so every line
becomes its own unit and carries its own citation status; consecutive UNCITED units are re-joined so
a hard-wrapped phrase split across two uncited lines is still caught, while a cited unit / heading /
blank line breaks the run so an uncited→cited hard-wrap is NOT joined (the drb_72 cited-evidence
false-positive stays fixed).

Probes A–K are the SPEC (every probe an explicit assert, all under framing_only=ON except K).
NO network / NO spend / NO GPU: pure string predicates. GREEN =
``python -m pytest tests/dr_benchmark/test_run_validity_framing_glued_uncited_gatefix.py -q``.
"""
from __future__ import annotations

from scripts.dr_benchmark.run_validity_gate import (
    _framing_violation,
    _norm,
    check_question_fidelity,
)

_FIR = "fourth industrial revolution"

# The bound question mentions NEITHER forbidden phrase, so a report carrying the phrase in a framing
# position is a reformulation tell (never legitimately-in-question).
_QUESTION = "The impact of Generative AI on the future labor market."
_CONTRACT = {"forbidden_reformulations": ["Fourth Industrial Revolution"]}


# ── MUST FLAG — a real UNCITED reformulation (violation) ─────────────────────────────────────────

# A. same physical line, two sentences; the FIRST (uncited) sentence is the reformulation.
_A = (
    "The Fourth Industrial Revolution will transform every occupation. "
    "Productivity evidence is mixed [1]."
)
# B. plain UNTERMINATED line (no .!?) glued before a cited next line.
_B = "The Fourth Industrial Revolution reshapes work\nProductivity mixed [1]"
# C. markdown bullets — uncited bullet before a cited bullet.
_C = "- The Fourth Industrial Revolution reshapes all work\n- Productivity mixed [1]"
# D. GFM table rows — uncited row before a cited row.
_D = "| The Fourth Industrial Revolution | broad claim |\n| Productivity | mixed [1] |"
# E. blockquote + numbered-list variants of the same glue pattern.
_E_BLOCKQUOTE = "> The Fourth Industrial Revolution reshapes work\n> Productivity mixed [1]"
_E_NUMBERED = "1. The Fourth Industrial Revolution reshapes work\n2. Productivity mixed [1]"
# F. hard-wrapped phrase, UNCITED — split across a newline, no citation anywhere near.
_F = "The Fourth Industrial\nRevolution reshapes work"
# G. heading carrying the phrase (cited or not) — always framing.
_G_PLAIN = "## The Fourth Industrial Revolution overview"
_G_H1 = "# The Fourth Industrial Revolution"
_G_CITED = "## The Fourth Industrial Revolution outlook [3]"


def test_probe_a_same_line_two_sentences_first_uncited_is_flagged():
    assert _framing_violation(_A, _FIR) is True


def test_probe_b_plain_unterminated_line_before_cited_is_flagged():
    assert _framing_violation(_B, _FIR) is True


def test_probe_c_markdown_bullets_is_flagged():
    assert _framing_violation(_C, _FIR) is True


def test_probe_d_gfm_table_rows_is_flagged():
    assert _framing_violation(_D, _FIR) is True


def test_probe_e_blockquote_variant_is_flagged():
    assert _framing_violation(_E_BLOCKQUOTE, _FIR) is True


def test_probe_e_numbered_list_variant_is_flagged():
    assert _framing_violation(_E_NUMBERED, _FIR) is True


def test_probe_f_hardwrapped_uncited_phrase_is_flagged():
    # The hard-wrap catching property MUST be preserved: consecutive uncited lines are re-joined.
    assert _framing_violation(_F, _FIR) is True


def test_probe_g_heading_plain_is_flagged():
    assert _framing_violation(_G_PLAIN, _FIR) is True


def test_probe_g_heading_h1_is_flagged():
    assert _framing_violation(_G_H1, _FIR) is True


def test_probe_g_heading_cited_is_flagged():
    # Headings are ALWAYS scanned regardless of a citation marker on the heading line.
    assert _framing_violation(_G_CITED, _FIR) is True


# ── MUST NOT FLAG — legitimate CITED evidence (no false positive; the drb_72 FIX-13 case) ─────────

# H. a single cited-only sentence that mentions the phrase and carries its OWN [N].
_H = "Industry 4.0, the so-called Fourth Industrial Revolution, is examined [27]."
# I. three SEPARATELY-cited sentences, each its own [N] sentence mentioning the phrase.
_I = (
    "The Fourth Industrial Revolution is examined here [1]. "
    "The Fourth Industrial Revolution recurs across policy analyses [2]. "
    "The Fourth Industrial Revolution debate continues in the literature [3]."
)
# J. hard-wrapped phrase INSIDE a cited sentence — the wrap spans an uncited-fragment→cited boundary,
#    so the cited unit breaks the run and the phrase is NOT joined/flagged.
_J = "Growth attributed to the Fourth Industrial\nRevolution is documented in the data [1]."


def test_probe_h_cited_only_sentence_is_not_flagged():
    assert _framing_violation(_H, _FIR) is False


def test_probe_i_three_separately_cited_sentences_not_flagged():
    assert _framing_violation(_I, _FIR) is False


def test_probe_j_hardwrap_inside_cited_sentence_not_flagged():
    assert _framing_violation(_J, _FIR) is False


# ── end-to-end through check_question_fidelity (framing_only=ON) ───────────────────────────────────

def test_all_must_flag_probes_flagged_under_framing_only_on():
    for report in (_A, _B, _C, _D, _E_BLOCKQUOTE, _E_NUMBERED, _F, _G_PLAIN, _G_H1, _G_CITED):
        v = check_question_fidelity(report, _QUESTION, _CONTRACT, framing_only=True)
        assert any("reformulation phrase" in m for m in v), report


def test_all_must_not_flag_probes_not_flagged_under_framing_only_on():
    for report in (_H, _I, _J):
        v = check_question_fidelity(report, _QUESTION, _CONTRACT, framing_only=True)
        assert not any("reformulation phrase" in m for m in v), report


# ── K. flag-OFF (framing_only=False) reproduces body-wide substring containment byte-identical ─────

def test_probe_k_flag_off_is_body_wide_containment_byte_identical():
    # The OFF branch of check_question_fidelity is a pure ``_norm(phrase) in _norm(report)`` substring
    # test that NEVER calls _framing_violation / _split_sentences, so it is byte-identical to the
    # pre-fix behaviour. Prove it: for EVERY probe (flag + non-flag), the framing_only=False
    # verdict-presence equals raw body-wide substring containment.
    phrase_n = _norm("Fourth Industrial Revolution")
    for report in (
        _A, _B, _C, _D, _E_BLOCKQUOTE, _E_NUMBERED, _F, _G_PLAIN, _G_H1, _G_CITED, _H, _I, _J,
    ):
        v_off = check_question_fidelity(report, _QUESTION, _CONTRACT, framing_only=False)
        off_flagged = any("reformulation phrase" in m for m in v_off)
        raw_present = phrase_n in _norm(report)
        assert off_flagged is raw_present, (report, off_flagged, raw_present)
        # Every probe DOES contain the phrase body-wide, so OFF flags ALL of them (incl. the
        # cited-only H/I/J that framing_only=ON correctly suppresses) — the exact pre-FIX-13 abort.
        assert off_flagged is True, report


def test_probe_k_default_kwarg_equals_off():
    # No framing_only kwarg => identical to framing_only=False (caller-compat, byte-identical).
    for report in (_A, _B, _C, _D, _F, _H, _I, _J):
        assert (
            check_question_fidelity(report, _QUESTION, _CONTRACT)
            == check_question_fidelity(report, _QUESTION, _CONTRACT, framing_only=False)
        ), report


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
