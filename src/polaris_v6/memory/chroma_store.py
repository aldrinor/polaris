"""ChromaDB-backed semantic workspace memory store (I-f14-001).

Cosine vector recall. Production sentence-transformers + router swap
deferred to I-f14-001b. Per CLAUDE.md §8.4 tests inject embed_fn.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from polaris_v6.memory.schema import (
    MemoryEntry,
    MemoryKind,
    MemoryQuery,
    MemoryRecallResult,
)

EmbedFn = Callable[[list[str]], list[list[float]]]


def _default_embed_fn(_t: list[str]) -> list[list[float]]:
    raise RuntimeError("inject embed_fn (sentence-transformers); deferred to I-f14-001b")


def _norm(raw: str) -> str:
    return raw.strip().lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta(e: MemoryEntry) -> dict:
    return {"workspace_id": e.workspace_id, "kind": e.kind, "entry_json": e.model_dump_json()}


class ChromaWorkspaceMemoryStore:
    def __init__(self, *, persist_directory: str | None, embed_fn: EmbedFn | None = None,
                 collection_name: str = "v6_workspace_memory") -> None:
        import chromadb
        from chromadb.config import Settings
        s = Settings(anonymized_telemetry=False)
        if persist_directory is not None:
            os.makedirs(persist_directory, exist_ok=True)
            client = chromadb.PersistentClient(path=persist_directory, settings=s)
        else:
            client = chromadb.EphemeralClient(settings=s)
        self._collection = client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"})
        space = (self._collection.metadata or {}).get("hnsw:space")
        if space != "cosine":
            raise RuntimeError(
                f"collection {collection_name} pre-existing with hnsw:space={space!r}; expected cosine")
        self._embed_fn: EmbedFn = embed_fn or _default_embed_fn

    def remember(self, *, workspace_id: str, kind: MemoryKind, content: str,
                 derived_from_run_ids: list[str] | None = None) -> MemoryEntry:
        emb = self._embed_fn([content])[0]
        entry = MemoryEntry(
            entry_id=uuid.uuid4().hex, workspace_id=_norm(workspace_id), kind=kind,
            content=content, embedding_vector=emb, created_at=_now(),
            derived_from_run_ids=derived_from_run_ids or [])
        self._collection.add(
            ids=[entry.entry_id], documents=[content], embeddings=[emb], metadatas=[_meta(entry)])
        return entry

    def recall(self, query: MemoryQuery) -> list[MemoryRecallResult]:
        if query.kinds is not None and len(query.kinds) == 0:
            return []
        ws = _norm(query.workspace_id)
        where: dict = {"workspace_id": ws} if query.kinds is None else {
            "$and": [{"workspace_id": ws}, {"kind": {"$in": list(query.kinds)}}]}
        emb = self._embed_fn([query.query_text])[0]
        result = self._collection.query(query_embeddings=[emb], n_results=query.top_k, where=where)
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        out: list[MemoryRecallResult] = []
        now = _now()
        for entry_id, distance, meta in zip(ids, distances, metas):
            entry = MemoryEntry.model_validate_json(meta["entry_json"])
            entry.use_count += 1
            entry.last_used_at = now
            self._collection.update(ids=[entry_id], metadatas=[_meta(entry)])
            out.append(MemoryRecallResult(entry=entry, score=max(0.0, min(1.0, 1.0 - float(distance)))))
        return out

    def forget(self, *, workspace_id: str, entry_id: str) -> bool:
        existing = self._collection.get(ids=[entry_id], include=["metadatas"])
        metas = existing.get("metadatas") or []
        if not metas or metas[0].get("workspace_id") != _norm(workspace_id):
            return False
        self._collection.delete(ids=[entry_id])
        return True

    def list_workspace(self, workspace_id: str) -> list[MemoryEntry]:
        result = self._collection.get(where={"workspace_id": _norm(workspace_id)}, include=["metadatas"])
        return [MemoryEntry.model_validate_json(m["entry_json"]) for m in (result.get("metadatas") or [])]
