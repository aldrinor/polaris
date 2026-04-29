"""M-INT-10 — M-25 Drive connector v2 (narrow) endpoints.

Per FINAL_PLAN: NARROW scope — Drive only (sharepoint/confluence
deferred). Endpoints expose register/list/get for CorpusSource;
approve/revoke require admin role.

Acceptance bar:
  1. Endpoints exist:
     - POST /api/inspector/private-corpus-sources (register)
     - GET  /api/inspector/private-corpus-sources (list)
     - GET  /api/inspector/private-corpus-sources/{source_id}
  2. Wraps PrivateCorpusSyncStore.register_source +
     list_sources_for_workspace + get_source
  3. Cross-org isolation
  4. PG_USE_DRIVE_CONNECTOR_ENDPOINT=0 returns 404
  5. Authn required; member+ for register
  6. Connector restricted to GOOGLE_DRIVE only at endpoint level
     (per FINAL_PLAN narrow scope)
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


def test_router_imports_drive_connector_substrates() -> None:
    router_mod = importlib.import_module(
        "src.polaris_graph.audit_ir.inspector_router"
    )
    assert hasattr(router_mod, "PrivateCorpusSyncStore")
    assert hasattr(router_mod, "SourceConnector")
    assert hasattr(router_mod, "SourceStatus")
    assert hasattr(router_mod, "source_to_dict")
    assert hasattr(router_mod, "_get_private_corpus_sync_store")


def test_register_drive_source_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client(role="member")
    response = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_test",
            "name": "Engineering Drive",
            "external_uri": "1abcDriveFolderId123456_AAA",
            "credential_ref": "vault://secrets/drive-key",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["connector"] == "google_drive"  # auto-set by endpoint
    assert body["status"] == "pending"  # awaits admin approval
    source_id = body["source_id"]

    # GET round-trip
    response2 = client.get(
        f"/api/inspector/private-corpus-sources/{source_id}"
    )
    assert response2.status_code == 200

    # LIST should have it (workspace-scoped)
    response3 = client.get(
        "/api/inspector/private-corpus-sources?workspace_id=ws_test"
    )
    assert response3.status_code == 200
    body3 = response3.json()
    assert len(body3["sources"]) == 1


def test_register_rejects_non_drive_connector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per FINAL_PLAN narrow scope: only Drive shipped in v1.
    Codex round-1 v2: extra='forbid' on Pydantic model + URL/path
    rejection on external_uri. Mislabeled SharePoint URLs MUST
    be rejected, not silently relabeled."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client(role="member")
    # Connector field in body → 422 (extra='forbid')
    response = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_test",
            "name": "SharePoint test",
            "external_uri": "https://contoso.sharepoint.com",
            "credential_ref": "vault://sp-key",
            "connector": "sharepoint",
        },
    )
    assert response.status_code == 422


def test_register_rejects_url_external_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 MEDIUM: URL-shaped external_uri MUST be
    rejected. v1 silently accepted SharePoint URL as
    connector='google_drive', mislabeling the source. v2 validates
    Drive folder ID shape at endpoint."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client(role="member")
    response = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_test",
            "name": "SharePoint mislabel",
            "external_uri": "https://contoso.sharepoint.com/sites/eng",
            "credential_ref": "vault://sp-key",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert "Drive folder ID" in body["detail"]


def test_register_rejects_short_external_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive folder IDs are 20+ chars; reject obviously-short
    inputs (less than 20 chars) at the endpoint."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client(role="member")
    response = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_test",
            "name": "Too short",
            "external_uri": "abc123",
            "credential_ref": "vault://test",
        },
    )
    assert response.status_code == 400


def test_list_empty_workspace_id_returns_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 LOW: empty workspace_id (?workspace_id=)
    must be 400, not silently 200 with empty list. Omitting the
    param entirely still returns []."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client()

    # Omitted query param → 200 + []
    r1 = client.get("/api/inspector/private-corpus-sources")
    assert r1.status_code == 200
    assert r1.json()["sources"] == []

    # Explicitly empty query param → 400
    r2 = client.get("/api/inspector/private-corpus-sources?workspace_id=")
    assert r2.status_code == 400
    body = r2.json()
    assert "non-empty" in body["detail"]

    # Whitespace-only → 400
    r3 = client.get(
        "/api/inspector/private-corpus-sources?workspace_id=%20%20%20"
    )
    assert r3.status_code == 400


def test_viewer_role_cannot_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write requires member+ role."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client(role="viewer")
    response = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_test",
            "name": "Should fail",
            "external_uri": "1xyzFolderId12345678_BBB",
            "credential_ref": "vault://test",
        },
    )
    assert response.status_code == 403


def test_get_source_unknown_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client()
    response = client.get(
        "/api/inspector/private-corpus-sources/nonexistent_id"
    )
    assert response.status_code == 404


def test_cross_org_cannot_see_other_orgs_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test, router,
    )
    _reset_private_corpus_sync_store_for_test()

    app = FastAPI()
    app.include_router(router)
    client_a = TestClient(
        app, headers={"X-Polaris-Caller": "org_a:usr_a:member"},
    )
    client_b = TestClient(
        app, headers={"X-Polaris-Caller": "org_b:usr_b:member"},
    )

    response = client_a.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_a",
            "name": "A's Drive",
            "external_uri": "1aaaaCrossOrgFolder123_CCC",
            "credential_ref": "vault://a",
        },
    )
    assert response.status_code == 201
    source_id = response.json()["source_id"]

    # org_b GET → 404
    r = client_b.get(
        f"/api/inspector/private-corpus-sources/{source_id}"
    )
    assert r.status_code == 404

    # org_b LIST workspace_id=ws_a → empty (workspace scoped + org gate)
    r2 = client_b.get(
        "/api/inspector/private-corpus-sources?workspace_id=ws_a"
    )
    assert r2.status_code == 200
    assert r2.json()["sources"] == []


def test_disabled_flag_returns_404_for_anonymous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag check runs before auth dep."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "0")
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)  # No header
    response = client.get("/api/inspector/private-corpus-sources")
    assert response.status_code == 404


def test_endpoint_requires_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/inspector/private-corpus-sources")
    assert response.status_code in {401, 403}


def test_workspace_id_normalization_consistent_post_vs_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-2 LOW: POST stripped workspace_id (substrate
    .strip()) but GET passed raw text through. v3 strips at
    endpoint on GET so '  ws_test  ' on POST is findable via
    '%20%20ws_test%20%20' on GET (or any whitespace-padded form)."""
    monkeypatch.setenv("PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1")
    monkeypatch.setenv(
        "PG_PRIVATE_CORPUS_DB_PATH", str(tmp_path / "corpus.sqlite"),
    )
    from src.polaris_graph.audit_ir.inspector_router import (
        _reset_private_corpus_sync_store_for_test,
    )
    _reset_private_corpus_sync_store_for_test()

    client = _make_client(role="member")

    # POST with padded workspace_id — substrate strips, stores "ws_pad".
    r_post = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "  ws_pad  ",
            "name": "Padded test",
            "external_uri": "1abcDriveFolderId123456_AAA",
            "credential_ref": "vault://test",
        },
    )
    assert r_post.status_code == 201
    assert r_post.json()["workspace_id"] == "ws_pad"

    # GET with same padded workspace_id MUST find it.
    r_get_padded = client.get(
        "/api/inspector/private-corpus-sources?workspace_id=%20%20ws_pad%20%20"
    )
    assert r_get_padded.status_code == 200
    body = r_get_padded.json()
    assert len(body["sources"]) == 1, (
        f"M-INT-10 v3: padded workspace_id on GET should find the "
        f"posted source; got {body!r}"
    )

    # GET with stripped workspace_id should also find it.
    r_get_stripped = client.get(
        "/api/inspector/private-corpus-sources?workspace_id=ws_pad"
    )
    assert r_get_stripped.status_code == 200
    assert len(r_get_stripped.json()["sources"]) == 1
