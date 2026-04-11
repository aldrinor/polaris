"""
Mesh database schema — DDL for every table in the POLARIS wiki mesh.

One SQLite file holds everything:

- 11 core tables (workspaces, source_pages, claims, edges, entities,
  claim_entities, topics, topic_claims, questions, answers, feedback)
- 1 meta table (mesh_meta)
- 1 op log table (op_log) for undo/rewind
- 4 vector virtual tables via sqlite-vec (vec_claims, vec_sources,
  vec_entities, vec_questions)
- 4 mapping tables (string_id -> integer rowid for the vec0 tables)

Single database file = single transaction boundary = no dual-store
consistency bugs. This is FIX D1 from the advisor review.

The schema reflects FIXES D1, D2, D3, S4, S6 inline (see the comments next
to the affected columns). See docs/wiki_mesh_design.md for the full rationale.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

# Core tables, indexes, triggers. Run after the sqlite-vec extension is
# loaded — the vec0 virtual tables are created from VECTOR_DDL below.
CORE_DDL: list[str] = [
    # ───── meta ─────
    """CREATE TABLE IF NOT EXISTS mesh_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",

    # ───── workspaces ─────
    """CREATE TABLE IF NOT EXISTS workspaces (
        id                              TEXT PRIMARY KEY,
        name                            TEXT NOT NULL,
        owner                           TEXT,
        root_question                   TEXT,
        created_at                      TEXT NOT NULL,
        source_count                    INTEGER NOT NULL DEFAULT 0,
        claim_count                     INTEGER NOT NULL DEFAULT 0,
        edge_count                      INTEGER NOT NULL DEFAULT 0,
        last_ingest_at                  TEXT,
        nearby_expansion_budget_daily   INTEGER NOT NULL DEFAULT 50,
        nearby_expansions_today         INTEGER NOT NULL DEFAULT 0,
        nearby_expansion_reset_at       TEXT
    )""",

    # ───── L1 source pages ─────
    """CREATE TABLE IF NOT EXISTS source_pages (
        id                TEXT PRIMARY KEY,
        workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        kind              TEXT NOT NULL CHECK (kind IN ('web', 'upload', 'api')),
        url               TEXT,
        filepath          TEXT NOT NULL,
        title             TEXT,
        authors           TEXT,
        year              INTEGER,
        doi               TEXT,
        venue             TEXT,
        fetched_at        TEXT NOT NULL,
        content_hash      TEXT NOT NULL,
        word_count        INTEGER,
        sig_authority     REAL NOT NULL,
        times_cited       INTEGER NOT NULL DEFAULT 0,
        last_used_at      TEXT,
        retracted         INTEGER NOT NULL DEFAULT 0,
        retraction_reason TEXT,
        UNIQUE (workspace_id, content_hash)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_src_workspace ON source_pages(workspace_id, kind)",
    "CREATE INDEX IF NOT EXISTS ix_src_authority ON source_pages(workspace_id, sig_authority DESC)",

    # ───── L2 claims ─────
    """CREATE TABLE IF NOT EXISTS claims (
        id                TEXT PRIMARY KEY,
        workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        source_page_id    TEXT NOT NULL REFERENCES source_pages(id) ON DELETE CASCADE,
        statement         TEXT NOT NULL,
        direct_quote      TEXT NOT NULL,
        char_start        INTEGER NOT NULL,
        char_end          INTEGER NOT NULL,
        tier              TEXT NOT NULL CHECK (tier IN ('GOLD', 'SILVER', 'BRONZE')),
        relevance_score   REAL NOT NULL,
        has_numeric       INTEGER NOT NULL DEFAULT 0,
        extracted_at      TEXT NOT NULL,
        times_used        INTEGER NOT NULL DEFAULT 0,
        last_used_at      TEXT,
        flagged           INTEGER NOT NULL DEFAULT 0,
        flagged_reason    TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_clm_source      ON claims(source_page_id)",
    "CREATE INDEX IF NOT EXISTS ix_clm_ws_tier_rel ON claims(workspace_id, tier, relevance_score DESC)",
    "CREATE INDEX IF NOT EXISTS ix_clm_ws_usage    ON claims(workspace_id, times_used DESC, last_used_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_clm_ws_flagged  ON claims(workspace_id, flagged)",

    # ───── L2 edges (FIX S4: split weight columns) ─────
    """CREATE TABLE IF NOT EXISTS edges (
        id                TEXT PRIMARY KEY,
        workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        claim_a           TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        claim_b           TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        kind              TEXT NOT NULL CHECK (
                            kind IN ('corroborates', 'contradicts', 'elaborates', 'cites')
                          ),
        evidence_weight   REAL NOT NULL,
        usage_boost       REAL NOT NULL DEFAULT 0
                          CHECK (usage_boost >= 0 AND usage_boost <= 0.2),
        discovered_at     TEXT NOT NULL,
        discovery_method  TEXT NOT NULL,
        UNIQUE (claim_a, claim_b, kind)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_edge_a_kind ON edges(workspace_id, claim_a, kind)",
    "CREATE INDEX IF NOT EXISTS ix_edge_b_kind ON edges(workspace_id, claim_b, kind)",

    # ───── L3 entities (FIX D2: confidence gating) ─────
    """CREATE TABLE IF NOT EXISTS entities (
        id                TEXT PRIMARY KEY,
        workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        canonical_name    TEXT NOT NULL,
        aliases           TEXT,
        entity_type       TEXT NOT NULL,
        description       TEXT,
        confidence        REAL NOT NULL DEFAULT 0.5
                          CHECK (confidence >= 0 AND confidence <= 1),
        user_confirmed    INTEGER NOT NULL DEFAULT 0,
        times_referenced  INTEGER NOT NULL DEFAULT 0,
        UNIQUE (workspace_id, canonical_name)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ent_ws_conf ON entities(workspace_id, confidence DESC)",

    """CREATE TABLE IF NOT EXISTS claim_entities (
        claim_id  TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        PRIMARY KEY (claim_id, entity_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ce_entity ON claim_entities(entity_id)",

    # ───── L4 topics (emergent) ─────
    """CREATE TABLE IF NOT EXISTS topics (
        id                TEXT PRIMARY KEY,
        workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        title             TEXT NOT NULL,
        description       TEXT,
        created_from      TEXT,
        size              INTEGER NOT NULL DEFAULT 0,
        created_at        TEXT NOT NULL,
        last_refreshed_at TEXT,
        dirty             INTEGER NOT NULL DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS topic_claims (
        topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
        claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        rank     REAL NOT NULL,
        PRIMARY KEY (topic_id, claim_id)
    )""",

    # ───── Q&A ─────
    """CREATE TABLE IF NOT EXISTS questions (
        id           TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        text         TEXT NOT NULL,
        parent_id    TEXT REFERENCES questions(id),
        asked_at     TEXT NOT NULL,
        asked_by     TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS answers (
        id               TEXT PRIMARY KEY,
        question_id      TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        text             TEXT NOT NULL,
        retrieved_claims TEXT,
        cited_claims     TEXT,
        artifact_paths   TEXT,
        model            TEXT,
        quality_score    REAL,
        created_at       TEXT NOT NULL
    )""",

    # ───── Feedback (drives bounded snowball) ─────
    """CREATE TABLE IF NOT EXISTS feedback (
        id        TEXT PRIMARY KEY,
        answer_id TEXT NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
        claim_id  TEXT REFERENCES claims(id) ON DELETE SET NULL,
        kind      TEXT NOT NULL CHECK (
                    kind IN ('used','upvoted','downvoted','flagged_wrong','cited_in_export')
                  ),
        timestamp TEXT NOT NULL
    )""",

    # ───── Op log (append-only, for undo/rewind) ─────
    """CREATE TABLE IF NOT EXISTS op_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        timestamp    TEXT NOT NULL,
        op_kind      TEXT NOT NULL,
        affected_ids TEXT,
        actor        TEXT,
        details      TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_oplog_ws_ts ON op_log(workspace_id, timestamp DESC)",

    # ───── Vector mapping tables (advisor checkpoint 1 fix) ─────
    # vec0 virtual tables use INTEGER rowid. We keep a mapping from our
    # string ids (clm_xxx, src_xxx, ...) to deterministic integer rowids
    # so the FK cascade semantics live in the core tables while the KNN
    # index lives in the vec0 tables. DDL belongs here, NOT on-the-fly
    # in store._insert_vector().
    """CREATE TABLE IF NOT EXISTS vec_claims_mapping (
        rowid     INTEGER PRIMARY KEY,
        entity_id TEXT    NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS vec_sources_mapping (
        rowid     INTEGER PRIMARY KEY,
        entity_id TEXT    NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS vec_entities_mapping (
        rowid     INTEGER PRIMARY KEY,
        entity_id TEXT    NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS vec_questions_mapping (
        rowid     INTEGER PRIMARY KEY,
        entity_id TEXT    NOT NULL UNIQUE
    )""",
]


# vec0 virtual tables require sqlite-vec to be loaded on the connection
# before they can be created. Keep them separate from CORE_DDL so the
# loader can be explicit about ordering.
#
# Embedding dimension fixed at 768 (matches sentence-transformers default).
# If we later switch to a 1024-dim or 4096-dim model, these DDL statements
# and the existing data will need a migration.
VECTOR_DDL: list[str] = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_claims    USING vec0(embedding float[768])",
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_sources   USING vec0(embedding float[768])",
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_entities  USING vec0(embedding float[768])",
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_questions USING vec0(embedding float[768])",
]


def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create every mesh table on a fresh or existing connection.

    The caller MUST have already loaded the sqlite-vec extension on the
    connection (store.MeshStore.open does this). If the extension is not
    loaded, the VECTOR_DDL statements will fail with "no such module: vec0".

    Idempotent: re-running on an initialized database is a no-op because
    every CREATE statement uses IF NOT EXISTS.
    """
    for stmt in CORE_DDL:
        conn.execute(stmt)
    for stmt in VECTOR_DDL:
        conn.execute(stmt)
    conn.execute(
        "INSERT OR IGNORE INTO mesh_meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()
