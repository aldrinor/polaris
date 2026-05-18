"""Tests for I-rdy-010 (#506) — uploaded-document grounding.

Covers the four units the async worker uses to ground a run on uploaded
documents:
* `chunk_text` / `get_upload_record` — upload-content resolution helpers.
* `_resolve_uploaded_documents` (POST /runs) — resolves document_ids →
  content before insert/enqueue; fails loud on a missing or unparsed id.
* `partition_uploads_by_sovereignty` — splits uploads into egress-allowed
  (PUBLIC_SYNTHETIC) vs blocked (CLIENT/CAN_REAL/PRIVATE/UNKNOWN).
* `build_upload_evidence_rows` — turns cleared uploads into pipeline-A
  evidence dict rows; rejects any forbidden classification.

The sovereignty router runs for real (per CLAUDE.md §9.4 — do not mock the
policy under test); only the in-memory upload table is populated directly.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from polaris_v6.adapters.upload_evidence import (
    UploadSovereigntyError,
    build_upload_evidence_rows,
    partition_uploads_by_sovereignty,
)
from polaris_v6.api import upload as upload_mod
from polaris_v6.api.runs import _resolve_uploaded_documents
from polaris_v6.api.upload import (
    MAX_GROUNDING_CHUNKS,
    UploadResponse,
    chunk_text,
    get_upload_record,
)


def _make_upload(
    document_id: str,
    *,
    classification: str = "PUBLIC_SYNTHETIC",
    content: str = "some uploaded text",
    filename: str = "doc.md",
) -> UploadResponse:
    return UploadResponse(
        document_id=document_id,
        filename=filename,
        bytes=len(content.encode()),
        sha256="0" * 64,
        classification=classification,
        parse_status="completed" if content else "queued",
        chunk_preview=[content[:280]] if content else [],
        content=content,
        html="",
    )


@pytest.fixture(autouse=True)
def _clean_upload_table():
    upload_mod._UPLOAD_TABLE.clear()
    yield
    upload_mod._UPLOAD_TABLE.clear()


# --------------------------------------------------------------------------
# chunk_text
# --------------------------------------------------------------------------

def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_short_text_single_chunk():
    assert chunk_text("hello world") == ["hello world"]


def test_chunk_text_splits_and_caps_at_max():
    # 100 chunks worth of text — must be capped at MAX_GROUNDING_CHUNKS.
    text = "x" * (280 * 100)
    chunks = chunk_text(text)
    assert len(chunks) == MAX_GROUNDING_CHUNKS
    assert all(len(c) <= 280 for c in chunks)


# --------------------------------------------------------------------------
# get_upload_record
# --------------------------------------------------------------------------

def test_get_upload_record_missing_returns_none():
    assert get_upload_record("nonexistent") is None


def test_get_upload_record_returns_inserted():
    record = _make_upload("doc1")
    upload_mod._UPLOAD_TABLE["doc1"] = record
    assert get_upload_record("doc1") is record


# --------------------------------------------------------------------------
# _resolve_uploaded_documents (POST /runs)
# --------------------------------------------------------------------------

def test_resolve_empty_list():
    assert _resolve_uploaded_documents([]) == []


def test_resolve_missing_document_id_raises_400():
    with pytest.raises(HTTPException) as exc:
        _resolve_uploaded_documents(["missing-id"])
    assert exc.value.status_code == 400
    assert "not found" in str(exc.value.detail)


def test_resolve_unparsed_document_raises_400():
    # An unparsed pdf/docx upload yields no extractable text — fail loud,
    # not a silent zero-evidence run.
    upload_mod._UPLOAD_TABLE["pdf1"] = _make_upload(
        "pdf1", content="", filename="report.pdf"
    )
    with pytest.raises(HTTPException) as exc:
        _resolve_uploaded_documents(["pdf1"])
    assert exc.value.status_code == 400
    assert "no extractable text" in str(exc.value.detail)


def test_resolve_happy_path_preserves_classification():
    upload_mod._UPLOAD_TABLE["doc1"] = _make_upload(
        "doc1",
        classification="CLIENT",
        content="alpha beta gamma",
        filename="brief.txt",
    )
    resolved = _resolve_uploaded_documents(["doc1"])
    assert len(resolved) == 1
    assert resolved[0]["document_id"] == "doc1"
    # Classification is preserved verbatim — the sovereignty filter runs
    # later, in the actor; /runs only resolves content.
    assert resolved[0]["classification"] == "CLIENT"
    assert resolved[0]["filename"] == "brief.txt"
    assert resolved[0]["chunks"] == ["alpha beta gamma"]


# --------------------------------------------------------------------------
# partition_uploads_by_sovereignty
# --------------------------------------------------------------------------

def test_partition_allows_public_synthetic_blocks_others():
    docs = [
        {"document_id": "a", "classification": "PUBLIC_SYNTHETIC"},
        {"document_id": "b", "classification": "CLIENT"},
        {"document_id": "c", "classification": "CAN_REAL"},
        {"document_id": "d", "classification": "PRIVATE"},
        {"document_id": "e", "classification": "UNKNOWN"},
    ]
    allowed, blocked = partition_uploads_by_sovereignty(docs)
    assert [d["document_id"] for d in allowed] == ["a"]
    assert {d["document_id"] for d in blocked} == {"b", "c", "d", "e"}


def test_partition_empty():
    assert partition_uploads_by_sovereignty([]) == ([], [])


# --------------------------------------------------------------------------
# build_upload_evidence_rows
# --------------------------------------------------------------------------

def test_build_rows_from_public_synthetic():
    docs = [
        {
            "document_id": "a",
            "classification": "PUBLIC_SYNTHETIC",
            "filename": "f.txt",
            "chunks": ["chunk one", "chunk two"],
        }
    ]
    rows = build_upload_evidence_rows(docs)
    assert len(rows) == 2
    assert rows[0]["evidence_id"] == "ev_upload_a_0"
    assert rows[1]["evidence_id"] == "ev_upload_a_1"
    assert rows[0]["statement"] == "chunk one"
    assert rows[0]["direct_quote"] == "chunk one"
    assert rows[0]["source_url"] == "upload://a"
    assert rows[0]["title"] == "f.txt"
    assert rows[0]["tier"] == "T2"
    assert rows[0]["uploaded_document"] is True


def test_build_rows_skips_empty_chunks():
    docs = [
        {
            "document_id": "a",
            "classification": "PUBLIC_SYNTHETIC",
            "filename": "f.txt",
            "chunks": ["real text", "   ", ""],
        }
    ]
    rows = build_upload_evidence_rows(docs)
    assert len(rows) == 1
    assert rows[0]["statement"] == "real text"


def test_build_rows_rejects_forbidden_classification():
    # Belt-and-suspenders: a CLIENT doc reaching row construction is a bug
    # (the actor-stage filter should have blocked it) — must raise, never
    # silently leak into generator evidence.
    docs = [
        {
            "document_id": "secret",
            "classification": "CLIENT",
            "filename": "c.txt",
            "chunks": ["confidential client text"],
        }
    ]
    with pytest.raises(UploadSovereigntyError, match="CLIENT"):
        build_upload_evidence_rows(docs)
