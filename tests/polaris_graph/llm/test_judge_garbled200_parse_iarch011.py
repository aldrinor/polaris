"""I-arch-011 (B12/B14, KEYSTONE) — garbled-200 JSON parse + fail-closed contract.

Both side judges (entailment + semantic-conflict) previously called a bare
``json.loads(content)`` on the LLM response body. A "garbled-200" — a valid JSON
verdict object FOLLOWED by trailing reasoning text, e.g.::

    {"verdict": "ENTAILED", "reason": "ok"}
    The span clearly supports the sentence because ...

raises ``json.JSONDecodeError: Extra data: line 2 column 1 (char N)`` under
``json.loads``. The salvageable verdict was thrown away, which on the entailment
path becomes a fail-closed DROP and on the semantic-conflict path becomes a HOLD
(strict) / fail-open neutral — the drb_72-class over-drop / coverage collapse.

The fix adds a brace-aware first-complete-JSON-object extractor
(``_extract_first_json_object``) to BOTH judge modules. It RAISES on every genuine
failure (empty / None / lone ``{`` / partial JSON / non-object first value), so the
fail-closed retry/sentinel/hold paths are byte-for-byte preserved for real failures.
Only the valid-object-plus-trailing-text case is newly rescued. Faithfulness is NOT
relaxed: a genuinely-unparseable response still fails closed exactly as today.

This test imports the extractor from BOTH judge modules (the lane requirement to
"cover BOTH judges / import each parser path") and asserts:
  * a garbled-200 parses to the verdict dict (the salvage),
  * empty / None / whitespace content STILL raises (fail-closed),
  * a lone ``{`` and other partial/invalid JSON STILL raises (fail-closed),
  * a brace inside a string value does NOT confuse the parser,
  * prose-before-JSON is still rescued (the un-constrained-output hedge),
  * the first complete object wins.

It FAILS on the pre-fix code (the symbol ``_extract_first_json_object`` does not
exist in either module pre-fix, so the import raises) and PASSES after the fix.
"""

import json

import pytest

# Import each parser path — one per judge module. Pre-fix these symbols do not
# exist, so collection fails (the fail-on-pre-fix mechanism).
from src.polaris_graph.llm.entailment_judge import (
    _extract_first_json_object as _entailment_extract,
)
from src.polaris_graph.retrieval.semantic_conflict_detector import (
    _extract_first_json_object as _conflict_extract,
)

# Run every assertion against BOTH judges' extractors so a regression in either is caught.
_EXTRACTORS = [
    pytest.param(_entailment_extract, id="entailment_judge"),
    pytest.param(_conflict_extract, id="semantic_conflict_detector"),
]


# ---------------------------------------------------------------------------
# SALVAGE cases — the garbled-200 must now parse to the verdict dict.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_garbled200_object_plus_trailing_text_parses(extract):
    """The motivating fault: a valid object followed by trailing reasoning prose.

    Pre-fix ``json.loads`` raised 'Extra data'; the extractor must return the dict.
    """
    garbled = (
        '{"verdict": "ENTAILED", "reason": "the span supports the sentence"}\n'
        "The span clearly entails the sentence because both mention the same dose."
    )
    parsed = extract(garbled)
    assert isinstance(parsed, dict)
    assert parsed["verdict"] == "ENTAILED"
    assert parsed["reason"] == "the span supports the sentence"


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_clean_json_still_parses(extract):
    """A pristine JSON-only body (the happy path) is byte-equivalent to json.loads."""
    clean = '{"verdict": "CONTRADICTED", "confidence": 0.92, "reason": "disagrees"}'
    assert extract(clean) == json.loads(clean)


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_brace_inside_string_value_not_miscounted(extract):
    """A naive depth counter miscounts braces inside string values; raw_decode must not.

    The object's ``reason`` contains a literal ``{x}`` — the parser must return the
    WHOLE object, not truncate at the inner brace.
    """
    tricky = '{"verdict": "NEUTRAL", "reason": "dose {x} mg not in span"}\ntrailing'
    parsed = extract(tricky)
    assert parsed["verdict"] == "NEUTRAL"
    assert parsed["reason"] == "dose {x} mg not in span"


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_prose_before_json_is_rescued(extract):
    """Without response_format the host may emit prose BEFORE the object — still rescue it."""
    leading = (
        "Here is my verdict for the pair you gave me:\n"
        '{"verdict": "ENTAILED", "reason": "supported"}'
    )
    parsed = extract(leading)
    assert parsed["verdict"] == "ENTAILED"


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_first_verdict_object_wins(extract):
    """When two verdict objects appear, the FIRST one is the verdict."""
    two = (
        '{"verdict": "CONTRADICTED", "reason": "first"}\n'
        '{"verdict": "ENTAILED", "reason": "second"}'
    )
    parsed = extract(two)
    assert parsed["verdict"] == "CONTRADICTED"
    assert parsed["reason"] == "first"


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_leading_non_verdict_object_is_skipped(extract):
    """A leading non-verdict object must NOT be selected — the verdict object wins.

    This is the fail-closed->fail-open regression guard: if the extractor returned the
    first dict unconditionally, ``{"note": ...}`` would yield verdict="" -> neutral, and a
    real CONTRADICTED verdict on the strict semantic-conflict path would be silently
    downgraded from a HOLD to a fail-open neutral. The verdict-bearing object must win.
    """
    body = (
        '{"note": "scratchpad reasoning, not the verdict"}\n'
        '{"verdict": "CONTRADICTED", "reason": "real verdict"}'
    )
    parsed = extract(body)
    assert parsed["verdict"] == "CONTRADICTED"
    assert parsed["reason"] == "real verdict"


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_nested_verdict_object_not_misselected(extract):
    """A verdict nested inside a wrapper must not be picked apart mid-object.

    The outer object carries ``verdict`` so it is returned whole; the scan must not
    descend into the nested ``{"x": ...}`` and return a fragment.
    """
    body = '{"verdict": "ENTAILED", "meta": {"x": 1}, "reason": "ok"}'
    parsed = extract(body)
    assert parsed["verdict"] == "ENTAILED"
    assert parsed["meta"] == {"x": 1}


def test_extractor_succeeds_where_bare_json_loads_raises():
    """Behavioral contrast: the bare json.loads (the pre-fix call) raises on a garbled-200,
    while BOTH extractors recover the verdict. Makes the fix's value self-evident."""
    garbled = '{"verdict": "ENTAILED", "reason": "ok"}\ntrailing reasoning text'
    with pytest.raises(json.JSONDecodeError):
        json.loads(garbled)  # the pre-fix behavior that DROPPED the verdict
    assert _entailment_extract(garbled)["verdict"] == "ENTAILED"
    assert _conflict_extract(garbled)["verdict"] == "ENTAILED"


@pytest.mark.parametrize("extract", _EXTRACTORS)
def test_fenced_json_code_block_is_rescued(extract):
    """A ```json fenced block (markdown wrapper) still yields the object."""
    fenced = '```json\n{"verdict": "NEUTRAL", "reason": "no shared claim"}\n```'
    parsed = extract(fenced)
    assert parsed["verdict"] == "NEUTRAL"


# ---------------------------------------------------------------------------
# FAIL-CLOSED cases — genuine failures must STILL raise (faithfulness preserved).
# A raise is what keeps the entailment retry/sentinel-drop and the semantic-conflict
# strict-HOLD / fail-open-neutral paths intact. The extractor must NEVER return a
# default / partial / sentinel on these inputs.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("extract", _EXTRACTORS)
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("", id="empty_string"),
        pytest.param(None, id="none"),
        pytest.param("   \n\t  ", id="whitespace_only"),
        pytest.param("{", id="lone_open_brace"),
        pytest.param('{"verdict": "ENTAILED"', id="unterminated_object"),
        pytest.param('{"verdict": ', id="truncated_mid_value"),
        pytest.param("no json here at all", id="no_brace_prose"),
        pytest.param("[1, 2, 3]", id="json_array_not_object"),
        pytest.param("42", id="bare_number"),
        pytest.param('"just a string"', id="bare_string"),
        pytest.param("{ this is not json }", id="braces_around_prose"),
        pytest.param(123, id="non_str_int"),
        pytest.param({"verdict": "ENTAILED"}, id="non_str_dict"),
        # Valid JSON object(s) but NONE carries "verdict" — must fail closed, never return a
        # non-verdict dict that downstream maps to neutral / "" (the fail-open regression).
        pytest.param('{"reason": "x"}', id="valid_object_no_verdict"),
        pytest.param('{"note": "a"}\n{"other": "b"}', id="two_objects_no_verdict"),
        # Codex P1 (iter 2): a MALFORMED OUTER envelope that happens to contain a COMPLETE
        # nested verdict object must FAIL CLOSED. The scan must NOT descend into the failed
        # outer object's interior and salvage the inner verdict — that would turn a malformed /
        # truncated body into an accepted judge verdict (fail-closed -> fail-open). Pre-iter-2
        # the extractor advanced one char past the failed outer "{" and returned the nested
        # {"verdict": ...}; post-fix the raw_decode failure at offset 0 raises.
        pytest.param(
            '{"wrapper": {"verdict": "NEUTRAL", "reason": "ok"}',
            id="malformed_outer_nested_verdict",
        ),
        pytest.param(
            '{"x": [1, 2, {"verdict": "ENTAILED", "reason": "buried"}',
            id="malformed_outer_array_nested_verdict",
        ),
    ],
)
def test_genuine_failures_still_raise_fail_closed(extract, bad):
    """Every genuinely-unparseable / non-object input must RAISE — never return a value."""
    with pytest.raises((ValueError, json.JSONDecodeError)):
        extract(bad)
