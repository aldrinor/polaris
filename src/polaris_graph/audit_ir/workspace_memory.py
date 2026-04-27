"""Retrieval-active workspace memory (M-21 — Phase C).

Per FINAL_PLAN Phase C deliverable #4:
  Retrieval-active workspace memory (10-18 eng days, Phase C per
  Codex split):
    - User-visible, attributable, removable
    - Retrieved priors LABELED in Evidence Inspector view 1 as
      "memory-derived"
    - Workspace boundaries strict; no cross-customer leakage
    - Freshness/staleness rules

Scope of v1:
  - Persist a workspace's memory entries (claim_text + source_url
    + tier + created_at + workspace_id) in SQLite.
  - retrieve(workspace_id, question) returns the top-K freshest
    memory entries that match question keywords. Pure deterministic
    retrieval — no LLM in the loop, no network.
  - Cross-workspace isolation: every API call requires workspace_id;
    the store layer scopes ALL reads + writes to that single
    workspace. Cross-workspace bleed is the dominant Phase C
    failure mode.
  - Freshness: entries carry created_at; retrieve() respects an
    optional `max_age_days` cutoff.
  - Removable: delete_entry(workspace_id, entry_id) hard-deletes.
    No silent retention.

Out of scope for v1 (intentionally — keep the LAW V "one
responsibility per module" surface narrow):
  - Embedding-based similarity. The keyword-overlap retriever in
    v1 is enough for the Inspector "memory-derived" label
    integration; we add embedding retrieval in a v2 milestone
    when the Phase D memory-quality work begins.
  - Cross-workspace propagation. Per the FINAL_PLAN, global-system
    memory is "quarantined from audit lane by default" — the
    workspace-memory module does not write to that surface, and
    the audit lane never reads from it.
  - Bulk import. Memory entries land via append_entry() one at a
    time, called by the V30 runner when an entry meets a memory-
    worthiness gate (deferred to runner integration).

LAW VII compliance: this module imports only from stdlib. No
reach-back into runner / generator. The endpoint that wires the
store into FastAPI is added in inspector_router.py with the auth
dependency on require_workspace_*.
"""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryEntry:
    """One workspace-memory record.

    `tier` is the same V30 tier vocabulary used by the audit IR
    (T1..T7, UNKNOWN). `source_url` is the canonical source URL the
    claim is grounded in — without it, the Inspector can't
    surface the "memory-derived" label with a back-link, which
    breaks the FINAL_PLAN attribution requirement.
    """

    entry_id: str
    workspace_id: str
    claim_text: str
    source_url: str
    source_tier: str
    source_evidence_id: str | None
    created_at: float
    last_used_at: float | None


def memory_entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "workspace_id": entry.workspace_id,
        "claim_text": entry.claim_text,
        "source_url": entry.source_url,
        "source_tier": entry.source_tier,
        "source_evidence_id": entry.source_evidence_id,
        "created_at": entry.created_at,
        "last_used_at": entry.last_used_at,
    }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkspaceMemoryError(Exception):
    """Base error for workspace-memory operations."""


class WorkspaceMemoryStateError(WorkspaceMemoryError):
    """Invalid input or state transition."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_memory (
    entry_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_tier TEXT NOT NULL,
    source_evidence_id TEXT,
    created_at REAL NOT NULL,
    last_used_at REAL
);

CREATE INDEX IF NOT EXISTS idx_workspace_memory_ws_created
    ON workspace_memory(workspace_id, created_at DESC);

-- Used by retrieve() to walk by-workspace + freshness in one
-- index pass. Without this index a workspace with thousands of
-- entries would full-scan; per the FINAL_PLAN budget of "1000
-- claims per workspace" this matters.
CREATE INDEX IF NOT EXISTS idx_workspace_memory_used
    ON workspace_memory(workspace_id, last_used_at DESC);
"""


# ---------------------------------------------------------------------------
# Tokenization (matches the M-10 stopword/tokenizer pattern so a
# question routed by template_classifier and a memory-retrieval
# call see the same surface vocabulary).
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Conservative stopword list — function words only. Medical/clinical
# content is never filtered.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does",
    "for", "from", "has", "have", "i", "if", "in", "into", "is",
    "it", "its", "of", "on", "or", "that", "the", "their", "them",
    "they", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "you", "your",
})


def _tokenize(text: str) -> set[str]:
    """Lowercase + alphanumeric token set, stopwords removed."""
    if not text:
        return set()
    raw = _TOKEN_RE.findall(text.lower())
    return {t for t in raw if t not in _STOPWORDS and len(t) > 1}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class WorkspaceMemoryStore:
    """SQLite-backed workspace memory.

    Per-call connections (matches WorkspaceStore + JobQueue +
    ReviewStore pattern). WAL journal for concurrent reads.
    Cross-workspace isolation: every method takes workspace_id
    and SQL filters on it.
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
    # Append
    # ------------------------------------------------------------------

    def append_entry(
        self,
        *,
        workspace_id: str,
        claim_text: str,
        source_url: str,
        source_tier: str,
        source_evidence_id: str | None = None,
    ) -> MemoryEntry:
        """Persist one memory entry. Cross-workspace isolation: the
        entry is bound to workspace_id; reads from another workspace
        cannot see it."""
        if not workspace_id.strip():
            raise WorkspaceMemoryStateError(
                "workspace_id must be non-empty"
            )
        claim = claim_text.strip()
        if not claim:
            raise WorkspaceMemoryStateError(
                "claim_text must be non-empty after stripping; "
                "memory entries must carry concrete prose"
            )
        url = source_url.strip()
        if not url:
            raise WorkspaceMemoryStateError(
                "source_url must be non-empty; the Inspector cannot "
                "show a memory-derived label without an attribution "
                "link to the original source"
            )
        tier = (source_tier or "").strip()
        if not tier:
            raise WorkspaceMemoryStateError(
                "source_tier must be non-empty; tier is part of the "
                "memory-derived attribution surface"
            )
        entry_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO workspace_memory (entry_id, workspace_id, "
                "claim_text, source_url, source_tier, "
                "source_evidence_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id, workspace_id.strip(), claim, url, tier,
                    (source_evidence_id or None), now,
                ),
            )
        return MemoryEntry(
            entry_id=entry_id, workspace_id=workspace_id.strip(),
            claim_text=claim, source_url=url, source_tier=tier,
            source_evidence_id=(source_evidence_id or None),
            created_at=now, last_used_at=None,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_entry(
        self, *, workspace_id: str, entry_id: str,
    ) -> MemoryEntry | None:
        """Single-entry read. Returns None if the entry doesn't
        exist OR if it belongs to a different workspace (no
        existence leak)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_memory "
                "WHERE entry_id = ? AND workspace_id = ?",
                (entry_id, workspace_id),
            ).fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def list_entries(
        self,
        *,
        workspace_id: str,
        max_age_days: float | None = None,
    ) -> list[MemoryEntry]:
        """List entries for a workspace, newest first.

        `max_age_days` (FINAL_PLAN: freshness/staleness rules) is
        applied at SQL level: entries older than the cutoff are
        excluded. Pass None to disable the cutoff.
        """
        if max_age_days is not None and max_age_days < 0:
            raise WorkspaceMemoryStateError(
                "max_age_days must be >= 0 if provided"
            )
        params: list[Any] = [workspace_id]
        sql = (
            "SELECT * FROM workspace_memory WHERE workspace_id = ? "
        )
        if max_age_days is not None:
            cutoff = time.time() - max_age_days * 86400.0
            sql += "AND created_at >= ? "
            params.append(cutoff)
        sql += "ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    # ------------------------------------------------------------------
    # Retrieve (the active piece — for the runner to call before
    # generating)
    # ------------------------------------------------------------------

    def retrieve(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int = 10,
        max_age_days: float | None = None,
    ) -> list[tuple[MemoryEntry, float]]:
        """Return up to `top_k` entries matching `query` keywords,
        scored by Jaccard overlap on stopword-filtered tokens.
        Each result is (entry, score) with score in [0, 1].

        Side effect: bumps `last_used_at` on each retrieved entry
        so freshness ranking can favor recently-useful memory.
        Per LAW II we surface this as deterministic SQL rather
        than a "magic refresh" — caller can audit the timestamps.

        Cross-workspace isolation: only entries from workspace_id
        are even considered. The retrieval cannot leak across
        workspaces because the SQL WHERE filters on it.
        """
        if not workspace_id.strip():
            raise WorkspaceMemoryStateError(
                "workspace_id must be non-empty"
            )
        if top_k < 1:
            raise WorkspaceMemoryStateError("top_k must be >= 1")
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        entries = self.list_entries(
            workspace_id=workspace_id, max_age_days=max_age_days,
        )
        scored: list[tuple[MemoryEntry, float]] = []
        for e in entries:
            e_tokens = _tokenize(e.claim_text)
            if not e_tokens:
                continue
            inter = q_tokens & e_tokens
            if not inter:
                continue
            union = q_tokens | e_tokens
            jaccard = len(inter) / len(union)
            scored.append((e, jaccard))
        scored.sort(key=lambda t: (-t[1], -t[0].created_at))
        top = scored[:top_k]

        if top:
            now = time.time()
            ids = [e.entry_id for (e, _s) in top]
            placeholders = ",".join("?" * len(ids))
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE workspace_memory SET last_used_at = ? "
                    f"WHERE workspace_id = ? AND entry_id IN ({placeholders})",
                    [now, workspace_id, *ids],
                )

        return top

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_entry(
        self, *, workspace_id: str, entry_id: str,
    ) -> bool:
        """Hard-delete one entry. Returns True if a row was deleted,
        False otherwise (entry didn't exist or belonged to another
        workspace).

        Per FINAL_PLAN, memory must be user-removable. Hard delete
        (no soft-delete tombstones) so customers can guarantee a
        deletion request actually purged the underlying data.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM workspace_memory "
                "WHERE entry_id = ? AND workspace_id = ?",
                (entry_id, workspace_id),
            )
        return cur.rowcount > 0

    def delete_all_for_workspace(self, *, workspace_id: str) -> int:
        """Bulk-delete every entry for a workspace.

        Used by workspace deletion / audit-bundle "wipe" requests.
        Returns the number of rows deleted.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM workspace_memory WHERE workspace_id = ?",
                (workspace_id,),
            )
        return cur.rowcount


# ---------------------------------------------------------------------------
# Row → object converter
# ---------------------------------------------------------------------------


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        entry_id=row["entry_id"],
        workspace_id=row["workspace_id"],
        claim_text=row["claim_text"],
        source_url=row["source_url"],
        source_tier=row["source_tier"],
        source_evidence_id=row["source_evidence_id"],
        created_at=float(row["created_at"]),
        last_used_at=(
            float(row["last_used_at"]) if row["last_used_at"] is not None
            else None
        ),
    )
