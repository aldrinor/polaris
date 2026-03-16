"""
Integration tests for pipeline CRUD endpoints and PipelineDefinition model.

Tests REAL code paths through the FastAPI ASGI app defined in scripts/live_server.py
and the Pydantic models in src/polaris_graph/pipeline_definition.py.

Zero mocks. Zero placeholders. All assertions against live ASGI transport.
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# Ensure project root is on sys.path for src.* and scripts.* imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.polaris_graph.pipeline_definition import (
    MacroStage,
    PipelineDefinition,
    PipelineStage,
    StageType,
    list_templates,
    load_template,
    TEMPLATES_DIR,
)


# ---------------------------------------------------------------------------
# Template file names expected on disk
# ---------------------------------------------------------------------------
EXPECTED_TEMPLATE_STEMS = [
    "academic_focus",
    "compliance_review",
    "multi_vector",
    "quick_scan",
    "standard_research",
]

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "pipeline_templates"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    """Real ASGI client hitting real FastAPI endpoints.

    Clears the module-level _custom_pipelines store between tests so each
    test starts with a clean slate (templates are always loaded from disk).
    """
    import scripts.live_server as srv

    srv._custom_pipelines.clear()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=srv.app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
def valid_pipeline_body():
    """A valid pipeline definition matching the real Pydantic schema."""
    return {
        "name": "Test Pipeline",
        "description": "Integration test pipeline for CRUD operations",
        "macro_stages": [
            {
                "macro_id": "planning",
                "label": "Planning",
                "stages": [
                    {
                        "stage_id": "plan_queries",
                        "stage_type": "plan",
                        "label": "Query Planning",
                    }
                ],
            },
            {
                "macro_id": "collection",
                "label": "Collection",
                "depends_on_macros": ["planning"],
                "stages": [
                    {
                        "stage_id": "web_search",
                        "stage_type": "search",
                        "label": "Web Search",
                    }
                ],
            },
        ],
        "tags": ["test", "integration"],
    }


@pytest.fixture
def cycle_body():
    """Pipeline body with circular macro-stage dependencies."""
    return {
        "name": "Cycle Test",
        "macro_stages": [
            {
                "macro_id": "a",
                "label": "Stage A",
                "depends_on_macros": ["b"],
                "stages": [
                    {"stage_id": "s1", "stage_type": "plan", "label": "Step 1"}
                ],
            },
            {
                "macro_id": "b",
                "label": "Stage B",
                "depends_on_macros": ["a"],
                "stages": [
                    {"stage_id": "s2", "stage_type": "search", "label": "Step 2"}
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# 1. GET /api/pipelines/templates -- returns templates with >= 5 items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_templates_returns_all_five(client):
    """GET /api/pipelines/templates returns 200 with at least 5 templates."""
    resp = await client.get("/api/pipelines/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert "templates" in data
    templates = data["templates"]
    assert len(templates) >= 5, f"Expected >= 5 templates, got {len(templates)}"


# ---------------------------------------------------------------------------
# 2. Each template has required metadata fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_metadata_fields(client):
    """Each template entry contains pipeline_id, name, description, total_nodes, macro_count."""
    resp = await client.get("/api/pipelines/templates")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    required_keys = {"pipeline_id", "name", "description", "total_nodes", "macro_count"}
    for tpl in templates:
        missing = required_keys - set(tpl.keys())
        assert not missing, f"Template '{tpl.get('name', '?')}' missing keys: {missing}"
        assert isinstance(tpl["total_nodes"], int)
        assert tpl["total_nodes"] >= 1
        assert isinstance(tpl["macro_count"], int)
        assert tpl["macro_count"] >= 1


# ---------------------------------------------------------------------------
# 3. GET /api/pipelines -- returns templates + custom
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pipelines_includes_templates(client):
    """GET /api/pipelines returns at least the 5 built-in templates."""
    resp = await client.get("/api/pipelines")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipelines" in data
    assert len(data["pipelines"]) >= 5


# ---------------------------------------------------------------------------
# 4. POST /api/pipelines with valid body -- creates pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_valid(client, valid_pipeline_body):
    """POST /api/pipelines with a valid body returns pipeline_id and status created."""
    resp = await client.post("/api/pipelines", json=valid_pipeline_body)
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_id" in data
    assert data["status"] == "created"
    assert data["pipeline_id"].startswith("pipe_")


# ---------------------------------------------------------------------------
# 5. POST /api/pipelines with cycle -- 422 rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_cycle_rejected(client, cycle_body):
    """POST /api/pipelines with circular deps returns 422."""
    resp = await client.post("/api/pipelines", json=cycle_body)
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "ircular" in data["error"].lower() or "cycle" in data["error"].lower()


# ---------------------------------------------------------------------------
# 6. GET /api/pipelines/{created_id} -- returns full definition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pipeline_by_id(client, valid_pipeline_body):
    """GET /api/pipelines/{id} returns the full pipeline definition."""
    create_resp = await client.post("/api/pipelines", json=valid_pipeline_body)
    pid = create_resp.json()["pipeline_id"]

    resp = await client.get(f"/api/pipelines/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_id"] == pid
    assert data["name"] == "Test Pipeline"
    assert len(data["macro_stages"]) == 2


# ---------------------------------------------------------------------------
# 7. GET /api/pipelines/nonexistent_id -- 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pipeline_not_found(client):
    """GET /api/pipelines/{nonexistent} returns 404."""
    resp = await client.get("/api/pipelines/does_not_exist_xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data


# ---------------------------------------------------------------------------
# 8. PUT /api/pipelines/{id} -- updates successfully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_pipeline(client, valid_pipeline_body):
    """PUT /api/pipelines/{id} updates an existing custom pipeline."""
    create_resp = await client.post("/api/pipelines", json=valid_pipeline_body)
    pid = create_resp.json()["pipeline_id"]

    updated_body = valid_pipeline_body.copy()
    updated_body["name"] = "Updated Test Pipeline"
    updated_body["description"] = "Updated description"

    resp = await client.put(f"/api/pipelines/{pid}", json=updated_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"

    # Verify update persisted
    get_resp = await client.get(f"/api/pipelines/{pid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Updated Test Pipeline"
    assert get_resp.json()["description"] == "Updated description"


# ---------------------------------------------------------------------------
# 9. DELETE /api/pipelines/{id} -- deleted, subsequent GET returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_pipeline(client, valid_pipeline_body):
    """DELETE removes pipeline; subsequent GET returns 404."""
    create_resp = await client.post("/api/pipelines", json=valid_pipeline_body)
    pid = create_resp.json()["pipeline_id"]

    del_resp = await client.delete(f"/api/pipelines/{pid}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    get_resp = await client.get(f"/api/pipelines/{pid}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. POST /api/pipelines/{id}/validate -- valid pipeline passes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_pipeline_passes(client, valid_pipeline_body):
    """POST /api/pipelines/{id}/validate returns valid=True for a well-formed pipeline."""
    create_resp = await client.post("/api/pipelines", json=valid_pipeline_body)
    pid = create_resp.json()["pipeline_id"]

    resp = await client.post(f"/api/pipelines/{pid}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert "execution_order" in data
    assert isinstance(data["execution_order"], list)
    assert len(data["execution_order"]) == 2
    assert data["total_nodes"] == 2


# ---------------------------------------------------------------------------
# 11. Validation catches empty macro_stages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_empty_macros_rejected(client):
    """POST /api/pipelines with empty macro_stages returns 422."""
    body = {
        "name": "Empty Macros",
        "macro_stages": [],
    }
    resp = await client.post("/api/pipelines", json=body)
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data


# ---------------------------------------------------------------------------
# 12. Validation catches invalid stage types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_invalid_stage_type_rejected(client):
    """POST /api/pipelines with an unrecognized stage_type returns 422."""
    body = {
        "name": "Bad Stage Type",
        "macro_stages": [
            {
                "macro_id": "m1",
                "label": "M1",
                "stages": [
                    {
                        "stage_id": "s1",
                        "stage_type": "nonexistent_type",
                        "label": "Bad",
                    }
                ],
            }
        ],
    }
    resp = await client.post("/api/pipelines", json=body)
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data


# ---------------------------------------------------------------------------
# 13. Round-trip: create -> get -> data matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_create_get(client, valid_pipeline_body):
    """Create a pipeline, then GET it back -- all user-supplied fields match."""
    create_resp = await client.post("/api/pipelines", json=valid_pipeline_body)
    pid = create_resp.json()["pipeline_id"]

    get_resp = await client.get(f"/api/pipelines/{pid}")
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert data["name"] == valid_pipeline_body["name"]
    assert data["description"] == valid_pipeline_body["description"]
    assert data["tags"] == valid_pipeline_body["tags"]
    assert len(data["macro_stages"]) == len(valid_pipeline_body["macro_stages"])

    # Verify macro_stage structure roundtripped
    for i, macro in enumerate(data["macro_stages"]):
        expected = valid_pipeline_body["macro_stages"][i]
        assert macro["macro_id"] == expected["macro_id"]
        assert macro["label"] == expected["label"]
        assert len(macro["stages"]) == len(expected["stages"])
        for j, stage in enumerate(macro["stages"]):
            expected_stage = expected["stages"][j]
            assert stage["stage_id"] == expected_stage["stage_id"]
            assert stage["stage_type"] == expected_stage["stage_type"]


# ---------------------------------------------------------------------------
# 14. All 5 YAML templates parse via PipelineDefinition.from_yaml_file()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stem", EXPECTED_TEMPLATE_STEMS)
def test_yaml_template_parses(stem):
    """Each YAML template on disk parses into a valid PipelineDefinition."""
    path = TEMPLATE_DIR / f"{stem}.yaml"
    assert path.exists(), f"Template file missing: {path}"

    pipeline = PipelineDefinition.from_yaml_file(path)
    assert isinstance(pipeline, PipelineDefinition)
    assert pipeline.name
    assert pipeline.is_template is True
    assert len(pipeline.macro_stages) >= 1
    assert pipeline.total_nodes >= 1


# ---------------------------------------------------------------------------
# 15. Topological sort produces valid execution order
# ---------------------------------------------------------------------------


def test_topological_sort_execution_order():
    """get_execution_order() returns macro_ids in dependency-valid order."""
    pipeline = PipelineDefinition(
        name="Topo Test",
        macro_stages=[
            MacroStage(
                macro_id="synthesis",
                label="Synthesis",
                depends_on_macros=["verify"],
                stages=[PipelineStage(stage_id="s3", stage_type=StageType.SYNTHESIZE)],
            ),
            MacroStage(
                macro_id="verify",
                label="Verify",
                depends_on_macros=["plan"],
                stages=[PipelineStage(stage_id="s2", stage_type=StageType.VERIFY)],
            ),
            MacroStage(
                macro_id="plan",
                label="Plan",
                stages=[PipelineStage(stage_id="s1", stage_type=StageType.PLAN)],
            ),
        ],
    )
    order = pipeline.get_execution_order()
    assert len(order) == 3
    # plan must come before verify, verify before synthesis
    assert order.index("plan") < order.index("verify")
    assert order.index("verify") < order.index("synthesis")


# ---------------------------------------------------------------------------
# 16. Cycle detection rejects circular dependencies (unit test on model)
# ---------------------------------------------------------------------------


def test_cycle_detection_rejects_circular():
    """PipelineDefinition model_validator raises ValueError on circular deps."""
    with pytest.raises(ValueError, match="[Cc]ircular"):
        PipelineDefinition(
            name="Circular",
            macro_stages=[
                MacroStage(
                    macro_id="x",
                    label="X",
                    depends_on_macros=["y"],
                    stages=[PipelineStage(stage_id="sx", stage_type=StageType.PLAN)],
                ),
                MacroStage(
                    macro_id="y",
                    label="Y",
                    depends_on_macros=["z"],
                    stages=[PipelineStage(stage_id="sy", stage_type=StageType.SEARCH)],
                ),
                MacroStage(
                    macro_id="z",
                    label="Z",
                    depends_on_macros=["x"],
                    stages=[PipelineStage(stage_id="sz", stage_type=StageType.ANALYZE)],
                ),
            ],
        )


# ---------------------------------------------------------------------------
# 17. PipelineStage field_validator rejects bad stage_id
# ---------------------------------------------------------------------------


def test_stage_id_rejects_special_chars():
    """PipelineStage field_validator rejects stage_ids with spaces or specials."""
    with pytest.raises(ValueError, match="stage_id"):
        PipelineStage(
            stage_id="has spaces",
            stage_type=StageType.PLAN,
        )

    with pytest.raises(ValueError, match="stage_id"):
        PipelineStage(
            stage_id="bad!@#$",
            stage_type=StageType.PLAN,
        )

    # Valid IDs should pass
    stage = PipelineStage(stage_id="valid_id_123", stage_type=StageType.PLAN)
    assert stage.stage_id == "valid_id_123"

    stage_with_hyphen = PipelineStage(stage_id="also-valid", stage_type=StageType.PLAN)
    assert stage_with_hyphen.stage_id == "also-valid"


# ---------------------------------------------------------------------------
# 18. POST /api/pipelines with missing name -- 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_missing_name_rejected(client):
    """POST /api/pipelines without a name field returns 422."""
    body = {
        "description": "No name provided",
        "macro_stages": [
            {
                "macro_id": "m1",
                "label": "M1",
                "stages": [
                    {"stage_id": "s1", "stage_type": "plan"}
                ],
            }
        ],
    }
    resp = await client.post("/api/pipelines", json=body)
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
