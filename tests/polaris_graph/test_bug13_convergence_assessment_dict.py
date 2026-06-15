"""BUG-13 (#1262): AgenticRoundAnalysis.convergence_assessment dict robustness.

The agentic-search "Reason" step LLM intermittently returns
``convergence_assessment`` as a DICT (e.g. ``{"assessment": "saturated"}``)
instead of the bare string the schema declares. Before the fix, the
``normalize_field_names`` pre-validator only handled ``None`` and ``str``,
so a dict fell through to the field's ``str`` validation and raised a
``ValidationError`` -> JSON-repair scramble (self-recovered but fragile).

The fix coerces a dict to its canonical string form FIRST, then runs it
through the SAME ``{expanding, narrowing, saturated}`` vocabulary mapping
that a bare string would take. A dict and the equivalent string must
therefore normalize to the identical canonical token.

FAITHFULNESS NOTE: ``convergence_assessment`` is an advisory agentic-loop
control signal (keep searching vs. converge), not a faithfulness verdict
or a citation. These tests assert input-parsing robustness only; no hard
gate (strict_verify / NLI / 4-role / span-grounding) is exercised or
relaxed, and no verified claim is dropped or altered.
"""
import pytest
from pydantic import ValidationError

from src.polaris_graph.schemas import AgenticRoundAnalysis


def _base_payload():
    """Minimal valid payload; convergence_assessment is overridden per-test."""
    return {
        "key_findings": ["finding 1"],
        "web_queries": ["query 1"],
        "should_continue": True,
        "reasoning": "still exploring",
    }


@pytest.mark.parametrize(
    ("ca_dict", "expected"),
    [
        # Canonical recognized key under the dict.
        ({"assessment": "saturated"}, "saturated"),
        ({"convergence": "narrowing"}, "narrowing"),
        ({"status": "expanding"}, "expanding"),
        ({"state": "converged"}, "saturated"),      # synonym maps to saturated
        ({"value": "refining"}, "narrowing"),         # synonym maps to narrowing
        ({"label": "exploring"}, "expanding"),         # synonym maps to expanding
        # Self-keyed dict (model nests the field name inside the dict).
        ({"convergence_assessment": "saturated"}, "saturated"),
        # Extra structured siblings must be ignored, primary key wins.
        ({"assessment": "narrowing", "confidence": 0.8, "reasoning": "x"}, "narrowing"),
        # Case / whitespace insensitivity (same as the string path).
        ({"assessment": "  SATURATED  "}, "saturated"),
        # No recognized key + no usable string -> safe default "expanding"
        # (identical to how an unrecognized bare string is handled).
        ({"confidence": 0.5}, "expanding"),
        ({}, "expanding"),
    ],
)
def test_convergence_assessment_accepts_dict(ca_dict, expected):
    """A DICT convergence_assessment validates and maps to the right token."""
    payload = _base_payload()
    payload["convergence_assessment"] = ca_dict

    # MUST NOT raise: this is the core BUG-13 robustness guarantee.
    analysis = AgenticRoundAnalysis.model_validate(payload)

    assert analysis.convergence_assessment == expected
    assert isinstance(analysis.convergence_assessment, str)


@pytest.mark.parametrize(
    ("dict_value", "string_value", "expected"),
    [
        ({"assessment": "saturated"}, "saturated", "saturated"),
        ({"assessment": "narrowing"}, "narrowing", "narrowing"),
        ({"assessment": "converging"}, "converging", "saturated"),
        ({"assessment": "broadening"}, "broadening", "expanding"),
    ],
)
def test_dict_and_string_normalize_identically(dict_value, string_value, expected):
    """The dict shape and the equivalent bare string yield the same token.

    This pins the fix's meaning-preservation invariant: coercing the dict
    must not change the schema's semantics versus the string path.
    """
    dict_payload = _base_payload()
    dict_payload["convergence_assessment"] = dict_value

    str_payload = _base_payload()
    str_payload["convergence_assessment"] = string_value

    dict_result = AgenticRoundAnalysis.model_validate(dict_payload).convergence_assessment
    str_result = AgenticRoundAnalysis.model_validate(str_payload).convergence_assessment

    assert dict_result == str_result == expected


def test_regression_dict_no_longer_raises_validation_error():
    """Regression: the OLD bug raised ValidationError for a dict value.

    Build the dict payload through the same key the model emits and assert
    construction succeeds. If the BUG-13 coercion is removed, pydantic's
    field-level ``str`` validation rejects the dict and this test fails.
    """
    payload = _base_payload()
    payload["convergence_assessment"] = {"assessment": "saturated", "confidence": 0.9}

    try:
        analysis = AgenticRoundAnalysis.model_validate(payload)
    except ValidationError as exc:  # pragma: no cover - only on regression
        pytest.fail(
            "BUG-13 regression: dict convergence_assessment raised "
            f"ValidationError instead of being coerced: {exc}"
        )

    assert analysis.convergence_assessment == "saturated"


def test_existing_none_and_string_paths_unchanged():
    """Guard: the pre-existing None / string handling is untouched by the fix."""
    none_payload = _base_payload()
    none_payload["convergence_assessment"] = None
    assert (
        AgenticRoundAnalysis.model_validate(none_payload).convergence_assessment
        == "expanding"
    )

    str_payload = _base_payload()
    str_payload["convergence_assessment"] = "narrowing"
    assert (
        AgenticRoundAnalysis.model_validate(str_payload).convergence_assessment
        == "narrowing"
    )

    # Field default still applies when the key is absent entirely.
    absent_payload = _base_payload()
    assert (
        AgenticRoundAnalysis.model_validate(absent_payload).convergence_assessment
        == "expanding"
    )
