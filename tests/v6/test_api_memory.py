"""Tests for F14 workspace memory HTTP endpoints."""

from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app
    from polaris_v6.api import memory as memory_mod
    from polaris_v6.memory.sqlite_store import SqliteWorkspaceMemoryStore

    app = create_app()
    # I-rdy-012 (#508): isolate each API test on a fresh SQLite DB so the
    # durable workspace-memory store does not accumulate fixed-workspace
    # rows across repeated runs (Codex brief-iter-1 P2).
    monkeypatch.setattr(
        memory_mod,
        "_store",
        SqliteWorkspaceMemoryStore(path=str(tmp_path / "api_memory.sqlite")),
    )
    return TestClient(app)


def test_remember_then_recall(client):
    create = client.post(
        "/workspaces/ws_test/memory",
        json={
            "kind": "domain_assumption",
            "content": "User prefers CMHC for Canadian housing data analysis.",
        },
    )
    assert create.status_code == 201

    recall = client.post(
        "/workspaces/ws_test/memory/recall",
        json={"query_text": "CMHC housing"},
    )
    assert recall.status_code == 200
    results = recall.json()
    assert len(results) >= 1
    assert "score" in results[0]


def test_workspace_isolation_via_http(client):
    client.post(
        "/workspaces/ws_alpha/memory",
        json={
            "kind": "user_preference",
            "content": "Alpha workspace prefers detailed citations.",
        },
    )
    recall = client.post(
        "/workspaces/ws_beta/memory/recall",
        json={"query_text": "alpha prefers"},
    )
    assert recall.status_code == 200
    assert recall.json() == []


def test_forget(client):
    create = client.post(
        "/workspaces/ws_forget/memory",
        json={
            "kind": "user_preference",
            "content": "Forget this entry after the test runs.",
        },
    )
    entry_id = create.json()["entry_id"]
    delete = client.delete(f"/workspaces/ws_forget/memory/{entry_id}")
    assert delete.status_code == 204
    delete_again = client.delete(f"/workspaces/ws_forget/memory/{entry_id}")
    assert delete_again.status_code == 404


def test_list_workspace(client):
    for i in range(3):
        client.post(
            "/workspaces/ws_listing/memory",
            json={
                "kind": "prior_run_summary",
                "content": f"Run {i} summary about housing supply analysis.",
            },
        )
    listing = client.get("/workspaces/ws_listing/memory")
    assert listing.status_code == 200
    assert len(listing.json()) == 3


def test_invalid_kind_rejected(client):
    response = client.post(
        "/workspaces/ws_x/memory",
        json={"kind": "not_a_real_kind", "content": "test content here"},
    )
    assert response.status_code == 422


def test_short_content_rejected(client):
    response = client.post(
        "/workspaces/ws_x/memory",
        json={"kind": "user_preference", "content": "x"},
    )
    assert response.status_code == 422
