"""M-INT-11 — M-24 customer support tickets endpoint.

Final integration milestone before LIVE/PROD phases. Ships
narrow CRUD: open ticket, list for caller's org, get one by id.
Assignment / resolve / close / message-append are deferred to
Phase F (admin UI flow).

Acceptance bar:
  1. Endpoints exist:
     - POST /api/inspector/support-tickets (open)
     - GET  /api/inspector/support-tickets (list for org)
     - GET  /api/inspector/support-tickets/{ticket_id}
  2. Wraps SupportTicketStore.{open_ticket, get_ticket,
     list_by_org}
  3. Cross-org isolation
  4. PG_USE_SUPPORT_TICKET_ENDPOINT=0 returns 404
  5. Authn required; member+ for write
  6. Category restricted to closed enum (billing/audit/
     integration/data_request/other)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _make_client(role: str = "owner") -> TestClient:
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(
        app,
        headers={"X-Polaris-Caller": f"org_default:usr_test:{role}"},
    )


def test_router_imports_support_ticket_substrates() -> None:
    router_mod = importlib.import_module(
        "src.polaris_graph.audit_ir.inspector_router"
    )
    assert hasattr(router_mod, "SupportTicketStore")
    assert hasattr(router_mod, "TicketCategory")
    assert hasattr(router_mod, "TicketPriority")
    assert hasattr(router_mod, "TicketStatus")
    assert hasattr(router_mod, "ticket_to_dict")
    assert hasattr(router_mod, "_get_support_ticket_store")


def test_open_ticket_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_SUPPORT_TICKET_DB_PATH", str(tmp_path / "tickets.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_support_ticket_store_for_test,
    )
    _reset_support_ticket_store_for_test()

    client = _make_client(role="member")
    response = client.post(
        "/api/inspector/support-tickets",
        json={
            "title": "Cannot enqueue audit run",
            "description": "Got a 500 when calling /api/inspector/jobs",
            "category": "audit",
            "priority": "high",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Cannot enqueue audit run"
    assert body["status"] == "open"
    ticket_id = body["ticket_id"]

    # Round-trip get
    r2 = client.get(f"/api/inspector/support-tickets/{ticket_id}")
    assert r2.status_code == 200

    # List
    r3 = client.get("/api/inspector/support-tickets")
    assert r3.status_code == 200
    assert len(r3.json()["tickets"]) == 1


def test_open_rejects_invalid_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_SUPPORT_TICKET_DB_PATH", str(tmp_path / "tickets.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_support_ticket_store_for_test,
    )
    _reset_support_ticket_store_for_test()

    client = _make_client(role="member")
    response = client.post(
        "/api/inspector/support-tickets",
        json={
            "title": "Test",
            "description": "Test description",
            "category": "nonexistent",
            "priority": "normal",
        },
    )
    assert response.status_code == 400


def test_viewer_role_cannot_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_SUPPORT_TICKET_DB_PATH", str(tmp_path / "tickets.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_support_ticket_store_for_test,
    )
    _reset_support_ticket_store_for_test()

    client = _make_client(role="viewer")
    response = client.post(
        "/api/inspector/support-tickets",
        json={
            "title": "Should fail",
            "description": "Test",
            "category": "other",
            "priority": "normal",
        },
    )
    assert response.status_code == 403


def test_get_unknown_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_SUPPORT_TICKET_DB_PATH", str(tmp_path / "tickets.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_support_ticket_store_for_test,
    )
    _reset_support_ticket_store_for_test()

    client = _make_client()
    response = client.get(
        "/api/inspector/support-tickets/nonexistent_id"
    )
    assert response.status_code == 404


def test_cross_org_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_SUPPORT_TICKET_DB_PATH", str(tmp_path / "tickets.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_support_ticket_store_for_test, router,
    )
    _reset_support_ticket_store_for_test()

    app = FastAPI()
    app.include_router(router)
    client_a = TestClient(
        app, headers={"X-Polaris-Caller": "org_a:usr_a:member"},
    )
    client_b = TestClient(
        app, headers={"X-Polaris-Caller": "org_b:usr_b:member"},
    )

    response = client_a.post(
        "/api/inspector/support-tickets",
        json={
            "title": "A's ticket",
            "description": "Private to org_a",
            "category": "billing",
            "priority": "normal",
        },
    )
    assert response.status_code == 201
    ticket_id = response.json()["ticket_id"]

    # org_b cannot see
    r = client_b.get(f"/api/inspector/support-tickets/{ticket_id}")
    assert r.status_code == 404

    r2 = client_b.get("/api/inspector/support-tickets")
    assert r2.status_code == 200
    assert r2.json()["tickets"] == []


def test_disabled_flag_returns_404_for_anonymous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "0")
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/inspector/support-tickets")
    assert response.status_code == 404


def test_endpoint_requires_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SUPPORT_TICKET_ENDPOINT", "1")
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/inspector/support-tickets")
    assert response.status_code in {401, 403}
