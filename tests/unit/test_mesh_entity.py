"""
Unit tests for wiki mesh entity canonicalization (Unit 3).

Covers the 5-step FIX D2 pipeline:
  1. Exact canonical_name match → confidence 1.0
  2. Alias match (case-insensitive) → confidence 0.95
  3. Cosine ≥ 0.92 merge → confidence = cosine
  4. Cosine 0.80-0.92 disambig:
     - YES → confidence 0.70 (still quarantined)
     - NO or no client → fall through to step 5
  5. New quarantined entity insert → confidence 0.5

Also covers:
  - `classify_entity_type` heuristic for 6 types
  - `canonicalize_entities_for_claim` orchestration (dedup, over-long skip,
    precomputed embeddings path, idempotent linking)
  - `llm_disambiguate` (YES / NO / exception)
  - FIX D2 quarantine semantics (in/out of quarantine queue)
  - `_find_by_canonical`, `_find_by_alias`, `_vec_neighbours` helpers
  - Cross-type merge prevention (step 3 filter)

Strategy:
  - Embeddings are constructed as unit vectors in the first 2 coordinates
    so we get exact known cosines without loading the real model. For
    cosine c we use `[c, sqrt(1-c²), 0, ..., 0]` which has dot product
    `c` with the reference vector `[1, 0, ..., 0]`.
  - All canonicalize_entity calls pass `embedding=...` explicitly so the
    tests never touch `src.utils.embedding_service`.
  - LLM disambig path uses `unittest.mock.AsyncMock` for speed.

Run:
    python -m pytest tests/unit/test_mesh_entity.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.polaris_graph.schemas import SourceAnalysisBatch
from src.polaris_graph.wiki.mesh import MeshStore, MeshStoreError
from src.polaris_graph.wiki.mesh.claim_extract import extract_claims_from_source
from src.polaris_graph.wiki.mesh.entity import (
    COSINE_DISAMBIG_LO,
    COSINE_MERGE_THRESHOLD,
    DISAMBIG_YES_CONFIDENCE,
    NEW_ENTITY_CONFIDENCE,
    QUARANTINE_GATE,
    DisambigResponse,
    _find_by_alias,
    _find_by_canonical,
    _vec_neighbours,
    canonicalize_entities_for_claim,
    canonicalize_entity,
    classify_entity_type,
    llm_disambiguate,
)
from src.polaris_graph.wiki.mesh.ingest import ingest_file
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───────── embedding helpers ─────────

def _unit_vec(cos_to_ref: float, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """
    Unit vector with a known cosine-to-reference.

    For cosine c, returns `[c, sqrt(1 - c²), 0, ..., 0]` which has norm 1
    and dot product c with `[1, 0, ..., 0]`. sqlite-vec computes L2
    distance, and `_vec_neighbours` converts back via
    `cosine = 1 - 0.5 * d²` — which for unit-length vectors equals the
    true cosine.
    """
    arr = np.zeros(dim, dtype=np.float32)
    c = float(cos_to_ref)
    arr[0] = c
    arr[1] = np.sqrt(max(0.0, 1.0 - c * c))
    return arr


def _ref_vec(dim: int = EMBEDDING_DIM) -> np.ndarray:
    """The reference vector `[1, 0, ..., 0]`."""
    arr = np.zeros(dim, dtype=np.float32)
    arr[0] = 1.0
    return arr


def _orthogonal_vec(axis: int, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """
    Unit vector along the `axis`-th basis direction.

    Two `_orthogonal_vec(i)` and `_orthogonal_vec(j)` with i != j have
    cosine 0 between them — they live on different dimensions. Use this
    when a test needs several entities that must NOT accidentally merge
    by cosine. (Note: `_unit_vec(a)` and `_unit_vec(b)` both live in
    the e₀-e₁ plane and are often near-collinear.)
    """
    arr = np.zeros(dim, dtype=np.float32)
    arr[axis] = 1.0
    return arr


# ───────── fixtures ─────────

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "mesh_entity.db"


@pytest.fixture
def store(tmp_db: Path):
    s = MeshStore.open(tmp_db)
    yield s
    s.close()


@pytest.fixture
def workspace_id(store: MeshStore) -> str:
    return store.create_workspace(
        name="entity_test",
        root_question="PFAS canonicalization tests",
    )


@pytest.fixture
def source_id(store: MeshStore, workspace_id: str) -> str:
    """Minimal source row so we can insert claims against it."""
    return store.insert_source(
        workspace_id=workspace_id,
        kind="web",
        filepath="nonexistent.md",
        content_hash="0" * 64,
        sig_authority=0.5,
        url="https://example.com/entity-test",
        title="Entity Test Source",
    )


@pytest.fixture
def claim_id(store: MeshStore, workspace_id: str, source_id: str) -> str:
    """A throw-away claim to link entities against."""
    return store.insert_claim(
        workspace_id=workspace_id,
        source_page_id=source_id,
        statement="A claim statement for entity linking",
        direct_quote="the full quote text goes here for testing",
        char_start=0,
        char_end=40,
        tier="SILVER",
        relevance_score=0.7,
        has_numeric=False,
        embedding=_ref_vec(),
    )


# ───────── TestClassifyEntityType ─────────

class TestClassifyEntityType:
    def test_acronym_is_compound(self):
        assert classify_entity_type("PFOS") == "compound"
        assert classify_entity_type("PFOA") == "compound"
        assert classify_entity_type("C8") == "compound"
        assert classify_entity_type("PFHXS") == "compound"

    def test_known_methods_override_compound(self):
        assert classify_entity_type("GAC") == "method"
        assert classify_entity_type("RO") == "method"
        assert classify_entity_type("HPLC") == "method"
        assert classify_entity_type("ELISA") == "method"

    def test_multi_word_all_caps_is_organization(self):
        assert classify_entity_type("EPA ORD") == "organization"

    def test_person_requires_explicit_disambiguation(self):
        # Explicit title prefix OR middle-initial dot — otherwise
        # 3-token organizations like "Water Research Foundation"
        # would get mis-classified as person.
        assert classify_entity_type("Dr. Jane Smith") == "person"
        assert classify_entity_type("Prof. John Q. Public") == "person"
        assert classify_entity_type("John A. Smith") == "person"

    def test_plain_multi_token_name_is_organization(self):
        # Both "Water Research" (2 tokens) and "Water Research Foundation"
        # (3 tokens) must classify as organization. No dot initial, no
        # honorific prefix → not a person.
        assert classify_entity_type("Water Research") == "organization"
        assert classify_entity_type("Water Research Foundation") == "organization"
        # 3-token person-sounding name without disambiguation also falls
        # through to organization (user can correct in quarantine review).
        assert classify_entity_type("John Michael Smith") == "organization"

    def test_metric_pattern(self):
        assert classify_entity_type("25%") == "metric"
        assert classify_entity_type("p < 0.05") == "metric"
        assert classify_entity_type("95% CI") == "metric"

    def test_fallback_concept(self):
        assert classify_entity_type("some random lowercase text") == "concept"
        assert classify_entity_type("") == "concept"
        assert classify_entity_type("    ") == "concept"


# ───────── TestHelperFunctions ─────────

class TestFindByCanonical:
    def test_exact_match_returns_row(self, store, workspace_id):
        ent_id = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=["pfos"],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        row = _find_by_canonical(store, workspace_id, "PFOS")
        assert row is not None
        assert row["id"] == ent_id

    def test_different_case_does_not_match(self, store, workspace_id):
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Exact canonical match is case-SENSITIVE (aliases handle case)
        assert _find_by_canonical(store, workspace_id, "pfos") is None

    def test_missing_returns_none(self, store, workspace_id):
        assert _find_by_canonical(store, workspace_id, "NOTHING") is None


class TestFindByAlias:
    def test_alias_match_case_insensitive(self, store, workspace_id):
        ent_id = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctanoic Acid",
            entity_type="compound",
            aliases=["pfoa", "C8"],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Different case than stored alias
        row = _find_by_alias(store, workspace_id, "pFoA")
        assert row is not None
        assert row["id"] == ent_id

    def test_mixed_case_alias_match(self, store, workspace_id):
        ent_id = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctanoic Acid",
            entity_type="compound",
            aliases=["pfoa", "C8"],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        row = _find_by_alias(store, workspace_id, "c8")
        assert row is not None
        assert row["id"] == ent_id

    def test_no_alias_match_returns_none(self, store, workspace_id):
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctanoic Acid",
            entity_type="compound",
            aliases=["pfoa"],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        assert _find_by_alias(store, workspace_id, "UNKNOWN") is None


class TestVecNeighbours:
    def test_empty_workspace_returns_empty(self, store, workspace_id):
        result = _vec_neighbours(
            store, workspace_id=workspace_id,
            query_embedding=_ref_vec(), k=5,
        )
        assert result == []

    def test_cosine_self_is_one(self, store, workspace_id):
        ent_id = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Target",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        result = _vec_neighbours(
            store, workspace_id=workspace_id,
            query_embedding=_ref_vec(), k=5,
        )
        assert len(result) == 1
        row, cos = result[0]
        assert row["id"] == ent_id
        assert abs(cos - 1.0) < 1e-4

    def test_cosine_formula_matches_known_angle(self, store, workspace_id):
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Target",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Query at cosine = 0.8 exactly
        result = _vec_neighbours(
            store, workspace_id=workspace_id,
            query_embedding=_unit_vec(0.8), k=5,
        )
        assert len(result) == 1
        _, cos = result[0]
        assert abs(cos - 0.8) < 1e-3

    def test_dim_mismatch_raises(self, store, workspace_id):
        bad = np.zeros(10, dtype=np.float32)
        with pytest.raises(MeshStoreError, match="dim="):
            _vec_neighbours(
                store, workspace_id=workspace_id,
                query_embedding=bad, k=5,
            )


# ───────── TestCanonicalizeEntity (5 paths) ─────────

class TestCanonicalizeEntityFivePaths:
    @pytest.mark.asyncio
    async def test_path_1_exact_canonical_match(self, store, workspace_id):
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        ent_id_2, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="PFOS",
            embedding=_ref_vec(),
            entity_type="compound",
        )
        assert ent_id_2 == ent_id_1
        assert conf == 1.0
        assert is_new is False

    @pytest.mark.asyncio
    async def test_path_2_alias_match_case_insensitive(
        self, store, workspace_id,
    ):
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctanoic Acid",
            entity_type="compound",
            aliases=["pfoa", "c8"],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Surface differs from canonical AND from stored alias case
        ent_id_2, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="PFOA",
            embedding=_ref_vec(),
            entity_type="compound",
        )
        assert ent_id_2 == ent_id_1
        assert conf == 0.95
        assert is_new is False

    @pytest.mark.asyncio
    async def test_path_3_cosine_merge(self, store, workspace_id):
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctane Sulfonate",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Query at cosine 0.95 — above merge threshold 0.92
        query_emb = _unit_vec(0.95)
        ent_id_2, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="perfluorooctyl sulfonate",
            embedding=query_emb,
            entity_type="compound",
        )
        assert ent_id_2 == ent_id_1
        assert conf >= COSINE_MERGE_THRESHOLD
        assert is_new is False
        # Alias was added
        row = store._conn.execute(
            "SELECT aliases FROM entities WHERE id = ?", (ent_id_1,),
        ).fetchone()
        aliases = json.loads(row["aliases"])
        assert "perfluorooctyl sulfonate" in aliases

    @pytest.mark.asyncio
    async def test_path_3_cosine_just_above_threshold(
        self, store, workspace_id,
    ):
        # Boundary case: cos just above MERGE_THRESHOLD.
        # We use 0.93 (not exactly 0.92) because float32 vectors make
        # the theoretical 0.92 land at ~0.9199 after L2→cosine conversion.
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Target",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        query_emb = _unit_vec(0.93)
        ent_id_2, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="AboveBoundary",
            embedding=query_emb,
            entity_type="compound",
        )
        assert ent_id_2 == ent_id_1
        assert is_new is False

    @pytest.mark.asyncio
    async def test_path_4_disambig_yes_merges(self, store, workspace_id):
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFBS",
            entity_type="compound",
            aliases=[],
            confidence=0.5,
            user_confirmed=False,
            embedding=_ref_vec(),
        )
        query_emb = _unit_vec(0.85)  # disambig zone

        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            return_value=DisambigResponse(same_entity=True, reasoning="synonym"),
        )

        ent_id_2, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="perfluorobutane sulfonate",
            embedding=query_emb,
            disambig_client=mock_client,
            entity_type="compound",
        )
        assert ent_id_2 == ent_id_1
        assert conf == DISAMBIG_YES_CONFIDENCE
        assert is_new is False
        mock_client.generate_structured.assert_called_once()
        # Confidence was promoted on the stored entity
        row = store._conn.execute(
            "SELECT confidence FROM entities WHERE id = ?", (ent_id_1,),
        ).fetchone()
        assert row["confidence"] >= DISAMBIG_YES_CONFIDENCE

    @pytest.mark.asyncio
    async def test_path_4_disambig_no_falls_through(
        self, store, workspace_id,
    ):
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFBS",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        query_emb = _unit_vec(0.85)

        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            return_value=DisambigResponse(same_entity=False, reasoning="no"),
        )

        ent_id_2, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="SomethingElse",
            embedding=query_emb,
            disambig_client=mock_client,
            entity_type="compound",
        )
        # New quarantined entity
        assert ent_id_2 != ent_id_1
        assert conf == NEW_ENTITY_CONFIDENCE
        assert is_new is True

    @pytest.mark.asyncio
    async def test_path_4_no_disambig_client_falls_through(
        self, store, workspace_id,
    ):
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFBS",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        query_emb = _unit_vec(0.85)
        ent_id, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="NewThingAltogether",
            embedding=query_emb,
            disambig_client=None,
            entity_type="compound",
        )
        assert is_new is True
        assert conf == NEW_ENTITY_CONFIDENCE

    @pytest.mark.asyncio
    async def test_path_4_disambig_exception_falls_through(
        self, store, workspace_id,
    ):
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Target",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        query_emb = _unit_vec(0.85)

        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            side_effect=RuntimeError("network failure"),
        )
        ent_id, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="DoesNotMatter",
            embedding=query_emb,
            disambig_client=mock_client,
            entity_type="compound",
        )
        # Exception treated as NO → new quarantined entity
        assert is_new is True
        assert conf == NEW_ENTITY_CONFIDENCE

    @pytest.mark.asyncio
    async def test_path_5_new_quarantined_empty_store(
        self, store, workspace_id,
    ):
        ent_id, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="BrandNewThing",
            embedding=_ref_vec(),
            entity_type="compound",
        )
        assert is_new is True
        assert conf == NEW_ENTITY_CONFIDENCE
        assert conf < QUARANTINE_GATE  # below 0.8 quarantine gate
        row = store._conn.execute(
            "SELECT confidence, user_confirmed FROM entities WHERE id = ?",
            (ent_id,),
        ).fetchone()
        assert row["confidence"] == NEW_ENTITY_CONFIDENCE
        assert row["user_confirmed"] == 0

    @pytest.mark.asyncio
    async def test_path_5_low_cosine_new_entity(self, store, workspace_id):
        # Existing entity far from query in embedding space
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Compound A",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Query at cosine 0.3 — below disambig lower bound 0.8
        query_emb = _unit_vec(0.3)
        ent_id, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="Compound B",
            embedding=query_emb,
            entity_type="compound",
        )
        assert is_new is True
        assert conf == NEW_ENTITY_CONFIDENCE


class TestCanonicalizeEntityValidation:
    @pytest.mark.asyncio
    async def test_empty_surface_raises(self, store, workspace_id):
        with pytest.raises(MeshStoreError, match="non-empty"):
            await canonicalize_entity(
                store,
                workspace_id=workspace_id,
                surface_form="   ",
                embedding=_ref_vec(),
            )

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises(self, store):
        with pytest.raises(MeshStoreError, match="Workspace not found"):
            await canonicalize_entity(
                store,
                workspace_id="ws_does_not_exist",
                surface_form="Anything",
                embedding=_ref_vec(),
            )


class TestCrossTypeFilter:
    @pytest.mark.asyncio
    async def test_type_filter_prevents_merge_with_high_cosine(
        self, store, workspace_id,
    ):
        # Compound entity at reference embedding
        store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Query with SAME high cosine but DIFFERENT entity_type
        query_emb = _unit_vec(0.98)  # well above merge threshold
        ent_id, conf, is_new = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="some_org",
            embedding=query_emb,
            entity_type="organization",
        )
        # Type filter blocked the merge → new quarantined entity
        assert is_new is True
        assert conf == NEW_ENTITY_CONFIDENCE


# ───────── TestCanonicalizeEntitiesForClaim ─────────

class TestCanonicalizeEntitiesForClaim:
    @pytest.mark.asyncio
    async def test_empty_list_short_circuits(
        self, store, workspace_id, claim_id,
    ):
        result = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=[],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_entities_each_linked(
        self, store, workspace_id, claim_id,
    ):
        # Use orthogonal embeddings so the 3 surfaces can't accidentally
        # merge via cosine. PFOS and EPA are both classified as
        # "compound" (acronym rule) — without orthogonal vectors, the
        # second one would cosine-merge into the first.
        embeddings = {
            "PFOS": _orthogonal_vec(0),
            "GAC":  _orthogonal_vec(1),
            "EPA":  _orthogonal_vec(2),
        }
        result = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=["PFOS", "GAC", "EPA"],
            embeddings=embeddings,
        )
        assert len(result) == 3
        # Each link exists in claim_entities
        rows = store._conn.execute(
            "SELECT entity_id FROM claim_entities WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_dedup_repeated_and_whitespace_surfaces(
        self, store, workspace_id, claim_id,
    ):
        embeddings = {"PFOS": _unit_vec(0.20)}
        result = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=["PFOS", "PFOS", "  PFOS  ", ""],
            embeddings=embeddings,
        )
        # Only one unique non-empty entity
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_over_long_surface_skipped(
        self, store, workspace_id, claim_id,
    ):
        long_surface = "a" * 100  # over 80-char bound
        embeddings = {
            "PFOS": _unit_vec(0.20),
            long_surface: _unit_vec(0.15),
        }
        result = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=[long_surface, "PFOS"],
            embeddings=embeddings,
        )
        # Only the short one made it through
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_idempotent_link_on_repeat_call(
        self, store, workspace_id, claim_id,
    ):
        embeddings = {"PFOS": _unit_vec(0.20)}
        result_1 = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=["PFOS"],
            embeddings=embeddings,
        )
        result_2 = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=["PFOS"],
            embeddings=embeddings,
        )
        # Same entity id both times, still exactly one claim_entities row
        assert result_1 == result_2
        rows = store._conn.execute(
            "SELECT COUNT(*) AS c FROM claim_entities WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        assert rows["c"] == 1

    @pytest.mark.asyncio
    async def test_precomputed_embedding_used_when_present(
        self, store, workspace_id, claim_id,
    ):
        # Pre-insert a target at the reference vector. We want
        # canonicalize_entities_for_claim to MERGE into it using the
        # precomputed embedding we supply — this proves the embedding
        # path is plumbed end-to-end.
        ent_id_target = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="Perfluorooctane Sulfonate",
            entity_type="compound",
            aliases=[],
            confidence=0.9,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Pre-compute a near-merge embedding for a new surface. Use an
        # all-caps surface so the classifier returns "compound" — same
        # type as the target, so the cross-type filter doesn't block
        # the path-3 cosine merge we're trying to exercise.
        embeddings = {"PFOSA": _unit_vec(0.96)}
        result = await canonicalize_entities_for_claim(
            store,
            workspace_id=workspace_id,
            claim_id=claim_id,
            surface_forms=["PFOSA"],
            embeddings=embeddings,
        )
        assert result == [ent_id_target]


# ───────── TestLLMDisambiguate ─────────

class TestLLMDisambiguate:
    @pytest.mark.asyncio
    async def test_yes_returns_true(self):
        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            return_value=DisambigResponse(same_entity=True),
        )
        result = await llm_disambiguate(
            mock_client,
            surface_form="PFOS",
            candidate_canonical="Perfluorooctane Sulfonate",
            entity_type="compound",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_no_returns_false(self):
        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            return_value=DisambigResponse(same_entity=False),
        )
        result = await llm_disambiguate(
            mock_client,
            surface_form="PFOS",
            candidate_canonical="GAC",
            entity_type="compound",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            side_effect=ConnectionError("network failure"),
        )
        result = await llm_disambiguate(
            mock_client,
            surface_form="anything",
            candidate_canonical="whatever",
            entity_type="compound",
        )
        assert result is False


# ───────── TestQuarantineSemantics ─────────

class TestQuarantineSemantics:
    @pytest.mark.asyncio
    async def test_new_entity_appears_in_quarantine(
        self, store, workspace_id,
    ):
        ent_id, _, _ = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="NovelCompound",
            embedding=_ref_vec(),
            entity_type="compound",
        )
        q = store.get_quarantined_entities(workspace_id)
        assert any(row["id"] == ent_id for row in q)

    @pytest.mark.asyncio
    async def test_confirm_removes_from_quarantine(
        self, store, workspace_id,
    ):
        ent_id, _, _ = await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="NovelCompound",
            embedding=_ref_vec(),
            entity_type="compound",
        )
        store.confirm_entity(ent_id)
        q = store.get_quarantined_entities(workspace_id)
        assert all(row["id"] != ent_id for row in q)

    @pytest.mark.asyncio
    async def test_high_confidence_path_1_not_in_quarantine(
        self, store, workspace_id,
    ):
        # Pre-seed a confirmed, high-confidence entity
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=[],
            confidence=0.95,
            user_confirmed=True,
            embedding=_ref_vec(),
        )
        # Exact canonical match should NOT push it back into quarantine
        await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="PFOS",
            embedding=_ref_vec(),
            entity_type="compound",
        )
        q = store.get_quarantined_entities(workspace_id)
        assert all(row["id"] != ent_id_1 for row in q)

    @pytest.mark.asyncio
    async def test_disambig_yes_confidence_still_quarantined(
        self, store, workspace_id,
    ):
        # Existing entity with low confidence (new)
        ent_id_1 = store.insert_entity(
            workspace_id=workspace_id,
            canonical_name="PFBS",
            entity_type="compound",
            aliases=[],
            confidence=0.5,
            user_confirmed=False,
            embedding=_ref_vec(),
        )
        mock_client = MagicMock()
        mock_client.generate_structured = AsyncMock(
            return_value=DisambigResponse(same_entity=True),
        )
        await canonicalize_entity(
            store,
            workspace_id=workspace_id,
            surface_form="perfluorobutane sulfonic acid",
            embedding=_unit_vec(0.85),
            disambig_client=mock_client,
            entity_type="compound",
        )
        # DISAMBIG_YES_CONFIDENCE = 0.70, still below the 0.8 quarantine
        # gate → entity remains in the quarantine queue for user review.
        q = store.get_quarantined_entities(workspace_id)
        assert any(row["id"] == ent_id_1 for row in q)


# ───────── TestClaimExtractEntityIntegration ─────────
#
# End-to-end: mock LLM returns AtomicFact objects with the new `entities`
# field populated. Feed them through `extract_claims_from_source`,
# verify both claims AND entities AND claim_entities links are written
# atomically in the same transaction.
#
# This is the top-level smoke test for the Unit 2 → Unit 3 integration.
# If this passes, the whole L2 write path — ingest → extract → parse →
# insert_claim → canonicalize_entities_for_claim — is working.


_INTEGRATION_BODY = (
    "This study evaluates household PFAS filtration approaches. "
    "GAC achieved 85% removal of PFOS and PFOA across independent "
    "trials at typical residential concentrations. Reverse osmosis "
    "membranes performed at 95% CI 91-97% but required substantial "
    "pressurization during normal household operation. Ion exchange "
    "resins using AIX showed variable results with n=12 trials."
)
_INTEGRATION_URL = "https://example.com/integration-study"


class _MockLLMClient:
    """Minimal LLM stand-in that always returns a pre-built batch."""

    def __init__(self, batch: SourceAnalysisBatch):
        self._batch = batch
        self.calls = 0

    async def generate_structured(
        self, *, prompt, schema, system, max_tokens,
        timeout, reasoning_enabled,
    ):
        self.calls += 1
        return self._batch


def _build_integration_batch(
    facts_with_entities: list[dict],
) -> SourceAnalysisBatch:
    """
    Build a SourceAnalysisBatch via model_validate(dict) — the production
    `filter_invalid_analyses` validator drops pre-instantiated
    SourceAnalysis objects because it expects dicts in `mode="before"`.
    """
    return SourceAnalysisBatch.model_validate({
        "analyses": [
            {
                "source_url": _INTEGRATION_URL,
                "source_title": "Integration Test",
                "source_type": "journal_article",
                "source_quality": 0.8,
                "overall_relevance": 0.85,
                "atomic_facts": facts_with_entities,
            }
        ]
    })


@pytest.fixture
def integration_source_file(tmp_path: Path) -> Path:
    f = tmp_path / "integration.md"
    f.write_text(_INTEGRATION_BODY, encoding="utf-8")
    return f


class TestClaimExtractEntityIntegration:
    """Full Unit 2 + Unit 3 integration via the orchestrator."""

    @pytest.mark.asyncio
    async def test_entities_populated_end_to_end(
        self, store, workspace_id, integration_source_file,
    ):
        src_id, _ = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=integration_source_file,
            kind="upload",
            url=_INTEGRATION_URL,
        )

        # Two facts with entities populated. The LLM-side extraction
        # prompt asks for 1-5 short canonical entity names per fact.
        batch = _build_integration_batch([
            {
                "statement": "GAC achieved 85% removal of PFOS and PFOA across independent trials",
                "direct_quote": "GAC achieved 85% removal of PFOS and PFOA across independent trials at typical residential concentrations",
                "relevance_score": 0.9,
                "confidence": 0.9,
                "entities": ["GAC", "PFOS", "PFOA"],
            },
            {
                "statement": "Reverse osmosis membranes performed at 95% CI 91-97% with high precision",
                "direct_quote": "Reverse osmosis membranes performed at 95% CI 91-97% but required substantial pressurization during normal household operation",
                "relevance_score": 0.85,
                "confidence": 0.9,
                "entities": ["RO", "95% CI"],
            },
        ])
        client = _MockLLMClient(batch)

        result = await extract_claims_from_source(
            client=client,
            store=store,
            workspace_id=workspace_id,
            source_page_id=src_id,
            query="How do PFAS filters work?",
            disambig_client=None,  # no disambig, direct quarantined insert
        )

        # Claims inserted
        assert len(result.inserted_claim_ids) == 2
        assert result.total_facts_seen == 2

        # 4 unique entities expected: GAC, PFOS, PFOA, RO, 95% CI
        # — wait that's 5. Let me recount: {GAC, PFOS, PFOA, RO, "95% CI"}
        # Note that "95% CI" classifies as metric, others are compound/method.
        ents = store._conn.execute(
            "SELECT canonical_name, entity_type FROM entities "
            "WHERE workspace_id = ? ORDER BY canonical_name",
            (workspace_id,),
        ).fetchall()
        canonical_names = sorted(e["canonical_name"] for e in ents)
        assert canonical_names == ["95% CI", "GAC", "PFOA", "PFOS", "RO"]

        # Check the classifier placed them in the right buckets
        type_map = {e["canonical_name"]: e["entity_type"] for e in ents}
        assert type_map["PFOS"] == "compound"
        assert type_map["PFOA"] == "compound"
        assert type_map["GAC"] == "method"
        assert type_map["RO"] == "method"
        assert type_map["95% CI"] == "metric"

        # claim_entities links: claim 1 → {GAC, PFOS, PFOA}, claim 2 → {RO, 95% CI}
        link_rows = store._conn.execute(
            "SELECT claim_id, entity_id FROM claim_entities"
        ).fetchall()
        assert len(link_rows) == 5

        # Every newly-created entity is in quarantine (confidence 0.5, not confirmed)
        q = store.get_quarantined_entities(workspace_id)
        assert len(q) == 5

    @pytest.mark.asyncio
    async def test_backward_compat_no_entities_field(
        self, store, workspace_id, integration_source_file,
    ):
        """
        Legacy AtomicFact input (no `entities` key in the dict) must
        round-trip cleanly — the backward-compat validator defaults
        entities=[], the parser emits an empty surface form list, and
        the orchestrator canonicalization pass is a no-op. No entities
        get created, no claim_entities rows written, claims still land.
        """
        src_id, _ = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=integration_source_file,
            kind="upload",
            url=_INTEGRATION_URL,
        )
        batch = _build_integration_batch([
            {
                "statement": "GAC achieved 85% removal of PFOS and PFOA across independent trials",
                "direct_quote": "GAC achieved 85% removal of PFOS and PFOA across independent trials at typical residential concentrations",
                "relevance_score": 0.9,
                "confidence": 0.9,
                # NOTE: no "entities" key at all — legacy / backward-compat path
            },
        ])
        client = _MockLLMClient(batch)
        result = await extract_claims_from_source(
            client=client,
            store=store,
            workspace_id=workspace_id,
            source_page_id=src_id,
            query="test query",
        )
        assert len(result.inserted_claim_ids) == 1
        # No entities created (legacy fact had none)
        ent_count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM entities WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()["c"]
        assert ent_count == 0
        # No links either
        link_count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM claim_entities"
        ).fetchone()["c"]
        assert link_count == 0

    @pytest.mark.asyncio
    async def test_duplicate_entity_across_claims_merges(
        self, store, workspace_id, integration_source_file,
    ):
        """Same entity mentioned in two different claims → single
        entity row, two claim_entities links."""
        src_id, _ = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=integration_source_file,
            kind="upload",
            url=_INTEGRATION_URL,
        )
        batch = _build_integration_batch([
            {
                "statement": "GAC achieved 85% removal of PFOS and PFOA across independent trials",
                "direct_quote": "GAC achieved 85% removal of PFOS and PFOA across independent trials at typical residential concentrations",
                "relevance_score": 0.9,
                "confidence": 0.9,
                "entities": ["GAC", "PFOS"],
            },
            {
                "statement": "Reverse osmosis membranes performed at 95% CI 91-97% with high precision",
                "direct_quote": "Reverse osmosis membranes performed at 95% CI 91-97% but required substantial pressurization during normal household operation",
                "relevance_score": 0.85,
                "confidence": 0.9,
                "entities": ["PFOS", "RO"],  # PFOS again
            },
        ])
        client = _MockLLMClient(batch)
        await extract_claims_from_source(
            client=client,
            store=store,
            workspace_id=workspace_id,
            source_page_id=src_id,
            query="test",
        )
        # 3 unique entities: GAC, PFOS, RO
        ent_count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM entities WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()["c"]
        assert ent_count == 3
        # 4 links: claim 1 → {GAC, PFOS}, claim 2 → {PFOS, RO}
        link_count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM claim_entities"
        ).fetchone()["c"]
        assert link_count == 4
        # PFOS.times_referenced should be 2 (linked twice)
        pfos_row = store._conn.execute(
            "SELECT times_referenced FROM entities "
            "WHERE workspace_id = ? AND canonical_name = ?",
            (workspace_id, "PFOS"),
        ).fetchone()
        assert pfos_row["times_referenced"] == 2
