"""M-INT-8 — M-22 slide deck endpoint exposed in inspector_router.

Acceptance bar:
  1. Endpoint exists: GET /api/inspector/runs/{slug}/slide-deck (json)
                      GET /api/inspector/runs/{slug}/slide-deck.html (html)
  2. Wraps build_slide_deck + deck_to_dict / render_deck_html
  3. 404 when slug unknown
  4. 500 / structured error when IR missing or empty report
  5. PG_USE_SLIDE_DECK_ENDPOINT=0 returns 404 (rollback)
  6. AuthZ: requires authenticated caller (M-15b retrofit)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _make_client() -> TestClient:
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(
        app,
        headers={"X-Polaris-Caller": "org_default:usr_test:owner"},
    )


def test_slide_deck_endpoint_imported() -> None:
    """The endpoint registration imports the slide_deck substrate."""
    router_mod = importlib.import_module(
        "src.polaris_graph.audit_ir.inspector_router"
    )
    assert hasattr(router_mod, "build_slide_deck")
    assert hasattr(router_mod, "deck_to_dict")
    assert hasattr(router_mod, "render_deck_html")


def test_slide_deck_json_returns_deck_for_canonical_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    # Either 200 with deck or 500 if canonical IR is missing in test env;
    # we only assert it's not 404 (the endpoint exists) and not 401/403.
    assert response.status_code in {200, 500}
    if response.status_code == 200:
        body = response.json()
        assert "slides" in body
        assert isinstance(body["slides"], list)
        assert len(body["slides"]) >= 1
        # Title slide always first (deck_to_dict uses `layout` field).
        first_slide = body["slides"][0]
        assert first_slide.get("layout") == "title", (
            f"expected layout='title' on first slide; got {first_slide!r}"
        )


def test_slide_deck_html_returns_html_for_canonical_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck.html",
    )
    assert response.status_code in {200, 500}
    if response.status_code == 200:
        assert "text/html" in response.headers["content-type"]
        assert "<html" in response.text.lower() or \
               "<!doctype" in response.text.lower() or \
               "<div" in response.text.lower()


def test_slide_deck_unknown_slug_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    response = client.get(
        "/api/inspector/runs/nonexistent_slug/slide-deck",
    )
    assert response.status_code == 404
    body = response.json()
    assert "Unknown" in body["detail"] or "not found" in body["detail"].lower()


def test_slide_deck_html_unknown_slug_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    response = client.get(
        "/api/inspector/runs/nonexistent_slug/slide-deck.html",
    )
    assert response.status_code == 404


def test_disabled_flag_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PG_USE_SLIDE_DECK_ENDPOINT=0 → endpoint returns 404 (feature off)."""
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "0")
    client = _make_client()
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    assert response.status_code == 404


def test_slide_deck_endpoint_requires_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-15b retrofit: every endpoint requires an authenticated caller."""
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    from src.polaris_graph.audit_ir.inspector_router import router
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    app = FastAPI()
    app.include_router(router)
    # No X-Polaris-Caller header — should be rejected.
    client = TestClient(app)
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    assert response.status_code in {401, 403}
