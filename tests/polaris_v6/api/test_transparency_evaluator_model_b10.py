"""B10 (2026-06-14) — /transparency must report the RESOLVED evaluator model, not gemma.

The old default (``google/gemma-4-31b-it``) made the public /transparency endpoint
LIE: the live faithfulness path runs the GLM mirror (I-arch-002/003), but the API
reported gemma — a sovereignty / transparency violation. These tests assert:

  - the payload's ``evaluator`` equals the resolved Mirror model (PG_EVALUATOR_MODEL
    else PG_MIRROR_MODEL else the locked GLM-5.1), and
  - the string "gemma" NEVER appears anywhere in the /transparency payload.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_v6.api import transparency as transparency_module


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(transparency_module.router)
    return TestClient(app)


def test_evaluator_reports_mirror_not_gemma_default_env(client, monkeypatch):
    """With NO evaluator/mirror env set, evaluator must default to the locked GLM,
    and 'gemma' must not appear anywhere in the payload."""
    monkeypatch.delenv("PG_EVALUATOR_MODEL", raising=False)
    monkeypatch.delenv("PG_MIRROR_MODEL", raising=False)
    resp = client.get("/transparency")
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluator_models"]["evaluator"] == "z-ai/glm-5.1"
    # The whole payload must be gemma-free (no stale model leaking anywhere).
    assert "gemma" not in json.dumps(body).lower()


def test_evaluator_follows_mirror_env(client, monkeypatch):
    """When PG_MIRROR_MODEL is set (and PG_EVALUATOR_MODEL unset), the evaluator
    surfaces the live Mirror — exactly what actually ran."""
    monkeypatch.delenv("PG_EVALUATOR_MODEL", raising=False)
    monkeypatch.setenv("PG_MIRROR_MODEL", "z-ai/glm-5.1")
    resp = client.get("/transparency")
    body = resp.json()
    assert body["evaluator_models"]["evaluator"] == "z-ai/glm-5.1"
    assert "gemma" not in json.dumps(body).lower()


def test_evaluator_env_overrides_mirror(client, monkeypatch):
    """An explicit PG_EVALUATOR_MODEL wins over the mirror (back-compat), and is
    reported faithfully (no gemma)."""
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "z-ai/glm-5.1")
    monkeypatch.setenv("PG_MIRROR_MODEL", "minimax/minimax-m2")
    resp = client.get("/transparency")
    body = resp.json()
    assert body["evaluator_models"]["evaluator"] == "z-ai/glm-5.1"
    assert body["evaluator_models"]["evaluator"] != body["evaluator_models"]["generator"]
    assert "gemma" not in json.dumps(body).lower()
