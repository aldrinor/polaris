"""Tests for F11 /followup and F12 /compare endpoints."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_followup_returns_answered_for_overlap(client):
    response = client.post(
        "/runs/golden_clinical_001/followup",
        json={"question": "What does the data show on cardiovascular outcomes?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parent_run_id"] == "golden_clinical_001"
    assert body["status"] == "answered"
    assert any(t.startswith("[#ev:") for t in body["provenance_tokens"])


def test_followup_out_of_scope(client):
    response = client.post(
        "/runs/golden_clinical_001/followup",
        json={"question": "Tell me about Renaissance painting techniques please"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "out_of_scope"


def test_followup_404_unknown_run(client):
    response = client.post(
        "/runs/does_not_exist/followup",
        json={"question": "Anything question text"},
    )
    assert response.status_code == 404


def test_followup_422_short_question(client):
    response = client.post(
        "/runs/golden_clinical_001/followup", json={"question": "x"}
    )
    assert response.status_code == 422


def test_compare_two_distinct_runs(client):
    response = client.get(
        "/runs/golden_clinical_001/compare/golden_housing_002"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["left_run_id"] == "golden_clinical_001"
    assert body["right_run_id"] == "golden_housing_002"
    assert body["same_template"] is False
    assert isinstance(body["shared_evidence_pct"], float)


def test_compare_same_run_400(client):
    response = client.get(
        "/runs/golden_clinical_001/compare/golden_clinical_001"
    )
    assert response.status_code == 400


def test_compare_unknown_run_404(client):
    response = client.get(
        "/runs/golden_clinical_001/compare/does_not_exist"
    )
    assert response.status_code == 404


def test_compare_defense_vs_climate_shared_zero(client):
    response = client.get(
        "/runs/golden_defense_004/compare/golden_climate_005"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["shared_evidence_ids"] == []
    assert body["same_template"] is False
