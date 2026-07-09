"""Codex P1 gate-fix — SENTENCE-granular citation exclusion in the FIX-13 framing scan.

The prior ``_framing_violation`` excluded an ENTIRE body line if ANY ``[N]`` marker appeared on it,
so an UNCITED reformulation sentence sharing a markdown line / paragraph with a cited sibling
sentence slipped through under ``PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY=1`` (the flag the launch
turns ON). The fix scopes the citation exclusion to the SENTENCE carrying the phrase, not the whole
line.

Acceptance (spec, this file):
  (1) the exact "Fourth Industrial Revolution ... [1]" mixed-paragraph case IS flagged (flag-ON);
  (2) a genuinely cited-only sentence adopting the phrase is NOT flagged (flag-ON);
  (3) a heading with the phrase IS flagged (flag-ON);
  (4) a newline-split uncited phrase IS flagged (flag-ON);
  (5) flag-OFF reproduces the body-wide containment (byte-identical OFF path).

NO network / NO spend / NO GPU: pure string predicates. GREEN =
``python -m pytest tests/dr_benchmark/test_run_validity_framing_sentence_granular_gatefix.py -q``.
"""
from __future__ import annotations

from scripts.dr_benchmark.run_validity_gate import (
    _framing_violation,
    _norm,
    check_question_fidelity,
)

_FIR = "fourth industrial revolution"

# The bound question mentions NEITHER forbidden phrase, so a report carrying the phrase is a
# reformulation tell (never legitimately-in-question).
_QUESTION = "The impact of Generative AI on the future labor market."
_CONTRACT = {"forbidden_reformulations": ["Fourth Industrial Revolution"]}

# (1) The exact mandated mixed-paragraph case: an UNCITED reformulation sentence sharing a markdown
#     line with a cited sibling sentence. The FIRST sentence is an uncited reformulation.
_MIXED_LINE = (
    "The Fourth Industrial Revolution will transform every occupation. "
    "Productivity evidence is mixed [1]."
)
# (2) A genuinely cited-only sentence that adopts the phrase and carries its OWN [N].
_CITED_ONLY = "The Fourth Industrial Revolution reshapes labor markets [2]."
# (3) A heading carrying the phrase (must be scanned cited-or-not).
_HEADING = "## The Fourth Industrial Revolution lens"
# (4) A hard line-wrap breaking the phrase across a newline, on an uncited sentence.
_NEWLINE_SPLIT = "The Fourth Industrial\nRevolution changes work."


# ── pure predicate ───────────────────────────────────────────────────────────────────────────
def test_mixed_line_uncited_reformulation_is_flagged():
    # (1) the uncited first sentence is a VIOLATION even though [1] shares the line.
    assert _framing_violation(_MIXED_LINE, _FIR) is True


def test_cited_only_sentence_is_not_flagged():
    # (2) a sentence that ITSELF carries [N] is cited evidence -> excluded.
    assert _framing_violation(_CITED_ONLY, _FIR) is False


def test_heading_with_phrase_is_flagged():
    # (3) headings are always scanned.
    assert _framing_violation(_HEADING, _FIR) is True


def test_newline_split_uncited_phrase_is_flagged():
    # (4) phrase broken across a hard newline still matches after per-sentence _norm.
    assert _framing_violation(_NEWLINE_SPLIT, _FIR) is True


def test_cited_only_heading_still_flagged():
    # A heading with the phrase AND a citation marker is STILL flagged (headings ignore citations).
    assert _framing_violation("## The Fourth Industrial Revolution outlook [7]", _FIR) is True


def test_mixed_line_with_leading_cited_then_uncited_reformulation():
    # Order-independence: cited claim FIRST, uncited reformulation SECOND on the same line.
    md = "Productivity evidence is mixed [1]. The Fourth Industrial Revolution transforms all work."
    assert _framing_violation(md, _FIR) is True


def test_two_cited_sentences_sharing_line_not_flagged():
    # Both sentences carry their own [N] -> neither is a violation.
    md = "The Fourth Industrial Revolution reshapes work [1]. Productivity is mixed [2]."
    assert _framing_violation(md, _FIR) is False


# ── check_question_fidelity end-to-end (flag-ON) ──────────────────────────────────────────────
def test_mixed_line_flagged_under_framing_only_on():
    v = check_question_fidelity(_MIXED_LINE, _QUESTION, _CONTRACT, framing_only=True)
    assert any("reformulation phrase" in m for m in v), v


def test_cited_only_not_flagged_under_framing_only_on():
    v = check_question_fidelity(_CITED_ONLY, _QUESTION, _CONTRACT, framing_only=True)
    assert not any("reformulation phrase" in m for m in v), v


# ── flag-OFF reproduces body-wide containment (byte-identical OFF path) ────────────────────────
def test_flag_off_is_body_wide_containment_for_cited_only():
    # OFF path is plain substring containment: even the cited-only mention trips it (unchanged).
    v_off = check_question_fidelity(_CITED_ONLY, _QUESTION, _CONTRACT, framing_only=False)
    assert any("reformulation phrase" in m for m in v_off), v_off
    # And that OFF verdict equals the raw containment predicate the OFF branch uses.
    assert (_norm("Fourth Industrial Revolution") in _norm(_CITED_ONLY)) is True


def test_flag_off_matches_raw_containment_across_reports():
    # For every fixture, framing_only=False verdict-presence == raw body-wide substring containment.
    for report in (_MIXED_LINE, _CITED_ONLY, _HEADING, _NEWLINE_SPLIT):
        v_off = check_question_fidelity(report, _QUESTION, _CONTRACT, framing_only=False)
        off_flagged = any("reformulation phrase" in m for m in v_off)
        raw_present = _norm("Fourth Industrial Revolution") in _norm(report)
        assert off_flagged is raw_present, (report, off_flagged, raw_present)


def test_default_kwarg_equals_off():
    # No framing_only kwarg => identical to framing_only=False (caller-compat, byte-identical).
    for report in (_MIXED_LINE, _CITED_ONLY, _HEADING, _NEWLINE_SPLIT):
        assert (
            check_question_fidelity(report, _QUESTION, _CONTRACT)
            == check_question_fidelity(report, _QUESTION, _CONTRACT, framing_only=False)
        )
