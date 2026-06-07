"""
Codex round 1 B-4 regression tests: budget cap must NOT be $0 when
tokens were consumed but OpenRouter omitted usage.cost.
"""
from __future__ import annotations


def _mod():
    import src.polaris_graph.llm.openrouter_client as m
    return m


def test_b4_deepseek_tokens_impute_nonzero() -> None:
    mod = _mod()
    cost = mod._impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp", 5000, 500, 0,
    )
    # DeepSeek rates: $0.27 in / $0.38 out per M
    # expected: 5000*0.27/1e6 + 500*0.38/1e6 = 0.00135 + 0.00019 = 0.00154
    assert cost > 0.001
    assert cost < 0.01, f"unexpectedly expensive: {cost}"


def test_b4_qwen_8b_tokens_impute_cheap() -> None:
    mod = _mod()
    cost = mod._impute_cost_from_tokens(
        "qwen/qwen3-8b", 1000, 100, 50,
    )
    # Qwen3-8B: $0.05 in / $0.40 out; reasoning tokens billed at output rate
    # expected: 1000*0.05/1e6 + (100+50)*0.40/1e6 = 0.00005 + 0.00006 = 0.00011
    assert 0 < cost < 0.001


def test_b4_unknown_model_uses_opus_tier_default() -> None:
    mod = _mod()
    cost = mod._impute_cost_from_tokens(
        "unknown-vendor/mystery-model-3.0", 1000, 100, 0,
    )
    # Opus-tier worst-case: $3/M in, $15/M out
    # expected: 1000*3/1e6 + 100*15/1e6 = 0.003 + 0.0015 = 0.0045
    assert cost > 0.003


def test_b4_zero_tokens_zero_cost() -> None:
    mod = _mod()
    assert mod._impute_cost_from_tokens("deepseek/x", 0, 0, 0) == 0.0


def test_b4_budget_guard_not_bypassable_when_cost_missing(
    monkeypatch,
) -> None:
    """If OpenRouter omits cost but tokens were used, the budget guard
    must still accumulate a non-zero amount per call."""
    # I-ready-018 (#1088): set the cap via monkeypatch.setattr on the LIVE module (auto-restored)
    # instead of setenv + importlib.reload(mod). Reloading openrouter_client rebinds
    # BudgetExceededError to a non-subclass class object and resets _RUN_COST_CTX, which poisoned
    # the 4-role seam / fx01 / semantic-conflict tests downstream in the full sweep. The budget
    # check reads PG_MAX_COST_PER_RUN as a module global at call time, so setattr is sufficient.
    import src.polaris_graph.llm.openrouter_client as mod
    monkeypatch.setattr(mod, "PG_MAX_COST_PER_RUN", 0.10)
    mod.reset_run_cost()
    # Simulate what the _call() code path does when api_cost is None
    # and tokens were consumed: the imputed cost is fed into _add_run_cost.
    for _ in range(10):
        imputed = mod._impute_cost_from_tokens(
            "unknown-vendor/mystery", 2000, 500, 0,
        )
        assert imputed > 0
        mod._add_run_cost(imputed)
    # 10 calls × ~$0.0135 imputed > $0.10 budget → check_run_budget raises
    # (10 × (2000*3 + 500*15)/1M = 0.135)
    assert mod.current_run_cost() > 0.10
    import pytest
    with pytest.raises(mod.BudgetExceededError):
        mod.check_run_budget()
    mod.reset_run_cost()


def test_b4_negative_tokens_clamped_to_zero() -> None:
    """Codex round 5 probe: a corrupted API response with negative
    token counts must NOT produce a negative cost that would silently
    reduce the accumulated run budget."""
    mod = _mod()
    # All-negative: returns 0
    assert mod._impute_cost_from_tokens("deepseek/x", -100, -50, -10) == 0.0
    # Partial negative: negative inputs clamp to 0, positives still count
    cost = mod._impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp", -100, 50, 0,
    )
    assert cost >= 0.0, f"Cost must be non-negative, got {cost}"
    # Should equal the cost of (0 input, 50 output, 0 reasoning)
    expected = 50 * 0.38 / 1_000_000
    assert abs(cost - expected) < 1e-9


def test_b4_float_tokens_coerced_via_int() -> None:
    """If an upstream handler passes floats, the clamp cast must not crash."""
    mod = _mod()
    cost = mod._impute_cost_from_tokens("deepseek/x", 100.7, 50.3, 0)
    assert cost > 0


def test_b4_legacy_cost_field_still_honored() -> None:
    """If OpenRouter DOES return usage.cost, we use it verbatim."""
    mod = _mod()
    mod.reset_run_cost()
    # Simulate the _call path when api_cost=0.005 was returned by API
    api_cost = 0.005
    mod._add_run_cost(api_cost)
    assert abs(mod.current_run_cost() - 0.005) < 1e-9
