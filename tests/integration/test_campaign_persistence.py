"""
Integration tests for campaign_store -- real SQLite, zero mocks.

Tests the async SQLite-backed campaign storage at
src/polaris_graph/memory/campaign_store.py using isolated temp-directory
databases per test via monkeypatch on ``campaign_store._DB_PATH``.
"""

import asyncio
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def campaign_db(tmp_path, monkeypatch):
    """Provide an isolated real SQLite database for each test.

    Monkeypatches the module-level ``_DB_PATH`` so every internal
    ``aiosqlite.connect(str(_DB_PATH))`` call hits the temp database.
    """
    db_path = tmp_path / "test_campaigns.sqlite"
    import src.polaris_graph.memory.campaign_store as cs

    monkeypatch.setattr(cs, "_DB_PATH", db_path)
    return db_path


def _make_campaign(
    campaign_id: str,
    *,
    name: str = "Test Campaign",
    description: str = "Integration test campaign",
    queries: list | None = None,
    status: str = "created",
    results: dict | None = None,
    metadata: dict | None = None,
    created_at: float | None = None,
) -> dict:
    """Build a campaign dict with sensible defaults."""
    now = time.time()
    return {
        "campaign_id": campaign_id,
        "name": name,
        "description": description,
        "queries_json": queries or ["query_a", "query_b"],
        "status": status,
        "results_json": results or {},
        "created_at": created_at or now,
        "updated_at": now,
        "metadata_json": metadata or {"source": "integration_test"},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCampaignPersistence:
    """Real SQLite integration tests for the campaign store."""

    # 1. save + get roundtrip
    @pytest.mark.asyncio
    async def test_save_and_get_roundtrip(self, campaign_db):
        """INSERT then SELECT returns identical data."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            get_campaign,
        )

        await init_campaign_store()
        campaign = _make_campaign("camp_001", name="Roundtrip Test")
        await save_campaign(campaign)

        retrieved = await get_campaign("camp_001")
        assert retrieved is not None
        assert retrieved["campaign_id"] == "camp_001"
        assert retrieved["name"] == "Roundtrip Test"
        assert retrieved["description"] == "Integration test campaign"
        assert isinstance(retrieved["queries_json"], list)
        assert retrieved["queries_json"] == ["query_a", "query_b"]
        assert retrieved["status"] == "created"
        assert isinstance(retrieved["results_json"], dict)
        assert isinstance(retrieved["metadata_json"], dict)
        assert retrieved["metadata_json"]["source"] == "integration_test"
        assert isinstance(retrieved["created_at"], float)
        assert isinstance(retrieved["updated_at"], float)

    # 2. list_campaigns -- sorted by created_at DESC
    @pytest.mark.asyncio
    async def test_list_campaigns_sorted_desc(self, campaign_db):
        """All campaigns returned, newest first."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            list_campaigns,
        )

        await init_campaign_store()

        base_time = time.time()
        for i in range(5):
            c = _make_campaign(
                f"camp_list_{i}",
                name=f"Campaign {i}",
                created_at=base_time + i,
            )
            await save_campaign(c)

        all_campaigns = await list_campaigns()
        assert len(all_campaigns) == 5
        # Newest (camp_list_4) should be first
        assert all_campaigns[0]["campaign_id"] == "camp_list_4"
        assert all_campaigns[-1]["campaign_id"] == "camp_list_0"
        # Verify strictly descending created_at
        for j in range(len(all_campaigns) - 1):
            assert all_campaigns[j]["created_at"] >= all_campaigns[j + 1]["created_at"]

    # 3. update_campaign_status to "running"
    @pytest.mark.asyncio
    async def test_update_status_to_running(self, campaign_db):
        """Status field updates correctly via UPDATE."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            get_campaign,
            update_campaign_status,
        )

        await init_campaign_store()
        await save_campaign(_make_campaign("camp_run"))

        await update_campaign_status("camp_run", "running")

        retrieved = await get_campaign("camp_run")
        assert retrieved is not None
        assert retrieved["status"] == "running"

    # 4. update_campaign_status to "completed" with results
    @pytest.mark.asyncio
    async def test_update_status_completed_with_results(self, campaign_db):
        """Status + results_json both update in a single call."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            get_campaign,
            update_campaign_status,
        )

        await init_campaign_store()
        await save_campaign(_make_campaign("camp_done"))

        results = {
            "total_queries": 10,
            "completed": 10,
            "average_score": 87.3,
            "top_findings": ["finding_a", "finding_b"],
        }
        await update_campaign_status("camp_done", "completed", results=results)

        retrieved = await get_campaign("camp_done")
        assert retrieved is not None
        assert retrieved["status"] == "completed"
        assert isinstance(retrieved["results_json"], dict)
        assert retrieved["results_json"]["total_queries"] == 10
        assert retrieved["results_json"]["average_score"] == 87.3
        assert len(retrieved["results_json"]["top_findings"]) == 2

    # 5. delete_campaign -- excluded from list after delete
    @pytest.mark.asyncio
    async def test_delete_campaign_excludes_from_list(self, campaign_db):
        """Deleted campaign no longer appears in list_campaigns."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            list_campaigns,
            delete_campaign,
        )

        await init_campaign_store()
        await save_campaign(_make_campaign("camp_keep"))
        await save_campaign(_make_campaign("camp_delete"))

        pre_delete = await list_campaigns()
        assert len(pre_delete) == 2

        deleted = await delete_campaign("camp_delete")
        assert deleted is True

        post_delete = await list_campaigns()
        assert len(post_delete) == 1
        assert post_delete[0]["campaign_id"] == "camp_keep"

    # 6. Persistence across "new" store instances (same DB path)
    @pytest.mark.asyncio
    async def test_persistence_across_store_instances(self, campaign_db, monkeypatch):
        """Data survives when module is re-accessed with the same DB path."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
        )

        await init_campaign_store()
        campaign = _make_campaign("camp_persist", name="Persistence Check")
        await save_campaign(campaign)

        # Simulate a "new" store connection by re-importing and re-initing.
        # The monkeypatch already points _DB_PATH at the same temp file,
        # so a fresh init_campaign_store + get_campaign proves disk persistence.
        import importlib
        import src.polaris_graph.memory.campaign_store as cs

        # Re-apply monkeypatch to the same path (simulates fresh process)
        monkeypatch.setattr(cs, "_DB_PATH", campaign_db)

        await init_campaign_store()
        retrieved = await cs.get_campaign("camp_persist")
        assert retrieved is not None
        assert retrieved["name"] == "Persistence Check"

    # 7. Concurrent save (asyncio.gather, no lock error)
    @pytest.mark.asyncio
    async def test_concurrent_save_no_lock_error(self, campaign_db):
        """Two simultaneous saves must not raise a database lock error."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            list_campaigns,
        )

        await init_campaign_store()

        camp_a = _make_campaign("camp_conc_a", name="Concurrent A")
        camp_b = _make_campaign("camp_conc_b", name="Concurrent B")

        await asyncio.gather(
            save_campaign(camp_a),
            save_campaign(camp_b),
        )

        all_campaigns = await list_campaigns()
        ids = {c["campaign_id"] for c in all_campaigns}
        assert "camp_conc_a" in ids
        assert "camp_conc_b" in ids

    # 8. get nonexistent campaign_id returns None
    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, campaign_db):
        """Querying a non-existent ID returns None, not an error."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            get_campaign,
        )

        await init_campaign_store()
        result = await get_campaign("does_not_exist_xyz")
        assert result is None

    # 9. update_campaign_status with nonexistent ID raises ValueError
    @pytest.mark.asyncio
    async def test_update_nonexistent_raises_value_error(self, campaign_db):
        """Updating status on a missing campaign is a loud failure."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            update_campaign_status,
        )

        await init_campaign_store()
        with pytest.raises(ValueError, match="Campaign not found"):
            await update_campaign_status("ghost_campaign", "running")

    # 10. Campaign with long query (2000 chars) in name
    @pytest.mark.asyncio
    async def test_long_name_field(self, campaign_db):
        """SQLite TEXT column handles 2000-char names without truncation."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            get_campaign,
        )

        await init_campaign_store()
        long_name = "A" * 2000
        campaign = _make_campaign("camp_long", name=long_name)
        await save_campaign(campaign)

        retrieved = await get_campaign("camp_long")
        assert retrieved is not None
        assert len(retrieved["name"]) == 2000
        assert retrieved["name"] == long_name

    # 11. Campaign with unicode/quotes/newlines in description
    @pytest.mark.asyncio
    async def test_unicode_and_special_chars_in_description(self, campaign_db):
        """Unicode, quotes, and newlines survive the JSON serialize roundtrip."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            get_campaign,
        )

        await init_campaign_store()
        tricky_description = (
            'Line 1 with "double quotes"\n'
            "Line 2 with 'single quotes'\n"
            "Line 3 with unicode: \u00e9\u00e0\u00fc\u00f1\u00f6\u2603\u2764\ufe0f\n"
            "Line 4 with backslashes: C:\\Users\\test\n"
            "Line 5 with null-ish: null undefined NaN\n"
            "Line 6 with CJK: \u6c34\u8d28\u8fc7\u6ee4\u7814\u7a76"
        )
        campaign = _make_campaign(
            "camp_unicode",
            description=tricky_description,
        )
        await save_campaign(campaign)

        retrieved = await get_campaign("camp_unicode")
        assert retrieved is not None
        assert retrieved["description"] == tricky_description

    # 12. Full lifecycle: create -> running -> completed -> verify all fields
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, campaign_db):
        """Walk through the entire campaign lifecycle and verify state at each step."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
            get_campaign,
            update_campaign_status,
        )

        await init_campaign_store()

        # Phase 1: Create
        campaign = _make_campaign(
            "camp_lifecycle",
            name="Lifecycle Test",
            queries=["q1", "q2", "q3"],
            metadata={"owner": "integration_test", "priority": "high"},
        )
        await save_campaign(campaign)

        created = await get_campaign("camp_lifecycle")
        assert created is not None
        assert created["status"] == "created"
        assert created["queries_json"] == ["q1", "q2", "q3"]
        assert created["results_json"] == {}
        created_at = created["created_at"]
        first_updated_at = created["updated_at"]

        # Phase 2: Running
        await update_campaign_status("camp_lifecycle", "running")
        running = await get_campaign("camp_lifecycle")
        assert running is not None
        assert running["status"] == "running"
        assert running["created_at"] == created_at  # created_at never changes
        assert running["updated_at"] >= first_updated_at

        # Phase 3: Completed with results
        final_results = {
            "total_queries": 3,
            "completed": 3,
            "findings": {
                "q1": {"score": 92.1, "evidence_count": 47},
                "q2": {"score": 88.5, "evidence_count": 31},
                "q3": {"score": 95.0, "evidence_count": 63},
            },
        }
        await update_campaign_status(
            "camp_lifecycle", "completed", results=final_results,
        )

        completed = await get_campaign("camp_lifecycle")
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["results_json"]["total_queries"] == 3
        assert completed["results_json"]["findings"]["q1"]["score"] == 92.1
        assert completed["created_at"] == created_at
        assert completed["updated_at"] >= running["updated_at"]
        # Metadata unchanged throughout lifecycle
        assert completed["metadata_json"]["owner"] == "integration_test"

    # 13. save_campaign with empty campaign_id raises ValueError
    @pytest.mark.asyncio
    async def test_save_empty_campaign_id_raises(self, campaign_db):
        """An empty campaign_id is rejected immediately."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            save_campaign,
        )

        await init_campaign_store()

        with pytest.raises(ValueError, match="non-empty"):
            await save_campaign({"campaign_id": ""})

        with pytest.raises(ValueError, match="non-empty"):
            await save_campaign({"name": "no id campaign"})

    # 14. delete_campaign with nonexistent ID returns False
    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, campaign_db):
        """Deleting a campaign that does not exist returns False, not an error."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            delete_campaign,
        )

        await init_campaign_store()
        result = await delete_campaign("never_existed")
        assert result is False

    # 15. list_campaigns empty store returns []
    @pytest.mark.asyncio
    async def test_list_campaigns_empty_store(self, campaign_db):
        """A freshly initialised store has zero campaigns."""
        from src.polaris_graph.memory.campaign_store import (
            init_campaign_store,
            list_campaigns,
        )

        await init_campaign_store()
        result = await list_campaigns()
        assert result == []
