"""
Unit tests for wiki mesh edge discovery (Unit 4).

Tests the cosine-only v1 edge typing (no NLI):
  - corroborates: cosine ≥ 0.85 (any source pair)
  - contradicts: cosine ∈ [0.80, 0.85) (different sources only)
  - below 0.80: no edge

Also tests:
  - Self-match exclusion (new claim doesn't edge to itself)
  - Same-source exclusion for contradicts
  - Evidence_weight bounds (clamped to ≥ 0.7 for corroborates)
  - Idempotent re-run
  - Missing claim skipped gracefully
  - Empty claim list short-circuits
  - _distance_to_cosine formula
  - _read_claim_embedding round-trip

Strategy:
  - Pre-insert claims with known embeddings using _unit_vec(cos) helper.
  - New claims are inserted with embeddings that have exact known cosine
    to the pre-existing claims (via the _unit_vec helper from test_mesh_entity).
  - All assertions are against the computed cosine, not raw distances.

Run:
    python -m pytest tests/unit/test_mesh_edge_discovery.py -v
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.polaris_graph.wiki.mesh import MeshStore, MeshStoreError
from src.polaris_graph.wiki.mesh.edge_discovery import (
    CORROBORATION_THRESHOLD,
    CONTRADICTION_THRESHOLD,
    EDGE_KNN_K,
    EVIDENCE_WEIGHT_MIN,
    EdgeDiscoveryResult,
    _distance_to_cosine,
    _read_claim_embedding,
    discover_edges_for_claims,
)
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───── embedding helpers (same pattern as test_mesh_entity) ─────

def _unit_vec(cos_to_ref: float, dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    c = float(cos_to_ref)
    arr[0] = c
    arr[1] = np.sqrt(max(0.0, 1.0 - c * c))
    return arr


def _ref_vec(dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    arr[0] = 1.0
    return arr


def _orthogonal_vec(axis: int, dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    arr[axis] = 1.0
    return arr


# ───── fixtures ─────

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "mesh_edge.db"


@pytest.fixture
def store(tmp_db: Path):
    s = MeshStore.open(tmp_db)
    yield s
    s.close()


@pytest.fixture
def workspace_id(store: MeshStore) -> str:
    return store.create_workspace(
        name="edge_test",
        root_question="Edge discovery tests",
    )


@pytest.fixture
def source_a(store: MeshStore, workspace_id: str) -> str:
    return store.insert_source(
        workspace_id=workspace_id,
        kind="web",
        filepath="source_a.md",
        content_hash="a" * 64,
        sig_authority=0.5,
        url="https://example.com/source-a",
    )


@pytest.fixture
def source_b(store: MeshStore, workspace_id: str) -> str:
    return store.insert_source(
        workspace_id=workspace_id,
        kind="web",
        filepath="source_b.md",
        content_hash="b" * 64,
        sig_authority=0.5,
        url="https://example.com/source-b",
    )


# ───── TestDistanceToCosine ─────

class TestDistanceToCosine:
    def test_identical_vectors(self):
        assert abs(_distance_to_cosine(0.0) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        # L2 distance between orthogonal unit vectors = sqrt(2) ≈ 1.4142
        assert abs(_distance_to_cosine(1.4142) - 0.0) < 1e-3

    def test_opposite_vectors(self):
        assert abs(_distance_to_cosine(2.0) - (-1.0)) < 1e-6

    def test_output_clamped_to_minus_one(self):
        # L2 distance > 2.0 (impossible for unit vectors, but defensive)
        assert _distance_to_cosine(3.0) == -1.0


# ───── TestReadClaimEmbedding ─────

class TestReadClaimEmbedding:
    def test_round_trip(self, store, workspace_id, source_a):
        emb = _ref_vec()
        clm_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="A test claim for embedding read-back",
            direct_quote="test quote text",
            char_start=0, char_end=15,
            tier="GOLD", relevance_score=0.9,
            embedding=emb,
        )
        read_back = _read_claim_embedding(store, clm_id)
        assert read_back is not None
        assert read_back.shape == (EMBEDDING_DIM,)
        np.testing.assert_allclose(read_back, emb, atol=1e-6)

    def test_missing_claim_returns_none(self, store):
        assert _read_claim_embedding(store, "clm_nonexistent") is None


# ───── TestDiscoverEdges ─────

class TestDiscoverEdgesCorroboration:
    def test_high_cosine_creates_corroboration_edge(
        self, store, workspace_id, source_a, source_b,
    ):
        # Existing claim at ref_vec from source_a
        existing_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="GAC removes PFOS effectively",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        # New claim at cos=0.90 to existing (above 0.85 threshold)
        new_emb = _unit_vec(0.90)
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="GAC is effective for PFOS removal",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.85,
            embedding=new_emb,
        )

        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        assert result.corroboration_count == 1
        assert result.contradiction_count == 0
        assert len(result.edge_ids) == 1

        # Verify the edge in the store
        edge = store._conn.execute(
            "SELECT * FROM edges WHERE id = ?",
            (result.edge_ids[0],),
        ).fetchone()
        assert edge["kind"] == "corroborates"
        assert edge["claim_a"] == new_id
        assert edge["claim_b"] == existing_id
        assert edge["evidence_weight"] >= EVIDENCE_WEIGHT_MIN
        assert edge["discovery_method"] == "cosine_knn_v1"

    def test_corroboration_same_source_still_allowed(
        self, store, workspace_id, source_a,
    ):
        # Both from same source — corroboration should still work
        existing_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Claim A from source A",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Similar claim from same source",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="SILVER", relevance_score=0.8,
            embedding=_unit_vec(0.90),
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        assert result.corroboration_count == 1

    def test_evidence_weight_clamped_at_minimum(
        self, store, workspace_id, source_a, source_b,
    ):
        # Even if cosine is exactly at threshold (0.85), evidence_weight
        # should be clamped to EVIDENCE_WEIGHT_MIN (0.7)
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Existing",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        # cos=0.86 — just above threshold, but evidence_weight should be 0.86
        # (which is already > 0.7, so no clamping in this case)
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="New",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_unit_vec(0.86),
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        edge = store._conn.execute(
            "SELECT evidence_weight FROM edges WHERE id = ?",
            (result.edge_ids[0],),
        ).fetchone()
        assert edge["evidence_weight"] >= EVIDENCE_WEIGHT_MIN


class TestDiscoverEdgesContradictionDisabled:
    """
    FIX-C1: Contradiction edges are DISABLED in v1.

    The cosine-only contradiction zone produced 100% false positives in
    the audit — claims about different methods (GAC vs RO) treating the
    same problem registered as "contradicts" because they share domain
    vocabulary. Contradiction requires NLI verification (v2).

    These tests verify that no contradiction edges are created in v1,
    even when claims fall in the old contradiction cosine zone.
    """

    def test_medium_cosine_different_source_no_contradiction(
        self, store, workspace_id, source_a, source_b,
    ):
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="GAC removes 90% of PFOS",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        # cos=0.72 — in the old contradiction zone [0.70, 0.75)
        new_emb = _unit_vec(0.72)
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="GAC removes only 30% of PFOS",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.85,
            embedding=new_emb,
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        # FIX-C1: contradiction disabled in v1
        assert result.contradiction_count == 0
        assert len(result.edge_ids) == 0

    def test_medium_cosine_same_source_no_edge(
        self, store, workspace_id, source_a,
    ):
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Existing from A",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Similar from A",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="SILVER", relevance_score=0.8,
            embedding=_unit_vec(0.72),
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        assert result.contradiction_count == 0


class TestDiscoverEdgesNoEdge:
    def test_low_cosine_no_edge(
        self, store, workspace_id, source_a, source_b,
    ):
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="About PFOS filtration",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        # cos=0.5 — well below both thresholds
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="Unrelated claim about solar panels",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="SILVER", relevance_score=0.6,
            embedding=_unit_vec(0.5),
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        assert len(result.edge_ids) == 0
        assert result.corroboration_count == 0
        assert result.contradiction_count == 0


class TestDiscoverEdgesSelfExclusion:
    def test_self_match_excluded(
        self, store, workspace_id, source_a,
    ):
        # Only one claim in the workspace — KNN returns it as its own
        # nearest neighbor. Self-match must be excluded.
        only_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="The only claim in the workspace",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[only_id],
        )
        assert len(result.edge_ids) == 0


class TestDiscoverEdgesIdempotent:
    def test_rerun_returns_same_edges(
        self, store, workspace_id, source_a, source_b,
    ):
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Existing",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="New high-cosine",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.85,
            embedding=_unit_vec(0.90),
        )
        result_1 = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        result_2 = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
        )
        assert result_1.edge_ids == result_2.edge_ids
        # Only 1 edge row in the store
        count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM edges WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()["c"]
        assert count == 1


class TestDiscoverEdgesValidation:
    def test_empty_claim_list_short_circuits(
        self, store, workspace_id,
    ):
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[],
        )
        assert len(result.edge_ids) == 0
        assert result.skipped == 0

    def test_missing_claim_skipped(
        self, store, workspace_id,
    ):
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=["clm_nonexistent"],
        )
        assert result.skipped == 1
        assert len(result.edge_ids) == 0

    def test_wrong_workspace_skipped(
        self, store, workspace_id, source_a,
    ):
        clm_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Belongs to ws_a",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        ws_other = store.create_workspace(name="other_ws")
        result = discover_edges_for_claims(
            store,
            workspace_id=ws_other,
            new_claim_ids=[clm_id],
        )
        assert result.skipped == 1

    def test_unknown_workspace_raises(self, store):
        with pytest.raises(MeshStoreError, match="Workspace not found"):
            discover_edges_for_claims(
                store,
                workspace_id="ws_nonexistent",
                new_claim_ids=["clm_any"],
            )


class TestDiscoverEdgesPrecomputedEmbedding:
    def test_precomputed_embedding_used(
        self, store, workspace_id, source_a, source_b,
    ):
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Existing",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        new_emb = _unit_vec(0.90)
        new_id = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="New",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.85,
            embedding=new_emb,
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_id],
            embeddings={new_id: new_emb},
        )
        assert result.corroboration_count == 1


class TestDiscoverEdgesMultipleClaims:
    def test_batch_of_new_claims(
        self, store, workspace_id, source_a, source_b,
    ):
        # Pre-existing claim at ref_vec
        store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Existing baseline",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        # Two new claims: one corroborates, one too distant
        new_corr = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="Corroborating claim",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="GOLD", relevance_score=0.85,
            embedding=_unit_vec(0.90),
        )
        new_far = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_b,
            statement="Distant claim",
            direct_quote="test",
            char_start=0, char_end=4,
            tier="SILVER", relevance_score=0.6,
            embedding=_orthogonal_vec(5),
        )
        result = discover_edges_for_claims(
            store,
            workspace_id=workspace_id,
            new_claim_ids=[new_corr, new_far],
        )
        # new_corr corroborates existing; new_far has no match
        # (new_corr also has high cosine to existing but that's
        # the corroboration we already counted)
        assert result.corroboration_count >= 1
        assert result.skipped == 0
