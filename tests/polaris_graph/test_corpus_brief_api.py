"""Tests for the M-12 brief HTTP endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir.corpus_retriever import RetrievedChunk
from src.polaris_graph.audit_ir.inspector_router import (
    _set_brief_llm_for_tests,
    _set_workspace_files_root_for_tests,
    _set_workspace_store_for_tests,
    router,
)
from src.polaris_graph.audit_ir.provenance import TextSpan, to_dict
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


class FakeLlm:
    def __init__(self, paragraphs: list[dict[str, Any]] | None = None) -> None:
        self.paragraphs = paragraphs or []

    def draft_brief(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> list[dict[str, Any]]:
        return self.paragraphs


@pytest.fixture
def client_with_corpus(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    files_root = tmp_path / "files"
    _set_workspace_store_for_tests(store)
    _set_workspace_files_root_for_tests(files_root)
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app), store
    _set_workspace_store_for_tests(None)
    _set_workspace_files_root_for_tests(None)
    _set_brief_llm_for_tests(None)


def _seed_workspace(store: WorkspaceStore) -> tuple[str, str]:
    ws = store.create_workspace("ApiBrief", max_docs=5)
    up = store.upload_file(
        ws.workspace_id, "diabetes.txt", "text/plain", 100, "/p/d",
    )
    store.transition_parser_status(up.upload_id, "parsing")
    store.insert_chunks(up.upload_id, [
        ("Tirzepatide for type 2 diabetes shows efficacy in trials.",
         to_dict(TextSpan(up.upload_id, 0, 60))),
    ])
    store.transition_parser_status(up.upload_id, "parsed")
    return ws.workspace_id, up.upload_id


def test_brief_endpoint_returns_supported_paragraph(client_with_corpus) -> None:
    client, store = client_with_corpus
    ws_id, _ = _seed_workspace(store)
    # Find the chunk_id we'll reference.
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes efficacy")
    cid = chunks[0].chunk_id
    _set_brief_llm_for_tests(FakeLlm(paragraphs=[
        {"claim": "Tirzepatide is effective.", "citations": [{"chunk_id": cid}]},
    ]))

    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={"question": "tirzepatide diabetes efficacy"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == ws_id
    assert body["question"] == "tirzepatide diabetes efficacy"
    assert len(body["paragraphs"]) == 1
    p = body["paragraphs"][0]
    assert p["support_status"] == "supported"
    assert p["claim"] == "Tirzepatide is effective."
    assert len(p["citations"]) == 1
    assert p["citations"][0]["chunk_id"] == cid


def test_brief_endpoint_returns_insufficient_support_when_no_retrieval(
    client_with_corpus,
) -> None:
    client, store = client_with_corpus
    ws_id, _ = _seed_workspace(store)
    _set_brief_llm_for_tests(FakeLlm())  # never called

    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={"question": "blockchain governance smart contracts"},
    )
    body = resp.json()
    assert len(body["paragraphs"]) == 1
    assert body["paragraphs"][0]["support_status"] == "insufficient_support"
    assert body["paragraphs"][0]["citations"] == []


def test_brief_endpoint_unknown_workspace_returns_404(client_with_corpus) -> None:
    client, _ = client_with_corpus
    _set_brief_llm_for_tests(FakeLlm())
    resp = client.post(
        "/api/inspector/workspaces/ws_missing/brief",
        json={"question": "tirzepatide"},
    )
    assert resp.status_code == 404


def test_brief_endpoint_validates_question_required(client_with_corpus) -> None:
    client, store = client_with_corpus
    ws_id, _ = _seed_workspace(store)
    _set_brief_llm_for_tests(FakeLlm())
    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={},  # missing question
    )
    assert resp.status_code == 422


def test_brief_endpoint_validates_top_k_bounds(client_with_corpus) -> None:
    client, store = client_with_corpus
    ws_id, _ = _seed_workspace(store)
    _set_brief_llm_for_tests(FakeLlm())
    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={"question": "x", "top_k": 0},  # below ge=1
    )
    assert resp.status_code == 422
    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={"question": "x", "top_k": 999},  # above le=50
    )
    assert resp.status_code == 422


def test_brief_endpoint_drops_fabricated_citations(client_with_corpus) -> None:
    client, store = client_with_corpus
    ws_id, _ = _seed_workspace(store)
    _set_brief_llm_for_tests(FakeLlm(paragraphs=[
        {"claim": "Made up.", "citations": [{"chunk_id": "ck_nope"}]},
    ]))
    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={"question": "tirzepatide diabetes"},
    )
    body = resp.json()
    assert body["paragraphs"][0]["support_status"] == "insufficient_support"


def test_brief_endpoint_excludes_chunks_from_deleted_uploads(
    client_with_corpus,
) -> None:
    """End-to-end: a chunk in a soft-deleted upload must not be a
    valid citation target — even if the LLM somehow returned its
    chunk_id, the brief drops it."""
    client, store = client_with_corpus
    ws_id, _ = _seed_workspace(store)
    deleted_up = store.upload_file(
        ws_id, "deleted.txt", "text/plain", 50, "/p/del",
    )
    store.transition_parser_status(deleted_up.upload_id, "parsing")
    store.insert_chunks(deleted_up.upload_id, [
        ("Tirzepatide diabetes hidden.",
         to_dict(TextSpan(deleted_up.upload_id, 0, 30))),
    ])
    store.transition_parser_status(deleted_up.upload_id, "parsed")
    deleted_chunk_id = store.list_chunks(deleted_up.upload_id)[0]["chunk_id"]
    store.soft_delete_upload(deleted_up.upload_id)

    _set_brief_llm_for_tests(FakeLlm(paragraphs=[
        {"claim": "Quoting deleted.", "citations": [
            {"chunk_id": deleted_chunk_id},
        ]},
    ]))

    resp = client.post(
        f"/api/inspector/workspaces/{ws_id}/brief",
        json={"question": "tirzepatide diabetes"},
    )
    body = resp.json()
    # The deleted-chunk citation is fabricated relative to the
    # retrieval-eligible set, so the validator drops the paragraph.
    assert body["paragraphs"][0]["support_status"] == "insufficient_support"
