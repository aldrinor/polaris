"""Tests for the v6 workspace memory store (Phase 2B Task 2B.6 substrate)."""

from __future__ import annotations

import pytest

from polaris_v6.memory.schema import MemoryQuery
from polaris_v6.memory.store import WorkspaceMemoryStore


@pytest.fixture
def store() -> WorkspaceMemoryStore:
    return WorkspaceMemoryStore()


def test_remember_and_recall_basic(store):
    store.remember(
        workspace_id="ws_carney",
        kind="domain_assumption",
        content="User prefers CMHC as primary housing source.",
    )
    results = store.recall(
        MemoryQuery(workspace_id="ws_carney", query_text="CMHC housing")
    )
    assert len(results) == 1
    assert results[0].score > 0


def test_workspace_isolation(store):
    store.remember(
        workspace_id="ws_alpha",
        kind="user_preference",
        content="Alpha workspace prefers detailed citations.",
    )
    store.remember(
        workspace_id="ws_beta",
        kind="user_preference",
        content="Beta workspace prefers terse summaries.",
    )
    alpha_results = store.recall(
        MemoryQuery(workspace_id="ws_alpha", query_text="prefers")
    )
    assert len(alpha_results) == 1
    assert "Alpha" in alpha_results[0].entry.content


def test_workspace_id_normalization():
    """Mismatch between write and read normalization is a P0 governance bug.

    Per .codex/REVIEW_BRIEF_FORMAT.md severity rubric.
    """
    store = WorkspaceMemoryStore()
    store.remember(
        workspace_id="WS_Carney",
        kind="domain_assumption",
        content="Mixed-case workspace id.",
    )
    results = store.recall(
        MemoryQuery(workspace_id="ws_carney  ", query_text="mixed")
    )
    assert len(results) == 1


def test_kind_filter(store):
    store.remember(
        workspace_id="ws_x",
        kind="user_preference",
        content="prefers Vancouver focus",
    )
    store.remember(
        workspace_id="ws_x",
        kind="rejected_source",
        content="reject blogspot prefers",
    )
    pref_only = store.recall(
        MemoryQuery(
            workspace_id="ws_x", query_text="prefers", kinds=["user_preference"]
        )
    )
    assert all(r.entry.kind == "user_preference" for r in pref_only)


def test_top_k_caps_results(store):
    for i in range(10):
        store.remember(
            workspace_id="ws_x",
            kind="prior_run_summary",
            content=f"Run {i}: housing starts data.",
        )
    results = store.recall(
        MemoryQuery(workspace_id="ws_x", query_text="housing", top_k=3)
    )
    assert len(results) == 3


def test_recall_increments_use_count(store):
    entry = store.remember(
        workspace_id="ws_x",
        kind="user_preference",
        content="The user prefers CMHC monthly housing data over StatCan annual.",
    )
    assert entry.use_count == 0
    store.recall(MemoryQuery(workspace_id="ws_x", query_text="housing prefers"))
    refreshed = next(
        e for e in store.list_workspace("ws_x") if e.entry_id == entry.entry_id
    )
    assert refreshed.use_count == 1
    assert refreshed.last_used_at is not None


def test_forget_respects_workspace(store):
    entry = store.remember(
        workspace_id="ws_x",
        kind="user_preference",
        content="Forgettable preference.",
    )
    assert not store.forget(workspace_id="ws_y", entry_id=entry.entry_id)
    assert store.forget(workspace_id="ws_x", entry_id=entry.entry_id)
    assert (
        store.recall(MemoryQuery(workspace_id="ws_x", query_text="forgettable")) == []
    )


def test_recall_empty_workspace_returns_empty(store):
    results = store.recall(
        MemoryQuery(workspace_id="ws_empty", query_text="anything")
    )
    assert results == []
