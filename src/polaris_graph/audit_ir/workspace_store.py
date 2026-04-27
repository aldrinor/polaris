"""Workspace + upload data model (M-11 — Phase B foundation).

Per FINAL_PLAN.md: "Bounded upload + workspace data model — 10-50
docs/workspace, persistent". This module ships the SQLite-backed
foundation: workspaces, uploads, parser status state machine,
bounded enforcement, soft-delete with audit trail.

OUT OF SCOPE for Phase B:
  - Filter modes (uploaded-only / web-only / blended) — M-12
  - Retrieval over uploads — M-12
  - ACL / RBAC beyond workspace_id scoping — Phase C
  - Real PDF/sheet/slide parsers — Phase C

State machine for upload.parser_status:
  pending  → parsing            (worker picks it up)
  parsing  → parsed | failed    (parse completes)
  any      → deleted_at SET     (soft-delete; audit trail)

Bounded enforcement:
  Each workspace has a `max_docs` (env-overridable default).
  upload_file() raises BoundedError if the workspace already holds
  `max_docs` non-deleted uploads. Fails LOUD per LAW II — no
  silent truncation.

Mirrors M-8 JobQueue patterns:
  - SQLite WAL mode, per-call connections.
  - Atomic state transitions via UPDATE..WHERE..AND status='X'.
  - Foreign keys enabled.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants + env-overrides
# ---------------------------------------------------------------------------

PARSER_STATUSES: tuple[str, ...] = ("pending", "parsing", "parsed", "failed")
TERMINAL_PARSER_STATUSES: frozenset[str] = frozenset({"parsed", "failed"})

ALLOWED_PARSER_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"parsing", "failed"}),
    "parsing": frozenset({"parsed", "failed"}),
    # parsed / failed are terminal (except for soft-delete).
    "parsed": frozenset(),
    "failed": frozenset(),
}

DEFAULT_MAX_DOCS_PER_WORKSPACE = 50


def _env_max_docs() -> int:
    """Read PG_WORKSPACE_MAX_DOCS at call time (not import time) so
    tests can monkeypatch."""
    raw = os.environ.get("PG_WORKSPACE_MAX_DOCS")
    if raw is None:
        return DEFAULT_MAX_DOCS_PER_WORKSPACE
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_DOCS_PER_WORKSPACE


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkspaceStoreError(Exception):
    """Base error for workspace_store. Subclasses are:
      - BoundedError: max_docs cap reached
      - WorkspaceStateError: illegal state transition / unknown row
    """


class BoundedError(WorkspaceStoreError):
    """Raised when an upload would exceed the workspace's max_docs.
    Per LAW II, fails LOUD — never silently truncates."""


class WorkspaceStateError(WorkspaceStoreError):
    """Illegal state transition or unknown row."""


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    name: str
    max_docs: int
    created_at: float


@dataclass(frozen=True)
class Upload:
    upload_id: str
    workspace_id: str
    filename: str
    content_type: str | None
    size_bytes: int
    storage_path: str
    parser_status: str  # one of PARSER_STATUSES
    parser_error: str | None
    created_at: float
    parsed_at: float | None
    deleted_at: float | None


def workspace_to_dict(ws: Workspace) -> dict[str, Any]:
    return {
        "workspace_id": ws.workspace_id,
        "name": ws.name,
        "max_docs": ws.max_docs,
        "created_at": ws.created_at,
    }


def upload_to_dict(up: Upload) -> dict[str, Any]:
    return {
        "upload_id": up.upload_id,
        "workspace_id": up.workspace_id,
        "filename": up.filename,
        "content_type": up.content_type,
        "size_bytes": up.size_bytes,
        "storage_path": up.storage_path,
        "parser_status": up.parser_status,
        "parser_error": up.parser_error,
        "created_at": up.created_at,
        "parsed_at": up.parsed_at,
        "deleted_at": up.deleted_at,
    }


# ---------------------------------------------------------------------------
# WorkspaceStore
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    max_docs INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    parser_status TEXT NOT NULL DEFAULT 'pending',
    parser_error TEXT,
    created_at REAL NOT NULL,
    parsed_at REAL,
    deleted_at REAL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_uploads_workspace
    ON uploads(workspace_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_uploads_parser_status
    ON uploads(parser_status, deleted_at);

CREATE TABLE IF NOT EXISTS upload_chunks (
    chunk_id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id)
);

CREATE INDEX IF NOT EXISTS idx_upload_chunks_upload
    ON upload_chunks(upload_id, seq);
"""


class WorkspaceStore:
    """SQLite-backed workspace + upload registry.

    Per-call connections (matches JobQueue pattern). WAL mode for
    concurrent reads. Foreign keys enabled.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    def create_workspace(self, name: str, max_docs: int | None = None) -> Workspace:
        if not name or not name.strip():
            raise WorkspaceStateError("workspace name must be non-empty")
        if max_docs is None:
            max_docs = _env_max_docs()
        if max_docs < 1:
            raise WorkspaceStateError(f"max_docs must be >= 1; got {max_docs}")
        ws_id = f"ws_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO workspaces (workspace_id, name, max_docs, created_at) "
                "VALUES (?, ?, ?, ?)",
                (ws_id, name.strip(), max_docs, now),
            )
        return Workspace(
            workspace_id=ws_id, name=name.strip(),
            max_docs=max_docs, created_at=now,
        )

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return _row_to_workspace(row) if row else None

    def list_workspaces(self) -> list[Workspace]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workspaces ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_workspace(r) for r in rows]

    # ------------------------------------------------------------------
    # Uploads
    # ------------------------------------------------------------------

    def upload_file(
        self,
        workspace_id: str,
        filename: str,
        content_type: str | None,
        size_bytes: int,
        storage_path: str,
    ) -> Upload:
        """Register a new upload. Atomically validates that the
        workspace exists AND has spare capacity. Raises BoundedError
        if at the cap; WorkspaceStateError if the workspace is
        unknown."""
        ws = self.get_workspace(workspace_id)
        if ws is None:
            raise WorkspaceStateError(f"unknown workspace: {workspace_id}")
        if not filename:
            raise WorkspaceStateError("filename must be non-empty")
        if size_bytes < 0:
            raise WorkspaceStateError(f"size_bytes must be >= 0; got {size_bytes}")
        upload_id = f"up_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM uploads "
                "WHERE workspace_id = ? AND deleted_at IS NULL",
                (workspace_id,),
            )
            current = cur.fetchone()[0]
            if current >= ws.max_docs:
                raise BoundedError(
                    f"workspace {workspace_id} at cap ({current}/{ws.max_docs}); "
                    f"delete an upload or raise PG_WORKSPACE_MAX_DOCS"
                )
            conn.execute(
                "INSERT INTO uploads (upload_id, workspace_id, filename, "
                "content_type, size_bytes, storage_path, parser_status, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (upload_id, workspace_id, filename, content_type,
                 size_bytes, storage_path, now),
            )
        return Upload(
            upload_id=upload_id, workspace_id=workspace_id, filename=filename,
            content_type=content_type, size_bytes=size_bytes,
            storage_path=storage_path, parser_status="pending",
            parser_error=None, created_at=now, parsed_at=None, deleted_at=None,
        )

    def get_upload(self, upload_id: str) -> Upload | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        return _row_to_upload(row) if row else None

    def list_uploads(
        self, workspace_id: str, include_deleted: bool = False
    ) -> list[Upload]:
        sql = "SELECT * FROM uploads WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_upload(r) for r in rows]

    def transition_parser_status(
        self,
        upload_id: str,
        new_status: str,
        parser_error: str | None = None,
    ) -> Upload:
        """Atomically transition parser_status. Raises
        WorkspaceStateError if the transition is illegal or the row
        is missing."""
        if new_status not in PARSER_STATUSES:
            raise WorkspaceStateError(f"unknown status: {new_status!r}")
        upload = self.get_upload(upload_id)
        if upload is None:
            raise WorkspaceStateError(f"unknown upload: {upload_id}")
        if upload.deleted_at is not None:
            raise WorkspaceStateError(
                f"upload {upload_id} is soft-deleted; cannot transition"
            )
        allowed = ALLOWED_PARSER_TRANSITIONS.get(upload.parser_status, frozenset())
        if new_status not in allowed:
            raise WorkspaceStateError(
                f"illegal transition {upload.parser_status} → {new_status} "
                f"for upload {upload_id}"
            )
        now = time.time()
        parsed_at = now if new_status == "parsed" else None
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE uploads SET parser_status = ?, parser_error = ?, "
                "parsed_at = COALESCE(?, parsed_at) "
                "WHERE upload_id = ? AND parser_status = ?",
                (new_status, parser_error, parsed_at, upload_id,
                 upload.parser_status),
            )
            if cur.rowcount == 0:
                raise WorkspaceStateError(
                    f"concurrent state change for upload {upload_id}; retry"
                )
        return replace(
            upload,
            parser_status=new_status,
            parser_error=parser_error,
            parsed_at=parsed_at if new_status == "parsed" else upload.parsed_at,
        )

    def soft_delete_upload(self, upload_id: str) -> Upload:
        """Soft-delete an upload. Sets deleted_at; the upload no
        longer counts toward the workspace cap. Audit trail
        preserved (record stays in DB)."""
        upload = self.get_upload(upload_id)
        if upload is None:
            raise WorkspaceStateError(f"unknown upload: {upload_id}")
        if upload.deleted_at is not None:
            return upload  # already deleted; idempotent
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE uploads SET deleted_at = ? WHERE upload_id = ? "
                "AND deleted_at IS NULL",
                (now, upload_id),
            )
        return replace(upload, deleted_at=now)

    # ------------------------------------------------------------------
    # Chunks (parsed content)
    # ------------------------------------------------------------------

    def insert_chunks(
        self,
        upload_id: str,
        chunks: list[tuple[str, dict[str, Any]]],
    ) -> int:
        """Insert parsed chunks for an upload. Each chunk is a
        (text, provenance_dict) tuple where provenance_dict is the
        output of `provenance.to_dict()`. Returns the number
        inserted."""
        upload = self.get_upload(upload_id)
        if upload is None:
            raise WorkspaceStateError(f"unknown upload: {upload_id}")
        rows = []
        for seq, (text, prov_dict) in enumerate(chunks):
            chunk_id = f"ck_{uuid.uuid4().hex[:12]}"
            rows.append((
                chunk_id, upload_id, seq, text, json.dumps(prov_dict),
            ))
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO upload_chunks (chunk_id, upload_id, seq, "
                "text, provenance_json) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def list_chunks(self, upload_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id, upload_id, seq, text, provenance_json "
                "FROM upload_chunks WHERE upload_id = ? ORDER BY seq",
                (upload_id,),
            ).fetchall()
        return [
            {
                "chunk_id": r["chunk_id"],
                "upload_id": r["upload_id"],
                "seq": r["seq"],
                "text": r["text"],
                "provenance": json.loads(r["provenance_json"]),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Internal row converters
# ---------------------------------------------------------------------------


def _row_to_workspace(row: sqlite3.Row) -> Workspace:
    return Workspace(
        workspace_id=row["workspace_id"],
        name=row["name"],
        max_docs=row["max_docs"],
        created_at=row["created_at"],
    )


def _row_to_upload(row: sqlite3.Row) -> Upload:
    return Upload(
        upload_id=row["upload_id"],
        workspace_id=row["workspace_id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        storage_path=row["storage_path"],
        parser_status=row["parser_status"],
        parser_error=row["parser_error"],
        created_at=row["created_at"],
        parsed_at=row["parsed_at"],
        deleted_at=row["deleted_at"],
    )
