"""I-carney-004 — static-accounts auth + JWT coverage.

Hermetic: no AWS calls, no real Secrets Manager. Uses tmp_path for the
static_accounts YAML + monkeypatched env vars for the JWT secret.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from passlib.hash import bcrypt

from polaris_v6.api import auth as auth_module


@pytest.fixture
def jwt_secret(monkeypatch):
    secret = "test-jwt-secret-" + "x" * 32
    monkeypatch.setenv("POLARIS_JWT_SECRET", secret)
    return secret


@pytest.fixture
def static_accounts_file(tmp_path, monkeypatch):
    """Builds a YAML with a known reviewer + admin."""
    accounts_path = tmp_path / "static_accounts.yaml"
    reviewer_hash = bcrypt.using(rounds=4).hash("reviewer_pw")
    admin_hash = bcrypt.using(rounds=4).hash("admin_pw")
    accounts_path.write_text(
        f"accounts:\n"
        f"  - username: carney_office\n"
        f"    password_bcrypt: \"{reviewer_hash}\"\n"
        f"    role: reviewer\n"
        f"  - username: ops\n"
        f"    password_bcrypt: \"{admin_hash}\"\n"
        f"    role: admin\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POLARIS_STATIC_ACCOUNTS_PATH", str(accounts_path))
    return accounts_path


@pytest.fixture
def app_with_auth(jwt_secret, static_accounts_file, monkeypatch):
    monkeypatch.delenv("POLARIS_AUTH_DISABLED", raising=False)
    app = FastAPI(dependencies=[pytest.importorskip("fastapi").Depends(auth_module.require_auth)])
    app.include_router(auth_module.router)

    # Mount a stub protected route for testing.
    @app.get("/protected/echo")
    def protected() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


def test_login_valid_credentials_returns_jwt(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.post(
        "/auth/login",
        json={"username": "carney_office", "password": "reviewer_pw"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "reviewer"
    assert body["expires_in"] == 12 * 3600


def test_login_invalid_password_returns_401(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.post(
        "/auth/login",
        json={"username": "carney_office", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_credentials"


def test_login_unknown_user_returns_401(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.post(
        "/auth/login",
        json={"username": "stranger", "password": "anything"},
    )
    assert resp.status_code == 401


def test_protected_route_requires_bearer(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get("/protected/echo")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "missing_bearer_token"


def test_protected_route_accepts_valid_jwt(app_with_auth):
    client = TestClient(app_with_auth)
    login = client.post(
        "/auth/login",
        json={"username": "carney_office", "password": "reviewer_pw"},
    ).json()
    token = login["access_token"]
    resp = client.get(
        "/protected/echo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_protected_route_rejects_malformed_jwt(app_with_auth):
    client = TestClient(app_with_auth)
    resp = client.get(
        "/protected/echo",
        headers={"Authorization": "Bearer garbage.token.string"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_token"


def test_health_and_transparency_are_public(app_with_auth, monkeypatch):
    client = TestClient(app_with_auth)
    # /health doesn't require auth (allowlist)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_verify_app_startup_fails_loud_on_missing_jwt_secret(
    static_accounts_file, monkeypatch
):
    monkeypatch.delenv("POLARIS_JWT_SECRET", raising=False)
    monkeypatch.delenv("POLARIS_AUTH_DISABLED", raising=False)
    with pytest.raises(RuntimeError, match="POLARIS_JWT_SECRET"):
        auth_module.verify_app_startup()


def test_verify_app_startup_fails_loud_on_missing_accounts(
    jwt_secret, tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "POLARIS_STATIC_ACCOUNTS_PATH", str(tmp_path / "nonexistent.yaml")
    )
    monkeypatch.delenv("POLARIS_AUTH_DISABLED", raising=False)
    with pytest.raises(RuntimeError, match="static_accounts.yaml not found"):
        auth_module.verify_app_startup()


def test_verify_app_startup_skipped_when_auth_disabled(monkeypatch):
    monkeypatch.setenv("POLARIS_AUTH_DISABLED", "1")
    monkeypatch.delenv("POLARIS_JWT_SECRET", raising=False)
    # Should NOT raise even with missing secret.
    auth_module.verify_app_startup()


def test_short_jwt_secret_rejected(static_accounts_file, monkeypatch):
    monkeypatch.setenv("POLARIS_JWT_SECRET", "too-short")
    monkeypatch.delenv("POLARIS_AUTH_DISABLED", raising=False)
    with pytest.raises(RuntimeError, match="too short"):
        auth_module.verify_app_startup()
