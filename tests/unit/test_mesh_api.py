"""
Unit tests for wiki mesh REST API (Unit 9).

Tests use FastAPI's TestClient (synchronous, no real server).
The store is injected via a test lifespan that points at a temp db.

Run:
    python -m pytest tests/unit/test_mesh_api.py -v
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.api.server import app
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───── helpers ─────

def _ref_vec(dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    arr[0] = 1.0
    return arr


# ───── fixtures ─────

@pytest.fixture
def client(tmp_path: Path):
    """TestClient with a temp store injected via app.state."""
    db_path = tmp_path / "test_api.db"
    store = MeshStore.open(db_path, check_same_thread=False)
    app.state.store = store
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    store.close()


@pytest.fixture
def seeded_client(tmp_path: Path):
    """TestClient with a workspace + source + claim pre-seeded."""
    db_path = tmp_path / "test_api_seeded.db"
    store = MeshStore.open(db_path, check_same_thread=False)
    ws_id = store.create_workspace(
        name="API Test WS",
        root_question="How do PFAS filters work?",
    )
    src_id = store.insert_source(
        workspace_id=ws_id,
        kind="web",
        filepath="api_test.md",
        content_hash="x" * 64,
        sig_authority=0.5,
        url="https://example.com/api-test",
        title="API Test Source",
        year=2024,
    )
    store.insert_claim(
        workspace_id=ws_id,
        source_page_id=src_id,
        statement="GAC removes 85% of PFOS in trials",
        direct_quote="GAC achieved 85% removal of PFOS",
        char_start=0, char_end=33,
        tier="GOLD", relevance_score=0.9,
        has_numeric=True,
        embedding=_ref_vec(),
    )
    app.state.store = store
    c = TestClient(app, raise_server_exceptions=True)
    yield c, ws_id
    store.close()


# ───── TestWorkspaces ─────

class TestCreateWorkspace:
    def test_creates_and_returns(self, client):
        resp = client.post("/workspaces", json={
            "name": "Test WS",
            "seed_question": "PFAS research",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test WS"
        assert data["id"].startswith("ws_")

    def test_without_seed(self, client):
        resp = client.post("/workspaces", json={"name": "Bare WS"})
        assert resp.status_code == 201


class TestListWorkspaces:
    def test_empty(self, client):
        resp = client.get("/workspaces")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_created(self, client):
        client.post("/workspaces", json={"name": "WS1"})
        client.post("/workspaces", json={"name": "WS2"})
        resp = client.get("/workspaces")
        assert resp.status_code == 200
        names = [ws["name"] for ws in resp.json()]
        assert "WS1" in names
        assert "WS2" in names


# ───── TestDryRun ─────

class TestDryRun:
    def test_returns_retrieval_result(self, seeded_client):
        client, ws_id = seeded_client
        resp = client.post(
            f"/workspaces/{ws_id}/ask/dry-run",
            json={"question": "How does GAC remove PFOS?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "gap_category" in data
        assert "total_claims" in data
        assert isinstance(data["top_claims"], list)

    def test_empty_workspace_returns_orthogonal(self, client):
        ws_resp = client.post("/workspaces", json={"name": "Empty"})
        ws_id = ws_resp.json()["id"]
        resp = client.post(
            f"/workspaces/{ws_id}/ask/dry-run",
            json={"question": "Anything"},
        )
        assert resp.status_code == 200
        assert resp.json()["gap_category"] == "ORTHOGONAL"
        assert resp.json()["total_claims"] == 0

    def test_invalid_workspace_returns_400(self, client):
        resp = client.post(
            "/workspaces/ws_fake/ask/dry-run",
            json={"question": "test"},
        )
        assert resp.status_code == 400


# ───── TestStats ─────

class TestStats:
    def test_returns_stats(self, seeded_client):
        client, ws_id = seeded_client
        resp = client.get(f"/workspaces/{ws_id}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "API Test WS"
        assert data["gold_claims"] >= 1

    def test_invalid_workspace_returns_404(self, client):
        resp = client.get("/workspaces/ws_fake/stats")
        assert resp.status_code == 404


# ───── TestQuarantinedEntities ─────

class TestQuarantinedEntities:
    def test_none_quarantined(self, seeded_client):
        client, ws_id = seeded_client
        resp = client.get(f"/workspaces/{ws_id}/entities/quarantined")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_shows_quarantined(self, seeded_client):
        client, ws_id = seeded_client
        store = app.state.store
        store.insert_entity(
            workspace_id=ws_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=["pfos"],
            confidence=0.5,
            user_confirmed=False,
            embedding=_ref_vec(),
        )
        resp = client.get(f"/workspaces/{ws_id}/entities/quarantined")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["quarantined"][0]["canonical_name"] == "PFOS"

    def test_invalid_workspace_returns_404(self, client):
        resp = client.get("/workspaces/ws_fake/entities/quarantined")
        assert resp.status_code == 404
