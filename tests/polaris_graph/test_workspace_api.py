"""Tests for the M-11 workspace + upload HTTP endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir.inspector_router import (
    _set_workspace_files_root_for_tests,
    _set_workspace_store_for_tests,
    router,
)
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


@pytest.fixture
def client_and_store(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    _set_workspace_store_for_tests(store)
    files_root = tmp_path / "files"
    _set_workspace_files_root_for_tests(files_root)
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app, headers={"X-Polaris-Caller": "org_default:usr_test:owner"}), store, files_root
    _set_workspace_store_for_tests(None)
    _set_workspace_files_root_for_tests(None)


# ---------------------------------------------------------------------------
# Workspace endpoints
# ---------------------------------------------------------------------------


def test_create_workspace_endpoint(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.post("/api/inspector/workspaces", json={"name": "Beta"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Beta"
    assert body["workspace_id"].startswith("ws_")


def test_create_workspace_with_explicit_max_docs(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.post(
        "/api/inspector/workspaces", json={"name": "Tiny", "max_docs": 3}
    )
    assert resp.json()["max_docs"] == 3


def test_create_workspace_rejects_empty_name(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.post("/api/inspector/workspaces", json={"name": ""})
    assert resp.status_code == 400


def test_list_and_get_workspace(client_and_store) -> None:
    client, _, _ = client_and_store
    a = client.post("/api/inspector/workspaces", json={"name": "A"}).json()
    b = client.post("/api/inspector/workspaces", json={"name": "B"}).json()
    listed = client.get("/api/inspector/workspaces").json()
    ids = [w["workspace_id"] for w in listed["workspaces"]]
    assert a["workspace_id"] in ids and b["workspace_id"] in ids
    fetched = client.get(f"/api/inspector/workspaces/{a['workspace_id']}").json()
    assert fetched["name"] == "A"


def test_get_unknown_workspace_returns_404(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.get("/api/inspector/workspaces/ws_nope")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------


def test_upload_text_file_parses_to_chunks(client_and_store) -> None:
    client, store, _ = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Up"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("notes.txt", b"hello world\nsecond line", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parser_status"] == "parsed"
    assert body["filename"] == "notes.txt"
    assert body["size_bytes"] > 0
    chunks = client.get(
        f"/api/inspector/uploads/{body['upload_id']}/chunks"
    ).json()["chunks"]
    assert len(chunks) >= 1
    for c in chunks:
        assert c["provenance"]["kind"] == "text_span"
        assert c["provenance"]["upload_id"] == body["upload_id"]


def test_upload_pdf_lands_as_failed_phase_b(client_and_store) -> None:
    """Phase B PdfParser stub must surface 'not yet supported'
    rather than silently returning an empty parse."""
    client, _, _ = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "PdfTry"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("doc.pdf", b"%PDF-1.4 stub", "application/pdf")},
    )
    body = resp.json()
    assert body["parser_status"] == "failed"
    assert body["parser_error"] is not None
    assert "not yet supported" in body["parser_error"].lower()


def test_upload_unsupported_type_stays_pending(client_and_store) -> None:
    """No parser → status stays pending; operator decides."""
    client, _, _ = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Other"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("v.mp4", b"\x00\x01stub-video", "video/mp4")},
    )
    body = resp.json()
    assert body["parser_status"] == "pending"


def test_upload_to_unknown_workspace_returns_404(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.post(
        "/api/inspector/workspaces/ws_nope/uploads",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 404


def test_upload_at_cap_returns_409(client_and_store) -> None:
    """Bounded enforcement at upload time returns 409 (Conflict)."""
    client, _, _ = client_and_store
    ws = client.post(
        "/api/inspector/workspaces", json={"name": "Cap", "max_docs": 1}
    ).json()
    client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("a.txt", b"hi", "text/plain")},
    )
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("b.txt", b"hi", "text/plain")},
    )
    assert resp.status_code == 409
    assert "at cap" in resp.json()["detail"]


def test_list_uploads_excludes_deleted_by_default(client_and_store) -> None:
    client, _, _ = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Soft"}).json()
    a = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("a.txt", b"a", "text/plain")},
    ).json()
    b = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("b.txt", b"b", "text/plain")},
    ).json()
    client.delete(f"/api/inspector/uploads/{a['upload_id']}")
    listed = client.get(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads"
    ).json()["uploads"]
    assert {u["upload_id"] for u in listed} == {b["upload_id"]}
    listed_all = client.get(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        params={"include_deleted": True},
    ).json()["uploads"]
    assert {u["upload_id"] for u in listed_all} == {a["upload_id"], b["upload_id"]}


def test_delete_unknown_upload_returns_404(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.delete("/api/inspector/uploads/up_nope")
    assert resp.status_code == 404


def test_get_unknown_upload_returns_404(client_and_store) -> None:
    client, _, _ = client_and_store
    resp = client.get("/api/inspector/uploads/up_nope")
    assert resp.status_code == 404


def test_uploaded_file_bytes_persist_on_disk(client_and_store) -> None:
    """Sanity: the upload pipeline actually writes bytes to disk."""
    client, _, files_root = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Disk"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("n.txt", b"persisted bytes", "text/plain")},
    ).json()
    storage_path = Path(resp["storage_path"])
    assert storage_path.exists()
    assert storage_path.read_bytes() == b"persisted bytes"


# ---------------------------------------------------------------------------
# Codex M-11 review regression: filename sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_name,expected_basename",
    [
        # Path traversal attempts.
        ("../../etc/passwd", "passwd"),
        ("..\\..\\..\\windows\\system32\\evil.txt", "evil.txt"),
        # Absolute paths.
        ("/tmp/abs.txt", "abs.txt"),
        ("/etc/passwd", "passwd"),
        ("C:/abs2.txt", "abs2.txt"),
        ("C:\\abs3.txt", "abs3.txt"),
        # Nested paths.
        ("subdir/name.txt", "name.txt"),
        ("a/b/c/deep.txt", "deep.txt"),
        # Mixed separators.
        ("foo/bar\\baz.txt", "baz.txt"),
        # NUL byte injection. FastAPI's multipart layer URL-encodes
        # literal NUL to "%00" before our sanitizer sees it; the
        # sanitizer strips both forms.
        ("clean%00.txt", "clean.txt"),
        # Dot-only fall back to "upload".
        (".", "upload"),
        ("..", "upload"),
    ],
)
def test_upload_filename_sanitization(
    client_and_store, raw_name: str, expected_basename: str
) -> None:
    """Codex M-11 review regression: filenames are reduced to a
    sanitized basename. Path traversal, absolute paths, drive
    letters, nested paths, and NUL bytes must all be neutralized
    BEFORE the file hits disk."""
    client, _, files_root = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Sanitize"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": (raw_name, b"x", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == expected_basename
    storage_path = Path(body["storage_path"])
    # Must be inside the workspace root.
    storage_path.resolve().relative_to(files_root.resolve())
    # Must end with the sanitized basename.
    assert storage_path.name == expected_basename


def test_upload_filename_with_traversal_does_not_escape_root(client_and_store) -> None:
    """Codex M-11 review regression: even with malicious traversal
    attempts, the resolved storage path stays inside the workspace
    files root (defense in depth)."""
    client, _, files_root = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Defense"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("../../escape.txt", b"x", "text/plain")},
    ).json()
    storage_path = Path(resp["storage_path"]).resolve()
    files_root_resolved = files_root.resolve()
    # Verify with relative_to — raises if outside.
    storage_path.relative_to(files_root_resolved)
    # The sanitized basename "escape.txt" is what's on disk.
    assert storage_path.name == "escape.txt"


def test_upload_csv_lands_as_pending_not_routed_through_text_parser(
    client_and_store,
) -> None:
    """Codex M-11 review regression: TextParser narrowed to plain
    text only. CSV uploads now stay 'pending' (no parser claims
    them) instead of being silently flattened to TextSpan."""
    client, _, _ = client_and_store
    ws = client.post("/api/inspector/workspaces", json={"name": "Csv"}).json()
    resp = client.post(
        f"/api/inspector/workspaces/{ws['workspace_id']}/uploads",
        files={"file": ("data.csv", b"a,b,c\n1,2,3", "text/csv")},
    ).json()
    assert resp["parser_status"] == "pending"
