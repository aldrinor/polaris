"""UNIT 4 (I-deepfix-001 #1344) — prune UNREFERENCED sourced inputs.

The drb_72 defect: 892 datapoints extracted, a valid quantified spec built, then
FATALLY rejected by ``non_affecting_input:robot_exposure_ratio`` because ONE
sourced (cited) input was wired into no output formula. The all-or-nothing
material-dependency gate killed the whole section over a single unreferenced
citation. This test locks the fix: an UNREFERENCED sourced input is PRUNED (the
same faithfulness-neutral treatment the modeled-prune already gives unreferenced
modeled assumptions), while a REFERENCED-but-canceling sourced input STAYS a hard
reject (a genuine misleading citation).

SPEND-FREE: ``build_quantified_spec`` takes a FAKE ``spec_llm`` (no LLM, no
network, no GPU/model). Plain assertions, no unittest.mock.

RED (pre-fix): ``test_unreferenced_sourced_input_is_pruned_not_rejected`` returns
None (reject non_affecting_input) → the ``is not None`` assert fails.
GREEN (post-fix): the spec builds with the unreferenced input gone and is
byte-identical (same outputs, same input_names, same spec_hash) to a spec that
never declared it.
"""
from __future__ import annotations

from src.polaris_graph.synthesis.tradeoff_modeler import build_quantified_spec


# ── evidence + datapoints ────────────────────────────────────────────────────
def _evidence_rows() -> dict:
    return {
        "ev_a": {
            "direct_quote": "Metric a is 10 apples in the study.",
            "source_url": "https://example.org/a", "tier": "T1",
        },
        "ev_b": {
            "direct_quote": "Metric b is 25 apples in the study.",
            "source_url": "https://example.org/b", "tier": "T1",
        },
        "ev_r": {
            "direct_quote": "The robot exposure ratio is 7 apples per site.",
            "source_url": "https://example.org/r", "tier": "T1",
        },
    }


def _dp(ev_id: str, label: str, context: str, value: float, unit: str = "apples") -> dict:
    return {
        "data_type": "count", "label": label, "context": context,
        "value": str(value), "unit": unit, "year": "2024",
        "evidence_id": ev_id, "source_url": "", "source_title": "",
    }


_DP_A = _dp("ev_a", "metric a", "Metric a is 10 apples in the study", 10.0)
_DP_B = _dp("ev_b", "metric b", "Metric b is 25 apples in the study", 25.0)
_DP_R = _dp("ev_r", "robot exposure ratio",
            "The robot exposure ratio is 7 apples per site", 7.0)


def _ref(ev_id: str, label: str, context: str, value: float, unit: str = "apples") -> dict:
    return {"ev_id": ev_id, "label": label, "context": context,
            "value": str(value), "unit": unit}


_A_IN = {"name": "a", "datapoint_ref": _ref(
    "ev_a", "metric a", "Metric a is 10 apples in the study", 10.0)}
_B_IN = {"name": "b", "datapoint_ref": _ref(
    "ev_b", "metric b", "Metric b is 25 apples in the study", 25.0)}
_R_IN = {"name": "robot_exposure_ratio", "datapoint_ref": _ref(
    "ev_r", "robot exposure ratio",
    "The robot exposure ratio is 7 apples per site", 7.0)}

_OUT_TOTAL = {"name": "total", "unit": "apples", "display_kind": "number",
              "formula": "a + b"}


def _build(inputs: list[dict], outputs: list[dict], sourced_numbers: list[dict]):
    return build_quantified_spec(
        "q", sourced_numbers, _evidence_rows(),
        spec_llm=lambda _q, _s: {
            "model_id": "unit4", "title": "Unit 4 prune",
            "inputs": inputs, "outputs": outputs,
        },
    )


# ── RED before / GREEN after ─────────────────────────────────────────────────
def test_unreferenced_sourced_input_is_pruned_not_rejected():
    """robot_exposure_ratio is sourced but referenced by NO formula. Pre-fix this
    fatally rejected the whole spec; post-fix it is pruned and the spec builds."""
    spec = _build([_A_IN, _B_IN, _R_IN], [_OUT_TOTAL], [_DP_A, _DP_B, _DP_R])
    assert spec is not None, (
        "unreferenced sourced input must be PRUNED, not fatally rejected"
    )
    # the unreferenced input is gone from the model
    assert "robot_exposure_ratio" not in spec.input_names()
    assert spec.input_names() == ["a", "b"]
    # the surviving output is untouched
    total = spec.output_by_name("total")
    assert total is not None and total.formula == "a + b"

    # byte-identical to a spec that NEVER declared robot_exposure_ratio
    baseline = _build([_A_IN, _B_IN], [_OUT_TOTAL], [_DP_A, _DP_B, _DP_R])
    assert baseline is not None
    assert spec.input_names() == baseline.input_names()
    assert [(o.name, o.unit, o.display_kind, o.formula) for o in spec.outputs] == \
           [(o.name, o.unit, o.display_kind, o.formula) for o in baseline.outputs]
    assert spec.spec_hash == baseline.spec_hash


def test_referenced_but_canceling_sourced_input_stays_rejected():
    """robot_exposure_ratio IS wired into a formula that cancels it out (does
    nothing). That is a genuine misleading citation and MUST stay fatal — it is
    referenced, so the prune never touches it."""
    canceling_out = {
        "name": "total", "unit": "apples", "display_kind": "number",
        # references robot_exposure_ratio but its net effect is zero
        "formula": "a + b + robot_exposure_ratio - robot_exposure_ratio",
    }
    spec = _build([_A_IN, _B_IN, _R_IN], [canceling_out], [_DP_A, _DP_B, _DP_R])
    assert spec is None, (
        "a referenced-but-canceling cited input is a misleading citation and "
        "must remain a hard reject"
    )


def test_fully_valid_spec_unchanged():
    """Every sourced input is referenced → nothing to prune → spec builds exactly
    as before (no regression)."""
    spec = _build([_A_IN, _B_IN], [_OUT_TOTAL], [_DP_A, _DP_B])
    assert spec is not None
    assert spec.input_names() == ["a", "b"]
    total = spec.output_by_name("total")
    assert total is not None and total.formula == "a + b"
