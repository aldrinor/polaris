"""P0 DEADLOCK-GUARD regression (2026-07-12).

Locks the startup guard that refuses the KNOWN-DEADLOCKING compose config (the FULL 328-basket
16-way compose that wedged 19/20 threads in futex_wait and was SIGKILLed) until a full-328
verdict-identity A/B has certified it. The guard can NEVER be regressed into shipping the deadlock
config by accident: shipping it requires PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED=1 attesting the A/B.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.compose_config_guard import (
    UnsafeComposeConfigError,
    assert_safe_compose_config,
    evaluate_compose_config,
)


def _safe(env):
    return evaluate_compose_config(env)[0]


def test_default_config_is_safe():
    # Unset => workers=1, sem=4 (the confirmed 24.2min clean-run defaults) => SAFE, no raise.
    assert _safe({}) is True
    assert_safe_compose_config({})  # no raise


def test_clean_run_config_is_safe():
    env = {"PG_COMPOSE_BASKET_WORKERS": "1", "PG_SIDE_JUDGE_MAX_CONCURRENCY": "8",
           "PG_PARALLEL_SECTIONS": "3"}
    assert _safe(env) is True
    assert_safe_compose_config(env)


@pytest.mark.parametrize("env", [
    {"PG_COMPOSE_BASKET_WORKERS": "2"},      # >1 basket workers
    {"PG_COMPOSE_BASKET_WORKERS": "16"},
    {"PG_SIDE_JUDGE_MAX_CONCURRENCY": "48"}, # >=48 side-judge sem
    {"PG_SIDE_JUDGE_MAX_CONCURRENCY": "64"},
    {"PG_COMPOSE_BASKET_WORKERS": "16", "PG_SIDE_JUDGE_MAX_CONCURRENCY": "48"},
])
def test_deadlock_config_is_refused(env):
    assert _safe(env) is False
    with pytest.raises(UnsafeComposeConfigError):
        assert_safe_compose_config(env)


@pytest.mark.parametrize("env", [
    {"PG_COMPOSE_BASKET_WORKERS": "16", "PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED": "1"},
    {"PG_SIDE_JUDGE_MAX_CONCURRENCY": "48", "PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED": "true"},
    {"PG_COMPOSE_BASKET_WORKERS": "16", "PG_SIDE_JUDGE_MAX_CONCURRENCY": "64",
     "PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED": "yes"},
])
def test_ab_certified_flag_allows_deadlock_config(env):
    # The single escape hatch: an operator attests the full-328 verdict-identity A/B passed.
    assert _safe(env) is True
    assert_safe_compose_config(env)  # no raise


@pytest.mark.parametrize("env", [
    {"PG_COMPOSE_BASKET_WORKERS": "garbage"},         # malformed => fail-safe to serial (1)
    {"PG_SIDE_JUDGE_MAX_CONCURRENCY": "not-a-number"}, # malformed => fail-safe to default (4)
    {"PG_SIDE_JUDGE_MAX_CONCURRENCY": "47"},           # just below the 48 threshold
    {"PG_SIDE_JUDGE_MAX_CONCURRENCY": "0"},            # unbounded-hatch but the guard only flags >=48
])
def test_malformed_or_below_threshold_is_safe(env):
    # A typo must never silently DISABLE the guard; below-threshold values are the safe band.
    assert _safe(env) is True
    assert_safe_compose_config(env)


def test_grace_default_parks_wall_for_mega_fetch():
    # P1 degrade-tail: the outer belt-and-suspenders grace must be large enough that a legit final
    # in-flight turn containing a ~466s mega-fetch COMPLETES agentic (wall+grace > wall+466) instead
    # of being cancelled -> degrade-to-seed. Raised 180 -> 600.
    from src.polaris_graph.outline.outline_agent import (
        PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS_DEFAULT as GRACE,
        PG_OUTLINE_AGENT_WALL_SECONDS_DEFAULT as WALL,
    )
    assert GRACE >= 600
    # documented mega-fetch overshoot 466.2s must fit inside the grace with margin.
    assert GRACE > 466
    # the outer ceiling still exists (catches a TRUE hang): wall+grace is a finite bound.
    assert WALL + GRACE < 3600
