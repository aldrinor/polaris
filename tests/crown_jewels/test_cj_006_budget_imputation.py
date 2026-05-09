"""Crown Jewel I-cj-006 — Budget cap holds without usage.cost.

Per CLAUDE.md §9.1.6: when OpenRouter omits usage.cost,
_impute_cost_from_tokens backstops the token-only response so the
budget guard cannot be silently bypassed. Negative tokens clamp to
zero — a corrupted API response cannot produce a negative cost that
would shrink the accumulated run budget.
"""

from __future__ import annotations

from src.polaris_graph.llm.openrouter_client import _impute_cost_from_tokens


def test_cj_006_known_model_imputes_positive_cost() -> None:
    cost = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        reasoning_tokens=0,
    )
    assert cost > 0.0
    assert cost < 5.0


def test_cj_006_unknown_model_uses_fallback() -> None:
    cost = _impute_cost_from_tokens(
        "unknown-vendor/some-model",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        reasoning_tokens=0,
    )
    assert 17.0 < cost < 19.0


def test_cj_006_zero_tokens_zero_cost() -> None:
    cost = _impute_cost_from_tokens("deepseek/deepseek-v3.2-exp", 0, 0, 0)
    assert cost == 0.0


def test_cj_006_negative_tokens_clamp_to_zero() -> None:
    cost = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=-5_000_000,
        output_tokens=-3_000_000,
        reasoning_tokens=-1_000_000,
    )
    assert cost == 0.0


def test_cj_006_reasoning_tokens_bill_at_output_rate() -> None:
    out_only = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=0,
        output_tokens=2_000_000,
        reasoning_tokens=0,
    )
    out_plus_reasoning = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=0,
        output_tokens=1_000_000,
        reasoning_tokens=1_000_000,
    )
    assert abs(out_only - out_plus_reasoning) < 1e-9


def test_cj_006_empty_model_uses_fallback() -> None:
    cost = _impute_cost_from_tokens(
        "",
        input_tokens=1_000_000,
        output_tokens=0,
        reasoning_tokens=0,
    )
    assert 2.5 < cost < 3.5
