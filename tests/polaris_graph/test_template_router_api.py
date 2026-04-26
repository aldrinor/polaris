"""Tests for the M-10 curated template router HTTP endpoints.

Covers:
  GET  /api/inspector/templates/catalog  — scope-page data source
  POST /api/inspector/templates/route    — advisory query classification
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir.inspector_router import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/inspector/templates/catalog
# ---------------------------------------------------------------------------


def test_catalog_endpoint_lists_v30_clinical(client: TestClient) -> None:
    resp = client.get("/api/inspector/templates/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert "templates" in body
    ids = [t["template_id"] for t in body["templates"]]
    assert "v30_clinical" in ids


def test_catalog_endpoint_includes_scope_summary(client: TestClient) -> None:
    """Per FINAL_PLAN scope-page reinforcement: the catalog endpoint
    must surface the full scope_summary so the UI can render an
    honest "what's supported / what's not" page."""
    resp = client.get("/api/inspector/templates/catalog")
    body = resp.json()
    for tmpl in body["templates"]:
        assert tmpl["scope_summary"]
        assert tmpl["display_name"]
        assert tmpl["description"]
        assert isinstance(tmpl["scope_examples"], list)
        assert len(tmpl["scope_examples"]) >= 1


# ---------------------------------------------------------------------------
# /api/inspector/templates/route
# ---------------------------------------------------------------------------


def test_route_endpoint_routes_in_scope_query(client: TestClient) -> None:
    resp = client.post(
        "/api/inspector/templates/route",
        json={"question": "What is the efficacy of tirzepatide for type 2 diabetes?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "routed"
    assert body["template_id"] == "v30_clinical"
    assert 0.0 <= body["confidence"] <= 1.0
    assert isinstance(body["candidates"], list)
    assert body["rationale"]


def test_route_endpoint_unsupported_for_off_scope_query(client: TestClient) -> None:
    resp = client.post(
        "/api/inspector/templates/route",
        json={"question": "What's the weather today?"},
    )
    body = resp.json()
    assert body["verdict"] == "unsupported_scope"
    assert body["template_id"] is None
    assert body["confidence"] < 0.30


def test_route_endpoint_operator_review_for_medical_off_scope(client: TestClient) -> None:
    resp = client.post(
        "/api/inspector/templates/route",
        json={"question": "Treatment options for chronic pain"},
    )
    body = resp.json()
    assert body["verdict"] == "operator_review_required"
    assert body["template_id"] == "v30_clinical"


def test_route_endpoint_empty_query_returns_unsupported(client: TestClient) -> None:
    """Empty question should not 400; UI flow expects a verdict."""
    resp = client.post(
        "/api/inspector/templates/route",
        json={"question": ""},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "unsupported_scope"


def test_route_endpoint_missing_question_returns_422(client: TestClient) -> None:
    """Pydantic validation: question is required."""
    resp = client.post("/api/inspector/templates/route", json={})
    assert resp.status_code == 422


def test_route_endpoint_does_not_enqueue_a_job(client: TestClient) -> None:
    """Route is advisory only — calling it must NOT create a job.
    UI must call /api/inspector/jobs explicitly after user confirms."""
    # Snapshot list-of-jobs count.
    before = client.get("/api/inspector/jobs").json()["count"]
    client.post(
        "/api/inspector/templates/route",
        json={"question": "tirzepatide for diabetes"},
    )
    after = client.get("/api/inspector/jobs").json()["count"]
    assert before == after, "/route created a job; must be advisory only"


def test_route_endpoint_candidates_include_score_and_keyword_hits(client: TestClient) -> None:
    """UI surfaces candidate scores + matched keywords for transparency."""
    resp = client.post(
        "/api/inspector/templates/route",
        json={"question": "FDA trial for tirzepatide"},
    )
    body = resp.json()
    assert body["candidates"]
    top = body["candidates"][0]
    assert "template_id" in top
    assert "score" in top
    assert "keyword_hits" in top
    assert "example_jaccard" in top
    assert isinstance(top["keyword_hits"], list)
