"""I-deepfix-006 (#1376) — splitter widening + PT13 lexicon v2 (provenance_generator).

Splitter (PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY): also split after terminal punctuation before a hard
furniture symbol (* © •, whitespace optional) or — with mandatory whitespace — a digit / opening quote,
so a Franken-sentence glue is separated. A decimal ("3.75", no whitespace) is NEVER split.

PT13 lexicon v2 (PG_PT13_LEXICON_V2): attribution verbs (warns / says / argues / predicts / …) are
source-anchoring hedges, and a ``top`` that is a list rank ("top 10") or positional ("at the top") is
not a superlative claim. Both default-ON, byte-identical OFF.
"""
import os

import pytest

from src.polaris_graph.generator import provenance_generator as pg


# ── splitter widening (PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY) ─────────────────────

def test_split_before_glued_furniture_symbol():
    out = pg.split_into_sentences("Adoption rose to 12%.* Bullet furniture here that is long.")
    assert out == ["Adoption rose to 12%.", "* Bullet furniture here that is long."]


def test_split_before_copyright_symbol():
    out = pg.split_into_sentences("The rate held steady.© 2025 Publisher name here.")
    assert out[0] == "The rate held steady."
    assert out[1].startswith("© 2025 Publisher")


def test_split_before_digit_requires_whitespace():
    out = pg.split_into_sentences("The trend held through 2020. 15 firms reported gains later.")
    assert out == ["The trend held through 2020.", "15 firms reported gains later."]


def test_decimal_is_never_split_mid_value():
    # "3.75" has no whitespace after the '.', so the digit leg must NOT split it.
    assert pg.split_into_sentences("The rate rose to 3.75 percent overall.") == [
        "The rate rose to 3.75 percent overall."
    ]


def test_split_before_opening_quote_sentence():
    out = pg.split_into_sentences('The analyst was blunt. "Automation is here to stay," she said.')
    assert out[0] == "The analyst was blunt."
    assert out[1].startswith('"Automation is here to stay,"')


def test_glued_closing_quote_is_not_split_off():
    # A closing quote glued to a period ("done.") must stay with its own sentence (no whitespace leg).
    assert pg.split_into_sentences('She said it was "done." Everyone agreed later.') == [
        'She said it was "done." Everyone agreed later.'
    ]


def test_splitter_off_is_byte_identical():
    os.environ["PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY"] = "0"
    try:
        s = "Adoption rose to 12%.* Bullet furniture here that is long."
        assert pg.split_into_sentences(s) == [s]
    finally:
        os.environ.pop("PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY", None)


# ── PT13 lexicon v2 (PG_PT13_LEXICON_V2) ─────────────────────────────────────

def test_attributed_warning_superlative_is_hedged_not_flagged():
    # "warns that … is the highest" ATTRIBUTES the superlative to a source => hedged => not flagged.
    assert pg._detect_unhedged_superlative(
        "The IMF warns that unemployment is the highest since 2008."
    ) is None


def test_attributed_says_predicts_are_hedged():
    assert pg._detect_unhedged_superlative("Goldman says growth will be the strongest in a decade.") is None
    assert pg._detect_unhedged_superlative("The model predicts the largest displacement yet.") is None


def test_top_list_rank_is_not_a_superlative():
    assert pg._detect_unhedged_superlative(
        "Thompson Rivers University's top 10 predictions for 2025 are listed."
    ) is None
    assert pg._detect_unhedged_superlative("The report ranks the top 5 disruptors.") is None


def test_top_positional_phrase_is_not_a_superlative():
    assert pg._detect_unhedged_superlative("The firm sits at the top of the ranking this year.") is None


def test_real_unhedged_superlative_still_flagged():
    # A genuine unhedged comparative claim is still flagged (no over-suppression).
    assert pg._detect_unhedged_superlative("Our method is the best approach available today.") == "best"


def test_real_top_superlative_still_flagged():
    # "top performer" (not a list rank / positional) is still a superlative.
    assert pg._detect_unhedged_superlative("This drug is the top performer among all rivals.") == "top"


def test_pt13_v2_off_is_byte_identical_legacy():
    os.environ["PG_PT13_LEXICON_V2"] = "0"
    try:
        # Legacy: attribution verbs are NOT hedges, and "top 10" IS flagged.
        assert pg._detect_unhedged_superlative(
            "The IMF warns that unemployment is the highest since 2008."
        ) == "highest"
        assert pg._detect_unhedged_superlative("Thompson Rivers top 10 predictions for 2025.") == "top"
    finally:
        os.environ.pop("PG_PT13_LEXICON_V2", None)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
