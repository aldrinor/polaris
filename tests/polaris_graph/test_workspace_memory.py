"""Tests for src/polaris_graph/audit_ir/workspace_memory.py (M-21)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.workspace_memory import (
    MemoryEntry,
    WorkspaceMemoryStateError,
    WorkspaceMemoryStore,
    memory_entry_to_dict,
)


@pytest.fixture
def store(tmp_path: Path) -> WorkspaceMemoryStore:
    return WorkspaceMemoryStore(tmp_path / "memory.sqlite")


# ---------------------------------------------------------------------------
# Append + read
# ---------------------------------------------------------------------------


def test_append_creates_entry(store: WorkspaceMemoryStore) -> None:
    entry = store.append_entry(
        workspace_id="ws_alpha",
        claim_text="Tirzepatide reduced HbA1c by 1.5% in SURPASS-1",
        source_url="https://clinicaltrials.gov/ct2/show/NCT03954834",
        source_tier="T1",
    )
    assert entry.entry_id.startswith("mem_")
    assert entry.workspace_id == "ws_alpha"
    assert entry.last_used_at is None
    assert entry.created_at > 0


def test_append_rejects_empty_claim(store: WorkspaceMemoryStore) -> None:
    with pytest.raises(WorkspaceMemoryStateError, match="claim_text"):
        store.append_entry(
            workspace_id="ws_a", claim_text="   ",
            source_url="https://x.example", source_tier="T1",
        )


def test_append_rejects_empty_url(store: WorkspaceMemoryStore) -> None:
    with pytest.raises(WorkspaceMemoryStateError, match="source_url"):
        store.append_entry(
            workspace_id="ws_a", claim_text="x", source_url="",
            source_tier="T1",
        )


def test_append_rejects_empty_tier(store: WorkspaceMemoryStore) -> None:
    with pytest.raises(WorkspaceMemoryStateError, match="source_tier"):
        store.append_entry(
            workspace_id="ws_a", claim_text="x",
            source_url="https://x.example", source_tier="",
        )


def test_append_rejects_empty_workspace_id(store: WorkspaceMemoryStore) -> None:
    with pytest.raises(WorkspaceMemoryStateError, match="workspace_id"):
        store.append_entry(
            workspace_id="   ", claim_text="x",
            source_url="https://x.example", source_tier="T1",
        )


def test_get_entry_round_trips(store: WorkspaceMemoryStore) -> None:
    e = store.append_entry(
        workspace_id="ws_a", claim_text="claim",
        source_url="https://x.example", source_tier="T2",
    )
    same = store.get_entry(workspace_id="ws_a", entry_id=e.entry_id)
    assert same is not None
    assert same.entry_id == e.entry_id
    assert same.claim_text == "claim"


# ---------------------------------------------------------------------------
# Cross-workspace isolation (the dominant Phase C failure mode)
# ---------------------------------------------------------------------------


def test_get_returns_none_for_wrong_workspace(
    store: WorkspaceMemoryStore,
) -> None:
    e = store.append_entry(
        workspace_id="ws_a", claim_text="x",
        source_url="https://x.example", source_tier="T1",
    )
    assert store.get_entry(
        workspace_id="ws_b", entry_id=e.entry_id,
    ) is None


def test_list_does_not_leak_across_workspaces(
    store: WorkspaceMemoryStore,
) -> None:
    store.append_entry(
        workspace_id="ws_a", claim_text="alpha-claim",
        source_url="https://a.example", source_tier="T1",
    )
    store.append_entry(
        workspace_id="ws_a", claim_text="alpha-claim-2",
        source_url="https://a2.example", source_tier="T1",
    )
    store.append_entry(
        workspace_id="ws_b", claim_text="beta-claim",
        source_url="https://b.example", source_tier="T2",
    )
    a = store.list_entries(workspace_id="ws_a")
    b = store.list_entries(workspace_id="ws_b")
    assert len(a) == 2
    assert len(b) == 1
    assert all(e.workspace_id == "ws_a" for e in a)
    assert all(e.workspace_id == "ws_b" for e in b)


def test_retrieve_does_not_leak_across_workspaces(
    store: WorkspaceMemoryStore,
) -> None:
    """Even when query keywords match B's claims, retrieve called
    with workspace_id=A must return only A's entries."""
    store.append_entry(
        workspace_id="ws_a", claim_text="lung cancer alpha",
        source_url="https://a.example", source_tier="T1",
    )
    store.append_entry(
        workspace_id="ws_b",
        claim_text="lung cancer pembrolizumab efficacy",
        source_url="https://b.example", source_tier="T1",
    )
    a_results = store.retrieve(
        workspace_id="ws_a", query="lung cancer pembrolizumab",
    )
    assert len(a_results) == 1
    assert a_results[0][0].workspace_id == "ws_a"


def test_delete_does_not_cross_workspaces(
    store: WorkspaceMemoryStore,
) -> None:
    e = store.append_entry(
        workspace_id="ws_a", claim_text="x",
        source_url="https://x.example", source_tier="T1",
    )
    deleted = store.delete_entry(
        workspace_id="ws_b", entry_id=e.entry_id,
    )
    assert deleted is False
    # Original entry must still exist for ws_a.
    assert store.get_entry(
        workspace_id="ws_a", entry_id=e.entry_id,
    ) is not None


def test_delete_succeeds_for_correct_workspace(
    store: WorkspaceMemoryStore,
) -> None:
    e = store.append_entry(
        workspace_id="ws_a", claim_text="x",
        source_url="https://x.example", source_tier="T1",
    )
    assert store.delete_entry(
        workspace_id="ws_a", entry_id=e.entry_id,
    ) is True
    assert store.get_entry(
        workspace_id="ws_a", entry_id=e.entry_id,
    ) is None


def test_delete_all_for_workspace(store: WorkspaceMemoryStore) -> None:
    for i in range(3):
        store.append_entry(
            workspace_id="ws_a", claim_text=f"claim {i}",
            source_url=f"https://x.example/{i}", source_tier="T1",
        )
    store.append_entry(
        workspace_id="ws_b", claim_text="b-claim",
        source_url="https://b.example", source_tier="T1",
    )
    deleted = store.delete_all_for_workspace(workspace_id="ws_a")
    assert deleted == 3
    assert store.list_entries(workspace_id="ws_a") == []
    # Other workspace not touched.
    assert len(store.list_entries(workspace_id="ws_b")) == 1


# ---------------------------------------------------------------------------
# Retrieve scoring + freshness
# ---------------------------------------------------------------------------


def test_retrieve_ranks_higher_overlap_first(
    store: WorkspaceMemoryStore,
) -> None:
    """Two entries; the one with more overlapping content tokens
    must score higher."""
    weak = store.append_entry(
        workspace_id="ws_a",
        claim_text="aspirin gastrointestinal bleeding small",
        source_url="https://x1", source_tier="T1",
    )
    strong = store.append_entry(
        workspace_id="ws_a",
        claim_text="tirzepatide HbA1c reduction phase 3 diabetes",
        source_url="https://x2", source_tier="T1",
    )
    results = store.retrieve(
        workspace_id="ws_a",
        query="tirzepatide phase 3 diabetes",
    )
    assert len(results) >= 1
    # Strong match must rank first.
    assert results[0][0].entry_id == strong.entry_id
    # Weak entry has 0 token overlap, so it shouldn't appear.
    eids = [r[0].entry_id for r in results]
    assert weak.entry_id not in eids


def test_retrieve_zero_overlap_returns_empty(
    store: WorkspaceMemoryStore,
) -> None:
    store.append_entry(
        workspace_id="ws_a",
        claim_text="lung cancer pembrolizumab",
        source_url="https://x", source_tier="T1",
    )
    results = store.retrieve(
        workspace_id="ws_a", query="quantum chromodynamics",
    )
    assert results == []


def test_retrieve_top_k_caps_results(store: WorkspaceMemoryStore) -> None:
    for i in range(20):
        store.append_entry(
            workspace_id="ws_a",
            claim_text=f"cardiovascular outcome trial {i}",
            source_url=f"https://x/{i}", source_tier="T1",
        )
    results = store.retrieve(
        workspace_id="ws_a",
        query="cardiovascular outcome trial",
        top_k=5,
    )
    assert len(results) == 5


def test_retrieve_freshness_cutoff_excludes_old(
    store: WorkspaceMemoryStore, monkeypatch,
) -> None:
    """An entry older than max_age_days must be excluded."""
    # Use a real entry but rewrite its created_at via the store's
    # internal connection so we don't have to wait days.
    e = store.append_entry(
        workspace_id="ws_a", claim_text="old cardiovascular outcome",
        source_url="https://x", source_tier="T1",
    )
    # Force created_at to 30 days ago.
    with store._connect() as conn:
        conn.execute(
            "UPDATE workspace_memory SET created_at = ? WHERE entry_id = ?",
            (time.time() - 30 * 86400.0, e.entry_id),
        )
    # max_age_days=7 must exclude it.
    results = store.retrieve(
        workspace_id="ws_a",
        query="cardiovascular outcome",
        max_age_days=7,
    )
    assert results == []
    # max_age_days=60 must include it.
    results = store.retrieve(
        workspace_id="ws_a",
        query="cardiovascular outcome",
        max_age_days=60,
    )
    assert len(results) == 1


def test_retrieve_bumps_last_used_at(store: WorkspaceMemoryStore) -> None:
    e = store.append_entry(
        workspace_id="ws_a", claim_text="aspirin outcome",
        source_url="https://x", source_tier="T1",
    )
    assert e.last_used_at is None
    store.retrieve(workspace_id="ws_a", query="aspirin outcome")
    same = store.get_entry(workspace_id="ws_a", entry_id=e.entry_id)
    assert same is not None
    assert same.last_used_at is not None
    assert same.last_used_at >= e.created_at


def test_retrieve_empty_query_returns_empty(
    store: WorkspaceMemoryStore,
) -> None:
    store.append_entry(
        workspace_id="ws_a", claim_text="x",
        source_url="https://x", source_tier="T1",
    )
    assert store.retrieve(workspace_id="ws_a", query="") == []
    assert store.retrieve(workspace_id="ws_a", query="   ") == []


def test_retrieve_top_k_must_be_positive(
    store: WorkspaceMemoryStore,
) -> None:
    with pytest.raises(WorkspaceMemoryStateError, match="top_k"):
        store.retrieve(workspace_id="ws_a", query="x", top_k=0)


def test_list_max_age_must_be_non_negative(
    store: WorkspaceMemoryStore,
) -> None:
    with pytest.raises(WorkspaceMemoryStateError, match="max_age_days"):
        store.list_entries(workspace_id="ws_a", max_age_days=-1.0)


# ---------------------------------------------------------------------------
# Stopword behavior (matches M-10 conventions)
# ---------------------------------------------------------------------------


def test_retrieve_ignores_stopwords(store: WorkspaceMemoryStore) -> None:
    """Query that overlaps with an entry only on stopwords (the,
    of, in) must NOT match."""
    store.append_entry(
        workspace_id="ws_a",
        claim_text="warfarin atrial fibrillation stroke prevention",
        source_url="https://x", source_tier="T1",
    )
    # Query has only stopwords in common — no real content overlap.
    results = store.retrieve(
        workspace_id="ws_a", query="what is the of in",
    )
    assert results == []


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_memory_entry_to_dict() -> None:
    entry = MemoryEntry(
        entry_id="mem_x", workspace_id="ws_a", claim_text="claim",
        source_url="https://x", source_tier="T2",
        source_evidence_id="ev_42", created_at=12345.0,
        last_used_at=67890.0,
    )
    d = memory_entry_to_dict(entry)
    assert d["entry_id"] == "mem_x"
    assert d["source_evidence_id"] == "ev_42"
    assert d["last_used_at"] == 67890.0


# ---------------------------------------------------------------------------
# HTTP endpoint integration (workspace authz, memory ops)
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path):
    """Build a TestClient that has a fresh memory store + workspace
    store, and returns (app, mem_store, ws_store, ws_id, org_id)."""
    from fastapi import FastAPI
    from src.polaris_graph.audit_ir import inspector_router
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStore,
    )
    from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore

    # Fresh per-test stores so we don't fight the global singletons.
    mem_store = WorkspaceMemoryStore(tmp_path / "mem.sqlite")
    ws_store = WorkspaceStore(tmp_path / "ws.sqlite")
    inspector_router._workspace_memory_store = mem_store
    inspector_router._workspace_store = ws_store

    # Create one workspace owned by org_alpha.
    workspace = ws_store.create_workspace(
        name="alpha-workspace", max_docs=10, org_id="org_alpha",
    )

    app = FastAPI()
    app.include_router(inspector_router.router)
    return app, mem_store, ws_store, workspace.workspace_id, "org_alpha"


def test_endpoint_append_memory(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, mem_store, _, ws_id, org_id = _make_app(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": f"{org_id}:usr_alice:member"},
    )
    res = client.post(
        f"/api/inspector/workspaces/{ws_id}/memory",
        json={
            "claim_text": "tirzepatide HbA1c reduction in SURPASS-1",
            "source_url": "https://example/surpass1",
            "source_tier": "T1",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["workspace_id"] == ws_id
    assert body["source_tier"] == "T1"


def test_endpoint_append_requires_member_role(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, _, _, ws_id, org_id = _make_app(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": f"{org_id}:usr_voyeur:viewer"},
    )
    res = client.post(
        f"/api/inspector/workspaces/{ws_id}/memory",
        json={
            "claim_text": "x", "source_url": "https://x",
            "source_tier": "T1",
        },
    )
    assert res.status_code == 403


def test_endpoint_cross_org_append_forbidden(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, _, _, ws_id, _ = _make_app(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_beta:usr_x:member"},
    )
    res = client.post(
        f"/api/inspector/workspaces/{ws_id}/memory",
        json={
            "claim_text": "x", "source_url": "https://x",
            "source_tier": "T1",
        },
    )
    assert res.status_code == 403


def test_endpoint_retrieve_and_list(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, mem_store, _, ws_id, org_id = _make_app(tmp_path)
    mem_store.append_entry(
        workspace_id=ws_id,
        claim_text="apixaban stroke prevention atrial fibrillation",
        source_url="https://example/aristotle",
        source_tier="T1",
    )
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": f"{org_id}:usr_alice:viewer"},
    )

    res = client.get(f"/api/inspector/workspaces/{ws_id}/memory")
    assert res.status_code == 200
    assert res.json()["count"] == 1

    res = client.post(
        f"/api/inspector/workspaces/{ws_id}/memory/retrieve",
        params={"query": "apixaban atrial fibrillation"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    assert body["results"][0]["score"] > 0.0


def test_endpoint_delete_returns_404_for_missing(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, _, _, ws_id, org_id = _make_app(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": f"{org_id}:usr_alice:member"},
    )
    res = client.delete(
        f"/api/inspector/workspaces/{ws_id}/memory/mem_phantom"
    )
    assert res.status_code == 404


def test_endpoint_delete_succeeds(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, mem_store, _, ws_id, org_id = _make_app(tmp_path)
    e = mem_store.append_entry(
        workspace_id=ws_id, claim_text="claim",
        source_url="https://x", source_tier="T1",
    )
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": f"{org_id}:usr_alice:member"},
    )
    res = client.delete(
        f"/api/inspector/workspaces/{ws_id}/memory/{e.entry_id}"
    )
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert mem_store.get_entry(
        workspace_id=ws_id, entry_id=e.entry_id,
    ) is None
