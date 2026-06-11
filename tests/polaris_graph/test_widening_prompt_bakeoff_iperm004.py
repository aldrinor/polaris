"""I-faith-006 (#1180) — offline tests for the widening-prompt bakeoff substrate.

The empirical PICK (which candidate wins) needs the real judge LLM and is spend-gated. These tests
cover everything offline: the labeled set is well-formed §-1.1 ground truth, the prompt selector is
BYTE-IDENTICAL by default, every candidate is a drop-in (same fields + STRICT-JSON contract), and the
pure scorer/winner-picker logic is correct (incl. the fail-safe to baseline on a precision regression).
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.llm import entailment_judge as ej
from src.polaris_graph.llm import widening_prompt_candidates as wpc


@pytest.fixture(autouse=True)
def _clear_variant():
    os.environ.pop("PG_ENTAILMENT_PROMPT_VARIANT", None)
    yield
    os.environ.pop("PG_ENTAILMENT_PROMPT_VARIANT", None)


# --- default byte-identical ----------------------------------------------------------------


def test_default_selector_is_baseline_byte_identical():
    os.environ.pop("PG_ENTAILMENT_PROMPT_VARIANT", None)
    assert ej._select_entailment_prompt() is ej._ENTAILMENT_PROMPT
    for value in ("", "baseline", "BASELINE", "unknown_variant"):
        os.environ["PG_ENTAILMENT_PROMPT_VARIANT"] = value
        assert ej._select_entailment_prompt() is ej._ENTAILMENT_PROMPT  # fail-safe to baseline


def test_selected_variant_returns_candidate():
    os.environ["PG_ENTAILMENT_PROMPT_VARIANT"] = "widen_b"
    assert ej._select_entailment_prompt() == wpc.WIDENING_VARIANTS["widen_b"]


# --- candidate prompts are drop-in replacements --------------------------------------------


def test_variants_keep_fields_and_json_contract():
    for name, tmpl in wpc.WIDENING_VARIANTS.items():
        formatted = tmpl.format(span="THE_SPAN", sentence="THE_SENTENCE")
        assert "THE_SPAN" in formatted and "THE_SENTENCE" in formatted, name
        assert '"verdict"' in formatted and "JSON:" in formatted, name
        # No stray format fields beyond span/sentence (would KeyError above otherwise).


# --- labeled set is well-formed §-1.1 ground truth -----------------------------------------


def test_labeled_set_well_formed():
    from scripts.dr_benchmark.widening_prompt_bakeoff import load_rows, validate_variants

    rows = load_rows()  # raises on malformed
    validate_variants()
    assert len(rows) >= 8
    golds = {r["gold"] for r in rows}
    assert {"NEUTRAL", "ENTAILED", "CONTRADICTED"} <= golds, "need all three verdict classes"
    # The drb_76 F02 widening case must be present and labeled NEUTRAL (the fix target).
    f02 = [r for r in rows if r["id"] == "F02_drb76_strain_to_class"]
    assert f02 and f02[0]["gold"] == "NEUTRAL"
    # Must include strain/scope-PRESERVING positives so the bakeoff can detect false-drops.
    assert any(r["gold"] == "ENTAILED" for r in rows)


# --- pure scorer + winner picker -----------------------------------------------------------


def _rows(golds):
    return [{"gold": g, "category": "x"} for g in golds]


def test_score_predictions_metrics():
    rows = _rows(["NEUTRAL", "NEUTRAL", "ENTAILED", "ENTAILED", "CONTRADICTED"])
    preds = ["NEUTRAL", "ENTAILED", "ENTAILED", "ENTAILED", "CONTRADICTED"]
    s = wpc.score_predictions(rows, preds)
    assert s["gold_neutral"] == 2 and s["gold_entailed"] == 2
    assert s["widening_neutral_recall"] == 0.5  # 1 of 2 NEUTRAL caught
    assert s["entailed_precision"] == 1.0  # 2 of 2 ENTAILED kept


def test_pick_winner_prefers_recall_within_precision_floor():
    scores = {
        "baseline": {"widening_neutral_recall": 0.0, "entailed_precision": 1.0},
        "widen_a": {"widening_neutral_recall": 0.8, "entailed_precision": 0.97},
        "widen_b": {"widening_neutral_recall": 0.9, "entailed_precision": 0.80},  # regresses precision
    }
    # widen_b has the best recall but fails the precision floor -> widen_a wins.
    assert wpc.pick_winner(scores, min_entailed_precision=0.95) == "widen_a"


def test_pick_winner_fails_safe_to_baseline():
    scores = {
        "widen_a": {"widening_neutral_recall": 0.9, "entailed_precision": 0.5},
        "widen_b": {"widening_neutral_recall": 0.8, "entailed_precision": 0.6},
    }
    # No candidate clears the precision floor -> do not regress faithfulness, keep baseline.
    assert wpc.pick_winner(scores, min_entailed_precision=0.95) == "baseline"


def test_score_predictions_length_mismatch_raises():
    with pytest.raises(ValueError):
        wpc.score_predictions(_rows(["NEUTRAL"]), ["NEUTRAL", "ENTAILED"])
