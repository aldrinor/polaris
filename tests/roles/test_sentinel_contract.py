"""Contract tests for the Sentinel (Granite Guardian) groundedness parser.

The LETHAL property under test: polarity is yes->UNGROUNDED / no->GROUNDED, and EVERY
malformed input fails CLOSED to UNGROUNDED. There is NO input that yields a silent
GROUNDED. Pure logic, no model, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.roles.sentinel_contract import (
    SentinelResult,
    SentinelVerdict,
    parse_sentinel_grounded_token,
    parse_sentinel_score,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# --- golden polarity ---------------------------------------------------------------
def test_yes_maps_to_ungrounded_golden_fixture() -> None:
    result = parse_sentinel_score(_read_fixture("sentinel_yes_ungrounded.txt"))
    assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True)


def test_no_maps_to_grounded_golden_fixture() -> None:
    result = parse_sentinel_score(_read_fixture("sentinel_no_grounded.txt"))
    assert result == SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)


@pytest.mark.parametrize(
    "raw",
    [
        "<score>yes</score>",
        "<score>YES</score>",
        "  <score>  Yes  </score>  ",
        "<SCORE>yes</SCORE>",
        "\n<score>yes</score>\n",
    ],
)
def test_yes_variants_all_ungrounded(raw: str) -> None:
    result = parse_sentinel_score(raw)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


@pytest.mark.parametrize(
    "raw",
    [
        "<score>no</score>",
        "<score>NO</score>",
        "  <score> No </score> ",
    ],
)
def test_no_variants_all_grounded(raw: str) -> None:
    result = parse_sentinel_score(raw)
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True


# --- fail CLOSED on malformed/missing/ambiguous ------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        "",                              # empty
        "   ",                           # whitespace only
        "yes",                           # no tag at all
        "<score></score>",              # empty body
        "<score>maybe</score>",         # off-enum body
        "<score>yes",                    # unclosed tag
        "the model refused to answer",  # prose, no tag
        "<score>yes</score><score>no</score>",  # ambiguous: disagreeing tags
        "<score>no</score><score>no</score>",   # P0: duplicate AGREEING tags (was GROUNDED)
        "<score>yes</score><score>yes</score>", # P0: duplicate agreeing tags
        "<score>no</score>\n<score>no</score>", # P0: duplicate across newline
        "<score>no</score><score>maybe",         # P0 iter-2: clean no + malformed 2nd tag (no close)
        "<score>no</score><score>",              # P0 iter-2: clean no + stray open tag
        "<score>yes</score><score>",             # P0 iter-2: clean yes + stray open tag
        "<score>no< /score>",                    # malformed close (stray whitespace)
        "<score>no</score></score>",             # extra stray close tag
        "Reasoning: risk detected.\n<score>yes</score>",  # P1 iter-3: prose-wrapped (yes)
        "prefix <score>no</score> suffix",                # P1 iter-3: prose-wrapped (no)
        "<score>no</score> trailing rationale",           # P1 iter-3: trailing prose
        "Reasoning: unsafe\n<score>no</score>",           # P1 iter-3: leading prose
    ],
)
def test_malformed_fails_closed_to_ungrounded_with_flag(raw: str) -> None:
    result = parse_sentinel_score(raw)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_duplicate_score_tags_fail_closed_codex_p0_regression() -> None:
    """Codex sub-PR-2 diff iter-1 P0: more than one `<score>` tag MUST fail closed,
    even when the tags agree. A set-of-distinct-values guard let two identical `no`
    tags collapse to one and return GROUNDED with parsed_ok=True — a silent
    grounded-on-bad-input path. Count occurrences, not distinct values.
    """
    for raw in (
        "<score>no</score><score>no</score>",
        "<score>NO</score>\n<score>no</score>",
        "<score>yes</score><score>yes</score>",
        "<score>no</score><score>no</score><score>no</score>",
    ):
        result = parse_sentinel_score(raw)
        assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False), raw


def test_clean_tag_then_malformed_tag_fails_closed_codex_p0_iter2_regression() -> None:
    """Codex sub-PR-2 diff iter-2 continuing P0: a clean `<score>no</score>` followed by
    MALFORMED score markup (a second tag with no close, or a stray `<score>`) left exactly
    one complete regex match and returned GROUNDED, parsed_ok=True. Counting raw opening/
    closing tag occurrences closes it: any extra/partial score markup fails closed.
    Codex's exact probes:
    """
    for raw in (
        "<score>no</score><score>maybe",   # Codex probe 1
        "<score>no</score><score>",        # Codex probe 2
        "<score>yes</score><score>",
        "<score>no< /score>",              # malformed close
        "<score>no</score></score>",       # extra close
    ):
        result = parse_sentinel_score(raw)
        assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False), raw


def test_prose_wrapped_score_fails_closed_codex_p1_iter3_regression() -> None:
    """Codex sub-PR-2 diff iter-3 P1: a single clean `no` tag wrapped in arbitrary prose
    returned (GROUNDED, parsed_ok=True). The strict full-match envelope means parsed_ok=True
    is reserved for a lone `<score>yes|no</score>` (surrounding whitespace aside); any prose
    fails closed to UNGROUNDED. Codex's exact probes:
    """
    for raw in (
        "Reasoning: unsafe\n<score>no</score>",
        "<score>no</score> trailing rationale",
        "prefix <score>no</score> suffix",
        "Reasoning: risk detected.\n<score>yes</score>",
    ):
        result = parse_sentinel_score(raw)
        assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False), raw


def test_unicode_homoglyph_tag_fails_closed_codex_p1_iter4_regression() -> None:
    """Codex sub-PR-2 diff iter-4 P1: Unicode case-folding under bare re.IGNORECASE accepted
    homoglyphs (U+017F LONG S 'ſ' folds to 's'), so `<ſcore>no</ſcore>` returned
    (GROUNDED, parsed_ok=True). re.ASCII restricts folding to a-z/A-Z so only the verified
    ASCII envelope is trusted. Probes (all must fail closed to UNGROUNDED):
    """
    for raw in (
        "<ſcore>no</ſcore>",   # Codex probe: <ſcore>no</ſcore>
        "<score>no</ſcore>",        # mixed: ASCII open, homoglyph close
        "<ſcore>yes</ſcore>",
        "<ſcore>no</ſcore>",             # literal long-s (same as ſ)
    ):
        result = parse_sentinel_score(raw)
        assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False), repr(raw)


def test_non_string_input_fails_closed() -> None:
    # Defensive: a non-string (e.g. None from an upstream bug) must NOT crash into a
    # silent GROUNDED. It fails closed.
    result = parse_sentinel_score(None)  # type: ignore[arg-type]
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


# --- explicit anti-inversion guard (the lethal property) ---------------------------
def test_yes_is_never_grounded_anti_inversion() -> None:
    """`yes` (risk present) must NEVER, under any spelling/spacing, map to GROUNDED."""
    for raw in (
        "<score>yes</score>",
        "<score>YES</score>",
        "<score>  yes  </score>",
        "<SCORE>Yes</SCORE>",
    ):
        result = parse_sentinel_score(raw)
        assert result.verdict is not SentinelVerdict.GROUNDED, raw
        assert result.verdict is SentinelVerdict.UNGROUNDED, raw


def test_no_malformed_input_ever_returns_grounded() -> None:
    """No malformed input may produce GROUNDED — the only safe failure side is UNGROUNDED."""
    for raw in ("", "yes", "<score>maybe</score>", "garbage", "<score>no", None):
        result = parse_sentinel_score(raw)  # type: ignore[arg-type]
        if not result.parsed_ok:
            assert result.verdict is SentinelVerdict.UNGROUNDED, repr(raw)


# === NON-INVERTED parser (benchmark Sentinel, I-run11-002 L1) =======================
# Direct polarity: GROUNDED -> GROUNDED, UNGROUNDED -> UNGROUNDED. EVERY ambiguous output
# (both tokens, neither, repeated, non-string) fails CLOSED to UNGROUNDED with parsed_ok=False.
# NOT a flip of the inverted parser — a separate contract over the non-inverted prompt's output.
@pytest.mark.parametrize(
    "raw",
    [
        "GROUNDED",
        "grounded",
        " GROUNDED ",
        "GROUNDED.",                 # word-boundary count tolerates a trailing period
        "\nGROUNDED\n",
    ],
)
def test_noninverted_grounded_token_maps_to_grounded(raw: str) -> None:
    result = parse_sentinel_grounded_token(raw)
    assert result == SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True), repr(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "UNGROUNDED",
        "ungrounded",
        " UNGROUNDED ",
        "UNGROUNDED.",
        "\nUNGROUNDED\n",
    ],
)
def test_noninverted_ungrounded_token_maps_to_ungrounded(raw: str) -> None:
    # The substring trap: UNGROUNDED contains "grounded", but `\bgrounded\b` does NOT fire inside
    # it (no left word boundary), so this is a CLEAN UNGROUNDED, not a both-present fail-close.
    result = parse_sentinel_grounded_token(raw)
    assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True), repr(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",                                  # empty
        "   ",                               # whitespace only
        "maybe",                             # neither token
        "the model refused to answer",       # prose, neither token
        "GROUNDED UNGROUNDED",               # both present -> ambiguous
        "UNGROUNDED GROUNDED",               # both present, other order
        "The claim is GROUNDED and also UNGROUNDED",  # both in prose
        "GROUNDED GROUNDED",                 # repeated GROUNDED -> ambiguous
        "UNGROUNDED UNGROUNDED",             # repeated UNGROUNDED -> ambiguous
        "groundedness",                      # NOT a \bgrounded\b match (no right boundary)
    ],
)
def test_noninverted_ambiguous_or_missing_fails_closed(raw: str) -> None:
    result = parse_sentinel_grounded_token(raw)
    assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False), repr(raw)


def test_noninverted_non_string_fails_closed() -> None:
    result = parse_sentinel_grounded_token(None)  # type: ignore[arg-type]
    assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)


def test_noninverted_score_tag_output_fails_closed() -> None:
    """The non-inverted parser must NOT accept the INVERTED `<score>` tags — a model emitting the
    wrong format under the non-inverted prompt is ambiguous and must fail closed, never a silent
    GROUNDED (the `<score>no</score>` would otherwise be mis-trusted)."""
    for raw in ("<score>no</score>", "<score>yes</score>"):
        result = parse_sentinel_grounded_token(raw)
        assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False), raw


def test_noninverted_never_silently_grounded_anti_inversion() -> None:
    """The lethal property for the non-inverted contract: no ambiguous/garbage input may yield a
    GROUNDED. The ONLY GROUNDED path is exactly one standalone `GROUNDED` and zero `UNGROUNDED`."""
    for raw in ("", "maybe", "UNGROUNDED", "GROUNDED UNGROUNDED", "groundedness", None):
        result = parse_sentinel_grounded_token(raw)  # type: ignore[arg-type]
        if not (
            result.verdict is SentinelVerdict.GROUNDED and result.parsed_ok
        ):
            assert result.verdict is SentinelVerdict.UNGROUNDED, repr(raw)
