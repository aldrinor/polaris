"""M-D3 phase 2 v1 — decision telemetry aggregation tests.

Pins:
  - compute_aggregates pure derivation contract
  - DecisionKind filter (induction vs scope_gate vs both)
  - Time-window filter (since/until inclusive on boundaries)
  - Rate semantics (None when total_terminal == 0)
  - Workspace isolation
  - Empty store / no-match window edge cases
  - Pending-only window (rates None)
  - Mixed terminal actions arithmetic
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.polaris_graph.audit_ir.decision_aggregates import (
    DecisionAggregates,
    DecisionAggregatesError,
    compute_aggregates,
)
from src.polaris_graph.audit_ir.decision_telemetry import (
    CuratorAction,
    DecisionKind,
    DecisionRecordStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> DecisionRecordStore:
    return DecisionRecordStore(tmp_path / "decisions.sqlite")


def _record(
    store: DecisionRecordStore,
    *,
    workspace_id: str = "ws1",
    kind: DecisionKind = DecisionKind.INDUCTION,
    confidence: float = 0.85,
    clock: float | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    rec = store.record_decision(
        workspace_id=workspace_id,
        decision_kind=kind,
        query="some query",
        proposed_payload=payload or {"foo": "bar"},
        proposed_confidence=confidence,
        clock=clock,
    )
    return rec.record_id


def _accept(store: DecisionRecordStore, record_id: str, ws: str = "ws1") -> None:
    store.update_curator_action(
        workspace_id=ws,
        record_id=record_id,
        curator_action=CuratorAction.ACCEPTED_AS_PROPOSED,
        actor_user_id="curator-1",
        final_payload={"foo": "bar"},
    )


def _modify(store: DecisionRecordStore, record_id: str, ws: str = "ws1") -> None:
    store.update_curator_action(
        workspace_id=ws,
        record_id=record_id,
        curator_action=CuratorAction.MODIFIED,
        actor_user_id="curator-1",
        final_payload={"foo": "baz"},
        diff_payload={"foo": ["bar", "baz"]},
    )


def _override(store: DecisionRecordStore, record_id: str, ws: str = "ws1") -> None:
    store.update_curator_action(
        workspace_id=ws,
        record_id=record_id,
        curator_action=CuratorAction.OVERRIDDEN,
        actor_user_id="curator-1",
        final_payload={"completely": "different"},
        diff_payload={"reason": "operator override"},
    )


def _reject(store: DecisionRecordStore, record_id: str, ws: str = "ws1") -> None:
    store.update_curator_action(
        workspace_id=ws,
        record_id=record_id,
        curator_action=CuratorAction.REJECTED,
        actor_user_id="curator-1",
    )


# ---------------------------------------------------------------------------
# Empty / contract validation
# ---------------------------------------------------------------------------


def test_empty_store_returns_zero_counts(store: DecisionRecordStore) -> None:
    agg = compute_aggregates(store, "ws1")
    assert agg.total_decisions == 0
    assert agg.total_terminal == 0
    assert agg.pending_count == 0
    assert agg.accepted_count == 0
    assert agg.modified_count == 0
    assert agg.overridden_count == 0
    assert agg.rejected_count == 0
    assert agg.acceptance_rate is None
    assert agg.modification_rate is None
    assert agg.override_rate is None
    assert agg.rejection_rate is None


def test_workspace_id_required(store: DecisionRecordStore) -> None:
    with pytest.raises(DecisionAggregatesError, match="workspace_id"):
        compute_aggregates(store, "")
    with pytest.raises(DecisionAggregatesError, match="workspace_id"):
        compute_aggregates(store, "   ")


def test_workspace_id_stripped(store: DecisionRecordStore) -> None:
    rid = _record(store, workspace_id="ws1")
    _accept(store, rid)
    agg = compute_aggregates(store, "  ws1  ")
    assert agg.workspace_id == "ws1"
    assert agg.total_decisions == 1


def test_non_store_argument_raises(store: DecisionRecordStore) -> None:
    with pytest.raises(DecisionAggregatesError, match="store must"):
        compute_aggregates("not a store", "ws1")  # type: ignore[arg-type]


def test_invalid_window_raises(store: DecisionRecordStore) -> None:
    with pytest.raises(DecisionAggregatesError, match="must be <= until"):
        compute_aggregates(store, "ws1", since=2000.0, until=1000.0)


# ---------------------------------------------------------------------------
# Pending-only: rates undefined
# ---------------------------------------------------------------------------


def test_only_pending_yields_none_rates(store: DecisionRecordStore) -> None:
    _record(store)
    _record(store)
    agg = compute_aggregates(store, "ws1")
    assert agg.total_decisions == 2
    assert agg.pending_count == 2
    assert agg.total_terminal == 0
    assert agg.acceptance_rate is None
    assert agg.modification_rate is None
    assert agg.override_rate is None
    assert agg.rejection_rate is None


# ---------------------------------------------------------------------------
# Single-action windows
# ---------------------------------------------------------------------------


def test_all_accepted_yields_unit_acceptance_rate(
    store: DecisionRecordStore,
) -> None:
    for _ in range(3):
        rid = _record(store)
        _accept(store, rid)
    agg = compute_aggregates(store, "ws1")
    assert agg.total_decisions == 3
    assert agg.total_terminal == 3
    assert agg.accepted_count == 3
    assert agg.acceptance_rate == 1.0
    assert agg.modification_rate == 0.0
    assert agg.override_rate == 0.0
    assert agg.rejection_rate == 0.0


def test_all_rejected_yields_unit_rejection_rate(
    store: DecisionRecordStore,
) -> None:
    for _ in range(2):
        rid = _record(store)
        _reject(store, rid)
    agg = compute_aggregates(store, "ws1")
    assert agg.rejected_count == 2
    assert agg.rejection_rate == 1.0
    assert agg.acceptance_rate == 0.0


# ---------------------------------------------------------------------------
# Mixed terminal arithmetic
# ---------------------------------------------------------------------------


def test_mixed_terminal_actions_count_correctly(
    store: DecisionRecordStore,
) -> None:
    # 2 accepted, 1 modified, 1 overridden, 1 rejected → 5 terminal
    for _ in range(2):
        rid = _record(store)
        _accept(store, rid)
    rid = _record(store)
    _modify(store, rid)
    rid = _record(store)
    _override(store, rid)
    rid = _record(store)
    _reject(store, rid)
    # 1 pending
    _record(store)

    agg = compute_aggregates(store, "ws1")
    assert agg.total_decisions == 6
    assert agg.pending_count == 1
    assert agg.total_terminal == 5
    assert agg.accepted_count == 2
    assert agg.modified_count == 1
    assert agg.overridden_count == 1
    assert agg.rejected_count == 1
    assert agg.acceptance_rate == pytest.approx(2 / 5)
    assert agg.modification_rate == pytest.approx(1 / 5)
    assert agg.override_rate == pytest.approx(1 / 5)
    assert agg.rejection_rate == pytest.approx(1 / 5)
    # Rates sum to 1.0 exactly when total_terminal > 0
    rate_sum = (
        agg.acceptance_rate + agg.modification_rate
        + agg.override_rate + agg.rejection_rate
    )
    assert rate_sum == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# DecisionKind filter
# ---------------------------------------------------------------------------


def test_filter_by_induction_excludes_scope_gate(
    store: DecisionRecordStore,
) -> None:
    rid = _record(store, kind=DecisionKind.INDUCTION)
    _accept(store, rid)
    rid = _record(store, kind=DecisionKind.SCOPE_GATE)
    _reject(store, rid)
    agg_ind = compute_aggregates(
        store, "ws1", decision_kind=DecisionKind.INDUCTION,
    )
    assert agg_ind.total_decisions == 1
    assert agg_ind.accepted_count == 1
    assert agg_ind.rejected_count == 0
    assert agg_ind.decision_kind == DecisionKind.INDUCTION


def test_filter_by_scope_gate_excludes_induction(
    store: DecisionRecordStore,
) -> None:
    rid = _record(store, kind=DecisionKind.INDUCTION)
    _accept(store, rid)
    rid = _record(store, kind=DecisionKind.SCOPE_GATE)
    _reject(store, rid)
    agg_sg = compute_aggregates(
        store, "ws1", decision_kind=DecisionKind.SCOPE_GATE,
    )
    assert agg_sg.total_decisions == 1
    assert agg_sg.rejected_count == 1
    assert agg_sg.accepted_count == 0
    assert agg_sg.decision_kind == DecisionKind.SCOPE_GATE


def test_no_kind_filter_aggregates_both(
    store: DecisionRecordStore,
) -> None:
    rid = _record(store, kind=DecisionKind.INDUCTION)
    _accept(store, rid)
    rid = _record(store, kind=DecisionKind.SCOPE_GATE)
    _reject(store, rid)
    agg = compute_aggregates(store, "ws1")
    assert agg.total_decisions == 2
    assert agg.accepted_count == 1
    assert agg.rejected_count == 1
    assert agg.decision_kind is None


# ---------------------------------------------------------------------------
# Time-window filter
# ---------------------------------------------------------------------------


def test_since_filter_excludes_older_records(
    store: DecisionRecordStore,
) -> None:
    rid_old = _record(store, clock=1000.0)
    _accept(store, rid_old)
    rid_new = _record(store, clock=2000.0)
    _accept(store, rid_new)
    agg = compute_aggregates(store, "ws1", since=1500.0)
    assert agg.total_decisions == 1
    assert agg.window_start == 1500.0
    assert agg.accepted_count == 1


def test_until_filter_excludes_newer_records(
    store: DecisionRecordStore,
) -> None:
    rid_old = _record(store, clock=1000.0)
    _accept(store, rid_old)
    rid_new = _record(store, clock=2000.0)
    _accept(store, rid_new)
    agg = compute_aggregates(store, "ws1", until=1500.0)
    assert agg.total_decisions == 1
    assert agg.window_end == 1500.0


def test_window_inclusive_at_boundaries(store: DecisionRecordStore) -> None:
    """A record exactly at since boundary is included; same for until."""
    rid = _record(store, clock=1500.0)
    _accept(store, rid)
    agg = compute_aggregates(store, "ws1", since=1500.0, until=1500.0)
    assert agg.total_decisions == 1


def test_window_with_no_matches_yields_empty_aggregates(
    store: DecisionRecordStore,
) -> None:
    rid = _record(store, clock=1000.0)
    _accept(store, rid)
    agg = compute_aggregates(store, "ws1", since=2000.0, until=3000.0)
    assert agg.total_decisions == 0
    assert agg.acceptance_rate is None


def test_open_window_includes_all(store: DecisionRecordStore) -> None:
    for clock in (1000.0, 2000.0, 3000.0):
        rid = _record(store, clock=clock)
        _accept(store, rid)
    agg = compute_aggregates(store, "ws1")
    assert agg.total_decisions == 3
    assert agg.window_start is None
    assert agg.window_end is None


def test_combined_window_kind_filter(
    store: DecisionRecordStore,
) -> None:
    """Filter by both kind AND window simultaneously."""
    # In window + induction
    rid = _record(store, clock=1500.0, kind=DecisionKind.INDUCTION)
    _accept(store, rid)
    # In window + scope_gate (excluded by kind filter)
    rid = _record(store, clock=1600.0, kind=DecisionKind.SCOPE_GATE)
    _accept(store, rid)
    # Out of window + induction (excluded by window)
    rid = _record(store, clock=500.0, kind=DecisionKind.INDUCTION)
    _accept(store, rid)
    agg = compute_aggregates(
        store, "ws1",
        decision_kind=DecisionKind.INDUCTION,
        since=1000.0, until=2000.0,
    )
    assert agg.total_decisions == 1
    assert agg.accepted_count == 1


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


def test_workspace_isolation(store: DecisionRecordStore) -> None:
    rid_a = _record(store, workspace_id="ws_a")
    _accept(store, rid_a, ws="ws_a")
    rid_b = _record(store, workspace_id="ws_b")
    _reject(store, rid_b, ws="ws_b")
    agg_a = compute_aggregates(store, "ws_a")
    assert agg_a.total_decisions == 1
    assert agg_a.accepted_count == 1
    assert agg_a.rejected_count == 0
    agg_b = compute_aggregates(store, "ws_b")
    assert agg_b.total_decisions == 1
    assert agg_b.rejected_count == 1
    assert agg_b.accepted_count == 0


# ---------------------------------------------------------------------------
# Aggregates dataclass invariants
# ---------------------------------------------------------------------------


def test_aggregates_workspace_id_echoed(store: DecisionRecordStore) -> None:
    agg = compute_aggregates(store, "ws1")
    assert agg.workspace_id == "ws1"


def test_pending_plus_terminal_equals_total(
    store: DecisionRecordStore,
) -> None:
    """Even with mixed states, pending + terminal accounting holds."""
    for _ in range(3):
        rid = _record(store)
        _accept(store, rid)
    for _ in range(2):
        _record(store)  # pending
    agg = compute_aggregates(store, "ws1")
    assert agg.pending_count + agg.total_terminal == agg.total_decisions
