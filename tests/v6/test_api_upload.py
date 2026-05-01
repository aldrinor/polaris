"""Tests for the F3b /upload endpoint."""

from __future__ import annotations

import io

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def _txt_upload(content: bytes = b"Sample text content for chunking.\n") -> dict:
    return {"file": ("sample.txt", io.BytesIO(content), "text/plain")}


def test_upload_text_file_returns_document_id(client):
    response = client.post(
        "/upload",
        files=_txt_upload(),
        data={"classification": "PUBLIC_SYNTHETIC"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "sample.txt"
    assert body["classification"] == "PUBLIC_SYNTHETIC"
    assert body["parse_status"] == "completed"
    assert len(body["chunk_preview"]) >= 1


def test_upload_default_classification_is_unknown(client):
    response = client.post("/upload", files=_txt_upload())
    assert response.status_code == 201
    assert response.json()["classification"] == "UNKNOWN"


def test_upload_pdf_returns_queued_status(client):
    fake_pdf = b"%PDF-1.4 fake pdf header bytes"
    response = client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["parse_status"] == "queued"
    assert body["chunk_preview"] == []


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/upload",
        files={"file": ("archive.zip", io.BytesIO(b"PK"), "application/zip")},
    )
    assert response.status_code == 415


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/upload",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 422


def test_upload_round_trip_via_get(client):
    create = client.post(
        "/upload",
        files=_txt_upload(b"alpha beta gamma delta"),
        data={"classification": "CAN_REAL"},
    )
    document_id = create.json()["document_id"]

    fetch = client.get(f"/upload/{document_id}")
    assert fetch.status_code == 200
    assert fetch.json()["classification"] == "CAN_REAL"


def test_upload_get_404_for_unknown(client):
    response = client.get("/upload/does_not_exist")
    assert response.status_code == 404
