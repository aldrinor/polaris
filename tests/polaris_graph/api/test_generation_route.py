"""Tests for the FastAPI HTTP route exposing process_generation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_graph.api.generation_route import get_completion_fn, router


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.include_router(router, prefix="/api")
    return a


def _override_completion_fn(app: FastAPI, text_per_call: list[str]):
    """Inject a stub completion_fn that returns text_per_call sequentially."""

    def stub() -> object:
        state = {"i": 0}

        def fn(prompt, section_plan, pool):
            i = state["i"]
            state["i"] = i + 1
            if i < len(text_per_call):
                return text_per_call[i]
            return text_per_call[-1] if text_per_call else ""

        return fn

    app.dependency_overrides[get_completion_fn] = stub


def _adequate_pool_payload(full_text: str | None = None) -> dict:
    """Build an EvidencePool JSON payload with adequacy=True + 1 source."""
    full = full_text or (
        "The randomized trial enrolled 1247 adults with chronic migraines. "
        "Aspirin 325mg demonstrated significant headache reduction at "
        "outcomes assessment."
    )
    return {
        "pool_id": "p-1",
        "decision_id": "d-1",
        "sources": [
            {
                "source_id": "src-1",
                "url": "https://www.cochrane.org/CD001",
                "domain": "cochrane.org",
                "tier": "T1",
                "title": "Source",
                "publication_date": None,
                "authors": [],
                "snippet": full[:200],
                "full_text_available": True,
                "full_text": full,
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "provenance": {},
            }
        ],
        "adequacy": {
            "is_adequate": True,
            "sources_per_tier": {"T1": 1, "T2": 0, "T3": 0},
            "min_required_per_tier": {"T1": 0, "T2": 0, "T3": 0},
            "failure_reason": None,
        },
        "queries_executed": ["aspirin headache"],
        "retrieval_started_at_utc": datetime.now(timezone.utc).isoformat(),
        "retrieval_finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "latency_ms": 100,
        "cost_usd": 0.0,
    }


def _good_efficacy_text(full_text: str) -> str:
    return (
        f"The trial enrolled 1247 adults with chronic migraines and showed "
        f"significant aspirin headache reduction "
        f"[#ev:src-1:0-{len(full_text)}]."
    )


# ---------- Health ----------

def test_health_endpoint(app: FastAPI):
    r = TestClient(app).get("/api/generation/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["slice"] == "slice_003_generator_strict_verify"
    assert "strict_verify" in body["pipeline_stages"]


# ---------- 400 paths ----------

def test_post_inadequate_pool_returns_400(app: FastAPI):
    payload = _adequate_pool_payload()
    payload["adequacy"]["is_adequate"] = False
    payload["adequacy"]["failure_reason"] = "not enough sources"
    payload["sources"] = []

    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_efficacy"}
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "inadequate_pool"


def test_post_no_completion_backend_returns_400(app: FastAPI):
    """Without dep override, sentinel default -> 400 completion_backend_unavailable."""
    payload = _adequate_pool_payload()
    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_efficacy"}
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "completion_backend_unavailable"


# ---------- 200 success paths ----------

def test_post_with_stub_returns_verified_report(app: FastAPI):
    full = (
        "The randomized trial enrolled 1247 adults with chronic migraines. "
        "Aspirin 325mg demonstrated significant headache reduction at "
        "outcomes assessment."
    )
    payload = _adequate_pool_payload(full_text=full)
    _override_completion_fn(app, [_good_efficacy_text(full)])

    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_efficacy"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is False
    assert "report" in body
    report = body["report"]
    assert report["pipeline_verdict"] == "success"
    assert len(report["sections"]) == 4


def test_post_token_less_text_yields_abort_verdict(app: FastAPI):
    """Generator returns no-token sentences -> all sections drop -> abort
    is HTTP 200 (verdict in body), not 400 (which is for structural fails)."""
    full = "x" * 200
    payload = _adequate_pool_payload(full_text=full)
    _override_completion_fn(app, ["Aspirin works in adults."])

    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_efficacy"}
    )
    assert r.status_code == 200
    body = r.json()
    report = body["report"]
    assert report["pipeline_verdict"] == "abort_no_verified_sections"
    assert all(s["section_status"] == "dropped" for s in report["sections"])


def test_response_includes_server_timestamp(app: FastAPI):
    full = (
        "The randomized trial enrolled 1247 adults with chronic migraines. "
        "Aspirin 325mg demonstrated significant headache reduction at "
        "outcomes assessment."
    )
    payload = _adequate_pool_payload(full_text=full)
    _override_completion_fn(app, [_good_efficacy_text(full)])
    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_efficacy"}
    )
    assert r.status_code == 200
    body = r.json()
    assert "server_time_utc" in body
    assert body["server_time_utc"].endswith("Z")


def test_response_report_has_required_fields(app: FastAPI):
    full = (
        "The randomized trial enrolled 1247 adults with chronic migraines. "
        "Aspirin 325mg demonstrated significant headache reduction at "
        "outcomes assessment."
    )
    payload = _adequate_pool_payload(full_text=full)
    _override_completion_fn(app, [_good_efficacy_text(full)])
    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_efficacy"}
    )
    assert r.status_code == 200
    report = r.json()["report"]
    for field in (
        "report_id",
        "pool_id",
        "decision_id",
        "sections",
        "overall_verify_pass_rate",
        "pipeline_verdict",
        "generator_model",
        "verifier_pass_threshold",
        "started_at_utc",
        "finished_at_utc",
        "latency_ms",
        "cost_usd",
    ):
        assert field in report


def test_safety_scope_class_uses_safety_blueprint(app: FastAPI):
    full = (
        "Older adults receiving metformin showed adverse events at 8% rate "
        "in pharmacovigilance reports of monitoring studies."
    )
    payload = _adequate_pool_payload(full_text=full)
    text = (
        f"Older adults showed adverse events at 8% rate in pharmacovigilance "
        f"monitoring [#ev:src-1:0-{len(full)}]."
    )
    _override_completion_fn(app, [text])
    r = TestClient(app).post(
        "/api/generation", json={"pool": payload, "scope_class": "clinical_safety"}
    )
    assert r.status_code == 200
    section_ids = {s["section_id"] for s in r.json()["report"]["sections"]}
    assert "sec_adverse_events" in section_ids


# ---------- 422 validation ----------

def test_post_missing_pool_returns_422(app: FastAPI):
    r = TestClient(app).post("/api/generation", json={})
    assert r.status_code == 422


def test_post_malformed_pool_returns_422(app: FastAPI):
    r = TestClient(app).post(
        "/api/generation",
        json={"pool": {"decision_id": "x"}},  # missing required fields
    )
    assert r.status_code in (400, 422)
