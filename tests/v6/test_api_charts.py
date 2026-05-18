"""Tests for GET /runs/{run_id}/charts/{chart_type}.

I-rdy-008 (#504) slice 8: the charts route migrated off the golden-fixture
`_GOLDEN_RUN_INDEX` onto `run_store -> artifact_dir -> load_audit_ir()` +
`chart_from_audit_ir`. These tests seed an isolated run_store with
completed runs pointing at `load_audit_ir()`-loadable artifact_dirs (the
default DB has no `golden_*` rows — Codex brief iter-1 P1-1) and assert the
3 AuditIR-native chart derivations.
"""

from __future__ import annotations

import pytest

from polaris_v6.queue import run_store
from tests.v6._audit_ir_fixtures import (
    QUESTION,
    seed_completed_run,
    write_audit_ir_artifact_dir,
)

# A contradiction cluster: two sources report different body-weight numbers.
_CONTRADICTION = {
    "subject": "tirzepatide",
    "predicate": "body weight reduction (%)",
    "severity": "high",
    "claims": [
        {"evidence_id": "ev_a", "predicate": "body weight reduction", "value": 15.2},
        {"evidence_id": "ev_b", "predicate": "body weight reduction", "value": 9.8},
    ],
}
_BIBLIOGRAPHY = [
    {"num": 1, "evidence_id": "ev_a", "tier": "T1"},
    {"num": 2, "evidence_id": "ev_b", "tier": "T1"},
    {"num": 3, "evidence_id": "ev_c", "tier": "T2"},
]
# A section with tokened kept sentences (timeline) and a real total_in
# (forest-plot section-rate fallback when there are no contradictions).
_SECTION_WITH_TOKENS = {
    "title": "Efficacy",
    "total_in": 4,
    "kept": [
        {
            "sentence": "Claim one [#ev:ev_a:0-5].",
            "tokens": [{"evidence_id": "ev_a", "start": 0, "end": 5}],
        },
        {
            "sentence": "Claim two [#ev:ev_b:0-5].",
            "tokens": [{"evidence_id": "ev_b", "start": 0, "end": 5}],
        },
    ],
    "dropped": [],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on a fresh per-test run-store DB.

    POLARIS_V6_RUN_DB is set BEFORE create_app() so both the seeding calls
    and the route resolve to the same temp DB.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "runs.sqlite"))
    run_store.init_db()
    return TestClient(create_app())


def test_unknown_run_returns_404(client):
    response = client.get("/runs/does_not_exist/charts/forest_plot")
    assert response.status_code == 404


def test_unknown_chart_type_returns_422(client, tmp_path):
    artifact_dir = write_audit_ir_artifact_dir(tmp_path / "artifacts" / "ct_run")
    seed_completed_run("ct_run", artifact_dir)
    response = client.get("/runs/ct_run/charts/pie_chart")
    assert response.status_code == 422


def test_abort_run_returns_422(client):
    run_store.insert_run("abort_run", "policy", QUESTION)
    run_store.mark_aborted(
        "abort_run",
        pipeline_status="abort_corpus_inadequate",
        abort_reason="corpus fails T1 threshold",
    )
    response = client.get("/runs/abort_run/charts/forest_plot")
    assert response.status_code == 422


@pytest.mark.parametrize(
    "chart_type", ["forest_plot", "comparison_table", "timeline"]
)
def test_chart_types_render_for_a_live_run(client, tmp_path, chart_type):
    artifact_dir = write_audit_ir_artifact_dir(
        tmp_path / "artifacts" / "full_run",
        bibliography=_BIBLIOGRAPHY,
        contradictions=[_CONTRADICTION],
        sections=[_SECTION_WITH_TOKENS],
    )
    seed_completed_run("full_run", artifact_dir)

    response = client.get(f"/runs/full_run/charts/{chart_type}")
    assert response.status_code == 200, response.text
    spec = response.json()
    assert spec["$schema"].startswith(
        "https://vega.github.io/schema/vega-lite/v5"
    )
    assert spec["polaris_provenance"]["chart_type"] == chart_type
    assert isinstance(spec["polaris_provenance"]["evidence_ids"], list)


def test_forest_plot_uses_contradiction_value_spread(client, tmp_path):
    # The forest point's bar is the real min-max of the values disagreeing
    # sources reported; the point is their mean.
    artifact_dir = write_audit_ir_artifact_dir(
        tmp_path / "artifacts" / "contra_run",
        contradictions=[_CONTRADICTION],
    )
    seed_completed_run("contra_run", artifact_dir)

    response = client.get("/runs/contra_run/charts/forest_plot")
    assert response.status_code == 200, response.text
    values = response.json()["data"]["values"]
    assert len(values) == 1
    point = values[0]
    assert point["label"] == "tirzepatide"  # cluster.subject
    assert point["ci_low"] == 9.8
    assert point["ci_high"] == 15.2
    assert point["estimate"] == pytest.approx(12.5)


def test_comparison_table_is_source_tier_mix(client, tmp_path):
    artifact_dir = write_audit_ir_artifact_dir(
        tmp_path / "artifacts" / "bib_run",
        bibliography=_BIBLIOGRAPHY,
    )
    seed_completed_run("bib_run", artifact_dir)

    response = client.get("/runs/bib_run/charts/comparison_table")
    assert response.status_code == 200, response.text
    rows = {r["entity"]: r["value"] for r in response.json()["data"]["values"]}
    assert rows == {"Tier T1": 2.0, "Tier T2": 1.0}


def test_timeline_steps_over_cited_sentences(client, tmp_path):
    artifact_dir = write_audit_ir_artifact_dir(
        tmp_path / "artifacts" / "timeline_run",
        sections=[_SECTION_WITH_TOKENS],
    )
    seed_completed_run("timeline_run", artifact_dir)

    response = client.get("/runs/timeline_run/charts/timeline")
    assert response.status_code == 200, response.text
    periods = [d["period"] for d in response.json()["data"]["values"]]
    assert periods == ["step-01", "step-02"]


def test_forest_plot_section_rate_fallback_when_no_contradictions(
    client, tmp_path
):
    # No contradictions -> one point per section with a genuine kept/total_in
    # verification rate.
    artifact_dir = write_audit_ir_artifact_dir(
        tmp_path / "artifacts" / "norate_run",
        sections=[_SECTION_WITH_TOKENS],  # 2 kept, total_in 4 -> rate 0.5
    )
    seed_completed_run("rate_run", artifact_dir)

    response = client.get("/runs/rate_run/charts/forest_plot")
    assert response.status_code == 200, response.text
    values = response.json()["data"]["values"]
    assert len(values) == 1
    assert values[0]["label"] == "Efficacy"
    assert values[0]["estimate"] == pytest.approx(0.5)


def test_forest_plot_zero_total_in_section_does_not_500(client, tmp_path):
    # A section whose total_in is absent loads as total_in == 0; the
    # section-rate fallback must skip it (no ZeroDivisionError -> no 500)
    # and degrade to the placeholder point (Codex brief iter-1 P1-2).
    artifact_dir = write_audit_ir_artifact_dir(
        tmp_path / "artifacts" / "zerotot_run",
        sections=[
            {
                "title": "No total_in section",
                "kept": [{"sentence": "A kept sentence.", "tokens": []}],
                "dropped": [],
            }
        ],
    )
    seed_completed_run("zerotot_run", artifact_dir)

    response = client.get("/runs/zerotot_run/charts/forest_plot")
    assert response.status_code == 200, response.text
    values = response.json()["data"]["values"]
    assert len(values) == 1
    assert values[0]["label"] == "(no data)"
