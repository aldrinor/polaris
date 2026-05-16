"""I-rdy-006 — /transparency model-fallback regression test.

Pins the documented default generator/evaluator pair so a future stale
edit to src/polaris_v6/api/transparency.py is caught by CI. The defaults
are the operator-locked pair: DeepSeek V4 Pro generator + Gemma 4 31B
evaluator (two-family segregation per CLAUDE.md §9.1).
"""

from __future__ import annotations

import pytest


def _transparency():
    pytest.importorskip("fastapi")
    pytest.importorskip("pydantic")
    from polaris_v6.api.transparency import transparency

    return transparency()


def test_transparency_default_models_when_env_unset(monkeypatch):
    """With PG_GENERATOR_MODEL / PG_EVALUATOR_MODEL unset, /transparency
    must report the operator-locked default pair."""
    monkeypatch.delenv("PG_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("PG_EVALUATOR_MODEL", raising=False)

    response = _transparency()

    assert response.evaluator_models["generator"] == "deepseek/deepseek-v4-pro"
    assert response.evaluator_models["evaluator"] == "google/gemma-4-31b-it"


def test_transparency_honors_env_override(monkeypatch):
    """An explicit PG_GENERATOR_MODEL / PG_EVALUATOR_MODEL override is
    surfaced verbatim — the default is a fallback, not a hard-code."""
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro-test")
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it-test")

    response = _transparency()

    assert response.evaluator_models["generator"] == "deepseek/deepseek-v4-pro-test"
    assert response.evaluator_models["evaluator"] == "google/gemma-4-31b-it-test"
