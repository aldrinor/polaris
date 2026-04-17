"""Pytest fixtures for polaris_graph tests.

Disables OpenAlex by default so tests don't hit the real API unless
they explicitly opt in via monkeypatch.setenv("PG_OPENALEX_ENABLED", "1").
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _disable_openalex_by_default(monkeypatch):
    """Default OpenAlex off for all tests; individual tests opt in."""
    # Only set if not already set by the test itself.
    if "PG_OPENALEX_ENABLED" not in os.environ or os.environ.get("PG_OPENALEX_ENABLED") == "1":
        monkeypatch.setenv("PG_OPENALEX_ENABLED", "0")
        from src.polaris_graph.tools import openalex_client as _oa
        _oa.ENABLED = False
    yield
