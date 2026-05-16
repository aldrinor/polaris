"""Tests for /health and /runs router contracts.

These run with TestClient (no real HTTP server / no Dramatiq dispatch).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"].startswith("6.")


def test_create_run_returns_202_and_queued(client):
    response = client.post(
        "/runs",
        json={"template": "clinical", "question": "What does the latest evidence show?"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["template"] == "clinical"
    assert body["run_id"]


def test_create_run_rejects_invalid_template(client):
    response = client.post(
        "/runs",
        json={"template": "not_a_template", "question": "test question"},
    )
    assert response.status_code == 422


def test_create_run_rejects_short_question(client):
    response = client.post(
        "/runs",
        json={"template": "clinical", "question": "x"},
    )
    assert response.status_code == 422


def test_get_run_returns_404_for_unknown(client):
    response = client.get("/runs/does_not_exist")
    assert response.status_code == 404


def test_create_then_get_run_round_trip(client):
    create_response = client.post(
        "/runs",
        json={"template": "policy", "question": "Tariff impact on supply chain?"},
    )
    run_id = create_response.json()["run_id"]

    get_response = client.get(f"/runs/{run_id}")
    assert get_response.status_code == 200
    assert get_response.json()["template"] == "policy"
