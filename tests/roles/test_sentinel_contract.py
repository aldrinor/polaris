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
    parse_sentinel_decomposition,
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


# === I-run11-002 L1 iter-2: strict non-inverted parser — no false-accept (Codex diff-gate P1) ===
import pytest as _pytest  # noqa: E402
from src.polaris_graph.roles.sentinel_contract import (  # noqa: E402
    parse_sentinel_grounded_token as _pg,
    SentinelVerdict as _SV,
)


@_pytest.mark.parametrize("raw,verdict,ok", [
    ("GROUNDED", _SV.GROUNDED, True),
    ("UNGROUNDED", _SV.UNGROUNDED, True),
    ("GROUNDED.", _SV.GROUNDED, True),
    ("  ungrounded  ", _SV.UNGROUNDED, True),
    # FALSE-ACCEPT guards (Codex P1): negated/prose must FAIL CLOSED to UNGROUNDED.
    ("not grounded", _SV.UNGROUNDED, False),
    ("The claim is not grounded.", _SV.UNGROUNDED, False),
    ("not fully grounded", _SV.UNGROUNDED, False),
    ("grounded: no", _SV.UNGROUNDED, False),
    ("ungrounded grounded", _SV.UNGROUNDED, False),
    ("", _SV.UNGROUNDED, False),
    (None, _SV.UNGROUNDED, False),
])
def test_noninverted_parser_strict_no_false_accept(raw, verdict, ok):
    r = _pg(raw)
    assert r.verdict == verdict and r.parsed_ok == ok


def test_sentinel_mode_invalid_env_raises(monkeypatch):
    from src.polaris_graph.roles.sentinel_adapter import sentinel_groundedness_mode
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "guardain")  # typo
    with _pytest.raises(ValueError):
        sentinel_groundedness_mode()


# === DECOMPOSITION parser (certified MiniMax-M2, I-run11-004) ========================
# Mapping: "supported" -> GROUNDED, "unsupported" -> UNGROUNDED. EVERY parse failure / missing /
# off-enum / non-string fails CLOSED to UNGROUNDED parsed_ok=False. NO silent GROUNDED on bad input.
def test_decomposition_supported_json_maps_grounded() -> None:
    # Full decomposition contract (non-empty atoms + unsupported_atoms == 0) -> GROUNDED.
    # F05 (GH #1254): the parser now ALSO carries the per-atom `atoms` list as appended metadata, so
    # assert on the SAFETY contract fields (verdict + parsed_ok), not full-tuple equality.
    raw = ('{"verdict": "supported", "unsupported_atoms": 0, '
           '"atoms": [{"atom": "x", "status": "supported"}]}')
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True


def test_decomposition_unsupported_json_maps_ungrounded() -> None:
    raw = '{"verdict": "unsupported", "unsupported_atoms": 2, "atoms": [{"atom": "x"}]}'
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


@pytest.mark.parametrize(
    "raw,verdict",
    [
        # supported cases carry the full contract (atoms + count) so they reach GROUNDED;
        # this isolates VERDICT-TOKEN casing/whitespace parsing, not the contract gate.
        ('{"verdict": "SUPPORTED", "unsupported_atoms": 0, "atoms": [{"atom": "x", "status": "supported"}]}', SentinelVerdict.GROUNDED),       # case-insensitive
        ('{"verdict": " supported ", "unsupported_atoms": 0, "atoms": [{"atom": "x", "status": "supported"}]}', SentinelVerdict.GROUNDED),     # whitespace tolerant
        ('{"verdict": "Unsupported"}', SentinelVerdict.UNGROUNDED),
    ],
)
def test_decomposition_verdict_case_and_whitespace_tolerant(raw, verdict) -> None:
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is verdict
    assert result.parsed_ok is True


def test_decomposition_fenced_json_parses() -> None:
    raw = ('```json\n{"verdict": "supported", "unsupported_atoms": 0, '
           '"atoms": [{"atom": "x", "status": "supported"}]}\n```')
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.GROUNDED  # F05: atoms metadata appended; check contract.
    assert result.parsed_ok is True


def test_decomposition_bare_fence_no_lang_parses() -> None:
    raw = '```\n{"verdict": "unsupported"}\n```'
    assert parse_sentinel_decomposition(raw) == SentinelResult(
        SentinelVerdict.UNGROUNDED, parsed_ok=True
    )


def test_decomposition_trailing_comma_json_parses() -> None:
    # The certified _strip_json repairs a trailing comma before the closing brace.
    raw = ('{"verdict": "supported", "unsupported_atoms": 0, '
           '"atoms": [{"atom": "x", "status": "supported"}],}')
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.GROUNDED  # F05: atoms metadata appended; check contract.
    assert result.parsed_ok is True


def test_decomposition_reasoning_prefix_then_json_parses() -> None:
    # Reasoning prose before the JSON object: _strip_json extracts the largest {...} span.
    raw = 'Let me decompose the claim.\nHere is my verdict:\n{"verdict": "unsupported", "atoms": []}'
    assert parse_sentinel_decomposition(raw) == SentinelResult(
        SentinelVerdict.UNGROUNDED, parsed_ok=True
    )


@pytest.mark.parametrize(
    "raw",
    [
        "",                                      # empty
        "   ",                                   # whitespace only
        "not json at all",                       # prose, no JSON
        "{ this is not valid json",              # malformed, unparseable
        '{"unsupported_atoms": 0, "atoms": []}',  # missing verdict key
        '{"verdict": "maybe"}',                  # off-enum verdict
        '{"verdict": ""}',                       # empty verdict
        '{"verdict": null}',                     # non-string verdict
        '{"verdict": 1}',                        # numeric verdict
        '{"verdict": "grounded"}',               # wrong vocabulary (not supported/unsupported)
        '["supported"]',                          # JSON array, no verdict object
        '"supported"',                            # bare JSON string scalar
    ],
)
def test_decomposition_malformed_fails_closed_to_ungrounded(raw) -> None:
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_decomposition_non_string_fails_closed() -> None:
    result = parse_sentinel_decomposition(None)  # type: ignore[arg-type]
    assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)


def test_decomposition_supported_verdict_with_unsupported_atom_vetoes_to_ungrounded() -> None:
    # SAFETY (Codex diff-gate iter-3 P1): a top-level "supported" verdict that SIMULTANEOUSLY
    # reports an unsupported atom (unsupported_atoms=1 + atom status "unsupported") is INTERNALLY
    # CONTRADICTORY. The PRODUCTION parser — not an upstream harness — must VETO this to UNGROUNDED;
    # trusting the top-level "supported" would be a fail-OPEN path (a fabricated claim -> VERIFIED).
    raw = ('{"atoms": [{"atom": "a", "status": "unsupported"}], '
           '"unsupported_atoms": 1, "verdict": "supported"}')
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.UNGROUNDED  # F05: atoms metadata appended; check contract.
    assert result.parsed_ok is True


def test_decomposition_supported_verdict_clean_atoms_stays_grounded() -> None:
    # The complement: a "supported" verdict with NO unsupported atoms is a clean GROUNDED parse.
    raw = '{"atoms": [{"atom": "a", "status": "supported"}], "unsupported_atoms": 0, "verdict": "supported"}'
    result = parse_sentinel_decomposition(raw)
    assert result.verdict is SentinelVerdict.GROUNDED  # F05: atoms metadata appended; check contract.
    assert result.parsed_ok is True


_ATOMS = '"atoms":[{"atom":"x","status":"supported"}]'  # full-contract atoms list (isolates count logic)


def _verdict_ok(raw: str) -> tuple[SentinelVerdict, bool]:
    """The SAFETY-contract projection of a parse result: (verdict, parsed_ok). F05 appends an
    `atoms` metadata field that does NOT affect groundedness, so these count/contract tests assert
    on the two safety fields, not full-tuple equality (which would now spuriously diff on atoms)."""
    r = parse_sentinel_decomposition(raw)
    return (r.verdict, r.parsed_ok)


def test_decomposition_quoted_unsupported_atoms_count_vetoes_to_ungrounded() -> None:
    # Codex diff-gate iter-4 P1: JSON-mode models can QUOTE the count ("unsupported_atoms": "1").
    # A bare numeric check would miss it -> fail-OPEN. The parser coerces int-like strings and
    # vetoes, and fail-closes on a present-but-non-coercible count under a "supported" verdict.
    # (Full-contract atoms present so these reach the count veto, not the contract gate.)
    assert _verdict_ok('{"verdict":"supported","unsupported_atoms":"1",%s}' % _ATOMS) == \
        (SentinelVerdict.UNGROUNDED, True)
    assert _verdict_ok('{"verdict":"supported","unsupported_atoms":"abc",%s}' % _ATOMS) == \
        (SentinelVerdict.UNGROUNDED, True)
    assert _verdict_ok('{"verdict":"supported","unsupported_atoms":1.5,%s}' % _ATOMS) == \
        (SentinelVerdict.UNGROUNDED, True)
    # A quoted clean zero with full-contract atoms is still GROUNDED.
    assert _verdict_ok('{"verdict":"supported","unsupported_atoms":"0",%s}' % _ATOMS) == \
        (SentinelVerdict.GROUNDED, True)


def test_decomposition_non_numeric_unsupported_atoms_vetoes_to_ungrounded() -> None:
    # Codex diff-gate iter-5 P1 (continuing iter-4): a JSON bool/null/container as
    # "unsupported_atoms" under a "supported" verdict is a PRESENT-but-non-coercible count.
    # A bare `is not None` check would treat bool/null like an absent key and fail-OPEN.
    # Any present-but-non-clean-zero count vetoes to UNGROUNDED (full-contract atoms present so the
    # count veto, parsed_ok=True, is reached rather than the contract gate).
    for present_value in ("true", "false", "null", "[]", '["a"]', "{}"):
        payload = '{"verdict":"supported","unsupported_atoms":%s,%s}' % (present_value, _ATOMS)
        assert _verdict_ok(payload) == (SentinelVerdict.UNGROUNDED, True), present_value
    # PRESENT clean numeric zero with full-contract atoms stays GROUNDED.
    assert _verdict_ok('{"verdict":"supported","unsupported_atoms":0,%s}' % _ATOMS) == \
        (SentinelVerdict.GROUNDED, True)


def test_decomposition_supported_without_full_contract_fails_closed() -> None:
    # Codex BRIEF-gate P1 (NEW fail-open the diff gate missed): a top-level "supported" verdict that
    # OMITS the decomposition contract did no per-atom span-coverage work. Trusting it as GROUNDED is
    # a fail-OPEN — a bare/truncated/non-atomized "supported" could release a fabricated claim if the
    # Judge verifies. EVERY such case fails CLOSED to UNGROUNDED parsed_ok=False.
    fail_closed = SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    assert parse_sentinel_decomposition('{"verdict":"supported"}') == fail_closed                         # bare
    assert parse_sentinel_decomposition('{"verdict":"supported","unsupported_atoms":0}') == fail_closed   # no atoms
    assert parse_sentinel_decomposition('{"verdict":"supported","atoms":[]}') == fail_closed              # empty atoms
    assert parse_sentinel_decomposition('{"verdict":"supported","atoms":[{"atom":"x","status":"supported"}]}') == fail_closed  # no count
    assert parse_sentinel_decomposition('{"verdict":"supported","unsupported_atoms":0,"atoms":["nope"]}') == fail_closed       # no atom OBJECT
    # Validated against the cert cache: all 25 real "supported" outputs carry both -> zero false-drops.


def test_decomposition_never_silently_grounded_anti_inversion() -> None:
    """The lethal property: no malformed/garbage input may yield GROUNDED. The ONLY GROUNDED path
    is a clean JSON object with verdict == 'supported'."""
    for raw in (
        "",
        "garbage",
        '{"verdict": "maybe"}',
        '{"no_verdict": true}',
        '{"verdict": "unsupported"}',
        None,
    ):
        result = parse_sentinel_decomposition(raw)  # type: ignore[arg-type]
        if not (result.verdict is SentinelVerdict.GROUNDED and result.parsed_ok):
            assert result.verdict is SentinelVerdict.UNGROUNDED, repr(raw)
