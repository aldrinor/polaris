"""M-INT-9 — M-26 contract drafting endpoints in inspector_router.

Acceptance bar:
  1. Endpoints exist:
     - GET    /api/inspector/contract-drafts (list for caller's org)
     - POST   /api/inspector/contract-drafts (create new draft)
     - GET    /api/inspector/contract-drafts/{draft_id} (read one)
  2. Wraps ContractDraftStore.{create_draft, get_draft,
     list_drafts_for_org}
  3. Org-scoping: caller.org_id is enforced (cross-tenant isolation)
  4. PG_USE_CONTRACT_DRAFT_ENDPOINT=0 returns 404 (rollback)
  5. AuthZ: requires authenticated caller (M-15b retrofit)
  6. Member role required for write (POST), viewer for reads
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


def test_router_imports_contract_draft_substrates() -> None:
    router_mod = importlib.import_module(
        "src.polaris_graph.audit_ir.inspector_router"
    )
    assert hasattr(router_mod, "ContractDraftStore")
    assert hasattr(router_mod, "ContractKind")
    assert hasattr(router_mod, "ContractDraftStatus")
    assert hasattr(router_mod, "draft_to_dict")
    assert hasattr(router_mod, "_get_contract_draft_store")


def test_list_drafts_returns_empty_for_new_org(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_CONTRACT_DRAFT_DB_PATH", str(tmp_path / "drafts.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_contract_draft_store_for_test,
    )
    _reset_contract_draft_store_for_test()

    client = _make_client()
    response = client.get("/api/inspector/contract-drafts")
    assert response.status_code == 200
    body = response.json()
    assert "drafts" in body
    assert body["drafts"] == []


def test_create_draft_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_CONTRACT_DRAFT_DB_PATH", str(tmp_path / "drafts.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_contract_draft_store_for_test,
    )
    _reset_contract_draft_store_for_test()

    client = _make_client()
    response = client.post(
        "/api/inspector/contract-drafts",
        json={
            "audit_run_id": "RUN_TEST_123",
            "kind": "dpa",
            "title": "Test DPA",
            "counterparty_name": "Acme Corp",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "draft_id" in body
    draft_id = body["draft_id"]
    assert body["org_id"] == "org_default"
    assert body["title"] == "Test DPA"
    assert body["status"] == "draft"

    # GET it back
    response2 = client.get(f"/api/inspector/contract-drafts/{draft_id}")
    assert response2.status_code == 200
    body2 = response2.json()
    assert body2["draft_id"] == draft_id
    assert body2["title"] == "Test DPA"

    # LIST should have it
    response3 = client.get("/api/inspector/contract-drafts")
    assert response3.status_code == 200
    body3 = response3.json()
    assert len(body3["drafts"]) == 1
    assert body3["drafts"][0]["draft_id"] == draft_id


def test_create_draft_invalid_kind_returns_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_CONTRACT_DRAFT_DB_PATH", str(tmp_path / "drafts.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_contract_draft_store_for_test,
    )
    _reset_contract_draft_store_for_test()

    client = _make_client()
    response = client.post(
        "/api/inspector/contract-drafts",
        json={
            "audit_run_id": "RUN_TEST_123",
            "kind": "nonexistent_kind",
            "title": "Test",
            "counterparty_name": "Acme",
        },
    )
    assert response.status_code == 400


def test_get_draft_unknown_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_CONTRACT_DRAFT_DB_PATH", str(tmp_path / "drafts.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_contract_draft_store_for_test,
    )
    _reset_contract_draft_store_for_test()

    client = _make_client()
    response = client.get("/api/inspector/contract-drafts/nonexistent_id")
    assert response.status_code == 404


def test_cross_org_cannot_see_other_orgs_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Org isolation: org_a creates a draft; org_b GET returns 404."""
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_CONTRACT_DRAFT_DB_PATH", str(tmp_path / "drafts.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_contract_draft_store_for_test, router,
    )
    _reset_contract_draft_store_for_test()

    app = FastAPI()
    app.include_router(router)
    client_a = TestClient(
        app, headers={"X-Polaris-Caller": "org_a:usr_a:owner"},
    )
    client_b = TestClient(
        app, headers={"X-Polaris-Caller": "org_b:usr_b:owner"},
    )

    response = client_a.post(
        "/api/inspector/contract-drafts",
        json={
            "audit_run_id": "RUN_A",
            "kind": "dpa",
            "title": "A's DPA",
            "counterparty_name": "Acme",
        },
    )
    assert response.status_code == 201
    draft_id = response.json()["draft_id"]

    # org_b should NOT see it via direct GET
    response_b_get = client_b.get(
        f"/api/inspector/contract-drafts/{draft_id}",
    )
    assert response_b_get.status_code == 404

    # org_b should see empty list
    response_b_list = client_b.get("/api/inspector/contract-drafts")
    assert response_b_list.status_code == 200
    assert response_b_list.json()["drafts"] == []


def test_disabled_flag_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "0")
    client = _make_client()
    response = client.get("/api/inspector/contract-drafts")
    assert response.status_code == 404


def test_endpoint_requires_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No X-Polaris-Caller header → rejected."""
    monkeypatch.setenv("PG_USE_CONTRACT_DRAFT_ENDPOINT", "1")
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/inspector/contract-drafts")
    assert response.status_code in {401, 403}
