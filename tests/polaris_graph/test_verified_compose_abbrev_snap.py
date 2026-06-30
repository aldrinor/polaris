"""I-deepfix-001 (Codex #1335 gate P2) — the span-snap sentence-terminator must NOT treat a ``.``
after a common abbreviation (Fig. / Dr. / U.S. / et al. / e.g. / i.e. / vs. / No. / pp.) as a real
sentence boundary, so ``_snap_span_end_to_sentence`` can no longer stop right after the abbreviation.

The guard is extend-ONLY and faithfulness-safe: refusing a boundary can only lengthen the snapped
span (still a superset within the same row), never truncate one. These tests pin both halves:
abbreviation dots are rejected, and genuine terminators (incl. decimals, real single-capital ends)
still terminate.
"""
from src.polaris_graph.generator.verified_compose import (
    _is_real_sentence_terminator,
    _preceding_token_is_abbreviation,
    _snap_span_end_to_sentence,
)


def _dot_index(text: str, occurrence: int = 1) -> int:
    """Index of the ``occurrence``-th '.' in ``text`` (1-based)."""
    pos = -1
    for _ in range(occurrence):
        pos = text.index(".", pos + 1)
    return pos


# ── abbreviation dots are NOT terminators ────────────────────────────────────

def test_fig_dot_is_not_a_terminator():
    s = "see Fig. 4 for the trend"
    k = _dot_index(s)  # the '.' in "Fig."
    assert s[k] == "."
    assert not _is_real_sentence_terminator(s, k, len(s))


def test_dr_dot_is_not_a_terminator():
    s = "treated by Dr. Smith and colleagues"
    k = _dot_index(s)
    assert not _is_real_sentence_terminator(s, k, len(s))


def test_et_al_dot_is_not_a_terminator():
    s = "as reported by Morrar et al. in the review"
    k = _dot_index(s)  # the '.' after "al"
    assert not _is_real_sentence_terminator(s, k, len(s))


def test_eg_initialism_final_dot_is_not_a_terminator():
    s = "many tasks e.g. writing and coding"
    k = _dot_index(s, 2)  # the final '.' of "e.g."
    assert s[k] == "."
    assert not _is_real_sentence_terminator(s, k, len(s))


def test_us_initialism_final_dot_is_not_a_terminator():
    s = "the U.S. workforce shifted"
    k = _dot_index(s, 2)  # the final '.' of "U.S."
    assert not _is_real_sentence_terminator(s, k, len(s))


def test_vs_and_no_and_pp_dots_are_not_terminators():
    for s in ("compared A vs. B here", "see No. 5 below", "found in pp. 12 onward"):
        k = _dot_index(s)
        assert not _is_real_sentence_terminator(s, k, len(s)), s


# ── genuine terminators STILL terminate (no over-reach) ──────────────────────

def test_plain_sentence_end_still_terminates():
    s = "Automation displaces labor. New tasks reinstate it."
    k = _dot_index(s)  # the '.' after "labor"
    assert _is_real_sentence_terminator(s, k, len(s))


def test_decimal_point_is_not_a_terminator():
    s = "the figure rose to 3.75 percent"
    k = _dot_index(s)
    assert not _is_real_sentence_terminator(s, k, len(s))


def test_single_capital_not_in_initialism_still_terminates():
    # A lone capital followed by '.' + space, NOT preceded by a dot, is a real end.
    s = "the assigned grade was A. The next cohort improved."
    k = _dot_index(s)  # the '.' after "A"
    assert _is_real_sentence_terminator(s, k, len(s))


def test_preceding_token_helper_direct():
    assert _preceding_token_is_abbreviation("Fig.", 3)
    assert _preceding_token_is_abbreviation("vs.", 2)
    assert not _preceding_token_is_abbreviation("labor.", 5)


# ── end-to-end: the snap extends PAST the abbreviation to the real boundary ───

def test_snap_extends_past_abbreviation_to_real_sentence_end():
    text = "Access improved per Fig. 4 across all agents. The next section follows."
    # A cited span that ends mid-sentence right after "Fig" (before the abbreviation dot region).
    start = 0
    end = text.index("Fig")  # span ends just before "Fig." -> mid-sentence
    snapped = _snap_span_end_to_sentence(text, start, end)
    # Must extend to the REAL sentence end ("... all agents."), never stop after "Fig.".
    assert text[:snapped].rstrip().endswith("all agents.")
    assert "Fig. 4 across all agents." in text[:snapped]
