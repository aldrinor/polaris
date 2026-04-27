"""Tests for src/polaris_graph/audit_ir/workspace_store.py (M-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.provenance import TextSpan, to_dict
from src.polaris_graph.audit_ir.workspace_store import (
    DEFAULT_MAX_DOCS_PER_WORKSPACE,
    BoundedError,
    Upload,
    Workspace,
    WorkspaceStateError,
    WorkspaceStore,
)


@pytest.fixture
def store(tmp_path: Path) -> WorkspaceStore:
    return WorkspaceStore(tmp_path / "workspaces.sqlite")


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


def test_create_workspace_assigns_ids_and_defaults(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Phase B Beta")
    assert ws.workspace_id.startswith("ws_")
    assert ws.name == "Phase B Beta"
    assert ws.max_docs == DEFAULT_MAX_DOCS_PER_WORKSPACE
    assert ws.created_at > 0


def test_create_workspace_respects_explicit_max_docs(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Tight", max_docs=5)
    assert ws.max_docs == 5


def test_create_workspace_rejects_empty_name(store: WorkspaceStore) -> None:
    with pytest.raises(WorkspaceStateError, match="non-empty"):
        store.create_workspace("")
    with pytest.raises(WorkspaceStateError, match="non-empty"):
        store.create_workspace("   ")


def test_create_workspace_rejects_zero_max_docs(store: WorkspaceStore) -> None:
    with pytest.raises(WorkspaceStateError, match="max_docs"):
        store.create_workspace("Bad", max_docs=0)


def test_get_workspace_returns_none_for_unknown(store: WorkspaceStore) -> None:
    assert store.get_workspace("ws_does_not_exist") is None


def test_list_workspaces_returns_recent_first(store: WorkspaceStore) -> None:
    a = store.create_workspace("A")
    b = store.create_workspace("B")
    listed = store.list_workspaces()
    assert [w.workspace_id for w in listed] == [b.workspace_id, a.workspace_id]


def test_max_docs_default_picks_up_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PG_WORKSPACE_MAX_DOCS", "7")
    s = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = s.create_workspace("Env-bounded")
    assert ws.max_docs == 7


def test_max_docs_garbage_env_falls_back(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PG_WORKSPACE_MAX_DOCS", "garbage")
    s = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = s.create_workspace("Garbage-env")
    assert ws.max_docs == DEFAULT_MAX_DOCS_PER_WORKSPACE


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def test_upload_file_persists_metadata(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Files", max_docs=10)
    up = store.upload_file(
        workspace_id=ws.workspace_id, filename="notes.txt",
        content_type="text/plain", size_bytes=1234,
        storage_path="/tmp/whatever",
    )
    assert up.upload_id.startswith("up_")
    assert up.workspace_id == ws.workspace_id
    assert up.parser_status == "pending"
    assert up.parser_error is None
    assert up.deleted_at is None
    # Round-trip via get_upload.
    fetched = store.get_upload(up.upload_id)
    assert fetched == up


def test_upload_file_rejects_unknown_workspace(store: WorkspaceStore) -> None:
    with pytest.raises(WorkspaceStateError, match="unknown workspace"):
        store.upload_file(
            workspace_id="ws_nope", filename="x.txt",
            content_type=None, size_bytes=0, storage_path="/tmp/x",
        )


def test_upload_file_enforces_bounded_cap(store: WorkspaceStore) -> None:
    """Codex M-11 mandate: bounded enforcement fails LOUD per LAW II.
    No silent truncation."""
    ws = store.create_workspace("Tiny", max_docs=2)
    store.upload_file(ws.workspace_id, "a.txt", "text/plain", 1, "/p/a")
    store.upload_file(ws.workspace_id, "b.txt", "text/plain", 1, "/p/b")
    with pytest.raises(BoundedError, match="at cap"):
        store.upload_file(ws.workspace_id, "c.txt", "text/plain", 1, "/p/c")


def test_soft_deleted_upload_does_not_count_against_cap(store: WorkspaceStore) -> None:
    """Soft-delete frees a slot; audit trail preserved."""
    ws = store.create_workspace("FillUp", max_docs=2)
    a = store.upload_file(ws.workspace_id, "a.txt", "text/plain", 1, "/p/a")
    store.upload_file(ws.workspace_id, "b.txt", "text/plain", 1, "/p/b")
    store.soft_delete_upload(a.upload_id)
    # Now there's room for one more.
    c = store.upload_file(ws.workspace_id, "c.txt", "text/plain", 1, "/p/c")
    assert c.deleted_at is None
    # The soft-deleted upload is still findable for audit.
    fetched_a = store.get_upload(a.upload_id)
    assert fetched_a is not None
    assert fetched_a.deleted_at is not None


def test_list_uploads_default_excludes_deleted(store: WorkspaceStore) -> None:
    ws = store.create_workspace("AuditTrail", max_docs=10)
    a = store.upload_file(ws.workspace_id, "a.txt", "text/plain", 1, "/p/a")
    b = store.upload_file(ws.workspace_id, "b.txt", "text/plain", 1, "/p/b")
    store.soft_delete_upload(a.upload_id)
    listed = store.list_uploads(ws.workspace_id)
    assert [u.upload_id for u in listed] == [b.upload_id]
    listed_with_deleted = store.list_uploads(
        ws.workspace_id, include_deleted=True
    )
    assert {u.upload_id for u in listed_with_deleted} == {a.upload_id, b.upload_id}


def test_soft_delete_is_idempotent(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Idem", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    first = store.soft_delete_upload(up.upload_id)
    second = store.soft_delete_upload(up.upload_id)
    assert first.deleted_at == second.deleted_at  # no double-stamp


# ---------------------------------------------------------------------------
# Parser-status state machine
# ---------------------------------------------------------------------------


def test_parser_transition_pending_to_parsing_to_parsed(store: WorkspaceStore) -> None:
    ws = store.create_workspace("StateMachine", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    after_parsing = store.transition_parser_status(up.upload_id, "parsing")
    assert after_parsing.parser_status == "parsing"
    after_parsed = store.transition_parser_status(up.upload_id, "parsed")
    assert after_parsed.parser_status == "parsed"
    assert after_parsed.parsed_at is not None


def test_parser_transition_pending_to_failed(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Failures", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    failed = store.transition_parser_status(
        up.upload_id, "failed", parser_error="bad bytes",
    )
    assert failed.parser_status == "failed"
    assert failed.parser_error == "bad bytes"


def test_parser_transition_parsing_to_failed(store: WorkspaceStore) -> None:
    ws = store.create_workspace("ParsingToFailed", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    store.transition_parser_status(up.upload_id, "parsing")
    failed = store.transition_parser_status(
        up.upload_id, "failed", parser_error="extractor crashed",
    )
    assert failed.parser_status == "failed"


def test_parser_transition_rejects_illegal_jumps(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Illegal", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    # pending → parsed (skip parsing) is illegal
    with pytest.raises(WorkspaceStateError, match="illegal transition"):
        store.transition_parser_status(up.upload_id, "parsed")


def test_parser_transition_terminal_is_sticky(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Sticky", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    store.transition_parser_status(up.upload_id, "parsing")
    store.transition_parser_status(up.upload_id, "parsed")
    # Terminal — no further transitions.
    with pytest.raises(WorkspaceStateError, match="illegal transition"):
        store.transition_parser_status(up.upload_id, "parsing")
    with pytest.raises(WorkspaceStateError, match="illegal transition"):
        store.transition_parser_status(up.upload_id, "failed")


def test_parser_transition_unknown_status_raises(store: WorkspaceStore) -> None:
    ws = store.create_workspace("UnknownStatus", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    with pytest.raises(WorkspaceStateError, match="unknown status"):
        store.transition_parser_status(up.upload_id, "weird")


def test_parser_transition_on_deleted_upload_raises(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Deleted", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    store.soft_delete_upload(up.upload_id)
    with pytest.raises(WorkspaceStateError, match="soft-deleted"):
        store.transition_parser_status(up.upload_id, "parsing")


# ---------------------------------------------------------------------------
# Chunks (parsed content + provenance)
# ---------------------------------------------------------------------------


def test_insert_and_list_chunks(store: WorkspaceStore) -> None:
    ws = store.create_workspace("Chunks", max_docs=2)
    up = store.upload_file(ws.workspace_id, "x.txt", "text/plain", 1, "/p/x")
    chunks = [
        ("hello world", to_dict(TextSpan(up.upload_id, 0, 11))),
        ("second chunk", to_dict(TextSpan(up.upload_id, 11, 23))),
    ]
    n = store.insert_chunks(up.upload_id, chunks)
    assert n == 2
    listed = store.list_chunks(up.upload_id)
    assert len(listed) == 2
    assert listed[0]["seq"] == 0
    assert listed[0]["text"] == "hello world"
    assert listed[0]["provenance"]["kind"] == "text_span"
    assert listed[0]["provenance"]["char_start"] == 0


def test_insert_chunks_rejects_unknown_upload(store: WorkspaceStore) -> None:
    with pytest.raises(WorkspaceStateError, match="unknown upload"):
        store.insert_chunks("up_no_such", [("text", {"kind": "text_span"})])
