"""Test that the sycophancy paired-prompt fixtures load + match the schema.

These fixtures are the dataset that Phase 1 LLM-hookup uses to score
candidate generators against the SycEval CI gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polaris_v6.sycophancy.paired_prompts import PairedPrompt

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sycophancy_v1"


def _load_fixtures() -> dict:
    return json.loads((FIXTURE_DIR / "paired_prompts.json").read_text(encoding="utf-8"))


def test_fixtures_load():
    payload = _load_fixtures()
    assert payload["schema_version"] == "1.0"
    assert len(payload["paired_prompts"]) >= 5


def test_each_paired_prompt_has_four_framings():
    payload = _load_fixtures()
    required = {"neutral", "leading_positive", "leading_negative", "opposite_frame"}
    for paired in payload["paired_prompts"]:
        assert required.issubset(paired["prompts"].keys()), (
            f"{paired['paired_id']} missing framings: {required - paired['prompts'].keys()}"
        )


@pytest.mark.parametrize(
    "paired_id",
    [
        "syc_clinical_001",
        "syc_housing_001",
        "syc_trade_001",
        "syc_defense_001",
        "syc_climate_001",
        "syc_clinical_refuse_001",
        "syc_workforce_001",
        "syc_ai_sov_001",
        "syc_canada_us_001",
        "syc_indigenous_consultation_001",
        "syc_personal_legal_refuse_001",
    ],
)
def test_paired_prompt_validates_against_pydantic(paired_id):
    payload = _load_fixtures()
    matching = [p for p in payload["paired_prompts"] if p["paired_id"] == paired_id]
    assert matching, f"fixture {paired_id} not found"
    paired = PairedPrompt.model_validate(matching[0])
    assert paired.paired_id == paired_id
    assert len(paired.prompts) == 4


def test_refusal_acceptable_marked_correctly():
    payload = _load_fixtures()
    refuse_cases = [p for p in payload["paired_prompts"] if p.get("refusal_acceptable")]
    assert any(
        "stop" in p["underlying_question"].lower()
        or "refuse" in p["paired_id"].lower()
        for p in refuse_cases
    ), "expected at least one refusal-acceptable case to relate to personal advice"


def test_factual_anchors_are_short():
    """Anchors must be short enough that a non-sycophantic model can include verbatim."""
    payload = _load_fixtures()
    for paired in payload["paired_prompts"]:
        if not paired.get("refusal_acceptable"):
            anchor = paired["expected_factual_anchor"]
            assert 3 <= len(anchor.split()) <= 12, (
                f"{paired['paired_id']} anchor wrong length: {anchor!r}"
            )


def test_no_duplicate_paired_ids():
    payload = _load_fixtures()
    ids = [p["paired_id"] for p in payload["paired_prompts"]]
    assert len(ids) == len(set(ids))
