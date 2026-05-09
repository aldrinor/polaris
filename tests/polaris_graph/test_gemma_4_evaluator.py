"""I-bug-087 — Gemma 4 31B evaluator default.

Pins:
  - family resolution to "gemma" so two-family invariant holds with
    DeepSeek generator
  - model-specific price entry inserted BEFORE generic "google/gemma"
    in _PRICE_TABLE_USD_PER_M so budget guard imputes correctly
    (specific 0.13/0.38 wins over generic 0.05/0.30)
"""

from __future__ import annotations

from src.polaris_graph.llm.openrouter_client import (
    _impute_cost_from_tokens,
    check_family_segregation,
    family_from_model,
)


def test_gemma_4_31b_family_is_gemma() -> None:
    assert family_from_model("google/gemma-4-31b-it") == "gemma"


def test_gemma_4_31b_passes_two_family_segregation_with_deepseek_v4_pro() -> None:
    gen, ev = check_family_segregation(
        generator_model="deepseek/deepseek-v4-pro",
        evaluator_model="google/gemma-4-31b-it",
        generator_override="",
        evaluator_override="",
    )
    assert (gen, ev) == ("deepseek", "gemma")


def test_gemma_4_31b_specific_price_wins_over_generic_gemma_prefix() -> None:
    cost = _impute_cost_from_tokens(
        "google/gemma-4-31b-it",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        reasoning_tokens=0,
    )
    assert abs(cost - (0.13 + 0.38)) < 1e-6
