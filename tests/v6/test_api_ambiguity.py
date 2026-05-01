"""Tests for the F2 /ambiguity endpoint."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_check_ambiguity_unambiguous_housing(client):
    response = client.post(
        "/ambiguity",
        json={
            "question": "Q3 2025 housing starts?",
            "candidates": [
                {"source_id": "h1", "text": "Canadian housing starts rose 3.4% in Q3 2025."},
                {"source_id": "h2", "text": "CMHC reports housing starts up 3.4% Q3 2025."},
                {"source_id": "h3", "text": "Q3 2025 housing starts data confirms a 3.4% increase."},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_ambiguous"] is False


def test_check_ambiguity_bpei_pattern(client):
    response = client.post(
        "/ambiguity",
        json={
            "question": "What is BPEI?",
            "candidates": [
                {
                    "source_id": "med1",
                    "text": "BPEI stands for blood pressure end-inspiration index in cardiovascular monitoring.",
                },
                {
                    "source_id": "med2",
                    "text": "Clinicians use BPEI as a blood pressure end-inspiration measurement during respiratory cycle.",
                },
                {
                    "source_id": "fin1",
                    "text": "BPEI in finance refers to bank-protected enterprise investment instruments.",
                },
                {
                    "source_id": "fin2",
                    "text": "Bank-protected enterprise investment (BPEI) products carry sovereign-guarantee structures.",
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_ambiguous"] is True
    assert len(body["clusters"]) >= 2
    rep_texts = {c["representative_text"] for c in body["clusters"]}
    assert any("blood pressure" in t.lower() for t in rep_texts)
    assert any("bank" in t.lower() or "enterprise" in t.lower() for t in rep_texts)


def test_check_ambiguity_rejects_short_question(client):
    response = client.post(
        "/ambiguity",
        json={
            "question": "x",
            "candidates": [{"source_id": "a", "text": "test"}],
        },
    )
    assert response.status_code == 422


def test_check_ambiguity_empty_candidates(client):
    response = client.post(
        "/ambiguity",
        json={"question": "What does the data show?", "candidates": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_ambiguous"] is False
    assert body["clusters"] == []
