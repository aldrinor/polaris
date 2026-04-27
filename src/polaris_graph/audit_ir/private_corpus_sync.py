"""Narrow private-corpus sync (M-25 — Phase C).

Per FINAL_PLAN Phase C deliverable #7:
  Narrow private-corpus sync (Drive/SharePoint/Confluence —
  approved-only, NOT broad connector parity).

Scope of v1:
  - Per-workspace approved-source registry. A "source" is one
    operator-approved external location (e.g. a specific Drive
    folder, a SharePoint site, a Confluence space). Operators
    must explicitly approve a source before sync.
  - Append-only sync_runs log per source — every sync attempt
    writes one row (status, started_at, finished_at, doc_count,
    bytes_synced, error_message). Customers can audit "when was
    Confluence Space X last synced?" without admin access.
  - Cross-workspace isolation: a source belongs to ONE workspace;
    cross-workspace reads return empty/None.
  - Approval gate: register_source() defaults status=PENDING; a
    separate approve_source() / revoke_source() lifecycle gates
    actual sync.

Out of scope for v1 (intentionally narrow per FINAL_PLAN):
  - Actual Drive/SharePoint/Confluence client integrations. v1
    is the registry + status surface; v2 wires the connectors.
  - OAuth credential storage. v1 stores opaque credential
    references (token IDs, service-account names) but does NOT
    store secrets — secrets live in a separate vault.
  - Differential sync, conflict resolution, deletion propagation.

LAW VII compliance: stdlib only. Endpoints wired separately.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SourceConnector(Enum):
    """Closed list of supported connector types. Per FINAL_PLAN
    "narrow scope, NOT broad connector parity" — only the three
    connector types Phase C explicitly names."""

    GOOGLE_DRIVE = "google_drive"
    SHAREPOINT = "sharepoint"
    CONFLUENCE = "confluence"


class SourceStatus(Enum):
    PENDING = "pending"  # registered, awaiting operator approval
    APPROVED = "approved"  # operator approved; sync may run
    REVOKED = "revoked"  # operator revoked; further syncs refused


class SyncRunStatus(Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusSource:
    """One approved external corpus source.

    `external_uri` is the connector-specific identifier:
      Drive: folder ID (e.g. "1AbC...")
      SharePoint: site URL (e.g. "https://contoso.sharepoint.com/sites/X")
      Confluence: space key (e.g. "ENG")

    `credential_ref` points to an external secrets-vault entry
    (e.g. "vault://service-accounts/drive-corpus-svc"); the
    secret value itself is NEVER stored here.
    """

    source_id: str
    workspace_id: str
    org_id: str
    connector: SourceConnector
    name: str
    external_uri: str
    credential_ref: str
    status: SourceStatus
    approved_by: str | None
    revoked_by: str | None
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class SyncRun:
    """One sync-attempt record.

    `bytes_synced` and `doc_count` may be 0 if the sync errored
    before fetching anything; check `status` first.
    `error_message` carries the connector error string when status
    is FAILED or PARTIAL.
    """

    sync_run_id: str
    source_id: str
    triggered_by_user_id: str
    status: SyncRunStatus
    doc_count: int
    bytes_synced: int
    error_message: str | None
    started_at: float
    finished_at: float | None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PrivateCorpusSyncError(Exception):
    """Base error for private-corpus sync operations."""


class SourceStateError(PrivateCorpusSyncError):
    """Invalid input or state transition."""


class SyncBlockedError(PrivateCorpusSyncError):
    """Sync attempted on a non-APPROVED source."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS corpus_sources (
    source_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    connector TEXT NOT NULL,
    name TEXT NOT NULL,
    external_uri TEXT NOT NULL,
    credential_ref TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT,
    revoked_by TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_corpus_sources_workspace
    ON corpus_sources(workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_corpus_sources_org
    ON corpus_sources(org_id, status);

CREATE TABLE IF NOT EXISTS sync_runs (
    sync_run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    triggered_by_user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0,
    bytes_synced INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at REAL NOT NULL,
    finished_at REAL,
    FOREIGN KEY (source_id) REFERENCES corpus_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_source_started
    ON sync_runs(source_id, started_at DESC);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class PrivateCorpusSyncStore:
    """SQLite-backed registry of approved external corpus sources
    and their sync history.

    Per-call connections; WAL mode; foreign keys enforced; mutating
    paths use BEGIN IMMEDIATE so concurrent approve/revoke calls
    serialize.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path, isolation_level=None, timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Source registration + lifecycle
    # ------------------------------------------------------------------

    def register_source(
        self,
        *,
        workspace_id: str,
        org_id: str,
        connector: SourceConnector,
        name: str,
        external_uri: str,
        credential_ref: str,
    ) -> CorpusSource:
        """Register a new external source. Lands in PENDING; an
        operator must call approve_source() before sync_now() will
        succeed."""
        if not workspace_id.strip() or not org_id.strip():
            raise SourceStateError(
                "workspace_id and org_id must be non-empty"
            )
        if not isinstance(connector, SourceConnector):
            raise SourceStateError(
                f"connector must be SourceConnector; got {connector!r}"
            )
        if not name.strip():
            raise SourceStateError("name must be non-empty")
        if not external_uri.strip():
            raise SourceStateError("external_uri must be non-empty")
        if not credential_ref.strip():
            raise SourceStateError(
                "credential_ref must be non-empty (a vault pointer; "
                "secrets must NOT be stored here)"
            )
        # Defense in depth: refuse any credential_ref that looks
        # like a raw secret. Vault references should never contain
        # JWT prefixes, common access-key prefixes, or PEM markers.
        if _looks_like_raw_secret(credential_ref):
            raise SourceStateError(
                "credential_ref appears to contain a raw secret; "
                "store secrets in a vault and pass an opaque pointer"
            )
        source_id = f"src_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO corpus_sources (source_id, workspace_id, "
                "org_id, connector, name, external_uri, "
                "credential_ref, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id, workspace_id.strip(), org_id.strip(),
                    connector.value, name.strip(),
                    external_uri.strip(), credential_ref.strip(),
                    SourceStatus.PENDING.value, now, now,
                ),
            )
        return CorpusSource(
            source_id=source_id, workspace_id=workspace_id.strip(),
            org_id=org_id.strip(), connector=connector,
            name=name.strip(), external_uri=external_uri.strip(),
            credential_ref=credential_ref.strip(),
            status=SourceStatus.PENDING,
            approved_by=None, revoked_by=None,
            created_at=now, updated_at=now,
        )

    def approve_source(
        self, *, source_id: str, org_id: str, approver_user_id: str,
    ) -> CorpusSource:
        """Operator approves a source for sync."""
        return self._transition_source(
            source_id=source_id, org_id=org_id,
            actor_user_id=approver_user_id,
            from_states=(
                SourceStatus.PENDING, SourceStatus.REVOKED,
            ),
            to_state=SourceStatus.APPROVED, set_approved_by=True,
        )

    def revoke_source(
        self, *, source_id: str, org_id: str, revoker_user_id: str,
    ) -> CorpusSource:
        """Operator revokes a previously-approved source. Future
        sync_now() calls raise SyncBlockedError. Already-completed
        sync history is preserved (append-only)."""
        return self._transition_source(
            source_id=source_id, org_id=org_id,
            actor_user_id=revoker_user_id,
            from_states=(
                SourceStatus.APPROVED, SourceStatus.PENDING,
            ),
            to_state=SourceStatus.REVOKED, set_revoked_by=True,
        )

    def _transition_source(
        self,
        *,
        source_id: str,
        org_id: str,
        actor_user_id: str,
        from_states: tuple[SourceStatus, ...],
        to_state: SourceStatus,
        set_approved_by: bool = False,
        set_revoked_by: bool = False,
    ) -> CorpusSource:
        if not actor_user_id.strip():
            raise SourceStateError(
                "actor_user_id must be non-empty"
            )
        from_values = tuple(s.value for s in from_states)
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM corpus_sources WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
                if row is None:
                    raise SourceStateError(
                        f"source {source_id!r} not found"
                    )
                if row["org_id"] != org_id:
                    raise SourceStateError(
                        f"source {source_id!r} belongs to a "
                        f"different org"
                    )
                current = SourceStatus(row["status"])
                if current not in from_states:
                    raise SourceStateError(
                        f"source {source_id!r} is in state "
                        f"{current.value!r}; expected one of "
                        f"{from_values} to transition to "
                        f"{to_state.value!r}"
                    )
                set_parts = ["status = ?", "updated_at = ?"]
                params: list[Any] = [to_state.value, now]
                if set_approved_by:
                    set_parts.append("approved_by = ?")
                    set_parts.append("revoked_by = NULL")
                    params.append(actor_user_id.strip())
                if set_revoked_by:
                    set_parts.append("revoked_by = ?")
                    params.append(actor_user_id.strip())
                params.append(source_id)
                conn.execute(
                    f"UPDATE corpus_sources SET {', '.join(set_parts)} "
                    f"WHERE source_id = ?",
                    params,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        result = self.get_source(source_id=source_id, org_id=org_id)
        if result is None:
            raise PrivateCorpusSyncError(
                f"transitioned source {source_id!r} but cannot read it back"
            )
        return result

    # ------------------------------------------------------------------
    # Sync attempts
    # ------------------------------------------------------------------

    def record_sync_run(
        self,
        *,
        source_id: str,
        org_id: str,
        triggered_by_user_id: str,
        status: SyncRunStatus,
        doc_count: int = 0,
        bytes_synced: int = 0,
        error_message: str | None = None,
    ) -> SyncRun:
        """Record one completed sync attempt. v1 doesn't actually
        run the sync; the runner / connector calls this to log
        the attempt outcome.

        Refuses if the source is not APPROVED — this is the gate
        FINAL_PLAN's "approved-only, NOT broad connector parity"
        requirement enforces.
        """
        if not triggered_by_user_id.strip():
            raise SourceStateError(
                "triggered_by_user_id must be non-empty"
            )
        if doc_count < 0 or bytes_synced < 0:
            raise SourceStateError(
                "doc_count and bytes_synced must be >= 0"
            )
        if not isinstance(status, SyncRunStatus):
            raise SourceStateError(
                f"status must be SyncRunStatus; got {status!r}"
            )
        source = self.get_source(source_id=source_id, org_id=org_id)
        if source is None:
            raise SourceStateError(
                f"source {source_id!r} is not accessible to this caller"
            )
        if source.status != SourceStatus.APPROVED:
            raise SyncBlockedError(
                f"source {source_id!r} is in state "
                f"{source.status.value!r}; sync only allowed when "
                f"approved"
            )
        sync_run_id = f"sync_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sync_runs (sync_run_id, source_id, "
                "triggered_by_user_id, status, doc_count, "
                "bytes_synced, error_message, started_at, "
                "finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sync_run_id, source_id,
                    triggered_by_user_id.strip(), status.value,
                    int(doc_count), int(bytes_synced),
                    error_message, now, now,
                ),
            )
        return SyncRun(
            sync_run_id=sync_run_id, source_id=source_id,
            triggered_by_user_id=triggered_by_user_id.strip(),
            status=status, doc_count=int(doc_count),
            bytes_synced=int(bytes_synced),
            error_message=error_message, started_at=now, finished_at=now,
        )

    def list_sync_runs(
        self, *, source_id: str, org_id: str, limit: int = 100,
    ) -> list[SyncRun]:
        if limit < 1 or limit > 1000:
            raise SourceStateError(
                f"limit must be in [1, 1000]; got {limit}"
            )
        # Org-scope check first.
        if self.get_source(source_id=source_id, org_id=org_id) is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_runs WHERE source_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (source_id, limit),
            ).fetchall()
        return [_row_to_sync_run(r) for r in rows]

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def get_source(
        self, *, source_id: str, org_id: str,
    ) -> CorpusSource | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM corpus_sources "
                "WHERE source_id = ? AND org_id = ?",
                (source_id, org_id),
            ).fetchone()
        return _row_to_source(row) if row is not None else None

    def list_sources_for_workspace(
        self,
        *,
        workspace_id: str,
        org_id: str,
        status: SourceStatus | None = None,
    ) -> list[CorpusSource]:
        clauses = ["workspace_id = ?", "org_id = ?"]
        params: list[Any] = [workspace_id, org_id]
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        sql = (
            f"SELECT * FROM corpus_sources WHERE "
            f"{' AND '.join(clauses)} ORDER BY created_at DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_source(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_like_raw_secret(value: str) -> bool:
    """Heuristic: refuse common raw-secret shapes so a misuse of
    register_source won't quietly persist a credential.

    This is defense in depth — the canonical guidance is "pass
    a vault pointer, not the secret itself."
    """
    v = value.strip()
    if v.startswith("eyJ") and len(v) > 60:  # JWT
        return True
    if v.startswith(("AKIA", "ASIA")) and len(v) >= 16:  # AWS access key
        return True
    if "BEGIN PRIVATE KEY" in v or "BEGIN RSA PRIVATE KEY" in v:
        return True
    if v.startswith("ghp_") and len(v) > 20:  # GitHub PAT
        return True
    if v.startswith(("sk-", "pk-")) and len(v) > 20:  # OpenAI-style
        return True
    return False


def _row_to_source(row: sqlite3.Row) -> CorpusSource:
    return CorpusSource(
        source_id=row["source_id"],
        workspace_id=row["workspace_id"],
        org_id=row["org_id"],
        connector=SourceConnector(row["connector"]),
        name=row["name"],
        external_uri=row["external_uri"],
        credential_ref=row["credential_ref"],
        status=SourceStatus(row["status"]),
        approved_by=row["approved_by"],
        revoked_by=row["revoked_by"],
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _row_to_sync_run(row: sqlite3.Row) -> SyncRun:
    return SyncRun(
        sync_run_id=row["sync_run_id"],
        source_id=row["source_id"],
        triggered_by_user_id=row["triggered_by_user_id"],
        status=SyncRunStatus(row["status"]),
        doc_count=int(row["doc_count"]),
        bytes_synced=int(row["bytes_synced"]),
        error_message=row["error_message"],
        started_at=float(row["started_at"]),
        finished_at=(
            float(row["finished_at"]) if row["finished_at"] is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def source_to_dict(s: CorpusSource) -> dict[str, Any]:
    return {
        "source_id": s.source_id,
        "workspace_id": s.workspace_id,
        "org_id": s.org_id,
        "connector": s.connector.value,
        "name": s.name,
        "external_uri": s.external_uri,
        "credential_ref": s.credential_ref,
        "status": s.status.value,
        "approved_by": s.approved_by,
        "revoked_by": s.revoked_by,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def sync_run_to_dict(r: SyncRun) -> dict[str, Any]:
    return {
        "sync_run_id": r.sync_run_id,
        "source_id": r.source_id,
        "triggered_by_user_id": r.triggered_by_user_id,
        "status": r.status.value,
        "doc_count": r.doc_count,
        "bytes_synced": r.bytes_synced,
        "error_message": r.error_message,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
    }
