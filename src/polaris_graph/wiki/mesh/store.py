"""
MeshStore — CRUD layer over a POLARIS wiki mesh database.

The mesh is stored in a single SQLite file with sqlite-vec for vector
similarity search. This eliminates the dual-store consistency bug (FIX D1
from the advisor review) — one file, one transaction, one source of truth.

Usage:

    from src.polaris_graph.wiki.mesh import MeshStore
    store = MeshStore.open("wiki/workspaces/pfas/mesh.db")

    with store.transaction():
        ws_id = store.create_workspace(name="PFAS study", root_question="...")
        src_id = store.insert_source(
            workspace_id=ws_id,
            kind="upload",
            filepath="sources/upload_xyz.md",
            content_hash="a7f3...",
            sig_authority=0.95,
        )
        clm_id = store.insert_claim(
            workspace_id=ws_id,
            source_page_id=src_id,
            statement="GAC filters remove 85% of long-chain PFAS.",
            direct_quote="Granular activated carbon achieved 85% removal",
            char_start=1024,
            char_end=1080,
            tier="GOLD",
            relevance_score=0.91,
            embedding=emb_vector,  # numpy float32 array, dim 384
        )

    # Later, in a retrieval path:
    results = store.search_claims_by_vector(
        workspace_id=ws_id,
        query_embedding=q_emb,
        k=40,
        tier_filter=("GOLD", "SILVER"),
    )

Fail-loudly policy (LAW II): every method raises on unrecoverable errors.
No silent fallbacks, no partial inserts.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


def _now_iso() -> str:
    """Current UTC time as ISO-8601 string. Tz-aware to avoid Python 3.13+
    `datetime.utcnow()` deprecation."""
    return datetime.now(timezone.utc).isoformat()

try:
    import sqlite_vec
    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _SQLITE_VEC_AVAILABLE = False

from .schema import CORE_DDL, SCHEMA_VERSION, VECTOR_DDL, create_schema


class MeshStoreError(Exception):
    """Raised when the mesh store encounters an unrecoverable error."""


# ───── constants ─────

EMBEDDING_DIM = 384  # matches schema.VECTOR_DDL float[384] and production embed_texts

# Over-fetch multiplier for KNN + post-filter pattern (advisor fix).
# When a vec0 KNN query is combined with a tier/flagged/workspace filter,
# the KNN runs first over ALL vectors and filters apply second. If the
# true top-k are outside the filter, results are silently truncated. We
# over-fetch by this multiplier, then apply filters, then LIMIT k.
_KNN_OVERFETCH_MULT = 3

# Max allowed edge usage_boost (FIX S4). Schema enforces this with a CHECK
# constraint; the constant here is for bump helpers that must clamp.
EDGE_USAGE_BOOST_MAX = 0.2

# FIX-CANON: Undirected edge kinds where (A→B) == (B→A). For these kinds,
# insert_edge canonicalizes the pair (claim_a < claim_b alphabetically)
# and get_edges_from queries both columns.
_UNDIRECTED_EDGE_KINDS = frozenset({"corroborates", "contradicts"})


# ───── the store ─────

class MeshStore:
    """
    Thin CRUD layer over a mesh database.

    Hold one per workspace mesh.db file. Not thread-safe — each thread
    must use its own MeshStore instance or serialize access.
    """

    def __init__(self, conn: sqlite3.Connection, db_path: Path):
        self._conn = conn
        self._db_path = db_path

    # ─────────── lifecycle ───────────

    @classmethod
    def open(
        cls, db_path: str | Path, *, check_same_thread: bool = True,
    ) -> "MeshStore":
        """
        Open (or create) a mesh database at `db_path`.

        If the file does not exist, a fresh schema is created. If it exists,
        the schema version is verified against SCHEMA_VERSION. A mismatch
        raises MeshStoreError (no auto-migration — the caller must run a
        migration script).

        Raises MeshStoreError if sqlite-vec is unavailable.
        """
        if not _SQLITE_VEC_AVAILABLE:
            raise MeshStoreError(
                "sqlite-vec is required for the mesh store. "
                "Install: pip install sqlite-vec"
            )

        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # isolation_level=None gives us explicit BEGIN/COMMIT/ROLLBACK control.
        # This matters because Python's sqlite3 auto-opens implicit
        # transactions before data-modifying statements, which would prevent
        # the transaction context manager from working cleanly.
        conn = sqlite3.connect(
            db_path, isolation_level=None,
            check_same_thread=check_same_thread,
        )
        conn.row_factory = sqlite3.Row

        # Load sqlite-vec extension (required before creating vec0 tables).
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)

        # Pragmas for correctness and performance.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        create_schema(conn)

        store = cls(conn, db_path)
        store._verify_schema_version()
        return store

    def _verify_schema_version(self) -> None:
        row = self._conn.execute(
            "SELECT value FROM mesh_meta WHERE key = 'schema_version'"
        ).fetchone()
        if not row:
            raise MeshStoreError(
                "mesh_meta missing schema_version — database corrupt"
            )
        if int(row["value"]) != SCHEMA_VERSION:
            raise MeshStoreError(
                f"Schema version mismatch: db={row['value']}, "
                f"code={SCHEMA_VERSION}. Migration required."
            )

    def close(self) -> None:
        self._conn.close()

    @property
    def db_path(self) -> Path:
        """Absolute path to the mesh database file."""
        return self._db_path

    @property
    def workspace_dir(self) -> Path:
        """
        Directory containing the mesh database.

        By convention the layout is:
            wiki/workspaces/{workspace_id}/
                mesh.db                     ← the file `db_path` points to
                sources/{src_id}.md         ← markdown written by ingest.py
                artifacts/{answer_id}/...   ← rendered artifacts
                snapshots/...               ← snapshots

        Ingest and export code should derive subdirectory paths from this
        property instead of poking at `_db_path` directly.
        """
        return self._db_path.parent

    @property
    def sources_dir(self) -> Path:
        """Directory where source markdown files live. Created lazily by ingest."""
        return self._db_path.parent / "sources"

    @contextlib.contextmanager
    def transaction(self) -> Iterator["MeshStore"]:
        """
        Atomic transaction. All-or-nothing across SQL + vector ops.

        FIX D1 relies on this: every insert_claim that takes an embedding
        writes to both the `claims` table and the `vec_claims` virtual
        table in the same transaction. Rollback rolls both back (verified
        empirically against sqlite-vec 0.1.6).
        """
        self._conn.execute("BEGIN")
        try:
            yield self
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ─────────── workspaces ───────────

    def create_workspace(
        self,
        *,
        name: str,
        root_question: str | None = None,
        owner: str | None = None,
        nearby_budget_daily: int = 50,
    ) -> str:
        ws_id = self._make_id("ws", f"{name}:{_now_iso()}")
        self._conn.execute(
            """INSERT INTO workspaces
               (id, name, owner, root_question, created_at,
                nearby_expansion_budget_daily)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ws_id, name, owner, root_question,
             _now_iso(), nearby_budget_daily),
        )
        return ws_id

    def get_workspace(self, workspace_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM workspaces ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_workspace(self, workspace_id: str) -> None:
        """Deletes the workspace row — FK cascade removes sources, claims,
        edges, entities, topics, questions, answers, op_log for this ws.
        Vector rows are left behind (they are in vec_* tables which have
        no FK); call `vacuum_orphan_vectors()` afterward if needed."""
        self._conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))

    # ─────────── source pages ───────────

    def insert_source(
        self,
        *,
        workspace_id: str,
        kind: str,
        filepath: str,
        content_hash: str,
        sig_authority: float,
        title: str | None = None,
        url: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        doi: str | None = None,
        venue: str | None = None,
        word_count: int | None = None,
        source_embedding: "Any | None" = None,
    ) -> str:
        """
        Insert a source_page row. Returns src_id.

        Raises MeshStoreError if a source with the same content_hash
        already exists in this workspace (use `source_id_by_hash()` to
        check first if you want dedup semantics).
        """
        if kind not in ("web", "upload", "api"):
            raise MeshStoreError(f"Invalid source kind: {kind!r}")
        if not (0.0 <= sig_authority <= 1.0):
            raise MeshStoreError(
                f"sig_authority must be in [0, 1], got {sig_authority}"
            )

        src_id = self._make_id("src", f"{workspace_id}:{content_hash}")
        try:
            self._conn.execute(
                """INSERT INTO source_pages
                   (id, workspace_id, kind, url, filepath, title, authors,
                    year, doi, venue, fetched_at, content_hash, word_count,
                    sig_authority)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (src_id, workspace_id, kind, url, filepath, title,
                 json.dumps(authors) if authors else None,
                 year, doi, venue, _now_iso(),
                 content_hash, word_count, sig_authority),
            )
        except sqlite3.IntegrityError as e:
            raise MeshStoreError(
                f"Source with content_hash={content_hash[:12]}... "
                f"already exists in workspace {workspace_id}"
            ) from e

        if source_embedding is not None:
            self._insert_vector("vec_sources", src_id, source_embedding)

        self._conn.execute(
            "UPDATE workspaces SET source_count = source_count + 1 WHERE id = ?",
            (workspace_id,),
        )
        return src_id

    def get_source(self, src_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM source_pages WHERE id = ?", (src_id,)
        ).fetchone()
        return dict(row) if row else None

    def source_id_by_hash(
        self, workspace_id: str, content_hash: str
    ) -> str | None:
        row = self._conn.execute(
            """SELECT id FROM source_pages
               WHERE workspace_id = ? AND content_hash = ?""",
            (workspace_id, content_hash),
        ).fetchone()
        return row["id"] if row else None

    def increment_source_citation(self, src_id: str) -> None:
        """Snowball (M1): bump times_cited when a source is used in an
        answer."""
        self._conn.execute(
            """UPDATE source_pages
               SET times_cited = times_cited + 1,
                   last_used_at = ?
               WHERE id = ?""",
            (_now_iso(), src_id),
        )

    # ─────────── claims ───────────

    def insert_claim(
        self,
        *,
        workspace_id: str,
        source_page_id: str,
        statement: str,
        direct_quote: str,
        char_start: int,
        char_end: int,
        tier: str,
        relevance_score: float,
        has_numeric: bool = False,
        embedding: "Any | None" = None,
    ) -> str:
        if tier not in ("GOLD", "SILVER", "BRONZE"):
            raise MeshStoreError(f"Invalid tier: {tier!r}")
        if not (0.0 <= relevance_score <= 1.0):
            raise MeshStoreError(
                f"relevance_score must be in [0, 1], got {relevance_score}"
            )
        if char_start < 0 or char_end <= char_start:
            raise MeshStoreError(
                f"Invalid char span: [{char_start}, {char_end})"
            )

        clm_id = self._make_id(
            "clm", f"{source_page_id}:{char_start}:{statement[:50]}"
        )
        try:
            self._conn.execute(
                """INSERT INTO claims
                   (id, workspace_id, source_page_id, statement, direct_quote,
                    char_start, char_end, tier, relevance_score, has_numeric,
                    extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (clm_id, workspace_id, source_page_id, statement, direct_quote,
                 char_start, char_end, tier, relevance_score,
                 1 if has_numeric else 0, _now_iso()),
            )
        except sqlite3.IntegrityError:
            # Idempotent: same source + same char_start + same leading
            # 50 chars of statement → same deterministic claim id. This
            # happens when Unit 2 re-extracts a source (update path).
            # Preserve the existing row, re-embed if a new embedding was
            # provided (allows switching embedding models), and return
            # the existing id without bumping claim_count.
            if embedding is not None:
                self._insert_vector("vec_claims", clm_id, embedding)
            return clm_id

        if embedding is not None:
            self._insert_vector("vec_claims", clm_id, embedding)

        self._conn.execute(
            "UPDATE workspaces SET claim_count = claim_count + 1 WHERE id = ?",
            (workspace_id,),
        )
        return clm_id

    def get_claim(self, clm_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM claims WHERE id = ?", (clm_id,)
        ).fetchone()
        return dict(row) if row else None

    def increment_claim_usage(self, clm_id: str) -> None:
        """Snowball (M1): bump times_used when a claim is retrieved.

        The age-decayed bonus in FIX D3 is applied at re-rank time in
        retrieve/lethal.py — this method only bumps the raw counter.
        """
        self._conn.execute(
            """UPDATE claims
               SET times_used = times_used + 1,
                   last_used_at = ?
               WHERE id = ?""",
            (_now_iso(), clm_id),
        )

    def flag_claim(self, clm_id: str, reason: str) -> None:
        """G5: user override — mark a claim as wrong."""
        self._conn.execute(
            "UPDATE claims SET flagged = 1, flagged_reason = ? WHERE id = ?",
            (reason, clm_id),
        )

    # ─────────── edges ───────────

    def insert_edge(
        self,
        *,
        workspace_id: str,
        claim_a: str,
        claim_b: str,
        kind: str,
        evidence_weight: float,
        discovery_method: str,
    ) -> str:
        """
        Insert an edge between two claims.

        FIX S4: `evidence_weight` is the IMMUTABLE part (from NLI/cosine at
        discovery time). The mutable `usage_boost` column starts at 0 and
        is bumped via `bump_edge_usage_boost()` — capped at +0.2.
        """
        if kind not in ("corroborates", "contradicts", "elaborates", "cites"):
            raise MeshStoreError(f"Invalid edge kind: {kind!r}")
        if not (0.0 <= evidence_weight <= 1.0):
            raise MeshStoreError(
                f"evidence_weight must be in [0, 1], got {evidence_weight}"
            )

        # FIX-CANON: For undirected edge kinds, canonicalize pair order
        # so that (A,B) and (B,A) always produce the same row. This lets
        # the DB UNIQUE(claim_a, claim_b, kind) constraint catch dupes
        # across separate discover_edges calls (the in-memory seen_pairs
        # set only works within a single call).
        if kind in _UNDIRECTED_EDGE_KINDS:
            claim_a, claim_b = sorted([claim_a, claim_b])

        edge_id = self._make_id(
            "edg", f"{claim_a}:{claim_b}:{kind}"
        )
        try:
            self._conn.execute(
                """INSERT INTO edges
                   (id, workspace_id, claim_a, claim_b, kind,
                    evidence_weight, usage_boost, discovered_at,
                    discovery_method)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (edge_id, workspace_id, claim_a, claim_b, kind,
                 evidence_weight, _now_iso(),
                 discovery_method),
            )
        except sqlite3.IntegrityError:
            # Edge already exists (UNIQUE on claim_a,claim_b,kind) —
            # idempotent, return the existing id.
            existing = self._conn.execute(
                """SELECT id FROM edges
                   WHERE claim_a = ? AND claim_b = ? AND kind = ?""",
                (claim_a, claim_b, kind),
            ).fetchone()
            if existing:
                return existing["id"]
            raise

        self._conn.execute(
            "UPDATE workspaces SET edge_count = edge_count + 1 WHERE id = ?",
            (workspace_id,),
        )
        return edge_id

    def bump_edge_usage_boost(
        self, edge_id: str, delta: float = 0.02
    ) -> None:
        """
        FIX S4: bump an edge's usage_boost, clamped to [0, 0.2].

        Using MIN() in SQL guarantees the cap is enforced even if the
        CHECK constraint on the schema is somehow bypassed.
        """
        self._conn.execute(
            """UPDATE edges
               SET usage_boost = MIN(?, usage_boost + ?)
               WHERE id = ?""",
            (EDGE_USAGE_BOOST_MAX, delta, edge_id),
        )

    def get_edges_from(
        self,
        claim_id: str,
        kind: str | None = None,
        min_evidence_weight: float = 0.0,
    ) -> list[dict]:
        """Fetch edges involving `claim_id`, sorted by effective weight
        (evidence_weight + 0.3*usage_boost) descending.

        FIX-CANON: For undirected edge kinds (corroborates, contradicts),
        the pair is canonicalized at insertion (claim_a < claim_b). So
        `claim_id` may appear in either column. We query both and
        normalize the result so **claim_a = queried claim** and
        **claim_b = neighbor** — the retrieval layer in lethal.py reads
        ``edge["claim_b"]`` as the neighbor and doesn't need to change.

        For directed kinds (elaborates, cites), only claim_a is checked
        (the caller IS the source of the directed relation).
        """
        undirected = kind in _UNDIRECTED_EDGE_KINDS if kind else False

        if kind is not None:
            if undirected:
                rows = self._conn.execute(
                    """SELECT *, (evidence_weight + 0.3 * usage_boost) AS effective
                       FROM edges
                       WHERE (claim_a = ? OR claim_b = ?)
                         AND kind = ? AND evidence_weight >= ?
                       ORDER BY effective DESC""",
                    (claim_id, claim_id, kind, min_evidence_weight),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT *, (evidence_weight + 0.3 * usage_boost) AS effective
                       FROM edges
                       WHERE claim_a = ? AND kind = ? AND evidence_weight >= ?
                       ORDER BY effective DESC""",
                    (claim_id, kind, min_evidence_weight),
                ).fetchall()
        else:
            # kind=None: query both directions unconditionally. All
            # current edge kinds are undirected (contradicts disabled,
            # elaborates/cites deferred to v2).
            rows = self._conn.execute(
                """SELECT *, (evidence_weight + 0.3 * usage_boost) AS effective
                   FROM edges
                   WHERE (claim_a = ? OR claim_b = ?)
                     AND evidence_weight >= ?
                   ORDER BY effective DESC""",
                (claim_id, claim_id, min_evidence_weight),
            ).fetchall()

        # Normalize: ensure claim_a = queried claim, claim_b = neighbor.
        results = []
        for r in rows:
            d = dict(r)
            if d["claim_a"] != claim_id:
                d["claim_a"], d["claim_b"] = d["claim_b"], d["claim_a"]
            results.append(d)
        return results

    # ─────────── entities (FIX D2) ───────────

    def insert_entity(
        self,
        *,
        workspace_id: str,
        canonical_name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        confidence: float = 0.5,
        user_confirmed: bool = False,
        embedding: "Any | None" = None,
    ) -> str:
        """
        Insert (or idempotently return) an entity.

        FIX D2: `confidence < 0.8 AND NOT user_confirmed` → quarantined.
        Quarantined entities are excluded from retrieval stage 2 entity
        expansion until the user confirms them via `confirm_entity()`.
        """
        if not (0.0 <= confidence <= 1.0):
            raise MeshStoreError(
                f"confidence must be in [0, 1], got {confidence}"
            )

        ent_id = self._make_id("ent", f"{workspace_id}:{canonical_name}")
        aliases_json = json.dumps(aliases or [canonical_name.lower()])

        try:
            self._conn.execute(
                """INSERT INTO entities
                   (id, workspace_id, canonical_name, aliases, entity_type,
                    description, confidence, user_confirmed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ent_id, workspace_id, canonical_name, aliases_json,
                 entity_type, description, confidence,
                 1 if user_confirmed else 0),
            )
        except sqlite3.IntegrityError:
            # Idempotent: return existing entity id
            existing = self._conn.execute(
                """SELECT id FROM entities
                   WHERE workspace_id = ? AND canonical_name = ?""",
                (workspace_id, canonical_name),
            ).fetchone()
            if existing:
                return existing["id"]
            raise

        if embedding is not None:
            self._insert_vector("vec_entities", ent_id, embedding)

        return ent_id

    def confirm_entity(self, entity_id: str) -> None:
        """FIX D2: user reviews and confirms an entity — unquarantines it."""
        self._conn.execute(
            """UPDATE entities
               SET user_confirmed = 1, confidence = 1.0
               WHERE id = ?""",
            (entity_id,),
        )

    def get_quarantined_entities(self, workspace_id: str) -> list[dict]:
        """FIX D2: return entities awaiting user review.

        An entity is quarantined when confidence < 0.8 AND not user-confirmed.
        Ordered by `times_referenced` DESC so the most-impactful ones are
        surfaced to the user first.
        """
        rows = self._conn.execute(
            """SELECT * FROM entities
               WHERE workspace_id = ?
               AND confidence < 0.8
               AND user_confirmed = 0
               ORDER BY times_referenced DESC""",
            (workspace_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def link_claim_entity(self, claim_id: str, entity_id: str) -> None:
        """Idempotent link. Bumps entity.times_referenced on first link."""
        try:
            self._conn.execute(
                """INSERT INTO claim_entities (claim_id, entity_id)
                   VALUES (?, ?)""",
                (claim_id, entity_id),
            )
            self._conn.execute(
                """UPDATE entities
                   SET times_referenced = times_referenced + 1
                   WHERE id = ?""",
                (entity_id,),
            )
        except sqlite3.IntegrityError:
            pass  # link already exists — idempotent

    # ─────────── vector insert + search (sqlite-vec) ───────────

    def _insert_vector(
        self, table: str, row_id: str, embedding: "Any"
    ) -> None:
        """
        Insert an embedding into a vec0 virtual table + its mapping table.

        Mapping tables are pre-created in schema.py (advisor fix #3) — this
        method only INSERTs, never creates tables.

        Raises MeshStoreError on dimension mismatch (the vec0 table is
        fixed at float[384] — all four mesh vector tables use the same
        dimension).
        """
        # Normalize embedding to float32
        try:
            import numpy as np  # deferred import — only needed here
        except ImportError as e:
            raise MeshStoreError("numpy is required for vector ops") from e

        arr = np.asarray(embedding, dtype=np.float32)
        if arr.ndim != 1 or arr.shape[0] != EMBEDDING_DIM:
            raise MeshStoreError(
                f"Embedding must be 1-D with dim={EMBEDDING_DIM}, "
                f"got shape {arr.shape}"
            )

        mapping_table = f"{table}_mapping"
        rowid = self._row_id_to_int(row_id)
        emb_bytes = arr.tobytes()

        # vec0 virtual tables do NOT support INSERT OR REPLACE — that
        # syntax raises a collision even for the same rowid. They DO
        # support INSERT, UPDATE, and DELETE. Note: sqlite-vec raises
        # sqlite3.OperationalError ("UNIQUE constraint failed on ...
        # primary key") rather than IntegrityError for this specific
        # collision, so we must catch OperationalError here. Pattern:
        # try INSERT first (fast path for new vectors), fall back to
        # UPDATE on collision (re-embed path for Unit 2 updates or
        # embedding-model migrations). The mapping table is a regular
        # SQLite table and accepts INSERT OR REPLACE normally.
        try:
            self._conn.execute(
                f"INSERT INTO {table} (rowid, embedding) VALUES (?, ?)",
                (rowid, emb_bytes),
            )
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            # Defensive: only treat the "UNIQUE constraint" message as
            # the upsert case. Any other OperationalError (e.g. disk
            # full, syntax error, extension unloaded) must propagate.
            if "UNIQUE" not in str(e) and "primary key" not in str(e):
                raise
            self._conn.execute(
                f"UPDATE {table} SET embedding = ? WHERE rowid = ?",
                (emb_bytes, rowid),
            )

        self._conn.execute(
            f"""INSERT OR REPLACE INTO {mapping_table}
                (rowid, entity_id) VALUES (?, ?)""",
            (rowid, row_id),
        )

    def search_claims_by_vector(
        self,
        *,
        workspace_id: str,
        query_embedding: "Any",
        k: int = 40,
        tier_filter: Sequence[str] = ("GOLD", "SILVER"),
        include_flagged: bool = False,
    ) -> list[tuple[str, float]]:
        """
        Vector KNN search over claims, filtered to a workspace + tier +
        flagged state.

        Returns list of (claim_id, distance) sorted by ascending distance,
        length up to `k`.

        IMPORTANT — over-fetch + post-filter (advisor fix):

        vec0 virtual tables run KNN over ALL vectors in the table, then
        WHERE/JOIN filters apply on the KNN results. If the true top-k
        vectors are outside the workspace/tier/flagged filter, the query
        silently returns fewer than k results (and zero in pathological
        cases). To prevent this, we ask vec0 for k × 3 candidates, then
        apply filters in the outer query, then LIMIT to k.

        At extreme mesh scales (>1M claims per workspace), the overfetch
        multiplier may need to grow with the filter fraction. For v1 scale
        (≤ 100K claims/workspace), 3× is sufficient.
        """
        try:
            import numpy as np
        except ImportError as e:
            raise MeshStoreError("numpy is required for vector search") from e

        q_arr = np.asarray(query_embedding, dtype=np.float32)
        if q_arr.ndim != 1 or q_arr.shape[0] != EMBEDDING_DIM:
            raise MeshStoreError(
                f"Query embedding must be 1-D with dim={EMBEDDING_DIM}, "
                f"got shape {q_arr.shape}"
            )

        if not tier_filter:
            raise MeshStoreError("tier_filter must be non-empty")
        for t in tier_filter:
            if t not in ("GOLD", "SILVER", "BRONZE"):
                raise MeshStoreError(f"Invalid tier in filter: {t!r}")

        overfetch_k = max(k * _KNN_OVERFETCH_MULT, 30)
        tier_placeholders = ",".join("?" * len(tier_filter))
        flagged_clause = "" if include_flagged else "AND c.flagged = 0"

        sql = f"""
            SELECT m.entity_id AS claim_id, v.distance
            FROM vec_claims v
            JOIN vec_claims_mapping m ON m.rowid = v.rowid
            JOIN claims c ON c.id = m.entity_id
            WHERE v.embedding MATCH ?
              AND v.k = ?
              AND c.workspace_id = ?
              AND c.tier IN ({tier_placeholders})
              {flagged_clause}
            ORDER BY v.distance
            LIMIT ?
        """
        params: list[Any] = [
            q_arr.tobytes(),
            overfetch_k,
            workspace_id,
        ]
        params.extend(tier_filter)
        params.append(k)

        rows = self._conn.execute(sql, params).fetchall()
        return [(r["claim_id"], float(r["distance"])) for r in rows]

    # ─────────── op log (append-only, for undo) ───────────

    def log_op(
        self,
        *,
        workspace_id: str,
        op_kind: str,
        affected_ids: list[str] | None = None,
        actor: str | None = None,
        details: dict | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO op_log
               (workspace_id, timestamp, op_kind, affected_ids, actor, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (workspace_id, _now_iso(), op_kind,
             json.dumps(affected_ids) if affected_ids else None,
             actor,
             json.dumps(details) if details else None),
        )

    def get_op_log(
        self,
        workspace_id: str,
        limit: int = 100,
    ) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM op_log
               WHERE workspace_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (workspace_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─────────── stats (useful for debugging / CLI) ───────────

    def workspace_stats(self, workspace_id: str) -> dict:
        ws = self.get_workspace(workspace_id)
        if not ws:
            raise MeshStoreError(f"Workspace not found: {workspace_id}")

        extra = self._conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM claims WHERE workspace_id = ? AND tier = 'GOLD')   AS gold,
                 (SELECT COUNT(*) FROM claims WHERE workspace_id = ? AND tier = 'SILVER') AS silver,
                 (SELECT COUNT(*) FROM claims WHERE workspace_id = ? AND tier = 'BRONZE') AS bronze,
                 (SELECT COUNT(*) FROM claims WHERE workspace_id = ? AND flagged = 1)     AS flagged,
                 (SELECT COUNT(*) FROM entities WHERE workspace_id = ?
                    AND confidence < 0.8 AND user_confirmed = 0)                          AS quarantined_entities""",
            (workspace_id,) * 5,
        ).fetchone()

        return {
            **dict(ws),
            "gold_claims": extra["gold"],
            "silver_claims": extra["silver"],
            "bronze_claims": extra["bronze"],
            "flagged_claims": extra["flagged"],
            "quarantined_entities": extra["quarantined_entities"],
        }

    # ─────────── Q&A (questions + answers) ───────────

    def insert_question(
        self,
        *,
        workspace_id: str,
        text: str,
        parent_id: str | None = None,
        asked_by: str | None = None,
    ) -> str:
        if not text.strip():
            raise MeshStoreError("Question text must be non-empty")
        q_id = self._make_id("q", f"{workspace_id}:{text}:{_now_iso()}")
        self._conn.execute(
            """INSERT INTO questions
               (id, workspace_id, text, parent_id, asked_at, asked_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (q_id, workspace_id, text.strip(), parent_id, _now_iso(), asked_by),
        )
        return q_id

    def get_question(self, question_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,),
        ).fetchone()
        return dict(row) if row else None

    def insert_answer(
        self,
        *,
        question_id: str,
        text: str,
        retrieved_claims: list[str] | None = None,
        cited_claims: list[str] | None = None,
        artifact_paths: list[str] | None = None,
        model: str | None = None,
    ) -> str:
        a_id = self._make_id("ans", f"{question_id}:{_now_iso()}")
        self._conn.execute(
            """INSERT INTO answers
               (id, question_id, text, retrieved_claims, cited_claims,
                artifact_paths, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a_id, question_id, text,
                json.dumps(retrieved_claims) if retrieved_claims else None,
                json.dumps(cited_claims) if cited_claims else None,
                json.dumps(artifact_paths) if artifact_paths else None,
                model, _now_iso(),
            ),
        )
        return a_id

    def get_answer_for_question(self, question_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM answers WHERE question_id = ? ORDER BY created_at DESC LIMIT 1",
            (question_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_thread_history(
        self, question_id: str, last_n: int = 3,
    ) -> list[dict]:
        """
        Walk the parent_id chain from `question_id` backward, collecting
        Q&A pairs in chronological order (oldest first). Returns at most
        `last_n` pairs, each as {"question": text, "answer": text}.
        """
        pairs: list[dict] = []
        current_id: str | None = question_id
        visited: set[str] = set()

        while current_id and len(pairs) < last_n + 1:
            if current_id in visited:
                break
            visited.add(current_id)
            q = self.get_question(current_id)
            if q is None:
                break
            ans = self.get_answer_for_question(current_id)
            pairs.append({
                "question": q["text"],
                "answer": ans["text"] if ans else "",
            })
            current_id = q.get("parent_id")

        # We collected from current → ancestors. Reverse for chronological
        # order, then drop the LAST entry (which is the current question
        # itself — we only want the history before it).
        pairs.reverse()
        if pairs:
            pairs.pop()  # remove the current question from history
        return pairs[-last_n:] if len(pairs) > last_n else pairs

    # ─────────── helpers ───────────

    @staticmethod
    def _make_id(prefix: str, source: str) -> str:
        """Deterministic short id from a salted source string."""
        h = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{h}"

    @staticmethod
    def _row_id_to_int(row_id: str) -> int:
        """
        Deterministic 63-bit positive integer from a string id.

        vec0 virtual tables use INTEGER rowid as the primary key, and
        SQLite INTEGER is signed 64-bit. We mask to 63 bits to stay
        strictly positive (some vec0 code paths reject negative rowids).

        Collision risk: two distinct row_ids that hash to the same 63-bit
        integer would cause `INSERT OR REPLACE` in `_insert_vector` to
        overwrite the first vector — silent data loss (the first claim
        becomes invisible to KNN). At v1 scale (≤1M vectors/workspace)
        the birthday-collision probability is ≈ 5.4 × 10⁻⁸ — negligible.
        The probability crosses 1% around 4.3 × 10⁸ vectors per table.
        Proper fix when we hit that scale: add an auto-incrementing
        rowid column to the mapping tables and look up via that instead.
        """
        h = hashlib.sha256(row_id.encode("utf-8")).digest()
        return int.from_bytes(h[:8], "big", signed=False) & 0x7FFF_FFFF_FFFF_FFFF
