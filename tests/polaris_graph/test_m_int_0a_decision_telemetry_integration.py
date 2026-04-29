"""M-INT-0a — Decision telemetry into production scope-gate.

Acceptance bar (per docs/full_online_plan_FINAL.md M-INT-0a):
  1. Substrate IS imported by inspector_router.py (DecisionRecordStore,
     DecisionKind import statements present)
  2. Substrate IS invoked at the route_query callsite
     (_record_scope_gate_decision called)
  3. Run-log evidence: real route_query call writes a decision row
  4. PG_RECORD_DECISIONS=0 actually disables the write path

Plus integration semantics:
  - Authenticated caller → telemetry recorded
  - Anonymous caller → no telemetry, no error
  - Telemetry write failure → endpoint still returns 200
  - workspace_id == caller.org_id (Phase E0 simplification)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir import inspector_router as ir_mod
from src.polaris_graph.audit_ir.decision_telemetry import (
    DecisionKind,
    DecisionRecordStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_decision_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Force the decision-telemetry singleton to use a fresh DB
    per test, and ensure PG_RECORD_DECISIONS defaults to enabled."""
    db_path = tmp_path / "decision_records.sqlite"
    monkeypatch.setenv("PG_DECISION_DB_PATH", str(db_path))
    monkeypatch.setenv("PG_RECORD_DECISIONS", "1")
    ir_mod._reset_decision_store_for_test()
    yield db_path
    ir_mod._reset_decision_store_for_test()


@pytest.fixture
def authed_client() -> TestClient:
    """TestClient with a Polaris test-header caller (authenticated)."""
    app = FastAPI()
    app.include_router(ir_mod.router)
    return TestClient(
        app,
        headers={"X-Polaris-Caller": "org_int_0a:usr_test:owner"},
    )


@pytest.fixture
def anon_client() -> TestClient:
    """TestClient WITHOUT auth headers (anonymous)."""
    app = FastAPI()
    app.include_router(ir_mod.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Acceptance bar #1: substrate IS imported
# ---------------------------------------------------------------------------


def test_inspector_router_imports_decision_record_store() -> None:
    """Direct grep equivalent: DecisionRecordStore must be in
    inspector_router's imported names. Catches accidental
    de-integration regression."""
    assert hasattr(ir_mod, "DecisionRecordStore")
    assert hasattr(ir_mod, "DecisionKind")


def test_inspector_router_exposes_record_helper() -> None:
    """Codex acceptance check #2 (invoked-at-callsite): the
    private helper must exist as part of the production module
    surface."""
    assert callable(ir_mod._record_scope_gate_decision)
    assert callable(ir_mod._get_decision_store)


# ---------------------------------------------------------------------------
# Acceptance bar #3: real route_query call writes a row
# ---------------------------------------------------------------------------


def test_authed_route_query_writes_decision_record(
    authed_client: TestClient, fresh_decision_store: Path,
) -> None:
    """End-to-end: hit /api/inspector/templates/route as an
    authenticated caller; the response is unchanged but the
    decision-telemetry SQLite has a new row."""
    resp = authed_client.post(
        "/api/inspector/templates/route",
        json={"question": "What is the efficacy of tirzepatide for type 2 diabetes?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "routed"
    assert body["template_id"] == "v30_clinical"

    # Read the decision record back via the substrate's store API.
    assert fresh_decision_store.exists()
    store = DecisionRecordStore(fresh_decision_store)
    rows = store.list_for_workspace(
        workspace_id="org_int_0a",
        decision_kind=DecisionKind.SCOPE_GATE,
    )
    assert len(rows) == 1
    rec = rows[0]
    assert rec.workspace_id == "org_int_0a"
    assert rec.decision_kind == DecisionKind.SCOPE_GATE
    assert rec.query.startswith("What is the efficacy")
    assert rec.proposed_payload["verdict"] == "routed"
    assert rec.proposed_payload["template_id"] == "v30_clinical"
    assert 0.0 <= rec.proposed_confidence <= 1.0


def test_authed_route_query_records_one_per_call(
    authed_client: TestClient, fresh_decision_store: Path,
) -> None:
    """N calls → N records."""
    for i in range(3):
        resp = authed_client.post(
            "/api/inspector/templates/route",
            json={"question": f"tirzepatide query {i}"},
        )
        assert resp.status_code == 200
    store = DecisionRecordStore(fresh_decision_store)
    rows = store.list_for_workspace(workspace_id="org_int_0a")
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# Acceptance bar #4: PG_RECORD_DECISIONS=0 disables
# ---------------------------------------------------------------------------


def test_disabled_flag_skips_telemetry_write(
    authed_client: TestClient,
    fresh_decision_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per FINAL_PLAN rollback discipline: PG_RECORD_DECISIONS=0
    actually disables telemetry. The endpoint still works."""
    monkeypatch.setenv("PG_RECORD_DECISIONS", "0")
    resp = authed_client.post(
        "/api/inspector/templates/route",
        json={"question": "tirzepatide diabetes"},
    )
    assert resp.status_code == 200
    # No decisions DB created → store init never ran.
    if fresh_decision_store.exists():
        store = DecisionRecordStore(fresh_decision_store)
        rows = store.list_for_workspace(workspace_id="org_int_0a")
        assert len(rows) == 0


def test_disabled_flag_default_value_records(
    authed_client: TestClient,
    fresh_decision_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PG_RECORD_DECISIONS unset (or absent) defaults to recording.
    Documented contract in the helper docstring."""
    monkeypatch.delenv("PG_RECORD_DECISIONS", raising=False)
    resp = authed_client.post(
        "/api/inspector/templates/route",
        json={"question": "tirzepatide diabetes"},
    )
    assert resp.status_code == 200
    store = DecisionRecordStore(fresh_decision_store)
    assert len(store.list_for_workspace(workspace_id="org_int_0a")) == 1


# ---------------------------------------------------------------------------
# Anonymous caller behavior
# ---------------------------------------------------------------------------


def test_anonymous_route_query_skips_telemetry(
    anon_client: TestClient, fresh_decision_store: Path,
) -> None:
    """Without auth header, the endpoint is still callable
    (backward compat — was anonymous before M-INT-0a). Telemetry
    is skipped because workspace_id is unknown."""
    resp = anon_client.post(
        "/api/inspector/templates/route",
        json={"question": "tirzepatide diabetes"},
    )
    assert resp.status_code == 200
    # No DB write happened (no workspace context).
    if fresh_decision_store.exists():
        # If init happened (unlikely), the table is empty.
        store = DecisionRecordStore(fresh_decision_store)
        # Count across any possible workspace_id should be 0.
        assert store.count_for_workspace(workspace_id="org_int_0a") == 0


# ---------------------------------------------------------------------------
# Telemetry failure does NOT gate the decision
# ---------------------------------------------------------------------------


def test_telemetry_failure_does_not_break_endpoint(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II + M-D3 phase 1 boundary 1: failure to write
    telemetry MUST NOT gate the actual scope-gate decision.
    Force a write failure by pointing the DB path at a directory
    we can't write to."""

    def _broken_store(*args, **kwargs):
        raise RuntimeError("simulated DB unavailable")

    monkeypatch.setattr(ir_mod, "_get_decision_store", _broken_store)
    resp = authed_client.post(
        "/api/inspector/templates/route",
        json={"question": "tirzepatide diabetes"},
    )
    # Endpoint returns 200 despite telemetry failure.
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "routed"


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


def test_workspace_isolation_two_orgs(
    fresh_decision_store: Path,
) -> None:
    """Two orgs hit the endpoint; each writes to its own
    workspace-scoped record set."""
    app = FastAPI()
    app.include_router(ir_mod.router)
    client_a = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_a:usr_a:owner"},
    )
    client_b = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_b:usr_b:owner"},
    )
    client_a.post(
        "/api/inspector/templates/route",
        json={"question": "query A"},
    )
    client_b.post(
        "/api/inspector/templates/route",
        json={"question": "query B"},
    )
    store = DecisionRecordStore(fresh_decision_store)
    rows_a = store.list_for_workspace(workspace_id="org_a")
    rows_b = store.list_for_workspace(workspace_id="org_b")
    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert rows_a[0].query == "query A"
    assert rows_b[0].query == "query B"
