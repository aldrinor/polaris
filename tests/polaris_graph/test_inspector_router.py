"""Tests for src/polaris_graph/audit_ir/inspector_router.py.

Spins up a minimal FastAPI app with just the inspector router mounted, to
keep tests independent of the full live_server.py surface area.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir.inspector_router import router
from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_runs_endpoint() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["canonical_demo_slug"] == CANONICAL_DEMO_SLUG
    assert body["count"] >= 1
    slugs = [r["slug"] for r in body["runs"]]
    assert CANONICAL_DEMO_SLUG in slugs


def test_get_run_returns_full_ir() -> None:
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"]
    assert body["manifest"]["contradictions_found"] == 14
    assert len(body["contradictions"]) == 14
    assert body["frame_coverage"]["pass_count"] == 14
    assert body["ir_schema_version"]


def test_get_run_unknown_slug_returns_404() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs/does_not_exist")
    assert resp.status_code == 404


def test_get_report_markdown_endpoint() -> None:
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/report.md")
    assert resp.status_code == 200
    assert "[1]" in resp.text  # has inline citations


def test_get_report_markdown_unknown_returns_404() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs/does_not_exist/report.md")
    assert resp.status_code == 404


def test_inspector_root_redirects_to_canonical_demo() -> None:
    client = _make_client()
    resp = client.get("/inspector", follow_redirects=False)
    assert resp.status_code in (302, 307, 308)
    assert resp.headers["location"].endswith(CANONICAL_DEMO_SLUG)


def test_inspector_page_renders_html() -> None:
    client = _make_client()
    resp = client.get(f"/inspector/{CANONICAL_DEMO_SLUG}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    # The 5-view scaffold tabs must be present
    assert 'data-view="report"' in body
    assert 'data-view="contradictions"' in body
    assert 'data-view="frame-coverage"' in body
    assert 'data-view="methods"' in body
    assert 'data-view="tier-mix"' in body
    # The slug must be substituted into the template
    assert CANONICAL_DEMO_SLUG in body
    # JS must be linked
    assert "/static/inspector/inspector.js" in body


def test_inspector_page_unknown_returns_404() -> None:
    client = _make_client()
    resp = client.get("/inspector/does_not_exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Codex M-2 review (high #1, #2): list/detail round-trip + uniqueness
# ---------------------------------------------------------------------------


def test_list_to_detail_round_trip_for_every_listed_run() -> None:
    """Every run from /api/inspector/runs must be fetchable at /api/inspector/runs/{slug}.

    Before the fix: list reported 90 runs, but 75 of them returned 500 on detail.
    """
    client = _make_client()
    list_resp = client.get("/api/inspector/runs")
    assert list_resp.status_code == 200
    body = list_resp.json()
    for run in body["runs"]:
        slug = run["slug"]
        listed_run_id = run["run_id"]
        detail_resp = client.get(f"/api/inspector/runs/{slug}")
        assert detail_resp.status_code == 200, f"Detail 404/500 for slug={slug}"
        detail = detail_resp.json()
        assert detail["run_id"] == listed_run_id, (
            f"run_id drift: list={listed_run_id} detail={detail['run_id']}"
        )
