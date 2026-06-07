"""
R-2 regression tests: per-run cost cap.

I-ready-018 (#1088): these tests previously did ``importlib.reload(openrouter_client)``
to pick up a new ``PG_MAX_COST_PER_RUN`` env value. That reload was a TEST-POLLUTER: it
rebound the module's ``BudgetExceededError`` to a NEW class object (NOT a subclass of the
pre-reload class) and created a fresh ``_RUN_COST_CTX`` ContextVar. Downstream tests that had
already captured the original class at import time (``tests/roles/test_four_role_budget_cap.py``
+ ``tests/roles/test_seam_parallel.py`` + the fx01 / semantic-conflict suites) then failed in the
full-process sweep because their ``pytest.raises(BudgetExceededError)`` held the stale class while
the 4-role seam raised the reloaded one — the exception went uncaught (the cap math was always
correct). Fix: use the live setter ``set_max_cost_per_run()`` (added I-cap-005 #1068, which the
budget check reads directly) — NO reload — plus an autouse fixture that captures + restores the cap
and resets the accumulator. Behaviour + thresholds unchanged; the module is never reloaded.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.llm.openrouter_client import (
    BudgetExceededError,
    _add_run_cost,
    check_run_budget,
    current_run_cost,
    get_max_cost_per_run,
    reset_run_cost,
    set_max_cost_per_run,
)


@pytest.fixture(autouse=True)
def _isolate_cap():
    """Capture + restore the live per-run cost cap and reset the run-cost accumulator around each
    test, so no test leaks a cap/accumulator into a sibling — and so NO importlib.reload is needed
    (reload rebinds BudgetExceededError + the ContextVar, poisoning the 4-role seam tests)."""
    original = get_max_cost_per_run()
    reset_run_cost()
    try:
        yield
    finally:
        set_max_cost_per_run(original)
        reset_run_cost()


def test_r2_reset_zero_baseline() -> None:
    reset_run_cost()
    assert current_run_cost() == 0.0


def test_r2_add_and_report() -> None:
    reset_run_cost()
    _add_run_cost(0.002)
    _add_run_cost(0.003)
    assert abs(current_run_cost() - 0.005) < 1e-9


def test_r2_check_below_cap_ok() -> None:
    set_max_cost_per_run(0.50)
    reset_run_cost()
    _add_run_cost(0.1)
    # Should not raise.
    check_run_budget()


def test_r2_check_above_cap_raises() -> None:
    set_max_cost_per_run(0.01)
    reset_run_cost()
    _add_run_cost(0.02)   # already over cap
    with pytest.raises(BudgetExceededError) as excinfo:
        check_run_budget()
    assert "PG_MAX_COST_PER_RUN" in str(excinfo.value)
    assert "0.0200" in str(excinfo.value) or "0.02" in str(excinfo.value)


def test_r2_anticipated_cost_tripwire() -> None:
    """A call BEFORE spending that would push us over the cap is caught by the
    anticipated_additional argument."""
    set_max_cost_per_run(0.05)
    reset_run_cost()
    _add_run_cost(0.04)   # already at $0.04, cap $0.05
    # A $0.001 call is fine.
    check_run_budget(anticipated_additional=0.001)
    # A $0.02 call would push us to $0.06, over cap.
    with pytest.raises(BudgetExceededError):
        check_run_budget(anticipated_additional=0.02)


def test_r2_reset_between_runs() -> None:
    set_max_cost_per_run(0.05)
    reset_run_cost()
    _add_run_cost(0.06)
    with pytest.raises(BudgetExceededError):
        check_run_budget()
    # Reset — next run is clean.
    reset_run_cost()
    assert current_run_cost() == 0.0
    check_run_budget()    # no raise
