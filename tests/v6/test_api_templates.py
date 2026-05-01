"""Tests for /templates endpoints."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_list_returns_all_templates(client):
    response = client.get("/templates")
    assert response.status_code == 200
    body = response.json()
    ids = {t["template_id"] for t in body}
    assert "defense" in ids
    assert "climate" in ids
    assert "ai_sovereignty" in ids
    assert "canada_us" in ids
    assert "workforce" in ids


def test_get_one_returns_full_content(client):
    response = client.get("/templates/defense")
    assert response.status_code == 200
    body = response.json()
    assert body["template_id"] == "defense"
    assert "norad_modernization" in {f["frame_id"] for f in body["frame_manifest"]}
    assert len(body["sample_questions"]) >= 2


def test_get_unknown_template_404(client):
    response = client.get("/templates/does_not_exist")
    assert response.status_code == 404
