"""M-D3 phase 1 — Induction → operator-review telemetry tests.

Pins:
  - Schema integrity (CHECK constraints + indexes)
  - record_decision invariants
  - update_curator_action transition matrix (PENDING → terminal × 4)
  - Terminal states are terminal (no further transitions)
  - Generic decision_kind discriminator (induction + scope_gate
    coexist in the same store)
  - List + count filters
  - Coexistence with M-21 / M-D7 / M-D10 (same DB file, no
    table-name collision)
  - JSON round-trip for proposed/final/diff payloads
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.decision_telemetry import (
    CuratorAction,
    DecisionKind,
    DecisionRecord,
    DecisionRecordStore,
    DecisionTelemetryError,
    DecisionTelemetryStateError,
    decision_to_dict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> DecisionRecordStore:
    return DecisionRecordStore(tmp_path / "telemetry.db")


_INDUCTION_PAYLOAD = {
    "contract_slug": "clinical_tirzepatide_t2dm",
    "section_order": ["efficacy", "safety", "monitoring"],
    "required_entities": [
        {"id": "drug", "type": "drug", "rendering_slot": "drug_named"},
    ],
}

_SCOPE_GATE_PAYLOAD = {
    "action": "route",
    "template_id": "v30_clinical",
    "threshold": 0.70,
    "router_score": 1.0,
    "rationale": "classifier in_scope and router routed",
}


# ---------------------------------------------------------------------------
# record_decision invariants
# ---------------------------------------------------------------------------


def test_record_decision_pending_state(store: DecisionRecordStore) -> None:
    rec = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="What is the efficacy of tirzepatide for T2DM?",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    assert isinstance(rec, DecisionRecord)
    assert rec.curator_action == CuratorAction.PENDING
    assert rec.final_payload is None
    assert rec.diff_payload is None
    assert rec.actor_user_id is None
    assert rec.decided_at is None
    assert rec.proposed_payload == _INDUCTION_PAYLOAD


def test_record_decision_persists_across_store_instances(tmp_path: Path) -> None:
    """Re-opening the DB must surface the same record."""
    db = tmp_path / "telemetry.db"
    s1 = DecisionRecordStore(db)
    rec = s1.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.7,
    )
    s2 = DecisionRecordStore(db)
    fetched = s2.get(rec.record_id, workspace_id="ws-a")
    assert fetched is not None
    assert fetched.proposed_payload == _INDUCTION_PAYLOAD


def test_record_decision_empty_workspace_raises(
    store: DecisionRecordStore,
) -> None:
    with pytest.raises(DecisionTelemetryError, match="workspace_id"):
        store.record_decision(
            workspace_id="",
            decision_kind=DecisionKind.INDUCTION,
            query="q",
            proposed_payload={},
            proposed_confidence=0.5,
        )


def test_record_decision_empty_query_raises(
    store: DecisionRecordStore,
) -> None:
    with pytest.raises(DecisionTelemetryError, match="query"):
        store.record_decision(
            workspace_id="ws-a",
            decision_kind=DecisionKind.INDUCTION,
            query="",
            proposed_payload={},
            proposed_confidence=0.5,
        )


def test_record_decision_invalid_decision_kind_raises(
    store: DecisionRecordStore,
) -> None:
    with pytest.raises(DecisionTelemetryError, match="DecisionKind"):
        store.record_decision(
            workspace_id="ws-a",
            decision_kind="induction",  # type: ignore[arg-type]
            query="q",
            proposed_payload={},
            proposed_confidence=0.5,
        )


def test_record_decision_confidence_above_one_raises(
    store: DecisionRecordStore,
) -> None:
    with pytest.raises(DecisionTelemetryError, match=r"outside \[0, 1\]"):
        store.record_decision(
            workspace_id="ws-a",
            decision_kind=DecisionKind.INDUCTION,
            query="q",
            proposed_payload={},
            proposed_confidence=1.5,
        )


def test_record_decision_confidence_negative_raises(
    store: DecisionRecordStore,
) -> None:
    with pytest.raises(DecisionTelemetryError, match=r"outside \[0, 1\]"):
        store.record_decision(
            workspace_id="ws-a",
            decision_kind=DecisionKind.INDUCTION,
            query="q",
            proposed_payload={},
            proposed_confidence=-0.1,
        )


def test_record_decision_unserializable_payload_raises(
    store: DecisionRecordStore,
) -> None:
    class _NotJsonable:
        pass

    with pytest.raises(
        DecisionTelemetryError, match="JSON-serializable"
    ):
        store.record_decision(
            workspace_id="ws-a",
            decision_kind=DecisionKind.INDUCTION,
            query="q",
            proposed_payload={"weird": _NotJsonable()},  # type: ignore[dict-item]
            proposed_confidence=0.5,
        )


# ---------------------------------------------------------------------------
# update_curator_action transition matrix
# ---------------------------------------------------------------------------


def _seed(store: DecisionRecordStore, **overrides) -> DecisionRecord:
    defaults = dict(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    defaults.update(overrides)
    return store.record_decision(**defaults)


def test_transition_to_accepted_as_proposed(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    updated = store.update_curator_action(
        rec.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.ACCEPTED_AS_PROPOSED,
        actor_user_id="curator-1",
        final_payload=_INDUCTION_PAYLOAD,
    )
    assert updated.curator_action == CuratorAction.ACCEPTED_AS_PROPOSED
    assert updated.final_payload == _INDUCTION_PAYLOAD
    assert updated.diff_payload is None
    assert updated.actor_user_id == "curator-1"
    assert updated.decided_at is not None


def test_transition_to_modified_with_diff(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    modified_payload = {**_INDUCTION_PAYLOAD, "section_order": ["efficacy", "safety"]}
    diff = {
        "section_order": {
            "removed": ["monitoring"],
            "kept": ["efficacy", "safety"],
        }
    }
    updated = store.update_curator_action(
        rec.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.MODIFIED,
        actor_user_id="curator-1",
        final_payload=modified_payload,
        diff_payload=diff,
        notes="Curator removed monitoring section per scope.",
    )
    assert updated.curator_action == CuratorAction.MODIFIED
    assert updated.final_payload == modified_payload
    assert updated.diff_payload == diff
    assert updated.notes == "Curator removed monitoring section per scope."


def test_transition_to_overridden(store: DecisionRecordStore) -> None:
    rec = _seed(store)
    overridden = {"contract_slug": "policy_medicare_drug_price"}
    diff = {
        "contract_slug": {
            "from": "clinical_tirzepatide_t2dm",
            "to": "policy_medicare_drug_price",
        }
    }
    updated = store.update_curator_action(
        rec.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.OVERRIDDEN,
        actor_user_id="curator-1",
        final_payload=overridden,
        diff_payload=diff,
    )
    assert updated.curator_action == CuratorAction.OVERRIDDEN
    assert updated.final_payload == overridden
    assert updated.diff_payload == diff


def test_transition_to_rejected(store: DecisionRecordStore) -> None:
    rec = _seed(store)
    updated = store.update_curator_action(
        rec.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.REJECTED,
        actor_user_id="curator-1",
        final_payload=None,
        notes="Out of scope",
    )
    assert updated.curator_action == CuratorAction.REJECTED
    assert updated.final_payload is None
    assert updated.diff_payload is None


def test_transition_to_pending_raises(store: DecisionRecordStore) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="PENDING"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.PENDING,
            actor_user_id="curator-1",
        )


def test_transition_without_actor_raises(store: DecisionRecordStore) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="actor_user_id"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.REJECTED,
            actor_user_id="",
        )


def test_rejected_with_final_payload_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="rejected"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.REJECTED,
            actor_user_id="curator-1",
            final_payload={"something": 1},
        )


def test_rejected_with_diff_raises(store: DecisionRecordStore) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="rejected"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.REJECTED,
            actor_user_id="curator-1",
            diff_payload={"x": 1},
        )


def test_accepted_as_proposed_with_diff_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="accepted_as_proposed"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.ACCEPTED_AS_PROPOSED,
            actor_user_id="curator-1",
            final_payload=_INDUCTION_PAYLOAD,
            diff_payload={"x": 1},
        )


def test_accepted_as_proposed_without_final_payload_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="final_payload required"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.ACCEPTED_AS_PROPOSED,
            actor_user_id="curator-1",
        )


def test_modified_without_final_payload_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="final_payload required"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.MODIFIED,
            actor_user_id="curator-1",
        )


def test_overridden_without_final_payload_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="final_payload required"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.OVERRIDDEN,
            actor_user_id="curator-1",
        )


# ---------------------------------------------------------------------------
# Terminal-state immutability
# ---------------------------------------------------------------------------


def test_double_transition_after_accepted_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    store.update_curator_action(
        rec.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.ACCEPTED_AS_PROPOSED,
        actor_user_id="curator-1",
        final_payload=_INDUCTION_PAYLOAD,
    )
    with pytest.raises(DecisionTelemetryStateError, match="terminal"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.MODIFIED,
            actor_user_id="curator-1",
            final_payload={},
            diff_payload={"x": 1},
        )


def test_double_transition_after_rejected_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    store.update_curator_action(
        rec.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.REJECTED,
        actor_user_id="curator-1",
    )
    with pytest.raises(DecisionTelemetryStateError, match="terminal"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-a",
            curator_action=CuratorAction.MODIFIED,
            actor_user_id="curator-1",
            final_payload={},
            diff_payload={"x": 1},
        )


def test_update_nonexistent_record_raises(
    store: DecisionRecordStore,
) -> None:
    with pytest.raises(DecisionTelemetryStateError, match="not found"):
        store.update_curator_action(
            "00000000-0000-0000-0000-000000000000",
            workspace_id="ws-a",
            curator_action=CuratorAction.REJECTED,
            actor_user_id="curator-1",
        )


# ---------------------------------------------------------------------------
# Generic decision_kind discriminator
# ---------------------------------------------------------------------------


def test_induction_and_scope_gate_records_coexist(
    store: DecisionRecordStore,
) -> None:
    induction = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="ind q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    scope_gate = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.SCOPE_GATE,
        query="gate q",
        proposed_payload=_SCOPE_GATE_PAYLOAD,
        proposed_confidence=0.95,
    )
    assert induction.decision_kind == DecisionKind.INDUCTION
    assert scope_gate.decision_kind == DecisionKind.SCOPE_GATE

    induction_only = store.list_for_workspace(
        "ws-a", decision_kind=DecisionKind.INDUCTION
    )
    gate_only = store.list_for_workspace(
        "ws-a", decision_kind=DecisionKind.SCOPE_GATE
    )
    assert len(induction_only) == 1
    assert induction_only[0].record_id == induction.record_id
    assert len(gate_only) == 1
    assert gate_only[0].record_id == scope_gate.record_id


# ---------------------------------------------------------------------------
# List + count filters
# ---------------------------------------------------------------------------


def test_list_filter_by_curator_action(store: DecisionRecordStore) -> None:
    rec_a = _seed(store, query="A")
    rec_b = _seed(store, query="B")
    store.update_curator_action(
        rec_a.record_id,
        workspace_id="ws-a",
        curator_action=CuratorAction.REJECTED,
        actor_user_id="curator-1",
    )
    rejected = store.list_for_workspace(
        "ws-a", curator_action=CuratorAction.REJECTED
    )
    pending = store.list_for_workspace(
        "ws-a", curator_action=CuratorAction.PENDING
    )
    assert {r.record_id for r in rejected} == {rec_a.record_id}
    assert {r.record_id for r in pending} == {rec_b.record_id}


def test_list_filter_workspace_isolation(
    store: DecisionRecordStore,
) -> None:
    """Different workspace ids must not leak across queries."""
    rec_a = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="A",
        proposed_payload={},
        proposed_confidence=0.5,
    )
    rec_b = store.record_decision(
        workspace_id="ws-b",
        decision_kind=DecisionKind.INDUCTION,
        query="B",
        proposed_payload={},
        proposed_confidence=0.5,
    )
    a_records = store.list_for_workspace("ws-a")
    b_records = store.list_for_workspace("ws-b")
    assert {r.record_id for r in a_records} == {rec_a.record_id}
    assert {r.record_id for r in b_records} == {rec_b.record_id}


def test_list_limit(store: DecisionRecordStore) -> None:
    for i in range(5):
        _seed(store, query=f"q{i}")
    limited = store.list_for_workspace("ws-a", limit=3)
    assert len(limited) == 3


def test_list_negative_limit_raises(store: DecisionRecordStore) -> None:
    with pytest.raises(DecisionTelemetryError, match="non-negative"):
        store.list_for_workspace("ws-a", limit=-1)


def test_list_ordered_by_created_at_desc(
    store: DecisionRecordStore,
) -> None:
    rec_first = _seed(store, query="first")
    rec_second = _seed(store, query="second")
    rec_third = _seed(store, query="third")
    listed = store.list_for_workspace("ws-a")
    assert [r.record_id for r in listed] == [
        rec_third.record_id,
        rec_second.record_id,
        rec_first.record_id,
    ]


def test_count_for_workspace(store: DecisionRecordStore) -> None:
    for i in range(3):
        _seed(store, query=f"q{i}")
    assert store.count_for_workspace("ws-a") == 3
    assert store.count_for_workspace(
        "ws-a", curator_action=CuratorAction.PENDING
    ) == 3
    assert store.count_for_workspace(
        "ws-a", curator_action=CuratorAction.REJECTED
    ) == 0


# ---------------------------------------------------------------------------
# Schema-level invariants (CHECK constraints, enums)
# ---------------------------------------------------------------------------


def test_schema_check_invalid_kind_string_raises(
    tmp_path: Path,
) -> None:
    """Direct SQL bypassing the dataclass must still trip the
    CHECK constraint at DB layer (defense-in-depth)."""
    db = tmp_path / "telemetry.db"
    DecisionRecordStore(db)
    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO decision_records (
                    record_id, workspace_id, decision_kind, query,
                    proposed_payload_json, proposed_confidence,
                    curator_action, created_at
                ) VALUES (?, 'ws', 'unknown_kind', 'q', '{}', 0.5,
                          'pending', 0)
                """,
                ("rec-1",),
            )
    finally:
        conn.close()


def test_schema_check_invalid_action_string_raises(
    tmp_path: Path,
) -> None:
    db = tmp_path / "telemetry.db"
    DecisionRecordStore(db)
    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO decision_records (
                    record_id, workspace_id, decision_kind, query,
                    proposed_payload_json, proposed_confidence,
                    curator_action, created_at
                ) VALUES (?, 'ws', 'induction', 'q', '{}', 0.5,
                          'flagrant_invalid', 0)
                """,
                ("rec-1",),
            )
    finally:
        conn.close()


def test_schema_check_confidence_out_of_range_raises(
    tmp_path: Path,
) -> None:
    db = tmp_path / "telemetry.db"
    DecisionRecordStore(db)
    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO decision_records (
                    record_id, workspace_id, decision_kind, query,
                    proposed_payload_json, proposed_confidence,
                    curator_action, created_at
                ) VALUES (?, 'ws', 'induction', 'q', '{}', 1.5,
                          'pending', 0)
                """,
                ("rec-1",),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Coexistence with M-21 / M-D7 / M-D10 (same DB file)
# ---------------------------------------------------------------------------


def test_coexistence_with_m21_workspace_memory(tmp_path: Path) -> None:
    """Same SQLite file hosts both M-21 workspace memory + M-D3
    decision telemetry without table-name collision."""
    db = tmp_path / "shared.db"
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStore,
    )

    mem = WorkspaceMemoryStore(db)
    telem = DecisionRecordStore(db)
    rec = telem.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    # Sanity check: M-21 still works after M-D3 schema is applied.
    assert mem.list_entries(workspace_id="ws-a") == []
    # And M-D3 still works after M-21 schema is applied.
    assert telem.get(rec.record_id, workspace_id="ws-a") is not None


def test_coexistence_with_md7_retrieval_cache(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    from src.polaris_graph.audit_ir.retrieval_cache import (
        RetrievalCacheStore,
    )

    cache = RetrievalCacheStore(db)
    telem = DecisionRecordStore(db)
    rec = telem.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    assert cache is not None
    assert telem.get(rec.record_id, workspace_id="ws-a") is not None


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_decision_to_dict_round_trip(store: DecisionRecordStore) -> None:
    rec = _seed(store)
    serialized = decision_to_dict(rec)
    assert serialized["record_id"] == rec.record_id
    assert serialized["decision_kind"] == "induction"
    assert serialized["curator_action"] == "pending"
    assert serialized["proposed_payload"] == _INDUCTION_PAYLOAD
    assert serialized["final_payload"] is None
    assert serialized["diff_payload"] is None


def test_get_with_wrong_workspace_returns_none(
    store: DecisionRecordStore,
) -> None:
    """Codex round-1 MED fix (v2): get() requires workspace_id and
    filters on it. A caller knowing a record_id from one workspace
    must not be able to fetch it via a different workspace.
    """
    rec = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    fetched_correct = store.get(rec.record_id, workspace_id="ws-a")
    fetched_wrong = store.get(rec.record_id, workspace_id="ws-b")
    assert fetched_correct is not None
    assert fetched_wrong is None


def test_get_with_empty_workspace_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="workspace_id"):
        store.get(rec.record_id, workspace_id="")


def test_update_with_wrong_workspace_raises(
    store: DecisionRecordStore,
) -> None:
    """Codex round-1 MED fix (v2): update_curator_action requires
    workspace_id; mismatched workspace surfaces as 'not found'.
    SELECT+UPDATE both filter on workspace_id, so partial knowledge
    of (record_id only) cannot transition a row across workspaces.
    """
    rec = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.INDUCTION,
        query="q",
        proposed_payload=_INDUCTION_PAYLOAD,
        proposed_confidence=0.85,
    )
    with pytest.raises(DecisionTelemetryStateError, match="not found"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="ws-b",
            curator_action=CuratorAction.REJECTED,
            actor_user_id="curator-1",
        )
    fetched = store.get(rec.record_id, workspace_id="ws-a")
    assert fetched is not None
    assert fetched.curator_action == CuratorAction.PENDING


def test_update_with_empty_workspace_raises(
    store: DecisionRecordStore,
) -> None:
    rec = _seed(store)
    with pytest.raises(DecisionTelemetryError, match="workspace_id"):
        store.update_curator_action(
            rec.record_id,
            workspace_id="",
            curator_action=CuratorAction.REJECTED,
            actor_user_id="curator-1",
        )


def test_validate_terminal_args_helper_centralization() -> None:
    """Codex round-1 MED fix (v2): cross-action invariants live in
    a single private helper `_validate_terminal_args`, called by
    `update_curator_action` before any DB mutation. Pin that the
    helper is the central enforcement site for every invariant
    documented in threat-model boundary 5.
    """
    from src.polaris_graph.audit_ir.decision_telemetry import (
        _validate_terminal_args,
    )
    # All four terminal actions exercised through the helper.
    _validate_terminal_args(
        CuratorAction.ACCEPTED_AS_PROPOSED, "u", _INDUCTION_PAYLOAD, None,
    )
    _validate_terminal_args(
        CuratorAction.MODIFIED, "u", {"a": 1}, {"diff": 1},
    )
    _validate_terminal_args(
        CuratorAction.OVERRIDDEN, "u", {"a": 1}, None,
    )
    _validate_terminal_args(CuratorAction.REJECTED, "u", None, None)
    # Exhaustive negative cases.
    with pytest.raises(DecisionTelemetryError, match="CuratorAction"):
        _validate_terminal_args("rejected", "u", None, None)  # type: ignore[arg-type]
    with pytest.raises(DecisionTelemetryError, match="PENDING"):
        _validate_terminal_args(CuratorAction.PENDING, "u", None, None)
    with pytest.raises(DecisionTelemetryError, match="actor_user_id"):
        _validate_terminal_args(CuratorAction.REJECTED, "", None, None)
    with pytest.raises(DecisionTelemetryError, match="rejected"):
        _validate_terminal_args(
            CuratorAction.REJECTED, "u", {"x": 1}, None,
        )
    with pytest.raises(DecisionTelemetryError, match="rejected"):
        _validate_terminal_args(
            CuratorAction.REJECTED, "u", None, {"x": 1},
        )
    with pytest.raises(
        DecisionTelemetryError, match="accepted_as_proposed"
    ):
        _validate_terminal_args(
            CuratorAction.ACCEPTED_AS_PROPOSED, "u", {"x": 1}, {"d": 1},
        )
    with pytest.raises(
        DecisionTelemetryError, match="final_payload required"
    ):
        _validate_terminal_args(
            CuratorAction.ACCEPTED_AS_PROPOSED, "u", None, None,
        )
    with pytest.raises(
        DecisionTelemetryError, match="final_payload required"
    ):
        _validate_terminal_args(CuratorAction.MODIFIED, "u", None, None)
    with pytest.raises(
        DecisionTelemetryError, match="final_payload required"
    ):
        _validate_terminal_args(CuratorAction.OVERRIDDEN, "u", None, None)


def test_complex_payload_round_trips(store: DecisionRecordStore) -> None:
    """Nested dicts + lists + numbers + None survive the SQLite trip."""
    complex_payload = {
        "nested": {"a": [1, 2, 3], "b": {"c": "x"}},
        "list_of_dicts": [{"k": "v1"}, {"k": "v2"}],
        "number": 0.123,
        "null_field": None,
        "bool_field": True,
    }
    rec = store.record_decision(
        workspace_id="ws-a",
        decision_kind=DecisionKind.SCOPE_GATE,
        query="complex",
        proposed_payload=complex_payload,
        proposed_confidence=0.5,
    )
    fetched = store.get(rec.record_id, workspace_id="ws-a")
    assert fetched is not None
    assert fetched.proposed_payload == complex_payload
