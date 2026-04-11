"""
Unit tests for the wiki mesh store (Unit 1 of the mesh build).

Covers:
  - Schema creation + version check
  - Workspace / source / claim / edge / entity CRUD
  - FIX D1: transactional rollback across SQL + vec0 virtual tables
  - FIX D2: entity confidence gating + quarantine query
  - FIX S4: edge usage_boost cap enforced at schema + helper levels
  - FIX D3: snowball usage counter increment
  - Advisor fix: KNN over-fetch prevents lossy filter behavior
  - FK cascade on workspace delete
  - Fail-loudly validation on invalid inputs

Run:
    python -m pytest tests/unit/test_mesh_store.py -v
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.polaris_graph.wiki.mesh import (
    MeshStore,
    MeshStoreError,
    SCHEMA_VERSION,
)
from src.polaris_graph.wiki.mesh.store import (
    EDGE_USAGE_BOOST_MAX,
    EMBEDDING_DIM,
)


# ───────── fixtures ─────────

@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "mesh.db"


@pytest.fixture
def store(tmp_db_path: Path) -> MeshStore:
    s = MeshStore.open(tmp_db_path)
    yield s
    s.close()


@pytest.fixture
def workspace_id(store: MeshStore) -> str:
    return store.create_workspace(
        name="test_workspace",
        root_question="What is the best household PFAS filter?",
    )


@pytest.fixture
def source_id(store: MeshStore, workspace_id: str) -> str:
    return store.insert_source(
        workspace_id=workspace_id,
        kind="upload",
        filepath="sources/test.md",
        content_hash="hash_test_1",
        sig_authority=0.95,
        title="Test source",
    )


def _random_emb(seed: int = 0) -> np.ndarray:
    """Deterministic 768-dim unit vector for tests."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


# ───────── schema / lifecycle ─────────

class TestLifecycle:

    def test_open_creates_fresh_schema(self, tmp_db_path: Path):
        assert not tmp_db_path.exists()
        store = MeshStore.open(tmp_db_path)
        assert tmp_db_path.exists()
        row = store._conn.execute(
            "SELECT value FROM mesh_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert int(row["value"]) == SCHEMA_VERSION
        store.close()

    def test_reopen_existing_db(self, tmp_db_path: Path):
        s1 = MeshStore.open(tmp_db_path)
        ws_id = s1.create_workspace(name="persist_test")
        s1.close()

        s2 = MeshStore.open(tmp_db_path)
        ws = s2.get_workspace(ws_id)
        assert ws is not None
        assert ws["name"] == "persist_test"
        s2.close()

    def test_vectors_persist_across_reopen(self, tmp_db_path: Path):
        """
        The most load-bearing test in the suite: FIX D1 is only real if
        sqlite-vec's virtual table data survives close → reopen and KNN
        queries still find the vectors after reopen. If this fails, the
        whole single-store architecture is broken — we'd have claims
        persisted but their embeddings lost on every restart.
        """
        s1 = MeshStore.open(tmp_db_path)
        ws_id = s1.create_workspace(name="vec_persist")
        src_id = s1.insert_source(
            workspace_id=ws_id, kind="upload", filepath="x.md",
            content_hash="h1", sig_authority=0.9,
        )
        emb = _random_emb(seed=99)
        clm_id = s1.insert_claim(
            workspace_id=ws_id, source_page_id=src_id,
            statement="persistent claim", direct_quote="q",
            char_start=0, char_end=5, tier="GOLD",
            relevance_score=0.9, embedding=emb,
        )
        # Search before close — sanity
        hits = s1.search_claims_by_vector(
            workspace_id=ws_id, query_embedding=emb, k=5,
        )
        assert len(hits) == 1 and hits[0][0] == clm_id
        s1.close()

        # Reopen from disk — vectors must still be there
        s2 = MeshStore.open(tmp_db_path)
        hits2 = s2.search_claims_by_vector(
            workspace_id=ws_id, query_embedding=emb, k=5,
        )
        assert len(hits2) == 1, (
            f"KNN returned 0 results after reopen — sqlite-vec may not "
            f"be persisting vectors to disk. Got: {hits2}"
        )
        assert hits2[0][0] == clm_id
        assert hits2[0][1] == pytest.approx(0.0, abs=1e-5)
        s2.close()

    def test_schema_version_mismatch_raises(self, tmp_db_path: Path):
        s = MeshStore.open(tmp_db_path)
        s._conn.execute(
            "UPDATE mesh_meta SET value = '999' WHERE key = 'schema_version'"
        )
        s.close()
        with pytest.raises(MeshStoreError, match="Schema version mismatch"):
            MeshStore.open(tmp_db_path)


# ───────── workspace ─────────

class TestWorkspace:

    def test_create_and_get(self, store: MeshStore):
        ws_id = store.create_workspace(
            name="PFAS study",
            root_question="What is the best filter?",
            owner="alice",
        )
        ws = store.get_workspace(ws_id)
        assert ws["name"] == "PFAS study"
        assert ws["owner"] == "alice"
        assert ws["source_count"] == 0
        assert ws["claim_count"] == 0
        assert ws["nearby_expansion_budget_daily"] == 50  # FIX S6 default

    def test_list_workspaces(self, store: MeshStore):
        store.create_workspace(name="a")
        store.create_workspace(name="b")
        assert len(store.list_workspaces()) == 2

    def test_stats_on_empty_workspace(
        self, store: MeshStore, workspace_id: str
    ):
        stats = store.workspace_stats(workspace_id)
        assert stats["gold_claims"] == 0
        assert stats["silver_claims"] == 0
        assert stats["quarantined_entities"] == 0


# ───────── source pages ─────────

class TestSource:

    def test_insert_and_get(
        self, store: MeshStore, workspace_id: str
    ):
        src_id = store.insert_source(
            workspace_id=workspace_id,
            kind="web",
            filepath="sources/web_1.md",
            content_hash="abc123",
            sig_authority=0.7,
            title="Example",
            authors=["Smith, J"],
            year=2025,
        )
        src = store.get_source(src_id)
        assert src["title"] == "Example"
        assert src["kind"] == "web"
        assert src["sig_authority"] == 0.7
        ws = store.get_workspace(workspace_id)
        assert ws["source_count"] == 1

    def test_dedup_raises(
        self, store: MeshStore, workspace_id: str
    ):
        store.insert_source(
            workspace_id=workspace_id,
            kind="upload",
            filepath="x.md",
            content_hash="same_hash",
            sig_authority=0.9,
        )
        with pytest.raises(MeshStoreError, match="already exists"):
            store.insert_source(
                workspace_id=workspace_id,
                kind="upload",
                filepath="y.md",
                content_hash="same_hash",  # same hash
                sig_authority=0.9,
            )

    def test_source_id_by_hash(
        self, store: MeshStore, workspace_id: str
    ):
        src_id = store.insert_source(
            workspace_id=workspace_id,
            kind="upload",
            filepath="x.md",
            content_hash="unique",
            sig_authority=0.9,
        )
        assert store.source_id_by_hash(workspace_id, "unique") == src_id
        assert store.source_id_by_hash(workspace_id, "nope") is None

    def test_invalid_kind_raises(
        self, store: MeshStore, workspace_id: str
    ):
        with pytest.raises(MeshStoreError, match="Invalid source kind"):
            store.insert_source(
                workspace_id=workspace_id,
                kind="bogus",
                filepath="x.md",
                content_hash="x",
                sig_authority=0.5,
            )

    def test_sig_authority_out_of_range_raises(
        self, store: MeshStore, workspace_id: str
    ):
        with pytest.raises(MeshStoreError, match="sig_authority"):
            store.insert_source(
                workspace_id=workspace_id,
                kind="upload",
                filepath="x.md",
                content_hash="x",
                sig_authority=1.5,
            )

    def test_increment_citation(
        self, store: MeshStore, source_id: str
    ):
        store.increment_source_citation(source_id)
        store.increment_source_citation(source_id)
        src = store.get_source(source_id)
        assert src["times_cited"] == 2
        assert src["last_used_at"] is not None


# ───────── claims ─────────

class TestClaim:

    def test_insert_basic(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        clm_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_id,
            statement="GAC filters remove 85% of long-chain PFAS.",
            direct_quote="GAC achieved 85% removal of long-chain PFAS compounds.",
            char_start=1024,
            char_end=1080,
            tier="GOLD",
            relevance_score=0.91,
            has_numeric=True,
        )
        clm = store.get_claim(clm_id)
        assert clm["tier"] == "GOLD"
        assert clm["has_numeric"] == 1
        assert clm["times_used"] == 0
        ws = store.get_workspace(workspace_id)
        assert ws["claim_count"] == 1

    def test_insert_with_embedding(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        emb = _random_emb(seed=1)
        clm_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_id,
            statement="s",
            direct_quote="q",
            char_start=0,
            char_end=1,
            tier="GOLD",
            relevance_score=0.9,
            embedding=emb,
        )
        # Verify vec_claims has an entry
        row = store._conn.execute(
            "SELECT COUNT(*) AS c FROM vec_claims"
        ).fetchone()
        assert row["c"] == 1
        # Verify mapping entry exists
        row = store._conn.execute(
            "SELECT entity_id FROM vec_claims_mapping"
        ).fetchone()
        assert row["entity_id"] == clm_id

    def test_invalid_tier_raises(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        with pytest.raises(MeshStoreError, match="Invalid tier"):
            store.insert_claim(
                workspace_id=workspace_id,
                source_page_id=source_id,
                statement="s", direct_quote="q",
                char_start=0, char_end=1,
                tier="PLATINUM",  # invalid
                relevance_score=0.9,
            )

    def test_invalid_char_span_raises(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        with pytest.raises(MeshStoreError, match="char span"):
            store.insert_claim(
                workspace_id=workspace_id,
                source_page_id=source_id,
                statement="s", direct_quote="q",
                char_start=100, char_end=50,  # end < start
                tier="GOLD", relevance_score=0.9,
            )

    def test_increment_usage(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        clm_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="s", direct_quote="q",
            char_start=0, char_end=1,
            tier="GOLD", relevance_score=0.9,
        )
        store.increment_claim_usage(clm_id)
        store.increment_claim_usage(clm_id)
        store.increment_claim_usage(clm_id)
        clm = store.get_claim(clm_id)
        assert clm["times_used"] == 3
        assert clm["last_used_at"] is not None

    def test_flag_claim(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        clm_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="s", direct_quote="q",
            char_start=0, char_end=1,
            tier="GOLD", relevance_score=0.9,
        )
        store.flag_claim(clm_id, reason="wrong number")
        clm = store.get_claim(clm_id)
        assert clm["flagged"] == 1
        assert clm["flagged_reason"] == "wrong number"

    def test_insert_claim_idempotent(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        """
        Re-extraction must not crash with IntegrityError.

        Unit 2 will re-extract sources when they are updated or when the
        extraction model changes. The deterministic id
            hash(source:char_start:statement[:50])
        collides with the existing row. insert_claim must catch the
        integrity error, return the existing id, and NOT double-count
        the workspace's claim_count.
        """
        emb = _random_emb(seed=11)
        first_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="GAC filters remove 85% of long-chain PFAS.",
            direct_quote="quote",
            char_start=100, char_end=200,
            tier="GOLD", relevance_score=0.9,
            embedding=emb,
        )
        ws1 = store.get_workspace(workspace_id)
        assert ws1["claim_count"] == 1

        # Re-insert the SAME claim — must be idempotent
        second_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="GAC filters remove 85% of long-chain PFAS.",
            direct_quote="quote",  # same body
            char_start=100, char_end=200,
            tier="GOLD", relevance_score=0.9,
            embedding=emb,
        )
        assert second_id == first_id  # same deterministic id

        # Workspace counter must NOT have been double-counted
        ws2 = store.get_workspace(workspace_id)
        assert ws2["claim_count"] == 1

        # Still only one row in claims
        row = store._conn.execute(
            "SELECT COUNT(*) AS c FROM claims WHERE id = ?", (first_id,)
        ).fetchone()
        assert row["c"] == 1

    def test_insert_claim_re_embed_on_idempotent(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        """
        When idempotent insert happens, the new embedding should replace
        the old one (for embedding-model migration). Verify via search.
        """
        emb_old = _random_emb(seed=20)
        clm_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="same statement",
            direct_quote="q",
            char_start=0, char_end=10,
            tier="GOLD", relevance_score=0.9,
            embedding=emb_old,
        )
        # New embedding — not close to the old one
        emb_new = _random_emb(seed=21)
        store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="same statement",
            direct_quote="q",
            char_start=0, char_end=10,
            tier="GOLD", relevance_score=0.9,
            embedding=emb_new,
        )
        # Querying with emb_new should find the claim with distance ~0
        hits = store.search_claims_by_vector(
            workspace_id=workspace_id, query_embedding=emb_new, k=3,
        )
        assert len(hits) == 1
        assert hits[0][0] == clm_id
        assert hits[0][1] == pytest.approx(0.0, abs=1e-5)


# ───────── edges (FIX S4) ─────────

class TestEdge:

    def _make_two_claims(
        self, store: MeshStore, workspace_id: str, source_id: str
    ) -> tuple[str, str]:
        a = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="claim A", direct_quote="q_a",
            char_start=0, char_end=10,
            tier="GOLD", relevance_score=0.9,
        )
        b = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="claim B", direct_quote="q_b",
            char_start=20, char_end=30,
            tier="GOLD", relevance_score=0.85,
        )
        return a, b

    def test_insert_edge_basic(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        a, b = self._make_two_claims(store, workspace_id, source_id)
        edge_id = store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="corroborates", evidence_weight=0.9,
            discovery_method="embed_cosine",
        )
        row = store._conn.execute(
            "SELECT * FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        assert row["evidence_weight"] == 0.9
        assert row["usage_boost"] == 0.0  # FIX S4: starts at 0

    def test_insert_edge_idempotent(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        a, b = self._make_two_claims(store, workspace_id, source_id)
        id1 = store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="corroborates", evidence_weight=0.8,
            discovery_method="m1",
        )
        id2 = store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="corroborates", evidence_weight=0.7,  # different weight
            discovery_method="m2",
        )
        assert id1 == id2  # idempotent — same edge returned
        # Original weight preserved (not overwritten)
        row = store._conn.execute(
            "SELECT evidence_weight FROM edges WHERE id = ?", (id1,)
        ).fetchone()
        assert row["evidence_weight"] == 0.8

    def test_bump_usage_boost_capped_at_max(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        """FIX S4: usage_boost must never exceed 0.2."""
        a, b = self._make_two_claims(store, workspace_id, source_id)
        edge_id = store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="corroborates", evidence_weight=0.9,
            discovery_method="m",
        )
        # Bump 20 times with delta=0.02 — should cap at 0.2 not reach 0.4
        for _ in range(20):
            store.bump_edge_usage_boost(edge_id, delta=0.02)
        row = store._conn.execute(
            "SELECT usage_boost FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        assert row["usage_boost"] == pytest.approx(EDGE_USAGE_BOOST_MAX)

        # And another bump still caps
        store.bump_edge_usage_boost(edge_id, delta=0.5)
        row = store._conn.execute(
            "SELECT usage_boost FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        assert row["usage_boost"] == pytest.approx(EDGE_USAGE_BOOST_MAX)

    def test_usage_boost_check_constraint(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        """Schema CHECK must reject direct writes of usage_boost > 0.2."""
        a, b = self._make_two_claims(store, workspace_id, source_id)
        # Direct INSERT bypassing the helper — must be rejected by CHECK
        with pytest.raises(sqlite3.IntegrityError):
            store._conn.execute(
                """INSERT INTO edges
                   (id, workspace_id, claim_a, claim_b, kind,
                    evidence_weight, usage_boost, discovered_at,
                    discovery_method)
                   VALUES (?, ?, ?, ?, 'corroborates', 0.9, 0.5,
                           '2026-04-10', 'direct')""",
                ("edg_bogus", workspace_id, a, b),
            )

    def test_invalid_edge_kind_raises(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        a, b = self._make_two_claims(store, workspace_id, source_id)
        with pytest.raises(MeshStoreError, match="edge kind"):
            store.insert_edge(
                workspace_id=workspace_id, claim_a=a, claim_b=b,
                kind="bogus", evidence_weight=0.5,
                discovery_method="m",
            )

    def test_get_edges_from_sorted_by_effective_weight(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        a = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="a", direct_quote="q",
            char_start=0, char_end=1, tier="GOLD", relevance_score=0.9,
        )
        b = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="b", direct_quote="q",
            char_start=2, char_end=3, tier="GOLD", relevance_score=0.9,
        )
        c = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="c", direct_quote="q",
            char_start=4, char_end=5, tier="GOLD", relevance_score=0.9,
        )
        eid_ab = store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="corroborates", evidence_weight=0.8, discovery_method="m",
        )
        eid_ac = store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=c,
            kind="corroborates", evidence_weight=0.9, discovery_method="m",
        )
        # Edge a→b has lower ev_w but we'll bump its usage_boost high
        store.bump_edge_usage_boost(eid_ab, delta=0.2)  # max
        # effective(ab) = 0.8 + 0.3*0.2 = 0.86
        # effective(ac) = 0.9 + 0.3*0  = 0.90
        edges = store.get_edges_from(a, kind="corroborates")
        assert len(edges) == 2
        assert edges[0]["claim_b"] == c  # higher effective
        assert edges[1]["claim_b"] == b

    def test_get_edges_from_kind_none_returns_all_kinds(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        """
        get_edges_from(kind=None) takes a different SQL path than
        kind="corroborates". Retrieval stages 3-5 will call this with
        kind=None to traverse mixed edge types. Must cover the untyped
        path explicitly so an unused branch doesn't ship.
        """
        a = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="a", direct_quote="q",
            char_start=0, char_end=1, tier="GOLD", relevance_score=0.9,
        )
        b = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="b", direct_quote="q",
            char_start=2, char_end=3, tier="GOLD", relevance_score=0.9,
        )
        c = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="c", direct_quote="q",
            char_start=4, char_end=5, tier="GOLD", relevance_score=0.9,
        )
        # Three edges from a, different kinds
        store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="corroborates", evidence_weight=0.9, discovery_method="m",
        )
        store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=c,
            kind="contradicts", evidence_weight=0.7, discovery_method="m",
        )
        store.insert_edge(
            workspace_id=workspace_id, claim_a=a, claim_b=b,
            kind="elaborates", evidence_weight=0.5, discovery_method="m",
        )

        all_edges = store.get_edges_from(a, kind=None)
        assert len(all_edges) == 3
        kinds = [e["kind"] for e in all_edges]
        # Sorted by effective weight DESC:
        #   corroborates 0.9, contradicts 0.7, elaborates 0.5
        assert kinds == ["corroborates", "contradicts", "elaborates"]

        # And kind=None respects the min_evidence_weight filter
        high_only = store.get_edges_from(a, kind=None, min_evidence_weight=0.8)
        assert len(high_only) == 1
        assert high_only[0]["kind"] == "corroborates"


# ───────── entities (FIX D2) ─────────

class TestEntity:

    def test_insert_basic(
        self, store: MeshStore, workspace_id: str
    ):
        ent_id = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctane sulfonate",
            entity_type="compound",
            aliases=["PFOS", "C8"],
            confidence=0.95,
            user_confirmed=True,
        )
        row = store._conn.execute(
            "SELECT * FROM entities WHERE id = ?", (ent_id,)
        ).fetchone()
        assert row["confidence"] == 0.95
        assert row["user_confirmed"] == 1

    def test_quarantine_low_confidence(
        self, store: MeshStore, workspace_id: str
    ):
        """FIX D2: entities with confidence < 0.8 AND not user_confirmed
        appear in the quarantine list."""
        store.insert_entity(
            workspace_id=workspace_id, canonical_name="RO",
            entity_type="method", confidence=0.6,  # ambiguous
        )
        store.insert_entity(
            workspace_id=workspace_id, canonical_name="GAC",
            entity_type="method", confidence=0.95,  # high confidence
        )
        store.insert_entity(
            workspace_id=workspace_id, canonical_name="Sketchy",
            entity_type="compound", confidence=0.5,
            user_confirmed=True,  # low conf but user-confirmed
        )
        quarantined = store.get_quarantined_entities(workspace_id)
        names = {e["canonical_name"] for e in quarantined}
        assert names == {"RO"}  # Only the low-confidence unconfirmed one

    def test_confirm_entity(
        self, store: MeshStore, workspace_id: str
    ):
        ent_id = store.insert_entity(
            workspace_id=workspace_id, canonical_name="RO",
            entity_type="method", confidence=0.6,
        )
        assert len(store.get_quarantined_entities(workspace_id)) == 1
        store.confirm_entity(ent_id)
        assert len(store.get_quarantined_entities(workspace_id)) == 0
        row = store._conn.execute(
            "SELECT confidence, user_confirmed FROM entities WHERE id = ?",
            (ent_id,)
        ).fetchone()
        assert row["confidence"] == 1.0
        assert row["user_confirmed"] == 1

    def test_insert_idempotent(
        self, store: MeshStore, workspace_id: str
    ):
        id1 = store.insert_entity(
            workspace_id=workspace_id, canonical_name="PFOS",
            entity_type="compound", confidence=0.9,
        )
        id2 = store.insert_entity(
            workspace_id=workspace_id, canonical_name="PFOS",
            entity_type="compound", confidence=0.5,  # different
        )
        assert id1 == id2

    def test_link_claim_entity_idempotent(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        clm_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="s", direct_quote="q",
            char_start=0, char_end=1,
            tier="GOLD", relevance_score=0.9,
        )
        ent_id = store.insert_entity(
            workspace_id=workspace_id, canonical_name="PFOS",
            entity_type="compound", confidence=0.9,
        )
        store.link_claim_entity(clm_id, ent_id)
        store.link_claim_entity(clm_id, ent_id)  # re-link
        row = store._conn.execute(
            "SELECT COUNT(*) AS c FROM claim_entities WHERE claim_id = ?",
            (clm_id,)
        ).fetchone()
        assert row["c"] == 1
        # times_referenced bumped once (first link only)
        row = store._conn.execute(
            "SELECT times_referenced FROM entities WHERE id = ?", (ent_id,)
        ).fetchone()
        assert row["times_referenced"] == 1


# ───────── vector search ─────────

class TestVectorSearch:

    def test_embedding_dim_mismatch_raises(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        bad_emb = np.zeros(100, dtype=np.float32)  # wrong dim
        with pytest.raises(MeshStoreError, match="dim"):
            store.insert_claim(
                workspace_id=workspace_id, source_page_id=source_id,
                statement="s", direct_quote="q",
                char_start=0, char_end=1,
                tier="GOLD", relevance_score=0.9,
                embedding=bad_emb,
            )

    def test_search_returns_closest(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        emb1 = _random_emb(seed=1)
        emb2 = _random_emb(seed=2)
        emb3 = _random_emb(seed=3)
        c1 = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="claim 1", direct_quote="q",
            char_start=0, char_end=5, tier="GOLD",
            relevance_score=0.9, embedding=emb1,
        )
        c2 = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="claim 2", direct_quote="q",
            char_start=10, char_end=15, tier="SILVER",
            relevance_score=0.8, embedding=emb2,
        )
        c3 = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="claim 3", direct_quote="q",
            char_start=20, char_end=25, tier="GOLD",
            relevance_score=0.7, embedding=emb3,
        )
        # Query with emb1 — should return c1 first
        results = store.search_claims_by_vector(
            workspace_id=workspace_id, query_embedding=emb1, k=3,
        )
        assert len(results) == 3
        assert results[0][0] == c1
        assert results[0][1] == pytest.approx(0.0, abs=1e-5)

    def test_search_filters_by_tier(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        emb1 = _random_emb(seed=1)
        emb2 = _random_emb(seed=2)
        store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="bronze claim", direct_quote="q",
            char_start=0, char_end=5, tier="BRONZE",
            relevance_score=0.3, embedding=emb1,
        )
        c_gold = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="gold claim", direct_quote="q",
            char_start=10, char_end=15, tier="GOLD",
            relevance_score=0.9, embedding=emb2,
        )
        results = store.search_claims_by_vector(
            workspace_id=workspace_id, query_embedding=emb2, k=5,
            tier_filter=("GOLD",),
        )
        assert len(results) == 1
        assert results[0][0] == c_gold

    def test_search_empty_result(
        self, store: MeshStore, workspace_id: str
    ):
        """Empty workspace / no matching claims → empty list, no crash."""
        q = _random_emb(seed=0)
        result = store.search_claims_by_vector(
            workspace_id=workspace_id, query_embedding=q, k=10,
        )
        assert result == []

    def test_search_excludes_flagged(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        emb = _random_emb(seed=1)
        c1 = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="good", direct_quote="q",
            char_start=0, char_end=5, tier="GOLD",
            relevance_score=0.9, embedding=emb,
        )
        c2 = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="bad", direct_quote="q",
            char_start=10, char_end=15, tier="GOLD",
            relevance_score=0.9, embedding=emb,
        )
        store.flag_claim(c2, reason="wrong")
        results = store.search_claims_by_vector(
            workspace_id=workspace_id, query_embedding=emb, k=5,
        )
        ids = [r[0] for r in results]
        assert c1 in ids
        assert c2 not in ids

    def test_search_overfetch_defends_against_lossy_knn(
        self, store: MeshStore
    ):
        """
        Advisor's actual concern: a naive JOIN+WHERE with k=2 can return
        zero results if the top-2 by KNN distance are outside the filter.
        Over-fetching (k × 3) with a LIMIT defends against this.
        """
        # Two workspaces share the same mesh.db
        ws_a = store.create_workspace(name="A")
        ws_b = store.create_workspace(name="B")
        src_a = store.insert_source(
            workspace_id=ws_a, kind="upload",
            filepath="a.md", content_hash="ha",
            sig_authority=0.9,
        )
        src_b = store.insert_source(
            workspace_id=ws_b, kind="upload",
            filepath="b.md", content_hash="hb",
            sig_authority=0.9,
        )

        # Build 5 claims: 2 in ws_b that are closest to q, 3 in ws_a
        # that are further away.
        q = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        q[0] = 1.0

        def emb(x0: float) -> np.ndarray:
            v = np.zeros(EMBEDDING_DIM, dtype=np.float32)
            v[0] = x0
            v[1] = float(np.sqrt(max(0.0, 1 - x0 * x0)))
            return v

        # Closest two: ws_b
        store.insert_claim(
            workspace_id=ws_b, source_page_id=src_b,
            statement="b1", direct_quote="q",
            char_start=0, char_end=2, tier="GOLD",
            relevance_score=0.9, embedding=emb(1.00),
        )
        store.insert_claim(
            workspace_id=ws_b, source_page_id=src_b,
            statement="b2", direct_quote="q",
            char_start=2, char_end=4, tier="GOLD",
            relevance_score=0.9, embedding=emb(0.99),
        )
        # Further: ws_a
        a1 = store.insert_claim(
            workspace_id=ws_a, source_page_id=src_a,
            statement="a1", direct_quote="q",
            char_start=0, char_end=2, tier="GOLD",
            relevance_score=0.9, embedding=emb(0.80),
        )
        a2 = store.insert_claim(
            workspace_id=ws_a, source_page_id=src_a,
            statement="a2", direct_quote="q",
            char_start=2, char_end=4, tier="GOLD",
            relevance_score=0.9, embedding=emb(0.70),
        )
        a3 = store.insert_claim(
            workspace_id=ws_a, source_page_id=src_a,
            statement="a3", direct_quote="q",
            char_start=4, char_end=6, tier="GOLD",
            relevance_score=0.9, embedding=emb(0.60),
        )

        # Query: asking for top-2 in ws_a only. The naive KNN-then-filter
        # would return 0 results (top-2 by distance are both ws_b and
        # get filtered out). Our over-fetch makes k=2 → k×3=6 under the
        # hood, which captures all 5 and then filters down to top-2 in ws_a.
        results = store.search_claims_by_vector(
            workspace_id=ws_a, query_embedding=q, k=2,
        )
        ids = [r[0] for r in results]
        assert len(results) == 2
        assert ids[0] == a1  # closest in ws_a
        assert ids[1] == a2


# ───────── transactions + rollback (FIX D1) ─────────

class TestTransactions:

    def test_rollback_undoes_both_sql_and_vec(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        """
        FIX D1 load-bearing test: rolling back a transaction must undo
        BOTH the claims row and the vec_claims virtual table row. If
        sqlite-vec's xRollback were broken, the vec row would persist
        without a corresponding claim row — the exact ghost-vector
        scenario D1 was added to prevent.
        """
        emb = _random_emb(seed=42)

        # Before: empty
        assert store._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
        assert store._conn.execute("SELECT COUNT(*) FROM vec_claims").fetchone()[0] == 0

        # Insert inside an explicit transaction, then raise → rollback
        with pytest.raises(ValueError):
            with store.transaction():
                store.insert_claim(
                    workspace_id=workspace_id, source_page_id=source_id,
                    statement="inside txn", direct_quote="q",
                    char_start=0, char_end=1,
                    tier="GOLD", relevance_score=0.9,
                    embedding=emb,
                )
                # Verify mid-transaction state
                assert store._conn.execute(
                    "SELECT COUNT(*) FROM claims"
                ).fetchone()[0] == 1
                assert store._conn.execute(
                    "SELECT COUNT(*) FROM vec_claims"
                ).fetchone()[0] == 1
                raise ValueError("abort")

        # After rollback: both tables back to empty
        assert store._conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0] == 0
        assert store._conn.execute(
            "SELECT COUNT(*) FROM vec_claims"
        ).fetchone()[0] == 0
        # Workspace counter rolled back too
        ws = store.get_workspace(workspace_id)
        # Source insert happened outside the txn — still counted
        assert ws["source_count"] == 1
        # Claim insert was rolled back
        assert ws["claim_count"] == 0

    def test_commit_persists(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        emb = _random_emb(seed=7)
        with store.transaction():
            store.insert_claim(
                workspace_id=workspace_id, source_page_id=source_id,
                statement="persisted", direct_quote="q",
                char_start=0, char_end=1,
                tier="GOLD", relevance_score=0.9, embedding=emb,
            )
        # Outside the transaction — should still be there
        assert store._conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0] == 1
        assert store._conn.execute(
            "SELECT COUNT(*) FROM vec_claims"
        ).fetchone()[0] == 1


# ───────── FK cascade ─────────

class TestCascade:

    def test_workspace_delete_cascades_core_tables(
        self, store: MeshStore, workspace_id: str, source_id: str
    ):
        clm_id = store.insert_claim(
            workspace_id=workspace_id, source_page_id=source_id,
            statement="s", direct_quote="q",
            char_start=0, char_end=1,
            tier="GOLD", relevance_score=0.9,
        )
        ent_id = store.insert_entity(
            workspace_id=workspace_id, canonical_name="X",
            entity_type="compound",
        )
        store.link_claim_entity(clm_id, ent_id)

        store.delete_workspace(workspace_id)

        assert store._conn.execute(
            "SELECT COUNT(*) FROM source_pages"
        ).fetchone()[0] == 0
        assert store._conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0] == 0
        assert store._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0] == 0
        assert store._conn.execute(
            "SELECT COUNT(*) FROM claim_entities"
        ).fetchone()[0] == 0


# ───────── op log ─────────

class TestOpLog:

    def test_log_and_retrieve(
        self, store: MeshStore, workspace_id: str
    ):
        store.log_op(
            workspace_id=workspace_id,
            op_kind="insert_claim",
            affected_ids=["clm_1", "clm_2"],
            actor="test_runner",
            details={"reason": "test"},
        )
        entries = store.get_op_log(workspace_id, limit=10)
        assert len(entries) == 1
        assert entries[0]["op_kind"] == "insert_claim"
        import json as _json
        assert _json.loads(entries[0]["affected_ids"]) == ["clm_1", "clm_2"]
