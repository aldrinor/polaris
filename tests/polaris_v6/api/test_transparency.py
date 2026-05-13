"""I-carney-003 — transparency endpoint coverage.

Verifies:
- GET /transparency returns full Pydantic shape with all 8 required keys
- GET /transparency/pubkey.asc returns text/plain + armored block when file present
- GET /transparency/pubkey.asc returns 503 when neither file nor POLARIS_GPG_KEY_ID
- GET /transparency/policy returns version + sovereignty_filter + enforcement_layer
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_v6.api import transparency as transparency_module


@pytest.fixture
def app_with_transparency():
    app = FastAPI()
    app.include_router(transparency_module.router)
    return app


def test_transparency_returns_required_keys(app_with_transparency, monkeypatch):
    monkeypatch.setenv("AWS_REGION", "ca-central-1")
    monkeypatch.setenv("POLARIS_GPG_KEY_ID", "TESTFINGERPRINT123")
    client = TestClient(app_with_transparency)
    resp = client.get("/transparency")
    assert resp.status_code == 200
    body = resp.json()
    required = {
        "region", "git_commit", "polaris_version", "deploy_timestamp",
        "signing_key_id", "signing_key_fingerprint", "sovereignty_filter",
        "evaluator_models", "egress_allowlist", "dependencies",
    }
    assert required.issubset(body.keys()), f"missing keys: {required - body.keys()}"
    assert body["region"] == "ca-central-1"
    assert body["signing_key_id"] == "TESTFINGERPRINT123"
    assert body["sovereignty_filter"]["cleared_tiers"] == ["T1"]
    assert "T1" in body["sovereignty_filter"]["tier_definitions"]


def test_transparency_pubkey_returns_armored_block(
    app_with_transparency, tmp_path, monkeypatch
):
    pubkey_path = tmp_path / "polaris_demo_pubkey.asc"
    pubkey_path.write_text(
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
        "test stub\n"
        "-----END PGP PUBLIC KEY BLOCK-----\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POLARIS_GPG_PUBKEY_PATH", str(pubkey_path))
    client = TestClient(app_with_transparency)
    resp = client.get("/transparency/pubkey.asc")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "BEGIN PGP PUBLIC KEY BLOCK" in resp.text


def test_transparency_pubkey_returns_503_when_missing(
    app_with_transparency, tmp_path, monkeypatch
):
    monkeypatch.setenv("POLARIS_GPG_PUBKEY_PATH", str(tmp_path / "nonexistent.asc"))
    monkeypatch.delenv("POLARIS_GPG_KEY_ID", raising=False)
    client = TestClient(app_with_transparency)
    resp = client.get("/transparency/pubkey.asc")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"] == "pubkey_unavailable"


def test_transparency_policy_returns_version_and_enforcement(
    app_with_transparency,
):
    client = TestClient(app_with_transparency)
    resp = client.get("/transparency/policy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "v1.0"
    assert "sovereignty_filter" in body
    assert "egress_allowlist" in body
    assert "enforcement_layer" in body
    assert any("iptables" in layer for layer in body["enforcement_layer"])
    assert any("DOCKER-USER" in layer for layer in body["enforcement_layer"])


def test_transparency_egress_allowlist_uses_env_override(
    app_with_transparency, tmp_path, monkeypatch
):
    allowlist_path = tmp_path / "egress_allowlist.txt"
    allowlist_path.write_text(
        "# comment\n"
        "openrouter.ai\n"
        "google.serper.dev\n"
        "\n"
        "api.semanticscholar.org\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POLARIS_EGRESS_ALLOWLIST", str(allowlist_path))
    client = TestClient(app_with_transparency)
    resp = client.get("/transparency")
    body = resp.json()
    assert "openrouter.ai" in body["egress_allowlist"]
    assert "google.serper.dev" in body["egress_allowlist"]
    assert "api.semanticscholar.org" in body["egress_allowlist"]
    assert len(body["egress_allowlist"]) == 3  # comment + blank skipped


def test_transparency_egress_allowlist_default_path_is_in_container(
    app_with_transparency, monkeypatch
):
    """Codex diff iter-1 P1-004 production-default test: with no env override
    and no /app/config/egress_allowlist.txt file (test env doesn't have it),
    the response must NOT be 'unrestricted' if the path is reachable. We
    verify the DEFAULT path is the in-container path (/app/config/...),
    not /etc/polaris/* which the container cannot see.
    """
    from polaris_v6.api import transparency as tmod
    assert tmod.DEFAULT_EGRESS_ALLOWLIST.startswith("/app/"), (
        f"Default egress allowlist path must be in-container; got {tmod.DEFAULT_EGRESS_ALLOWLIST}"
    )
    # On a real deploy with Dockerfile.v6, /app/config/egress_allowlist.txt
    # exists (COPY config/ config/) → /transparency returns the 17 domains.
    # In the test env, file doesn't exist → response is 'unrestricted'.
    monkeypatch.delenv("POLARIS_EGRESS_ALLOWLIST", raising=False)
    client = TestClient(app_with_transparency)
    resp = client.get("/transparency")
    assert resp.status_code == 200
    # The default path is correct shape, even if the file isn't there in tests.
