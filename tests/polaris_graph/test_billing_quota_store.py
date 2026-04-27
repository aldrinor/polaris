"""Tests for src/polaris_graph/audit_ir/billing_quota_store.py (M-NEW)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.billing_quota_store import (
    BillingQuotaStore,
    PlanTier,
    QuotaEventKind,
    QuotaExceededError,
    QuotaStateError,
)


@pytest.fixture
def store(tmp_path: Path) -> BillingQuotaStore:
    return BillingQuotaStore(tmp_path / "billing.sqlite")


# ---------------------------------------------------------------------------
# Plan assignment
# ---------------------------------------------------------------------------


def test_assign_plan_creates_row(store: BillingQuotaStore) -> None:
    plan = store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    assert plan.org_id == "org_a"
    assert plan.tier == PlanTier.PILOT
    assert plan.cycle_start > 0
    # Pilot tier defaults populate quotas.
    assert plan.quotas[QuotaEventKind.AUDIT_RUN_ENQUEUED] == 50
    assert plan.quotas[QuotaEventKind.WORKSPACE_CREATED] == 5


def test_assign_plan_idempotent_overwrites(store: BillingQuotaStore) -> None:
    """Re-assigning a plan updates in-place; cycle_start refreshes."""
    p1 = store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    time.sleep(0.001)
    p2 = store.assign_plan(org_id="org_a", tier=PlanTier.PRODUCTION)
    assert p2.tier == PlanTier.PRODUCTION
    assert p2.cycle_start > p1.cycle_start
    assert (
        p2.quotas[QuotaEventKind.AUDIT_RUN_ENQUEUED]
        == 5000  # PRODUCTION default
    )


def test_assign_plan_with_quota_override(store: BillingQuotaStore) -> None:
    plan = store.assign_plan(
        org_id="org_a", tier=PlanTier.PILOT,
        quotas_override={QuotaEventKind.AUDIT_RUN_ENQUEUED: 100},
    )
    # Override applies for the named kind.
    assert plan.quotas[QuotaEventKind.AUDIT_RUN_ENQUEUED] == 100
    # Other kinds keep PILOT defaults.
    assert plan.quotas[QuotaEventKind.WORKSPACE_CREATED] == 5


def test_assign_plan_rejects_empty_org(store: BillingQuotaStore) -> None:
    with pytest.raises(QuotaStateError, match="org_id"):
        store.assign_plan(org_id="", tier=PlanTier.PILOT)


def test_assign_plan_rejects_non_enum_tier(store: BillingQuotaStore) -> None:
    with pytest.raises(QuotaStateError, match="tier"):
        store.assign_plan(org_id="org_a", tier="pilot")  # type: ignore[arg-type]


def test_assign_plan_rejects_bad_override_key(
    store: BillingQuotaStore,
) -> None:
    with pytest.raises(QuotaStateError, match="QuotaEventKind"):
        store.assign_plan(
            org_id="org_a", tier=PlanTier.PILOT,
            quotas_override={"wrong_key": 100},  # type: ignore[dict-item]
        )


def test_get_plan_returns_none_for_unknown_org(
    store: BillingQuotaStore,
) -> None:
    assert store.get_plan(org_id="org_phantom") is None


# ---------------------------------------------------------------------------
# Quota check (read)
# ---------------------------------------------------------------------------


def test_check_quota_no_plan_returns_zero_cap(
    store: BillingQuotaStore,
) -> None:
    """An org with no assigned plan must NOT silently get default
    free quota — it gets cap=0 + is_exceeded=True so the caller's
    pre-check refuses the action."""
    res = store.check_quota(
        org_id="org_no_plan", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res.cap == 0
    assert res.is_exceeded is True


def test_check_quota_unlimited_for_enterprise(
    store: BillingQuotaStore,
) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.ENTERPRISE)
    res = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res.cap == -1
    assert res.remaining == -1
    assert res.is_exceeded is False


def test_check_quota_remaining_decreases_with_usage(
    store: BillingQuotaStore,
) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    res0 = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res0.remaining == 50
    store.consume(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    res1 = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res1.remaining == 49
    assert res1.used == 1


# ---------------------------------------------------------------------------
# Atomic consume + quota enforcement
# ---------------------------------------------------------------------------


def test_consume_succeeds_under_cap(store: BillingQuotaStore) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    event = store.consume(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        user_id="alice",
    )
    assert event.event_id.startswith("bil_")
    assert event.cost_units == 1
    assert event.user_id == "alice"


def test_consume_raises_at_cap(store: BillingQuotaStore) -> None:
    store.assign_plan(
        org_id="org_a", tier=PlanTier.PILOT,
        quotas_override={QuotaEventKind.AUDIT_RUN_ENQUEUED: 2},
    )
    store.consume(org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED)
    store.consume(org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED)
    with pytest.raises(QuotaExceededError):
        store.consume(
            org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )


def test_consume_raises_for_org_with_no_plan(
    store: BillingQuotaStore,
) -> None:
    with pytest.raises(QuotaExceededError, match="no assigned plan"):
        store.consume(
            org_id="org_no_plan",
            kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )


def test_consume_unlimited_tier_does_not_raise(
    store: BillingQuotaStore,
) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.ENTERPRISE)
    for _ in range(100):
        store.consume(
            org_id="org_a",
            kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )
    res = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res.is_exceeded is False
    assert res.used == 100


def test_consume_cost_units_must_be_positive(
    store: BillingQuotaStore,
) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    with pytest.raises(QuotaStateError, match="cost_units"):
        store.consume(
            org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
            cost_units=0,
        )


def test_consume_with_cost_units_greater_than_one(
    store: BillingQuotaStore,
) -> None:
    """Larger cost_units must consume the whole bundle atomically."""
    store.assign_plan(
        org_id="org_a", tier=PlanTier.PILOT,
        quotas_override={QuotaEventKind.AUDIT_BUNDLE_EXPORTED: 5},
    )
    # Consume 3 units in one call.
    store.consume(
        org_id="org_a",
        kind=QuotaEventKind.AUDIT_BUNDLE_EXPORTED,
        cost_units=3,
    )
    res = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_BUNDLE_EXPORTED,
    )
    assert res.used == 3
    assert res.remaining == 2
    # Asking for 3 more should fail (only 2 left).
    with pytest.raises(QuotaExceededError):
        store.consume(
            org_id="org_a",
            kind=QuotaEventKind.AUDIT_BUNDLE_EXPORTED,
            cost_units=3,
        )


# ---------------------------------------------------------------------------
# Cross-org isolation
# ---------------------------------------------------------------------------


def test_org_a_consumption_does_not_affect_org_b(
    store: BillingQuotaStore,
) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    store.assign_plan(org_id="org_b", tier=PlanTier.PILOT)
    for _ in range(10):
        store.consume(
            org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )
    res_a = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    res_b = store.check_quota(
        org_id="org_b", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res_a.used == 10
    assert res_b.used == 0  # cross-org isolation


# ---------------------------------------------------------------------------
# Cycle reset
# ---------------------------------------------------------------------------


def test_reset_monthly_counters_clears_used(
    store: BillingQuotaStore,
) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    for _ in range(5):
        store.consume(
            org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )
    res_before = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res_before.used == 5
    time.sleep(0.005)
    store.reset_monthly_counters(org_id="org_a")
    res_after = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res_after.used == 0
    assert res_after.remaining == 50  # full PILOT cap restored


def test_reset_does_not_delete_billing_events(
    store: BillingQuotaStore,
) -> None:
    """Append-only billing log: reset bumps cycle_start but does
    NOT delete prior events. Invoicing reconciliation reads the
    full history."""
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    for _ in range(5):
        store.consume(
            org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )
    store.reset_monthly_counters(org_id="org_a")
    events = store.list_events(org_id="org_a")
    assert len(events) == 5  # all preserved


def test_reset_unknown_org_raises(store: BillingQuotaStore) -> None:
    with pytest.raises(QuotaStateError, match="no assigned plan"):
        store.reset_monthly_counters(org_id="org_phantom")


# ---------------------------------------------------------------------------
# Event log query
# ---------------------------------------------------------------------------


def test_list_events_filters_by_kind(store: BillingQuotaStore) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    store.consume(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    store.consume(
        org_id="org_a", kind=QuotaEventKind.WORKSPACE_CREATED,
    )
    store.consume(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    runs = store.list_events(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    workspaces = store.list_events(
        org_id="org_a", kind=QuotaEventKind.WORKSPACE_CREATED,
    )
    assert len(runs) == 2
    assert len(workspaces) == 1


def test_list_events_time_range(store: BillingQuotaStore) -> None:
    store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    store.consume(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    time.sleep(0.005)
    cutoff = time.time()
    time.sleep(0.005)
    store.consume(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    after = store.list_events(org_id="org_a", since=cutoff)
    assert len(after) == 1


# ---------------------------------------------------------------------------
# Codex M-NEW v1 review fixes
# ---------------------------------------------------------------------------


def test_negative_quota_override_rejected_unless_unlimited(
    store: BillingQuotaStore,
) -> None:
    """Codex M-NEW v1: any negative cap silently became unlimited
    because the enforcement path treats cap<0 as unbounded. v2
    rejects negative values except -1 (the explicit unlimited
    sentinel)."""
    with pytest.raises(QuotaStateError, match=">= 0|-1"):
        store.assign_plan(
            org_id="org_a", tier=PlanTier.PILOT,
            quotas_override={QuotaEventKind.AUDIT_RUN_ENQUEUED: -5},
        )
    # Explicit unlimited (-1) is allowed.
    plan = store.assign_plan(
        org_id="org_a", tier=PlanTier.PILOT,
        quotas_override={QuotaEventKind.AUDIT_RUN_ENQUEUED: -1},
    )
    assert plan.quotas[QuotaEventKind.AUDIT_RUN_ENQUEUED] == -1


def test_redundant_assign_plan_does_not_refresh_cycle(
    store: BillingQuotaStore,
) -> None:
    """Codex M-NEW v1: re-calling assign_plan with the SAME tier
    and overrides used to refresh cycle_start, granting the
    customer a fresh budget. v2 only refreshes when composition
    actually changes."""
    p1 = store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    # Use a few units of the budget.
    for _ in range(3):
        store.consume(
            org_id="org_a",
            kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
        )
    res_after_use = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res_after_use.used == 3

    # Re-assign with the SAME tier — must NOT refresh cycle.
    time.sleep(0.005)
    p2 = store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    assert p2.cycle_start == p1.cycle_start, (
        "redundant re-assign must NOT refresh cycle_start"
    )
    res_after_reassign = store.check_quota(
        org_id="org_a", kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )
    assert res_after_reassign.used == 3, (
        "redundant re-assign must NOT zero the budget counter"
    )


def test_changing_tier_does_refresh_cycle(
    store: BillingQuotaStore,
) -> None:
    """A real tier change should refresh cycle_start (the customer
    is on a new plan now)."""
    p1 = store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    time.sleep(0.005)
    p2 = store.assign_plan(org_id="org_a", tier=PlanTier.PRODUCTION)
    assert p2.cycle_start > p1.cycle_start


def test_changing_quota_override_refreshes_cycle(
    store: BillingQuotaStore,
) -> None:
    """Same tier but different override should be treated as a
    composition change."""
    p1 = store.assign_plan(org_id="org_a", tier=PlanTier.PILOT)
    time.sleep(0.005)
    p2 = store.assign_plan(
        org_id="org_a", tier=PlanTier.PILOT,
        quotas_override={QuotaEventKind.AUDIT_RUN_ENQUEUED: 200},
    )
    assert p2.cycle_start > p1.cycle_start
    assert p2.quotas[QuotaEventKind.AUDIT_RUN_ENQUEUED] == 200


def test_list_events_limit_validation(store: BillingQuotaStore) -> None:
    with pytest.raises(QuotaStateError, match="limit"):
        store.list_events(org_id="org_a", limit=0)
    with pytest.raises(QuotaStateError, match="limit"):
        store.list_events(org_id="org_a", limit=10001)
