"""Tests for SqliteWorkspaceMemoryStore (I-rdy-012 / #508).

Covers the three acceptance criteria — durability across restart,
workspace isolation, cited recall (`derived_from_run_ids` round-trip) —
plus keyword-cosine ranking, kind filtering, workspace-id normalization,
and forget semantics. All offline (pure SQLite, per-test temp DB).
"""

from __future__ import annotations

import pytest

from polaris_v6.memory.schema import MemoryQuery
from polaris_v6.memory.sqlite_store import SqliteWorkspaceMemoryStore


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "memory.sqlite")


def test_durability_survives_new_store_instance(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws1",
        kind="domain_assumption",
        content="User prefers CMHC for Canadian housing data.",
    )
    # Simulate a process restart: a brand-new store object on the same DB.
    reopened = SqliteWorkspaceMemoryStore(path=db_path)
    results = reopened.recall(
        MemoryQuery(workspace_id="ws1", query_text="CMHC housing")
    )
    assert len(results) == 1
    assert "CMHC" in results[0].entry.content


def test_workspace_isolation_recall(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws_alpha",
        kind="user_preference",
        content="Alpha workspace prefers detailed citations.",
    )
    results = store.recall(
        MemoryQuery(workspace_id="ws_beta", query_text="alpha prefers")
    )
    assert results == []


def test_workspace_isolation_list(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws_a", kind="user_preference", content="entry in workspace a"
    )
    assert len(store.list_workspace("ws_a")) == 1
    assert store.list_workspace("ws_b") == []


def test_workspace_isolation_forget_cross_workspace(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    entry = store.remember(
        workspace_id="ws_owner",
        kind="user_preference",
        content="owned by ws_owner only",
    )
    # A different workspace cannot forget another workspace's entry.
    assert store.forget(workspace_id="ws_other", entry_id=entry.entry_id) is False
    assert len(store.list_workspace("ws_owner")) == 1
    # The owning workspace can.
    assert store.forget(workspace_id="ws_owner", entry_id=entry.entry_id) is True
    assert store.list_workspace("ws_owner") == []


def test_workspace_id_normalized_write_and_read(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="  WS_Mixed  ",
        kind="user_preference",
        content="written with a messy workspace id",
    )
    # Recall with a differently-cased / padded id finds it (P0 governance:
    # workspace_id normalized identically on write and read).
    results = store.recall(
        MemoryQuery(workspace_id="ws_mixed", query_text="messy workspace")
    )
    assert len(results) == 1


def test_cited_recall_round_trips_run_ids(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws1",
        kind="prior_run_summary",
        content="Prior run found housing supply constraints.",
        derived_from_run_ids=["run_aaa", "run_bbb"],
    )
    reopened = SqliteWorkspaceMemoryStore(path=db_path)
    results = reopened.recall(
        MemoryQuery(workspace_id="ws1", query_text="housing supply")
    )
    assert len(results) == 1
    # Cited recall: the recalled entry surfaces which past runs contributed.
    assert results[0].entry.derived_from_run_ids == ["run_aaa", "run_bbb"]


def test_keyword_cosine_ranking(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws1",
        kind="domain_assumption",
        content="housing starts and housing supply in Canada",
    )
    store.remember(
        workspace_id="ws1",
        kind="domain_assumption",
        content="unrelated note about clinical trial endpoints",
    )
    results = store.recall(
        MemoryQuery(workspace_id="ws1", query_text="housing supply")
    )
    assert len(results) == 2
    assert "housing" in results[0].entry.content  # the matching entry ranks first
    assert results[0].score > results[1].score


def test_recall_increments_use_count_durably(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws1",
        kind="user_preference",
        content="entry whose use count is tracked",
    )
    r1 = store.recall(
        MemoryQuery(workspace_id="ws1", query_text="use count tracked")
    )
    assert r1[0].entry.use_count == 1
    # use_count is persisted — a fresh store instance sees the increment.
    reopened = SqliteWorkspaceMemoryStore(path=db_path)
    r2 = reopened.recall(
        MemoryQuery(workspace_id="ws1", query_text="use count tracked")
    )
    assert r2[0].entry.use_count == 2


def test_recall_kinds_filter(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    store.remember(
        workspace_id="ws1", kind="user_preference", content="a user preference entry"
    )
    store.remember(
        workspace_id="ws1", kind="prior_run_summary", content="a prior run summary entry"
    )
    results = store.recall(
        MemoryQuery(
            workspace_id="ws1", query_text="entry", kinds=["prior_run_summary"]
        )
    )
    assert len(results) == 1
    assert results[0].entry.kind == "prior_run_summary"


def test_forget_missing_entry_returns_false(db_path):
    store = SqliteWorkspaceMemoryStore(path=db_path)
    assert store.forget(workspace_id="ws1", entry_id="does-not-exist") is False
