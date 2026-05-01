"""Tests for the F1 scope discovery contract."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_research_question_is_accepted(client):
    response = client.post(
        "/scope/check",
        json={
            "template": "housing",
            "question": "What did Q3 2025 housing starts data show across major Canadian metros?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "accepted"
    assert body["refusals"] == []
    assert "T1" in body["intended_source_tiers"]


def test_personal_treatment_request_rejected(client):
    response = client.post(
        "/scope/check",
        json={
            "template": "clinical",
            "question": "Should I take ozempic for my diabetes?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "rejected"
    assert "clinical_treatment_recommendation" in body["refusals"]


def test_short_question_needs_clarification(client):
    response = client.post(
        "/scope/check",
        json={"template": "trade", "question": "tariffs?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "needs_clarification"


def test_personal_legal_advice_rejected(client):
    response = client.post(
        "/scope/check",
        json={
            "template": "canada_us",
            "question": "Can I sue Canada Revenue Agency for my 2024 tax bill?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "rejected"
    assert "individual_legal_advice" in body["refusals"]


def test_political_endorsement_rejected(client):
    response = client.post(
        "/scope/check",
        json={
            "template": "canada_us",
            "question": "Who should I vote for in the next election?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "rejected"
    assert "personal_political_endorsement" in body["refusals"]
