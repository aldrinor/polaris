"""
R-2 regression tests: per-run cost cap.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.llm.openrouter_client import (
    BudgetExceededError,
    _add_run_cost,
    check_run_budget,
    current_run_cost,
    reset_run_cost,
)


def test_r2_reset_zero_baseline() -> None:
    reset_run_cost()
    assert current_run_cost() == 0.0


def test_r2_add_and_report() -> None:
    reset_run_cost()
    _add_run_cost(0.002)
    _add_run_cost(0.003)
    assert abs(current_run_cost() - 0.005) < 1e-9


def test_r2_check_below_cap_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_run_cost()
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.50")
    # Reload module constant
    import importlib
    import src.polaris_graph.llm.openrouter_client as mod
    importlib.reload(mod)
    mod.reset_run_cost()
    mod._add_run_cost(0.1)
    # Should not raise
    mod.check_run_budget()


def test_r2_check_above_cap_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.01")
    import importlib
    import src.polaris_graph.llm.openrouter_client as mod
    importlib.reload(mod)
    mod.reset_run_cost()
    mod._add_run_cost(0.02)   # already over cap
    with pytest.raises(mod.BudgetExceededError) as excinfo:
        mod.check_run_budget()
    assert "PG_MAX_COST_PER_RUN" in str(excinfo.value)
    assert "0.0200" in str(excinfo.value) or "0.02" in str(excinfo.value)
    # Restore
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.10")
    importlib.reload(mod)


def test_r2_anticipated_cost_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """A call BEFORE spending that would push us over the cap is caught
    by the anticipated_additional argument."""
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.05")
    import importlib
    import src.polaris_graph.llm.openrouter_client as mod
    importlib.reload(mod)
    mod.reset_run_cost()
    mod._add_run_cost(0.04)   # already at $0.04, cap $0.05
    # A $0.001 call is fine
    mod.check_run_budget(anticipated_additional=0.001)
    # A $0.02 call would push us to $0.06, over cap
    with pytest.raises(mod.BudgetExceededError):
        mod.check_run_budget(anticipated_additional=0.02)
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.10")
    importlib.reload(mod)


def test_r2_reset_between_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.05")
    import importlib
    import src.polaris_graph.llm.openrouter_client as mod
    importlib.reload(mod)
    mod.reset_run_cost()
    mod._add_run_cost(0.06)
    with pytest.raises(mod.BudgetExceededError):
        mod.check_run_budget()
    # Reset — next run is clean
    mod.reset_run_cost()
    assert mod.current_run_cost() == 0.0
    mod.check_run_budget()    # no raise
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "0.10")
    importlib.reload(mod)
