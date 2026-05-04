"""Tests that slice 001 + slice 002 routes are mounted in the live app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_real_backend_keys(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests don't accidentally instantiate real backends.

    create_app() reads SERPER_API_KEY + OPENROUTER_API_KEY at construction;
    we monkeypatch both to empty so sentinel defaults stay in place.
    """
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    yield


def _client() -> TestClient:
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_slice_001_intake_health_mounted():
    r = _client().get("/api/intake/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_001_clinical_scope_discovery"


def test_slice_002_retrieval_health_mounted():
    r = _client().get("/api/retrieval/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_002_clinical_retrieval"


def test_slice_001_intake_post_works():
    """End-to-end smoke: a real intake call works through the mounted route."""
    r = _client().post(
        "/api/intake",
        json={"question": "Is aspirin effective for headache in adults?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is False
    assert body["decision"]["scope_class"] == "clinical_efficacy"


def test_slice_002_retrieval_post_without_serper_key_fails_loudly():
    """No SERPER_API_KEY -> sentinel default -> 400 fetch_backend_unavailable.

    Verifies LAW II (fail-loud). The route must NOT silently return an
    empty pool when the backend is unconfigured.
    """
    decision_payload = {
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
    r = _client().post(
        "/api/retrieval",
        json={"decision": decision_payload},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "fetch_backend_unavailable"


def test_slice_001_and_slice_002_share_same_app():
    """Both routes must be reachable from a single app instance (no
    create_app() side effect that mounts only the most recent slice)."""
    client = _client()
    intake = client.get("/api/intake/health")
    retrieval = client.get("/api/retrieval/health")
    assert intake.status_code == 200
    assert retrieval.status_code == 200


def test_slice_003_generation_health_mounted():
    r = _client().get("/api/generation/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_003_generator_strict_verify"


def test_slice_003_generation_post_without_completion_fn_fails_loudly():
    """No completion_fn injected -> sentinel default -> 400 with
    completion_backend_unavailable. Verifies LAW II fail-loud behavior."""
    pool_payload = {
        "pool_id": "p-1",
        "decision_id": "d-1",
        "sources": [
            {
                "source_id": "src-1",
                "url": "https://www.cochrane.org/CD001",
                "domain": "cochrane.org",
                "tier": "T1",
                "title": "x",
                "publication_date": None,
                "authors": [],
                "snippet": "x" * 50,
                "full_text_available": True,
                "full_text": "x" * 200,
                "fetched_at_utc": "2026-05-04T12:00:00+00:00",
                "provenance": {},
            }
        ],
        "adequacy": {
            "is_adequate": True,
            "sources_per_tier": {"T1": 1, "T2": 0, "T3": 0},
            "min_required_per_tier": {"T1": 0, "T2": 0, "T3": 0},
            "failure_reason": None,
        },
        "queries_executed": [],
        "retrieval_started_at_utc": "2026-05-04T12:00:00+00:00",
        "retrieval_finished_at_utc": "2026-05-04T12:00:01+00:00",
        "latency_ms": 0,
        "cost_usd": 0.0,
    }
    r = _client().post(
        "/api/generation",
        json={"pool": pool_payload, "scope_class": "clinical_efficacy"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "completion_backend_unavailable"


def test_all_three_slices_share_same_app():
    """Smoke: intake + retrieval + generation health all reachable
    from a single create_app() instance."""
    client = _client()
    for path in (
        "/api/intake/health",
        "/api/retrieval/health",
        "/api/generation/health",
    ):
        assert client.get(path).status_code == 200, path
