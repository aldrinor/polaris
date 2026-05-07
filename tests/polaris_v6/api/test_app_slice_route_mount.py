"""Tests that slice 001 + slice 002 routes are mounted in the live app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_real_backend_keys(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests don't accidentally instantiate real backends.

    create_app() reads SERPER_API_KEY + OPENROUTER_API_KEY +
    POLARIS_GPG_KEY_ID at construction; we monkeypatch all three to
    empty so sentinel defaults stay in place.
    """
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("POLARIS_GPG_KEY_ID", raising=False)
    monkeypatch.delenv("POLARIS_BENCHMARK_RESULTS_DIR", raising=False)
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


def test_slice_004_audit_bundle_health_mounted():
    r = _client().get("/api/audit-bundle/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_004_audit_bundle_export"


def test_slice_004_audit_bundle_post_without_gpg_returns_503():
    """No POLARIS_GPG_KEY_ID -> sentinel sign_fn -> 503 (LAW II fail-loud)."""
    iso = "2026-05-04T12:00:00+00:00"
    decision = {
        "decision_id": "dec-1",
        "status": "in_scope",
        "scope_class": "clinical_efficacy",
        "ambiguity_axes": [
            {
                "axis": "population",
                "plausible_interpretations": ["adults"],
                "needs_clarification": False,
            }
        ],
        "clarifications_needed": [],
        "provenance": {},
        "latency_ms": 0,
    }
    pool = {
        "pool_id": "pool-1",
        "decision_id": "dec-1",
        "sources": [
            {
                "source_id": "src-A",
                "url": "https://www.cochrane.org/CD001",
                "domain": "cochrane.org",
                "tier": "T1",
                "title": "x",
                "publication_date": None,
                "authors": [],
                "snippet": "snippet",
                "full_text_available": True,
                "full_text": "trial",
                "fetched_at_utc": iso,
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
        "retrieval_started_at_utc": iso,
        "retrieval_finished_at_utc": iso,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }
    report = {
        "pool_id": "pool-1",
        "decision_id": "dec-1",
        "sections": [
            {
                "section_id": "sec_x",
                "section_title": "X",
                "verified_sentences": [
                    {
                        "section_id": "sec_x",
                        "sentence_text": "claim [#ev:src-A:0-3].",
                        "provenance_tokens": ["[#ev:src-A:0-3]"],
                        "verifier_pass": True,
                        "drop_reason": None,
                    }
                ],
                "section_verify_pass_rate": 1.0,
                "section_status": "verified",
            }
        ],
        "overall_verify_pass_rate": 1.0,
        "pipeline_verdict": "success",
        "generator_model": "test/m",
        "evaluator_model": "strict_verify_v1",
        "verifier_pass_threshold": 0.4,
        "started_at_utc": iso,
        "finished_at_utc": iso,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }
    r = _client().post(
        "/api/audit-bundle",
        json={"decision": decision, "pool": pool, "report": report},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "gpg_unavailable"


def test_all_four_slices_share_same_app():
    client = _client()
    for path in (
        "/api/intake/health",
        "/api/retrieval/health",
        "/api/generation/health",
        "/api/audit-bundle/health",
    ):
        assert client.get(path).status_code == 200, path


def test_slice_005_benchmark_health_mounted():
    r = _client().get("/api/benchmark/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_005_beat_both_benchmark"
    # No POLARIS_BENCHMARK_RESULTS_DIR set in test fixture -> empty list
    assert body["available_benchmarks"] == []
    assert body["results_root"] is None


def test_slice_005_benchmark_scoreboard_503_when_no_results_dir():
    r = _client().get("/api/benchmark/some_bench/scoreboard")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "benchmark_results_unavailable"


def test_all_five_slices_share_same_app():
    client = _client()
    for path in (
        "/api/intake/health",
        "/api/retrieval/health",
        "/api/generation/health",
        "/api/audit-bundle/health",
        "/api/benchmark/health",
    ):
        assert client.get(path).status_code == 200, path
