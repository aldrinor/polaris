"""Tests for the F15 bundle export endpoint."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_bundle_returns_404_for_unknown_run(client):
    response = client.get("/runs/does_not_exist/bundle")
    assert response.status_code == 404


def test_bundle_returns_clinical_golden_run(client):
    response = client.get("/runs/golden_clinical_001/bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["run_id"] == "golden_clinical_001"
    assert body["template"] == "clinical"
    assert body["family_segregation_passed"] is True
    assert body["pipeline_status"] == "success"
    assert len(body["evidence_pool"]) >= 1


def test_bundle_returns_contradiction_golden_run(client):
    response = client.get("/runs/golden_housing_002/bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["template"] == "policy"
    assert len(body["contradictions"]) == 1
    assert body["contradictions"][0]["resolution"] == "noted_both"


def test_bundle_returns_abort_run(client):
    response = client.get("/runs/golden_abort_003/bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_status"] == "abort_no_verified_sections"
    assert body["verified_sentences"] == []
