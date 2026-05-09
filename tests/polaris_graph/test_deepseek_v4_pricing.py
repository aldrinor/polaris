"""I-bug-086 — V4 Pro / V4 Flash pricing + family pinning.

Pins the price-table entries inserted BEFORE the generic `deepseek/`
prefix so V4-specific pricing wins over the V3.2-tier generic price.
A regression that drops the V4 entries (or reorders so generic wins)
weakens the budget guard and breaks this test.
"""

from __future__ import annotations

from src.polaris_graph.llm.openrouter_client import (
    _impute_cost_from_tokens,
    check_family_segregation,
    family_from_model,
)


def test_v4_pro_uses_specific_price_not_generic() -> None:
    cost = _impute_cost_from_tokens(
        "deepseek/deepseek-v4-pro",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        reasoning_tokens=0,
    )
    assert abs(cost - (0.435 + 0.87)) < 1e-6


def test_v4_flash_uses_specific_price_not_generic() -> None:
    cost = _impute_cost_from_tokens(
        "deepseek/deepseek-v4-flash",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        reasoning_tokens=0,
    )
    assert abs(cost - (0.14 + 0.28)) < 1e-6


def test_v4_pro_family_segregation_with_qwen_evaluator() -> None:
    assert family_from_model("deepseek/deepseek-v4-pro") == "deepseek"
    gen, ev = check_family_segregation(
        generator_model="deepseek/deepseek-v4-pro",
        evaluator_model="qwen/qwen3-8b",
        generator_override="",
        evaluator_override="",
    )
    assert (gen, ev) == ("deepseek", "qwen")
