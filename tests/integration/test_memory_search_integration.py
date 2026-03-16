"""Integration tests: memory search returns relevant items.

Sprint 3 deferred item — verifies the full LTM lifecycle:
  promote_to_ltm() → get_ltm_stats() → query_ltm() → list_ltm_items() → delete_ltm_item()

Uses a real (ephemeral) ChromaDB EphemeralClient for each test so tests are
fully isolated and exercise the actual embedding model + similarity search.
"""

import os
import uuid
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Skip if chromadb not installed
# ---------------------------------------------------------------------------
try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

pytestmark = pytest.mark.skipif(not HAS_CHROMA, reason="chromadb not installed")


_MODULE_CHROMA = chromadb.EphemeralClient()


# ---------------------------------------------------------------------------
# Fixture: isolated cross_vector module with unique collection names per test
# ---------------------------------------------------------------------------

@pytest.fixture()
def cv():
    """Yield the cross_vector module with unique per-test collection names
    to guarantee full isolation (EphemeralClient shares a global backend)."""
    import importlib

    try:
        import src.polaris_graph.memory.cross_vector as cv_mod
        importlib.reload(cv_mod)
    except Exception:
        pytest.skip("Cannot import cross_vector module")

    client = _MODULE_CHROMA
    suffix = uuid.uuid4().hex[:8]
    ltm_name = f"{cv_mod.LTM_COLLECTION_NAME}_{suffix}"
    ovr_name = f"{cv_mod.OVERRIDE_COLLECTION_NAME}_{suffix}"

    original_get_col = cv_mod._get_collection
    original_get_ovr = getattr(cv_mod, "_get_override_collection", None)

    def _patched_get_collection(manager):
        return client.get_or_create_collection(name=ltm_name)

    def _patched_get_override_collection(manager):
        return client.get_or_create_collection(name=ovr_name)

    with patch.object(cv_mod, "_get_chroma_manager", return_value=client):
        cv_mod._get_collection = _patched_get_collection
        cv_mod._get_override_collection = _patched_get_override_collection
        yield cv_mod
        cv_mod._get_collection = original_get_col
        if original_get_ovr is not None:
            cv_mod._get_override_collection = original_get_ovr

    # Cleanup per-test collections
    for col_name in (ltm_name, ovr_name):
        try:
            client.delete_collection(col_name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sample evidence fixtures
# ---------------------------------------------------------------------------

def _gold_evidence(n: int = 5) -> list[dict]:
    return [
        {
            "evidence_id": f"ev_gold_{i:03d}",
            "statement": f"PFAS concentration reduced by {90 + i}% using GAC filtration.",
            "source": f"https://epa.gov/pfas/study{i}",
            "quality_tier": "GOLD",
            "faithfulness": 0.95,
            "relevance_score": 0.85 + i * 0.01,
            "perspective": "regulatory",
        }
        for i in range(n)
    ]


def _silver_evidence(n: int = 3) -> list[dict]:
    return [
        {
            "evidence_id": f"ev_silver_{i:03d}",
            "statement": f"Ion exchange resin shows {75 + i}% removal efficiency.",
            "source": f"https://watertech.org/study{i}",
            "quality_tier": "SILVER",
            "faithfulness": 0.80,
            "relevance_score": 0.70,
            "perspective": "technical",
        }
        for i in range(n)
    ]


def _bronze_evidence(n: int = 2) -> list[dict]:
    return [
        {
            "evidence_id": f"ev_bronze_{i:03d}",
            "statement": f"Preliminary data suggests nanofiltration approach {i}.",
            "source": f"https://blog.example.com/nf{i}",
            "quality_tier": "BRONZE",
            "faithfulness": 0.55,
            "relevance_score": 0.50,
            "perspective": "industry",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests: promote_to_ltm
# ---------------------------------------------------------------------------


class TestPromoteToLtm:
    """Verify evidence promotion with quality gates."""

    def test_promote_gold_evidence(self, cv):
        count = cv.promote_to_ltm(
            _gold_evidence(5), vector_id="VEC_001",
            min_quality="BRONZE", min_faithfulness=0.5,
        )
        assert count == 5, f"Expected 5 promoted, got {count}"

    def test_promote_respects_tier_gate(self, cv):
        """With min_quality=GOLD, SILVER and BRONZE should be filtered out."""
        mixed = _gold_evidence(2) + _silver_evidence(2) + _bronze_evidence(2)
        count = cv.promote_to_ltm(mixed, vector_id="VEC_002",
                                  min_quality="GOLD", min_faithfulness=0.9)
        assert count == 2, f"Only GOLD with faith>=0.9 should pass, got {count}"

    def test_promote_respects_faithfulness_gate(self, cv):
        """Evidence below faithfulness threshold should be filtered."""
        low_faith = _gold_evidence(1)
        low_faith[0]["faithfulness"] = 0.3
        count = cv.promote_to_ltm(low_faith, vector_id="VEC_003",
                                  min_quality="BRONZE", min_faithfulness=0.5)
        assert count == 0

    def test_promote_empty_list(self, cv):
        count = cv.promote_to_ltm([], vector_id="VEC_004")
        assert count == 0

    def test_promote_idempotent(self, cv):
        """Upserting same evidence twice should not create duplicates."""
        ev = _gold_evidence(3)
        cv.promote_to_ltm(ev, vector_id="VEC_005",
                          min_quality="BRONZE", min_faithfulness=0.5)
        cv.promote_to_ltm(ev, vector_id="VEC_005",
                          min_quality="BRONZE", min_faithfulness=0.5)
        stats = cv.get_ltm_stats()
        assert stats["total_items"] == 3


# ---------------------------------------------------------------------------
# Tests: get_ltm_stats
# ---------------------------------------------------------------------------


class TestGetLtmStats:
    """Verify stats reflect promoted items accurately."""

    def test_stats_empty_collection(self, cv):
        stats = cv.get_ltm_stats()
        assert stats["available"] is True
        assert stats["total_items"] == 0

    def test_stats_after_promotion(self, cv):
        cv.promote_to_ltm(_gold_evidence(3) + _silver_evidence(2),
                          vector_id="VEC_STATS",
                          min_quality="BRONZE", min_faithfulness=0.5)
        stats = cv.get_ltm_stats()
        assert stats["total_items"] == 5
        assert stats["by_tier"]["GOLD"] == 3
        assert stats["by_tier"]["SILVER"] == 2

    def test_stats_top_domains(self, cv):
        cv.promote_to_ltm(_gold_evidence(5), vector_id="VEC_DOM",
                          min_quality="BRONZE", min_faithfulness=0.5)
        stats = cv.get_ltm_stats()
        domains = stats.get("top_domains", [])
        assert len(domains) >= 1
        # All gold evidence comes from epa.gov
        assert any(d["domain"] == "epa.gov" for d in domains)


# ---------------------------------------------------------------------------
# Tests: query_ltm (semantic search)
# ---------------------------------------------------------------------------


class TestQueryLtm:
    """Verify semantic similarity search returns relevant results."""

    @pytest.fixture(autouse=True)
    def _populate(self, cv):
        """Seed LTM with mixed evidence for search tests."""
        all_ev = _gold_evidence(5) + _silver_evidence(3) + _bronze_evidence(2)
        cv.promote_to_ltm(all_ev, vector_id="VEC_SEARCH",
                          min_quality="BRONZE", min_faithfulness=0.5)
        self.cv = cv

    def test_query_returns_results(self):
        results = self.cv.query_ltm("PFAS filtration GAC carbon", max_results=10)
        assert len(results) >= 1

    def test_query_result_schema(self):
        results = self.cv.query_ltm("activated carbon filtration", max_results=5)
        assert len(results) >= 1
        item = results[0]
        required_keys = {"id", "statement", "source", "quality_tier",
                         "faithfulness", "vector_id", "distance"}
        assert required_keys.issubset(set(item.keys())), \
            f"Missing keys: {required_keys - set(item.keys())}"

    def test_query_relevance_ordering(self):
        """Results should be ordered by distance (ascending = most similar first)."""
        results = self.cv.query_ltm("GAC activated carbon PFAS removal", max_results=10)
        if len(results) >= 2:
            distances = [r["distance"] for r in results]
            assert distances == sorted(distances), \
                f"Results not sorted by distance: {distances}"

    def test_query_max_results_respected(self):
        results = self.cv.query_ltm("water treatment", max_results=3)
        assert len(results) <= 3

    def test_query_empty_string_safe(self):
        """Empty query should not crash."""
        results = self.cv.query_ltm("", max_results=5)
        assert isinstance(results, list)

    def test_query_unrelated_topic_low_similarity(self):
        """Query for unrelated topic should have higher distances."""
        related = self.cv.query_ltm("PFAS water filtration methods", max_results=5)
        unrelated = self.cv.query_ltm("quantum computing algorithms", max_results=5)
        if related and unrelated:
            avg_related = sum(r["distance"] for r in related) / len(related)
            avg_unrelated = sum(r["distance"] for r in unrelated) / len(unrelated)
            assert avg_unrelated > avg_related, \
                f"Unrelated ({avg_unrelated:.3f}) should have higher distance " \
                f"than related ({avg_related:.3f})"


# ---------------------------------------------------------------------------
# Tests: list_ltm_items (pagination)
# ---------------------------------------------------------------------------


class TestListLtmItems:
    """Verify listing with pagination."""

    @pytest.fixture(autouse=True)
    def _populate(self, cv):
        cv.promote_to_ltm(_gold_evidence(5) + _silver_evidence(3),
                          vector_id="VEC_LIST",
                          min_quality="BRONZE", min_faithfulness=0.5)
        self.cv = cv

    def test_list_returns_all(self):
        result = self.cv.list_ltm_items(limit=100, offset=0)
        assert result["total"] == 8
        assert len(result["items"]) == 8

    def test_list_pagination(self):
        page1 = self.cv.list_ltm_items(limit=3, offset=0)
        page2 = self.cv.list_ltm_items(limit=3, offset=3)
        assert len(page1["items"]) == 3
        assert len(page2["items"]) == 3
        ids_1 = {i["id"] for i in page1["items"]}
        ids_2 = {i["id"] for i in page2["items"]}
        assert ids_1.isdisjoint(ids_2), "Pages should not overlap"

    def test_list_item_schema(self):
        result = self.cv.list_ltm_items(limit=1)
        item = result["items"][0]
        assert "id" in item
        assert "statement" in item
        assert "quality_tier" in item


# ---------------------------------------------------------------------------
# Tests: delete_ltm_item
# ---------------------------------------------------------------------------


class TestDeleteLtmItem:
    """Verify item deletion."""

    @pytest.fixture(autouse=True)
    def _populate(self, cv):
        cv.promote_to_ltm(_gold_evidence(3), vector_id="VEC_DEL",
                          min_quality="BRONZE", min_faithfulness=0.5)
        self.cv = cv

    def test_delete_existing_item(self):
        items = self.cv.list_ltm_items(limit=1)["items"]
        item_id = items[0]["id"]
        deleted = self.cv.delete_ltm_item(item_id)
        assert deleted is True
        stats = self.cv.get_ltm_stats()
        assert stats["total_items"] == 2

    def test_delete_nonexistent_item(self):
        deleted = self.cv.delete_ltm_item("ltm_NONEXISTENT_ev_999")
        assert deleted is False

    def test_delete_then_query_excludes(self):
        """Deleted item should not appear in search results."""
        items = self.cv.list_ltm_items(limit=1)["items"]
        item_id = items[0]["id"]
        stmt = items[0]["statement"]
        self.cv.delete_ltm_item(item_id)
        results = self.cv.query_ltm(stmt, max_results=10)
        found_ids = {r["id"] for r in results}
        assert item_id not in found_ids


# ---------------------------------------------------------------------------
# Tests: full lifecycle (promote → query → delete → verify)
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """End-to-end LTM lifecycle within a single test."""

    def test_promote_query_delete_cycle(self, cv):
        # 1. Promote
        evidence = _gold_evidence(3)
        promoted = cv.promote_to_ltm(evidence, vector_id="VEC_LIFE",
                                     min_quality="BRONZE", min_faithfulness=0.5)
        assert promoted == 3

        # 2. Stats
        stats = cv.get_ltm_stats()
        assert stats["total_items"] == 3
        assert stats["available"] is True

        # 3. Query
        results = cv.query_ltm("PFAS GAC carbon filtration", max_results=10)
        assert len(results) >= 1

        # 4. Delete one
        first_id = results[0]["id"]
        assert cv.delete_ltm_item(first_id) is True

        # 5. Verify deletion
        stats_after = cv.get_ltm_stats()
        assert stats_after["total_items"] == 2

        # 6. Re-query — deleted item gone
        results_after = cv.query_ltm("PFAS GAC carbon filtration", max_results=10)
        result_ids_after = {r["id"] for r in results_after}
        assert first_id not in result_ids_after


# ---------------------------------------------------------------------------
# Tests: disk persistence with PersistentClient (real production path)
# ---------------------------------------------------------------------------


class TestDiskPersistence:
    """Verify that ChromaDB PersistentClient survives close+reopen cycles.

    This exercises the REAL production path (cross_vector.py uses PersistentClient).
    Each test uses a unique temp directory for full isolation.
    """

    @staticmethod
    def _make_client(persist_dir: str):
        """Create a fresh PersistentClient at the given directory."""
        from chromadb.config import Settings
        return chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

    def test_store_close_reopen_query(self, tmp_path):
        """Items stored via PersistentClient survive close+reopen."""
        persist_dir = str(tmp_path / "chroma_persist_test")
        col_name = f"ltm_persist_{uuid.uuid4().hex[:8]}"

        # Phase 1: store items
        client1 = self._make_client(persist_dir)
        col1 = client1.get_or_create_collection(name=col_name)
        col1.add(
            ids=["ev_persist_001", "ev_persist_002", "ev_persist_003"],
            documents=[
                "GAC removes 90% of PFAS from municipal water",
                "Ion exchange resin achieves 95% removal of short-chain PFAS",
                "Nanofiltration membranes reject 99% of all PFAS compounds",
            ],
            metadatas=[
                {"quality_tier": "GOLD", "source": "https://epa.gov/pfas"},
                {"quality_tier": "GOLD", "source": "https://waterresearch.org"},
                {"quality_tier": "SILVER", "source": "https://sciencedirect.com"},
            ],
        )
        assert col1.count() == 3
        # Close: delete client reference (ChromaDB PersistentClient flushes on GC)
        del col1
        del client1

        # Phase 2: reopen and verify
        client2 = self._make_client(persist_dir)
        col2 = client2.get_collection(name=col_name)
        assert col2.count() == 3

        # Verify semantic search still works
        results = col2.query(
            query_texts=["PFAS water treatment carbon"],
            n_results=3,
        )
        assert len(results["ids"][0]) == 3
        assert "ev_persist_001" in results["ids"][0]

        del col2
        del client2

    def test_store_close_reopen_stats_match(self, tmp_path):
        """Stats (count, IDs) match after close+reopen."""
        persist_dir = str(tmp_path / "chroma_stats_test")
        col_name = f"ltm_stats_{uuid.uuid4().hex[:8]}"

        # Phase 1: store 5 items
        client1 = self._make_client(persist_dir)
        col1 = client1.get_or_create_collection(name=col_name)
        ids = [f"ev_stat_{i:03d}" for i in range(5)]
        docs = [f"Evidence statement number {i} about PFAS filtration" for i in range(5)]
        metas = [{"quality_tier": "GOLD", "faithfulness": str(0.9 + i * 0.01)} for i in range(5)]
        col1.add(ids=ids, documents=docs, metadatas=metas)

        original_count = col1.count()
        original_get = col1.get()
        original_ids = set(original_get["ids"])

        del col1
        del client1

        # Phase 2: reopen
        client2 = self._make_client(persist_dir)
        col2 = client2.get_collection(name=col_name)
        reopened_count = col2.count()
        reopened_get = col2.get()
        reopened_ids = set(reopened_get["ids"])

        assert reopened_count == original_count, (
            f"Count mismatch: {reopened_count} != {original_count}"
        )
        assert reopened_ids == original_ids, (
            f"ID mismatch: {reopened_ids} != {original_ids}"
        )

        del col2
        del client2

    def test_store_delete_reopen_verify(self, tmp_path):
        """Items deleted before close stay deleted after reopen."""
        persist_dir = str(tmp_path / "chroma_delete_test")
        col_name = f"ltm_del_{uuid.uuid4().hex[:8]}"

        # Phase 1: store 3 items, delete 1
        client1 = self._make_client(persist_dir)
        col1 = client1.get_or_create_collection(name=col_name)
        col1.add(
            ids=["ev_del_001", "ev_del_002", "ev_del_003"],
            documents=[
                "GAC bed life is 6-18 months",
                "RO generates brine needing treatment",
                "Combined GAC-NF reduces cost by 30%",
            ],
        )
        col1.delete(ids=["ev_del_002"])
        assert col1.count() == 2

        del col1
        del client1

        # Phase 2: reopen and verify deletion persisted
        client2 = self._make_client(persist_dir)
        col2 = client2.get_collection(name=col_name)
        assert col2.count() == 2
        remaining = col2.get()
        assert "ev_del_002" not in remaining["ids"]
        assert "ev_del_001" in remaining["ids"]
        assert "ev_del_003" in remaining["ids"]

        del col2
        del client2

    def test_metadata_survives_restart(self, tmp_path):
        """Metadata fields (quality_tier, source, faithfulness) persist."""
        persist_dir = str(tmp_path / "chroma_meta_test")
        col_name = f"ltm_meta_{uuid.uuid4().hex[:8]}"

        # Phase 1: store with rich metadata
        client1 = self._make_client(persist_dir)
        col1 = client1.get_or_create_collection(name=col_name)
        col1.add(
            ids=["ev_meta_001"],
            documents=["GAC removes 90% of long-chain PFAS compounds"],
            metadatas=[{
                "quality_tier": "GOLD",
                "source": "https://epa.gov/pfas",
                "faithfulness": "0.95",
                "vector_id": "VEC_META_TEST",
            }],
        )
        del col1
        del client1

        # Phase 2: reopen and verify metadata
        client2 = self._make_client(persist_dir)
        col2 = client2.get_collection(name=col_name)
        result = col2.get(ids=["ev_meta_001"], include=["metadatas", "documents"])
        assert len(result["ids"]) == 1
        meta = result["metadatas"][0]
        assert meta["quality_tier"] == "GOLD"
        assert meta["source"] == "https://epa.gov/pfas"
        assert meta["faithfulness"] == "0.95"
        assert meta["vector_id"] == "VEC_META_TEST"
        assert "GAC removes" in result["documents"][0]

        del col2
        del client2
