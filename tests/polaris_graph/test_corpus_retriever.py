"""Tests for src/polaris_graph/audit_ir/corpus_retriever.py (M-12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.corpus_retriever import (
    DEFAULT_MIN_SCORE,
    RetrievedChunk,
    retrieve_chunks,
)
from src.polaris_graph.audit_ir.provenance import TextSpan, to_dict
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


@pytest.fixture
def populated_store(tmp_path: Path) -> tuple[WorkspaceStore, str]:
    """A workspace with three parsed uploads on different topics
    and one soft-deleted upload."""
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = store.create_workspace("Retrieve", max_docs=10)

    diabetes_up = store.upload_file(
        ws.workspace_id, "diabetes.txt", "text/plain", 100, "/p/d",
    )
    store.transition_parser_status(diabetes_up.upload_id, "parsing")
    store.insert_chunks(diabetes_up.upload_id, [
        ("Tirzepatide for type 2 diabetes shows efficacy in trials.",
         to_dict(TextSpan(diabetes_up.upload_id, 0, 60))),
        ("Adverse events for tirzepatide include nausea and reduced appetite.",
         to_dict(TextSpan(diabetes_up.upload_id, 60, 130))),
    ])
    store.transition_parser_status(diabetes_up.upload_id, "parsed")

    obesity_up = store.upload_file(
        ws.workspace_id, "obesity.txt", "text/plain", 100, "/p/o",
    )
    store.transition_parser_status(obesity_up.upload_id, "parsing")
    store.insert_chunks(obesity_up.upload_id, [
        ("Semaglutide weight loss outcomes in obesity were significant.",
         to_dict(TextSpan(obesity_up.upload_id, 0, 60))),
    ])
    store.transition_parser_status(obesity_up.upload_id, "parsed")

    # Pending upload — should be excluded.
    pending_up = store.upload_file(
        ws.workspace_id, "pending.txt", "text/plain", 30, "/p/p",
    )
    # Soft-deleted upload — should be excluded.
    deleted_up = store.upload_file(
        ws.workspace_id, "deleted.txt", "text/plain", 30, "/p/del",
    )
    store.transition_parser_status(deleted_up.upload_id, "parsing")
    store.insert_chunks(deleted_up.upload_id, [
        ("Tirzepatide secret deleted content about diabetes.",
         to_dict(TextSpan(deleted_up.upload_id, 0, 50))),
    ])
    store.transition_parser_status(deleted_up.upload_id, "parsed")
    store.soft_delete_upload(deleted_up.upload_id)

    return store, ws.workspace_id


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_retrieve_returns_top_chunks(populated_store) -> None:
    store, ws_id = populated_store
    results = retrieve_chunks(store, ws_id, "tirzepatide diabetes efficacy")
    assert results, "expected non-empty retrieval"
    assert all(isinstance(r, RetrievedChunk) for r in results)
    # Top result should mention tirzepatide+diabetes (chunk 1 of
    # diabetes.txt), not semaglutide.
    top = results[0]
    assert "tirzepatide" in top.text.lower()
    assert "diabetes" in top.text.lower()


def test_retrieve_scores_are_descending(populated_store) -> None:
    store, ws_id = populated_store
    results = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_carries_provenance(populated_store) -> None:
    store, ws_id = populated_store
    results = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    assert results
    for r in results:
        assert r.provenance["kind"] == "text_span"
        assert r.provenance["upload_id"] == r.upload_id
        assert r.chunk_id.startswith("ck_")


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_retrieve_excludes_deleted_uploads(populated_store) -> None:
    """Per LAW II — soft-deleted uploads must NOT appear in results."""
    store, ws_id = populated_store
    results = retrieve_chunks(store, ws_id, "tirzepatide diabetes secret")
    for r in results:
        assert "secret deleted" not in r.text.lower(), (
            f"soft-deleted chunk leaked: {r.text!r}"
        )


def test_retrieve_excludes_pending_uploads(populated_store) -> None:
    """Only parsed uploads are searchable."""
    store, ws_id = populated_store
    results = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    for r in results:
        assert r.filename != "pending.txt"


def test_retrieve_top_k_caps_results(populated_store) -> None:
    store, ws_id = populated_store
    results = retrieve_chunks(store, ws_id, "tirzepatide diabetes", top_k=1)
    assert len(results) == 1


def test_retrieve_min_score_filters_below_floor(populated_store) -> None:
    """An impossibly-high min_score returns empty without crashing."""
    store, ws_id = populated_store
    results = retrieve_chunks(
        store, ws_id, "tirzepatide diabetes", min_score=999.0,
    )
    assert results == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_retrieve_empty_workspace_returns_empty(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = store.create_workspace("Empty", max_docs=10)
    assert retrieve_chunks(store, ws.workspace_id, "anything") == []


def test_retrieve_workspace_without_parsed_uploads_returns_empty(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = store.create_workspace("PendingOnly", max_docs=10)
    store.upload_file(
        ws.workspace_id, "x.txt", "text/plain", 10, "/p/x",
    )
    # Status is pending — never transitioned to parsed.
    assert retrieve_chunks(store, ws.workspace_id, "x") == []


def test_retrieve_unknown_workspace_raises(populated_store) -> None:
    """Per LAW II: unknown workspace must NOT silently return [].
    Caller (API) maps this to 404."""
    store, _ = populated_store
    with pytest.raises(ValueError, match="unknown workspace"):
        retrieve_chunks(store, "ws_does_not_exist", "anything")


def test_retrieve_empty_question_returns_empty(populated_store) -> None:
    store, ws_id = populated_store
    assert retrieve_chunks(store, ws_id, "") == []
    assert retrieve_chunks(store, ws_id, "    ") == []
    # Stopword-only query also yields nothing.
    assert retrieve_chunks(store, ws_id, "the and of") == []


def test_retrieve_query_with_no_matches_returns_empty(populated_store) -> None:
    """Query about an unrelated topic → BM25 floor filters all."""
    store, ws_id = populated_store
    results = retrieve_chunks(
        store, ws_id, "blockchain governance smart contracts",
        min_score=DEFAULT_MIN_SCORE,
    )
    assert results == []
