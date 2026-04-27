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
    """A workspace.

    Codex M-15b review fix: `org_id` added — every workspace
    belongs to an org, gated by M-15b authz dependencies.
    Workspaces created before M-15b are tagged with the
    sentinel `_DEFAULT_ORG_ID` (see store schema migration);
    the M-15b retrofit treats those as belonging to a notional
    "system" org so cross-org gates still apply consistently.
    """

    workspace_id: str
    name: str
    max_docs: int
    created_at: float
    org_id: str = "org_default"


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
        "org_id": ws.org_id,
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
    created_at REAL NOT NULL,
    org_id TEXT NOT NULL DEFAULT 'org_default'
);

CREATE INDEX IF NOT EXISTS idx_workspaces_org ON workspaces(org_id);

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
            # Codex M-15b review fix: migration for pre-M-15b
            # databases that lack the org_id column. CREATE TABLE
            # IF NOT EXISTS is a no-op when the table already
            # exists, so an old DB never picks up new columns.
            # Add the column lazily here.
            self._migrate_workspaces_org_id(conn)
            self._migrate_uploads_indexes(conn)

    @staticmethod
    def _migrate_workspaces_org_id(conn: sqlite3.Connection) -> None:
        cols = [
            r[1] for r in conn.execute(
                "PRAGMA table_info(workspaces)"
            ).fetchall()
        ]
        if "org_id" not in cols:
            conn.execute(
                "ALTER TABLE workspaces ADD COLUMN org_id TEXT NOT NULL "
                "DEFAULT 'org_default'"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspaces_org "
                "ON workspaces(org_id)"
            )

    @staticmethod
    def _migrate_uploads_indexes(conn: sqlite3.Connection) -> None:
        # Future-proofing hook; no-op for now.
        pass

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    def create_workspace(
        self,
        name: str,
        max_docs: int | None = None,
        org_id: str = "org_default",
    ) -> Workspace:
        """Codex M-15b review fix: `org_id` is now a parameter.
        Defaults to `org_default` so the (small number of)
        Phase A-vintage callers without an org tag still work.
        Phase C callers (M-15b retrofitted endpoints) must pass
        the authenticated caller's org_id."""
        if not name or not name.strip():
            raise WorkspaceStateError("workspace name must be non-empty")
        if max_docs is None:
            max_docs = _env_max_docs()
        if max_docs < 1:
            raise WorkspaceStateError(f"max_docs must be >= 1; got {max_docs}")
        if not org_id or not org_id.strip():
            raise WorkspaceStateError("org_id must be non-empty")
        ws_id = f"ws_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO workspaces (workspace_id, name, max_docs, "
                "created_at, org_id) VALUES (?, ?, ?, ?, ?)",
                (ws_id, name.strip(), max_docs, now, org_id.strip()),
            )
        return Workspace(
            workspace_id=ws_id, name=name.strip(),
            max_docs=max_docs, created_at=now, org_id=org_id.strip(),
        )

    def list_workspaces_for_org(self, org_id: str) -> list[Workspace]:
        """Codex M-15b review fix: list endpoint must scope to the
        caller's org. Plain list_workspaces() is now used only by
        platform-admin code paths."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workspaces WHERE org_id = ? "
                "ORDER BY created_at DESC",
                (org_id,),
            ).fetchall()
        return [_row_to_workspace(r) for r in rows]

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
        unknown.

        Codex M-11 review fix: enforcement is now transactional via
        BEGIN IMMEDIATE — without it, two concurrent uploads could
        both see (max_docs - 1) and oversubscribe the cap. The
        IMMEDIATE lock acquires SQLite's write lock at BEGIN time,
        so the second connection blocks until the first commits.
        """
        if not filename:
            raise WorkspaceStateError("filename must be non-empty")
        if size_bytes < 0:
            raise WorkspaceStateError(f"size_bytes must be >= 0; got {size_bytes}")
        upload_id = f"up_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                ws_row = conn.execute(
                    "SELECT max_docs FROM workspaces WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone()
                if ws_row is None:
                    conn.execute("ROLLBACK")
                    raise WorkspaceStateError(
                        f"unknown workspace: {workspace_id}"
                    )
                max_docs = ws_row["max_docs"]
                cur = conn.execute(
                    "SELECT COUNT(*) FROM uploads "
                    "WHERE workspace_id = ? AND deleted_at IS NULL",
                    (workspace_id,),
                )
                current = cur.fetchone()[0]
                if current >= max_docs:
                    conn.execute("ROLLBACK")
                    raise BoundedError(
                        f"workspace {workspace_id} at cap "
                        f"({current}/{max_docs}); delete an upload or "
                        f"raise PG_WORKSPACE_MAX_DOCS"
                    )
                conn.execute(
                    "INSERT INTO uploads (upload_id, workspace_id, filename, "
                    "content_type, size_bytes, storage_path, parser_status, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (upload_id, workspace_id, filename, content_type,
                     size_bytes, storage_path, now),
                )
                conn.execute("COMMIT")
            except (BoundedError, WorkspaceStateError):
                # Already rolled back above.
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return Upload(
            upload_id=upload_id, workspace_id=workspace_id, filename=filename,
            content_type=content_type, size_bytes=size_bytes,
            storage_path=storage_path, parser_status="pending",
            parser_error=None, created_at=now, parsed_at=None, deleted_at=None,
        )

    def update_storage_path(self, upload_id: str, storage_path: str) -> Upload:
        """Codex M-11 review fix: store-owned storage_path update.
        Avoids the inspector_router layering violation of reaching
        into `store._connect()` directly.

        Codex M-11 v2 review fix: rowcount is checked so a
        concurrent soft-delete cannot make the UPDATE a no-op
        while we return success. Caller (inspector_router) catches
        the resulting WorkspaceStateError and cleans up the bytes
        on disk.
        """
        upload = self.get_upload(upload_id)
        if upload is None:
            raise WorkspaceStateError(f"unknown upload: {upload_id}")
        if upload.deleted_at is not None:
            raise WorkspaceStateError(
                f"upload {upload_id} is soft-deleted; cannot update path"
            )
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE uploads SET storage_path = ? "
                "WHERE upload_id = ? AND deleted_at IS NULL",
                (storage_path, upload_id),
            )
            if cur.rowcount == 0:
                raise WorkspaceStateError(
                    f"upload {upload_id} was soft-deleted concurrently; "
                    f"storage_path not updated"
                )
        return replace(upload, storage_path=storage_path)

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
            # Codex M-11 review fix: include `deleted_at IS NULL` in
            # the atomic UPDATE so a concurrent soft-delete cannot
            # race past the pre-read check and let a deleted row
            # transition.
            cur = conn.execute(
                "UPDATE uploads SET parser_status = ?, parser_error = ?, "
                "parsed_at = COALESCE(?, parsed_at) "
                "WHERE upload_id = ? AND parser_status = ? "
                "AND deleted_at IS NULL",
                (new_status, parser_error, parsed_at, upload_id,
                 upload.parser_status),
            )
            if cur.rowcount == 0:
                raise WorkspaceStateError(
                    f"concurrent state change for upload {upload_id} "
                    f"(soft-deleted or status moved); retry"
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
        inserted.

        Codex M-11 review fix: rejects writes to soft-deleted
        uploads. Without this, a parse already in flight could
        append chunks to a deleted upload — weakening the audit
        meaning of soft-delete.
        """
        upload = self.get_upload(upload_id)
        if upload is None:
            raise WorkspaceStateError(f"unknown upload: {upload_id}")
        if upload.deleted_at is not None:
            raise WorkspaceStateError(
                f"upload {upload_id} is soft-deleted; cannot insert chunks"
            )
        rows = []
        for seq, (text, prov_dict) in enumerate(chunks):
            chunk_id = f"ck_{uuid.uuid4().hex[:12]}"
            rows.append((
                chunk_id, upload_id, seq, text, json.dumps(prov_dict),
            ))
        # Use a transaction so the soft-delete check + insert are
        # atomic relative to a concurrent soft-delete: the INSERT
        # gates on deleted_at via a sub-select.
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                still_live = conn.execute(
                    "SELECT 1 FROM uploads WHERE upload_id = ? "
                    "AND deleted_at IS NULL",
                    (upload_id,),
                ).fetchone()
                if still_live is None:
                    conn.execute("ROLLBACK")
                    raise WorkspaceStateError(
                        f"upload {upload_id} was soft-deleted concurrently; "
                        f"chunks not inserted"
                    )
                conn.executemany(
                    "INSERT INTO upload_chunks (chunk_id, upload_id, seq, "
                    "text, provenance_json) VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
                conn.execute("COMMIT")
            except WorkspaceStateError:
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
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

    def list_eligible_chunks(self, workspace_id: str) -> list[dict[str, Any]]:
        """Codex M-12 review fix: atomic snapshot of all chunks
        eligible for retrieval — single SQL query joining
        upload_chunks to uploads, gated on `uploads.deleted_at IS
        NULL AND uploads.parser_status = 'parsed' AND
        uploads.workspace_id = ?`.

        Replaces the v1 two-phase pattern (list_uploads then
        list_chunks per-upload) which raced soft-delete: a delete
        landing between the two reads let the deleted upload's
        chunks leak into the retrieval set.

        Returns chunk dicts enriched with `filename` from the
        joined uploads row so the retriever doesn't need a second
        lookup.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.chunk_id, c.upload_id, c.seq, c.text, "
                "c.provenance_json, u.filename "
                "FROM upload_chunks c "
                "JOIN uploads u ON u.upload_id = c.upload_id "
                "WHERE u.workspace_id = ? "
                "AND u.deleted_at IS NULL "
                "AND u.parser_status = 'parsed' "
                "ORDER BY u.created_at DESC, c.seq",
                (workspace_id,),
            ).fetchall()
        return [
            {
                "chunk_id": r["chunk_id"],
                "upload_id": r["upload_id"],
                "seq": r["seq"],
                "text": r["text"],
                "provenance": json.loads(r["provenance_json"]),
                "filename": r["filename"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Internal row converters
# ---------------------------------------------------------------------------


def _row_to_workspace(row: sqlite3.Row) -> Workspace:
    # Codex M-15b: tolerant column read so older DBs that ran
    # the migration still work even if the row has no org_id.
    org_id = "org_default"
    try:
        org_id = row["org_id"] or "org_default"
    except (IndexError, KeyError):
        pass
    return Workspace(
        workspace_id=row["workspace_id"],
        name=row["name"],
        max_docs=row["max_docs"],
        created_at=row["created_at"],
        org_id=org_id,
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
