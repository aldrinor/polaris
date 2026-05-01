"""Tests for /runs/{run_id}/charts/{chart_type} endpoint."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


@pytest.mark.parametrize(
    "chart_type", ["forest_plot", "comparison_table", "timeline"]
)
def test_charts_for_clinical_golden(client, chart_type):
    response = client.get(f"/runs/golden_clinical_001/charts/{chart_type}")
    assert response.status_code == 200
    spec = response.json()
    assert spec["$schema"].startswith("https://vega.github.io/schema/vega-lite/v5")
    assert spec["polaris_provenance"]["chart_type"] == chart_type
    assert isinstance(spec["polaris_provenance"]["evidence_ids"], list)


def test_charts_404_for_unknown_run(client):
    response = client.get("/runs/does_not_exist/charts/forest_plot")
    assert response.status_code == 404


def test_charts_422_for_unknown_chart_type(client):
    response = client.get("/runs/golden_clinical_001/charts/pie_chart")
    assert response.status_code == 422


def test_contradiction_run_forest_plot_has_contradiction_label(client):
    response = client.get(
        "/runs/golden_housing_002/charts/forest_plot"
    )
    assert response.status_code == 200
    spec = response.json()
    labels = [datum["label"] for datum in spec["data"]["values"]]
    assert any(l.startswith("c_") for l in labels)


def test_climate_timeline_uses_verified_sentence_steps(client):
    response = client.get("/runs/golden_climate_005/charts/timeline")
    assert response.status_code == 200
    spec = response.json()
    periods = [datum["period"] for datum in spec["data"]["values"]]
    assert all(p.startswith("step-") for p in periods)
