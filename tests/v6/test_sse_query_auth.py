"""I-rdy-004 (#500) — SSE query-param auth.

The browser's native EventSource cannot set request headers, so the SSE
endpoint accepts the JWT from the ?access_token= query param. This is scoped:
it works for /stream/* paths ONLY and must never authenticate any other
route. These tests pin that contract.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def auth_app(monkeypatch):
    """A FastAPI app with the real global require_auth dependency and two
    test routes: a /stream/{id} (SSE-style) and a /runs/{id} (normal)."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("POLARIS_JWT_SECRET", "x" * 40)
    monkeypatch.delenv("POLARIS_AUTH_DISABLED", raising=False)

    from fastapi import Depends, FastAPI
    from polaris_v6.api.auth import require_auth

    app = FastAPI(dependencies=[Depends(require_auth)])

    @app.get("/stream/{run_id}")
    def _stream(run_id: str):  # noqa: ANN202 — test route
        return {"run_id": run_id}

    @app.get("/runs/{run_id}")
    def _run(run_id: str):  # noqa: ANN202 — test route
        return {"run_id": run_id}

    return app


def _mint_token() -> str:
    """A valid 12h JWT (the auth_app fixture has set POLARIS_JWT_SECRET)."""
    from polaris_v6.api.auth import issue_token

    token, _ = issue_token("reviewer", "reviewer")
    return token


def test_stream_accepts_query_token(auth_app):
    from fastapi.testclient import TestClient

    token = _mint_token()
    resp = TestClient(auth_app).get(f"/stream/rid-1?access_token={token}")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "rid-1"


def test_stream_missing_token_is_401(auth_app):
    from fastapi.testclient import TestClient

    resp = TestClient(auth_app).get("/stream/rid-1")
    assert resp.status_code == 401


def test_stream_invalid_query_token_is_401(auth_app):
    from fastapi.testclient import TestClient

    resp = TestClient(auth_app).get("/stream/rid-1?access_token=not-a-jwt")
    assert resp.status_code == 401


def test_query_token_does_not_authenticate_non_stream_route(auth_app):
    """The access_token query param must NOT authenticate /runs/* — only
    /stream/*. A state-changing route still requires the Bearer header."""
    from fastapi.testclient import TestClient

    token = _mint_token()
    resp = TestClient(auth_app).get(f"/runs/rid-1?access_token={token}")
    assert resp.status_code == 401


def test_stream_still_accepts_bearer_header(auth_app):
    """Header-based auth keeps working on /stream/* (e.g. server-side calls)."""
    from fastapi.testclient import TestClient

    token = _mint_token()
    resp = TestClient(auth_app).get(
        "/stream/rid-1", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
