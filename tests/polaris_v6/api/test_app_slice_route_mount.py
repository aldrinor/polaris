"""Tests that slice 001 + slice 002 routes are mounted in the live app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_real_serper_key(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests don't accidentally instantiate the real fetcher.

    create_app() reads SERPER_API_KEY at import time of build_real_fetcher;
    we monkeypatch it to empty so the sentinel default stays in place.
    """
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
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
