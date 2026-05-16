"""SQLite-backed durable workspace memory store (I-rdy-012 / #508).

F14 Phase 3.9: the durable replacement for the in-memory
`WorkspaceMemoryStore` demo store (`memory/store.py`). Memory now survives
a process restart, stays workspace-scoped, and round-trips
`derived_from_run_ids` so recall surfaces which past run contributed
(cited recall).

Recall keeps the in-memory store's keyword-cosine scoring verbatim — #508's
acceptance is durability + workspace isolation + cited recall, NOT semantic
recall. The semantic upgrade (Chroma + a real sentence-transformers
embedder) is `ChromaWorkspaceMemoryStore`, left untouched here and wired by
a separate deferred issue.

Storage pattern mirrors `polaris_v6.queue.run_store` (WAL, idempotent
additive `_migrate_schema`). DB path: env `POLARIS_V6_MEMORY_DB`, default
`state/v6_workspace_memory.sqlite` (gitignored).

Per CLAUDE.md security posture: `workspace_id` is normalized identically on
write and read — a mismatch is a P0 governance issue.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone

from polaris_v6.memory.schema import (
    MemoryEntry,
    MemoryKind,
    MemoryQuery,
    MemoryRecallResult,
)

DEFAULT_DB_PATH = "state/v6_workspace_memory.sqlite"
ENV_DB_PATH = "POLARIS_V6_MEMORY_DB"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _resolve_path(path: str | None) -> str:
    if path is not None:
        return path
    return os.environ.get(ENV_DB_PATH, DEFAULT_DB_PATH)


def _normalize_workspace_id(raw: str) -> str:
    return raw.strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> Counter[str]:
    return Counter(_TOKEN_RE.findall(text.lower()))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _connect(path: str) -> sqlite3.Connection:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Idempotent additive migration. Safe to call on every init."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_entries (
            entry_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            use_count INTEGER NOT NULL DEFAULT 0,
            derived_from_run_ids TEXT NOT NULL DEFAULT '[]',
            embedding_vector TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_workspace "
        "ON memory_entries(workspace_id)"
    )


def _init_db(path: str) -> None:
    conn = _connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _migrate_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    raw_runs = row["derived_from_run_ids"]
    raw_emb = row["embedding_vector"]
    return MemoryEntry(
        entry_id=row["entry_id"],
        workspace_id=row["workspace_id"],
        kind=row["kind"],
        content=row["content"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        use_count=row["use_count"],
        derived_from_run_ids=json.loads(raw_runs) if raw_runs else [],
        embedding_vector=json.loads(raw_emb) if raw_emb else None,
    )


class SqliteWorkspaceMemoryStore:
    """Durable SQLite implementation of the workspace memory store.

    Drop-in replacement for `WorkspaceMemoryStore` — identical
    `remember` / `recall` / `forget` / `list_workspace` interface.
    """

    def __init__(self, *, path: str | None = None) -> None:
        self._path = _resolve_path(path)
        _init_db(self._path)

    def remember(
        self,
        *,
        workspace_id: str,
        kind: MemoryKind,
        content: str,
        derived_from_run_ids: list[str] | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            entry_id=uuid.uuid4().hex,
            workspace_id=_normalize_workspace_id(workspace_id),
            kind=kind,
            content=content,
            created_at=_now_iso(),
            derived_from_run_ids=derived_from_run_ids or [],
        )
        conn = _connect(self._path)
        try:
            conn.execute(
                "INSERT INTO memory_entries "
                "(entry_id, workspace_id, kind, content, created_at, "
                "last_used_at, use_count, derived_from_run_ids, embedding_vector) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.entry_id,
                    entry.workspace_id,
                    entry.kind,
                    entry.content,
                    entry.created_at,
                    entry.last_used_at,
                    entry.use_count,
                    json.dumps(entry.derived_from_run_ids),
                    json.dumps(entry.embedding_vector)
                    if entry.embedding_vector is not None
                    else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return entry

    def recall(self, query: MemoryQuery) -> list[MemoryRecallResult]:
        ws_norm = _normalize_workspace_id(query.workspace_id)
        conn = _connect(self._path)
        try:
            rows = conn.execute(
                "SELECT * FROM memory_entries WHERE workspace_id=?", (ws_norm,)
            ).fetchall()
        finally:
            conn.close()
        candidates = [_row_to_entry(r) for r in rows]
        if query.kinds is not None:
            kind_set = set(query.kinds)
            candidates = [e for e in candidates if e.kind in kind_set]
        if not candidates:
            return []
        q_tokens = _tokens(query.query_text)
        scored = [
            MemoryRecallResult(entry=e, score=_cosine(q_tokens, _tokens(e.content)))
            for e in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        top = scored[: query.top_k]
        # Persist the recall (use_count + last_used_at) for the returned set.
        now = _now_iso()
        conn = _connect(self._path)
        try:
            for r in top:
                r.entry.use_count += 1
                r.entry.last_used_at = now
                conn.execute(
                    "UPDATE memory_entries SET use_count=?, last_used_at=? "
                    "WHERE entry_id=?",
                    (r.entry.use_count, r.entry.last_used_at, r.entry.entry_id),
                )
            conn.commit()
        finally:
            conn.close()
        return top

    def forget(self, *, workspace_id: str, entry_id: str) -> bool:
        ws_norm = _normalize_workspace_id(workspace_id)
        conn = _connect(self._path)
        try:
            # Workspace-scoped DELETE: an entry in a different workspace is
            # not matched, so cross-workspace forget returns False.
            cur = conn.execute(
                "DELETE FROM memory_entries WHERE entry_id=? AND workspace_id=?",
                (entry_id, ws_norm),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_workspace(self, workspace_id: str) -> list[MemoryEntry]:
        ws_norm = _normalize_workspace_id(workspace_id)
        conn = _connect(self._path)
        try:
            rows = conn.execute(
                "SELECT * FROM memory_entries WHERE workspace_id=?", (ws_norm,)
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_entry(r) for r in rows]
