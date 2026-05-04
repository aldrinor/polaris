"""Tests for the FastAPI HTTP route exposing process_retrieval.

Uses FastAPI TestClient — no real HTTP server, no real network.
The fetch_fn is injected via FastAPI's dependency-override mechanism.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_graph.api.retrieval_route import get_fetch_fn, router
from polaris_graph.retrieval2.clinical_retriever import FetchResult


# ---------------------------------------------------------------------------
# Test app + fetch_fn override fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.include_router(router, prefix="/api")
    return a


def _override_fetch_fn(app: FastAPI, results: list[FetchResult]):
    """Inject a stub fetcher that returns `results` for every query."""

    def stub() -> object:
        def fetcher(_query: str) -> list[FetchResult]:
            return list(results)

        return fetcher

    app.dependency_overrides[get_fetch_fn] = stub


@pytest.fixture
def in_scope_decision_payload() -> dict:
    """A ScopeDecision JSON payload that satisfies retrieval validation."""
    return {
        "status": "in_scope",
        "scope_class": "clinical_efficacy",
        "ambiguity_axes": [
            {
                "axis": "population",
                "plausible_interpretations": ["adults"],
                "needs_clarification": False,
            },
            {
                "axis": "intervention",
                "plausible_interpretations": ["aspirin"],
                "needs_clarification": False,
            },
            {
                "axis": "outcome",
                "plausible_interpretations": ["headache"],
                "needs_clarification": False,
            },
        ],
        "clarifications_needed": [],
        "provenance": {},
        "latency_ms": 5,
    }


# ---------- Health ----------

def test_health_endpoint_returns_ok(app: FastAPI):
    client = TestClient(app)
    r = client.get("/api/retrieval/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["slice"] == "slice_002_clinical_retrieval"
    assert "query_planner" in body["pipeline_stages"]
    assert "corpus_adequacy_gate" in body["pipeline_stages"]


# ---------- 400 paths ----------

def test_post_out_of_scope_decision_returns_400(
    app: FastAPI, in_scope_decision_payload: dict
):
    payload = dict(in_scope_decision_payload)
    payload["status"] = "out_of_scope"
    payload["scope_class"] = None
    payload["ambiguity_axes"] = []

    client = TestClient(app)
    r = client.post("/api/retrieval", json={"decision": payload})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "wrong_status"


def test_post_non_clinical_scope_class_returns_400(
    app: FastAPI, in_scope_decision_payload: dict
):
    payload = dict(in_scope_decision_payload)
    payload["scope_class"] = "out_of_scope"
    payload["ambiguity_axes"] = []

    client = TestClient(app)
    r = client.post("/api/retrieval", json={"decision": payload})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "wrong_scope_class"


def test_post_no_fetch_backend_returns_400(
    app: FastAPI, in_scope_decision_payload: dict
):
    """Without a fetch_fn override, the sentinel default raises and the
    orchestrator returns RetrievalError(fetch_backend_unavailable)."""
    client = TestClient(app)
    r = client.post(
        "/api/retrieval", json={"decision": in_scope_decision_payload}
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "fetch_backend_unavailable"


# ---------- 200 success paths ----------

def test_post_with_stub_fetcher_returns_evidence_pool(
    app: FastAPI, in_scope_decision_payload: dict
):
    _override_fetch_fn(
        app,
        [
            FetchResult(
                url="https://www.cochrane.org/CD001",
                title="Cochrane review",
                snippet="snippet",
            ),
            FetchResult(
                url="https://www.nejm.org/doi/abc",
                title="NEJM article",
                snippet="snippet",
            ),
        ],
    )
    client = TestClient(app)
    r = client.post(
        "/api/retrieval", json={"decision": in_scope_decision_payload}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is False
    assert "pool" in body
    assert body["pool"]["decision_id"]
    assert isinstance(body["pool"]["sources"], list)
    assert len(body["pool"]["sources"]) >= 2


def test_post_inadequate_corpus_still_returns_200(
    app: FastAPI, in_scope_decision_payload: dict
):
    """Adequacy=False is HTTP 200 — request succeeded, corpus just weak."""
    _override_fetch_fn(
        app,
        [FetchResult(url="https://www.nejm.org/doi/abc", title="t", snippet="s")],
    )
    client = TestClient(app)
    r = client.post(
        "/api/retrieval", json={"decision": in_scope_decision_payload}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is False
    assert body["pool"]["adequacy"]["is_adequate"] is False
    assert body["pool"]["adequacy"]["failure_reason"]


def test_response_includes_server_timestamp(
    app: FastAPI, in_scope_decision_payload: dict
):
    _override_fetch_fn(
        app,
        [FetchResult(url="https://www.nejm.org/doi/abc", title="t", snippet="s")],
    )
    client = TestClient(app)
    r = client.post(
        "/api/retrieval", json={"decision": in_scope_decision_payload}
    )
    assert r.status_code == 200
    body = r.json()
    assert "server_time_utc" in body
    assert body["server_time_utc"].endswith("Z")


def test_response_pool_has_required_fields(
    app: FastAPI, in_scope_decision_payload: dict
):
    _override_fetch_fn(
        app,
        [FetchResult(url="https://www.nejm.org/doi/abc", title="t", snippet="s")],
    )
    client = TestClient(app)
    r = client.post(
        "/api/retrieval", json={"decision": in_scope_decision_payload}
    )
    assert r.status_code == 200
    pool = r.json()["pool"]
    for field in (
        "pool_id",
        "decision_id",
        "sources",
        "adequacy",
        "queries_executed",
        "retrieval_started_at_utc",
        "retrieval_finished_at_utc",
        "latency_ms",
        "cost_usd",
    ):
        assert field in pool


# ---------- 422 validation ----------

def test_post_missing_decision_field_returns_422(app: FastAPI):
    client = TestClient(app)
    r = client.post("/api/retrieval", json={})
    assert r.status_code == 422


def test_post_malformed_decision_returns_422(app: FastAPI):
    client = TestClient(app)
    r = client.post(
        "/api/retrieval",
        json={"decision": {"status": "in_scope"}},  # missing required fields
    )
    # ScopeDecision requires scope_class to be present (even if None);
    # Pydantic validation rejects malformed payloads.
    assert r.status_code in (400, 422)


# ---------- Adequacy template routing per scope_class ----------

def test_safety_decision_uses_safety_template(
    app: FastAPI, in_scope_decision_payload: dict
):
    """A clinical_safety decision should be assessed against the
    safety template (T1>=3); 2 T1 sources should not satisfy."""
    payload = dict(in_scope_decision_payload)
    payload["scope_class"] = "clinical_safety"

    _override_fetch_fn(
        app,
        [
            FetchResult(url="https://www.cochrane.org/CD001", title="t", snippet="s"),
            FetchResult(url="https://www.fda.gov/drugs/safety-info", title="t", snippet="s"),
            FetchResult(url="https://www.nejm.org/doi/a1", title="t", snippet="s"),
            FetchResult(url="https://www.nejm.org/doi/a2", title="t", snippet="s"),
            FetchResult(url="https://www.nejm.org/doi/a3", title="t", snippet="s"),
            FetchResult(url="https://clinicaltrials.gov/study/NCT001", title="t", snippet="s"),
        ],
    )
    client = TestClient(app)
    r = client.post("/api/retrieval", json={"decision": payload})
    assert r.status_code == 200
    body = r.json()
    assert body["pool"]["adequacy"]["is_adequate"] is False
    assert "clinical_safety" in body["pool"]["adequacy"]["failure_reason"]
