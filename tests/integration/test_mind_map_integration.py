"""Integration tests: mind map endpoint via real ASGI transport.

Sprint 3 deferred item — verifies that the /api/research/mindmap/{vector_id}
endpoint correctly transforms a polaris_graph result JSON into the hierarchical
mind-map data structure consumed by mind_map.js.

All tests hit the REAL FastAPI ASGI app via httpx.ASGITransport.
Zero mocks. Zero duplicated production code.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# Ensure project root is on sys.path for scripts.* imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "mindmap_test_result.json"


# ---------------------------------------------------------------------------
# Helpers — build result JSONs for different test scenarios
# ---------------------------------------------------------------------------

def _load_fixture() -> dict:
    """Load the real-schema fixture from tests/fixtures/."""
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _rich_result(num_sections: int = 5, findings_per: int = 6,
                 num_sources: int = 10) -> dict:
    """Generate a realistic result JSON with cross-cutting sources."""
    sections = []
    evidence = []
    bibliography = []
    ev_counter = 0

    for s in range(num_sections):
        sec_id = f"sec_{s + 1}"
        sec_ev_ids = []
        for f_idx in range(findings_per):
            ev_counter += 1
            eid = f"ev_{ev_counter:04d}"
            sec_ev_ids.append(eid)
            src_idx = ev_counter % num_sources
            evidence.append({
                "evidence_id": eid,
                "statement": f"Finding {ev_counter} about topic {s + 1}.",
                "source": f"https://source-{src_idx}.example.com/paper",
                "quality_tier": ["GOLD", "SILVER", "BRONZE"][ev_counter % 3],
                "faithfulness": round(0.7 + 0.03 * (ev_counter % 10), 2),
                "relevance_score": round(0.5 + 0.05 * (ev_counter % 10), 2),
            })
        sections.append({
            "section_id": sec_id,
            "title": f"Section {s + 1} Title",
            "content": f"Content for section {s + 1}.",
            "evidence_ids": sec_ev_ids,
        })

    for i in range(num_sources):
        bibliography.append({
            "citation_number": i + 1,
            "title": f"Source {i + 1}",
            "url": f"https://source-{i}.example.com/paper",
            "quality_tier": ["GOLD", "SILVER", "BRONZE"][i % 3],
        })

    return {
        "original_query": "Advanced PFAS filtration and remediation strategies",
        "vector_id": "TEST_MM_RICH",
        "sections": sections,
        "evidence": evidence,
        "bibliography": bibliography,
    }


# ---------------------------------------------------------------------------
# Fixtures: temp output dir + ASGI client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def output_dir():
    """Create a temp directory that mimics outputs/polaris_graph/.

    The endpoint reads from Path("outputs/polaris_graph") / f"{safe_id}.json",
    so we temporarily replace the real output dir with a temp one.
    """
    tmp = tempfile.mkdtemp(prefix="polaris_mm_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def _write_result(output_dir: str, data: dict) -> str:
    """Write a result JSON to the temp output directory. Returns the vector_id."""
    vector_id = data.get("vector_id", "test")
    fp = os.path.join(output_dir, f"{vector_id}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return vector_id


@pytest_asyncio.fixture
async def client(output_dir):
    """Real ASGI client hitting the real FastAPI mind map endpoint.

    Patches the outputs/polaris_graph directory to use our temp dir so
    the endpoint finds our test JSON files.
    """
    import scripts.live_server as srv

    # Save original and monkey-patch the outputs path used by get_mindmap_data.
    # The endpoint reads:  Path("outputs/polaris_graph") / f"{safe_id}.json"
    # We patch Path so that "outputs/polaris_graph" resolves to our temp dir.
    original_func = srv.get_mindmap_data

    # The simplest reliable approach: override the endpoint with a wrapper
    # that temporarily changes the working dir for Path resolution.
    # Instead, we write our fixture files to the ACTUAL outputs/polaris_graph/
    # directory (creating it if needed) and clean up after.
    real_output_dir = os.path.join(_PROJECT_ROOT, "outputs", "polaris_graph")
    os.makedirs(real_output_dir, exist_ok=True)

    # Copy all test result files from temp dir to real output dir
    written_files = []
    for fname in os.listdir(output_dir):
        src = os.path.join(output_dir, fname)
        dst = os.path.join(real_output_dir, fname)
        shutil.copy2(src, dst)
        written_files.append(dst)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=srv.app),
        base_url="http://testserver",
    ) as c:
        # Attach output_dir and written_files for tests that need to write more
        c._test_output_dir = output_dir  # type: ignore[attr-defined]
        c._test_written_files = written_files  # type: ignore[attr-defined]
        c._test_real_output_dir = real_output_dir  # type: ignore[attr-defined]
        yield c

    # Cleanup: remove only the files WE wrote (not other real results)
    for fp in written_files:
        try:
            os.remove(fp)
        except OSError:
            pass


def _sync_to_real_output(client, data: dict) -> str:
    """Write result to both temp and real output dirs. Returns vector_id."""
    vector_id = data.get("vector_id", "test")
    # Write to temp
    fp_temp = os.path.join(client._test_output_dir, f"{vector_id}.json")
    with open(fp_temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # Write to real
    fp_real = os.path.join(client._test_real_output_dir, f"{vector_id}.json")
    with open(fp_real, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    client._test_written_files.append(fp_real)
    return vector_id


# ---------------------------------------------------------------------------
# Write the standard fixture before any tests run
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="module")
def _write_fixtures(output_dir):
    """Pre-write the standard fixture to the temp output directory."""
    data = _load_fixture()
    _write_result(output_dir, data)
    # Also write the rich result
    rich = _rich_result(num_sections=5, findings_per=6, num_sources=10)
    _write_result(output_dir, rich)


# ---------------------------------------------------------------------------
# Tests: mind map from minimal/standard fixture via REAL endpoint
# ---------------------------------------------------------------------------


class TestMindMapMinimal:
    """Verify mind map builds from the standard fixture via real ASGI endpoint."""

    @pytest.mark.asyncio
    async def test_center_node(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["center"]["label"] == data["original_query"]
        assert body["center"]["type"] == "question"

    @pytest.mark.asyncio
    async def test_sections_populated(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["sections"]) == 3
        titles = [s["title"] for s in body["sections"]]
        assert "Granular Activated Carbon (GAC) Filtration" in titles

    @pytest.mark.asyncio
    async def test_findings_linked_to_section(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        findings = body["findings"]
        # Fixture has 8 evidence total across 3 sections
        assert len(findings) == 8
        sec1_findings = [f for f in findings if f["section_id"] == "sec_1"]
        assert len(sec1_findings) == 3  # ev_001, ev_002, ev_003

    @pytest.mark.asyncio
    async def test_sources_have_tier(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        sources = body["sources"]
        assert len(sources) == 4  # 4 bibliography entries
        tiers = {s["tier"] for s in sources}
        assert "GOLD" in tiers

    @pytest.mark.asyncio
    async def test_edges_connect_nodes(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        edges = body["edges"]
        edge_types = {e["type"] for e in edges}
        assert "section" in edge_types
        assert "finding" in edge_types
        assert "source" in edge_types

    @pytest.mark.asyncio
    async def test_stats_present(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        stats = body["stats"]
        assert stats["total_sections"] == 3
        assert stats["total_findings"] == 8
        assert stats["total_sources"] == 4

    @pytest.mark.asyncio
    async def test_finding_evidence_id_tracked(self, client):
        data = _load_fixture()
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        ev_ids = {f["evidence_id"] for f in body["findings"]}
        assert "ev_001" in ev_ids
        assert "ev_008" in ev_ids


class TestMindMapRich:
    """Verify mind map with a realistic multi-section result via ASGI endpoint."""

    @pytest.mark.asyncio
    async def test_multi_section_structure(self, client):
        data = _rich_result(num_sections=5, findings_per=6, num_sources=10)
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["sections"]) == 5
        assert len(body["findings"]) == 30  # 5 * 6
        assert len(body["sources"]) == 10

    @pytest.mark.asyncio
    async def test_cross_cutting_sources_detected(self, client):
        data = _rich_result(num_sections=5, findings_per=6, num_sources=10)
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        cross_cutting = [s for s in body["sources"] if s["cross_cutting"]]
        assert len(cross_cutting) >= 1
        assert body["stats"]["cross_cutting_sources"] >= 1

    @pytest.mark.asyncio
    async def test_edge_count_reasonable(self, client):
        data = _rich_result(num_sections=5, findings_per=6, num_sources=10)
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        edges = body["edges"]
        # 5 center→section + 30 section→finding + up to 30 finding→source
        assert len(edges) >= 35

    @pytest.mark.asyncio
    async def test_per_section_finding_cap(self, client):
        """Each section caps at 30 findings in the endpoint."""
        data = _rich_result(num_sections=1, findings_per=40, num_sources=5)
        data["vector_id"] = "TEST_MM_CAP30"
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        # Only 30 of 40 findings should make it through the endpoint cap
        assert len(body["findings"]) == 30

    @pytest.mark.asyncio
    async def test_total_findings_cap(self, client):
        """Total findings capped at 200 in the endpoint."""
        data = _rich_result(num_sections=10, findings_per=25, num_sources=20)
        data["vector_id"] = "TEST_MM_CAP200"
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        assert len(body["findings"]) <= 200

    @pytest.mark.asyncio
    async def test_edges_cap(self, client):
        """Total edges capped at 500 in the endpoint."""
        data = _rich_result(num_sections=15, findings_per=25, num_sources=30)
        data["vector_id"] = "TEST_MM_CAP500"
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        assert len(body["edges"]) <= 500

    @pytest.mark.asyncio
    async def test_source_citation_count(self, client):
        """Sources should track how many findings cite them."""
        data = _rich_result(num_sections=3, findings_per=4, num_sources=4)
        data["vector_id"] = "TEST_MM_CITE"
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        total_citations = sum(s["citation_count"] for s in body["sources"])
        assert total_citations >= 1


class TestMindMapEdgeCases:
    """Verify graceful handling of missing or empty data via ASGI endpoint."""

    @pytest.mark.asyncio
    async def test_empty_sections(self, client):
        data = _load_fixture()
        data["vector_id"] = "TEST_MM_EMPTY_SEC"
        data["sections"] = []
        data["evidence"] = []
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["stats"]["total_sections"] == 0
        assert body["stats"]["total_findings"] == 0

    @pytest.mark.asyncio
    async def test_no_bibliography(self, client):
        data = _load_fixture()
        data["vector_id"] = "TEST_MM_NO_BIB"
        data["bibliography"] = []
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        assert body["stats"]["total_sources"] == 0
        source_edges = [e for e in body["edges"] if e["type"] == "source"]
        assert len(source_edges) == 0

    @pytest.mark.asyncio
    async def test_missing_evidence_ids(self, client):
        """Evidence IDs in section that don't exist in evidence pool."""
        data = _load_fixture()
        data["vector_id"] = "TEST_MM_MISS_EV"
        data["sections"][0]["evidence_ids"] = ["ev_missing_001", "ev_missing_002"]
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        # sec_1 findings should be 0 (missing evidence), but sec_2 and sec_3 still work
        sec1_findings = [f for f in body["findings"] if f["section_id"] == "sec_1"]
        assert len(sec1_findings) == 0

    @pytest.mark.asyncio
    async def test_empty_original_query(self, client):
        data = _load_fixture()
        data["vector_id"] = "TEST_MM_EMPTY_Q"
        data["original_query"] = ""
        _sync_to_real_output(client, data)
        resp = await client.get(f"/api/research/mindmap/{data['vector_id']}")
        body = resp.json()
        assert body["center"]["label"] == ""
        assert body["center"]["type"] == "question"

    @pytest.mark.asyncio
    async def test_nonexistent_vector_returns_404(self, client):
        """Requesting a vector_id with no result file should return 404."""
        resp = await client.get("/api/research/mindmap/NONEXISTENT_VECTOR_999")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
