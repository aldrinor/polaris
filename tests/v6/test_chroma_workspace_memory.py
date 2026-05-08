"""Tests for ChromaWorkspaceMemoryStore (I-f14-001). §8.4 hash embedder."""

from __future__ import annotations

import os
import uuid

import pytest

from polaris_v6.memory.chroma_store import ChromaWorkspaceMemoryStore
from polaris_v6.memory.schema import MemoryQuery


def _hash_embed_fn(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for text in texts:
        vec = [0.0] * 8
        for i, ch in enumerate(text.lower()):
            vec[i % 8] += (ord(ch) % 31) / 31.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        out.append([v / norm for v in vec])
    return out


def _make(name: str, persist: str | None = None, embed=_hash_embed_fn):
    return ChromaWorkspaceMemoryStore(persist_directory=persist, embed_fn=embed,
                                      collection_name=f"t_{name}_{uuid.uuid4().hex[:8]}")


@pytest.fixture
def store(request):
    return _make(request.node.name)


def test_remember_and_recall_basic(store):
    store.remember(workspace_id="ws_carney", kind="domain_assumption", content="CMHC housing source.")
    r = store.recall(MemoryQuery(workspace_id="ws_carney", query_text="CMHC housing"))
    assert len(r) == 1 and r[0].score > 0


def test_workspace_isolation(store):
    store.remember(workspace_id="ws_alpha", kind="user_preference", content="Alpha prefers detailed.")
    store.remember(workspace_id="ws_beta", kind="user_preference", content="Beta prefers terse.")
    r = store.recall(MemoryQuery(workspace_id="ws_alpha", query_text="prefers"))
    assert len(r) == 1 and "Alpha" in r[0].entry.content


def test_kind_filter(store):
    store.remember(workspace_id="ws_x", kind="user_preference", content="prefers Vancouver")
    store.remember(workspace_id="ws_x", kind="rejected_source", content="reject blogspot prefers")
    r = store.recall(MemoryQuery(workspace_id="ws_x", query_text="prefers", kinds=["user_preference"]))
    assert all(x.entry.kind == "user_preference" for x in r)


def test_top_k_caps_results(store):
    for i in range(10):
        store.remember(workspace_id="ws_x", kind="prior_run_summary", content=f"Run {i}: housing data.")
    r = store.recall(MemoryQuery(workspace_id="ws_x", query_text="housing", top_k=3))
    assert len(r) == 3


def test_forget_respects_workspace(store):
    e = store.remember(workspace_id="ws_x", kind="user_preference", content="Forgettable.")
    assert not store.forget(workspace_id="ws_y", entry_id=e.entry_id)
    assert store.forget(workspace_id="ws_x", entry_id=e.entry_id)


def test_default_embed_fn_fails_loudly(request):
    s = _make(request.node.name, embed=None)
    with pytest.raises(RuntimeError, match="inject embed_fn"):
        s.remember(workspace_id="ws_x", kind="user_preference", content="should fail")


def test_persistent_client_round_trip(tmp_path):
    persist = str(tmp_path / "chroma")
    name = f"rt_{uuid.uuid4().hex[:8]}"
    a = ChromaWorkspaceMemoryStore(persist_directory=persist, embed_fn=_hash_embed_fn, collection_name=name)
    e = a.remember(workspace_id="ws_p", kind="user_preference", content="Persistent CMHC.")
    b = ChromaWorkspaceMemoryStore(persist_directory=persist, embed_fn=_hash_embed_fn, collection_name=name)
    assert any(x.entry_id == e.entry_id for x in b.list_workspace("ws_p"))
    assert b.recall(MemoryQuery(workspace_id="ws_p", query_text="CMHC"))[0].score > 0


def test_pre_existing_collection_with_wrong_metric_raises(tmp_path):
    import chromadb
    from chromadb.config import Settings
    persist = str(tmp_path / "chroma")
    os.makedirs(persist, exist_ok=True)
    name = f"wm_{uuid.uuid4().hex[:8]}"
    client = chromadb.PersistentClient(path=persist, settings=Settings(anonymized_telemetry=False))
    client.get_or_create_collection(name=name, metadata={"hnsw:space": "l2"})
    with pytest.raises(RuntimeError, match="hnsw:space"):
        ChromaWorkspaceMemoryStore(persist_directory=persist, embed_fn=_hash_embed_fn, collection_name=name)
