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


@pytest.fixture(autouse=True)
def _reset_phase_b_singletons():
    """Reset M-8 module-level singletons (job queue, worker, runner registry)
    around every test to prevent cross-test pollution.

    Flake root cause: a worker started by test A keeps polling test A's
    SQLite DB after test A finishes; test B then sees unexpected state
    transitions on its own DB (different file path) but the worker is
    still alive in the same process. Module-level state resets on entry
    AND exit make this deterministic.
    """
    try:
        from src.polaris_graph.audit_ir import inspector_router as _ir
        from src.polaris_graph.audit_ir.job_runner import _reset_runners_for_tests
    except ImportError:
        # If audit_ir hasn't been loaded yet (test doesn't touch it),
        # there's nothing to reset.
        yield
        return

    def _reset() -> None:
        if _ir._job_worker is not None:
            try:
                _ir._job_worker.stop(join_timeout=2.0)
            except Exception:
                pass
            _ir._job_worker = None
        _ir._job_queue = None
        _reset_runners_for_tests()

    _reset()
    yield
    _reset()
