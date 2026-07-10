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
def _disable_core_by_default(monkeypatch):
    """Default CORE (core.ac.uk) OA full-text fetch off for all tests
    (I-faith-002). Hermeticity: a developer/CI shell (or a loaded .env)
    may carry CORE_API_KEY, and the frame_fetcher Step 2b CORE call uses
    its OWN client (not the test's injected MockTransport), so leaving
    CORE on would let it reach the real api.core.ac.uk and break the
    deterministic M-56 OA-full-text tests. frame_fetcher._core_enabled()
    reads PG_CORE_ENABLED at call time, so a plain setenv disables it.
    Tests exercising the CORE wiring opt in via
    monkeypatch.setenv("PG_CORE_ENABLED", "1") IN THEIR OWN BODY — that
    setenv runs AFTER this autouse fixture, so it wins.
    """
    # Force off UNCONDITIONALLY (not setdefault): an inherited
    # PG_CORE_ENABLED=1 in the CI/dev shell must NOT let an unrelated test
    # reach live api.core.ac.uk just because CORE_API_KEY is also present.
    monkeypatch.setenv("PG_CORE_ENABLED", "0")
    yield


@pytest.fixture(autouse=True)
def _disable_strict_verify_entailment_by_default(monkeypatch):
    """I-bug-095: production default for PG_STRICT_VERIFY_ENTAILMENT is
    'enforce', which lazy-constructs an OpenRouter judge if the test
    calls verify_sentence and the env var is unset. To keep unit tests
    network-free + cost-free, force the env to 'off' here unconditionally
    (per Codex iter-1 diff review P2 — stricter hermeticity prevents an
    inherited developer/CI shell env of 'warn' or 'enforce' from leaking
    into unrelated tests). Tests that exercise the entailment gate
    explicitly override via monkeypatch.setenv inside the test body.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    yield


@pytest.fixture(autouse=True)
def _enable_test_caller_header(monkeypatch):
    """Codex M-15b retrofit: every M-1..M-13 endpoint now requires
    auth. For the test surface we use the X-Polaris-Caller test
    header (gated by PG_AUTH_TRUSTED_TEST_HEADER) so unit tests
    don't need to mint real bcrypt-hashed API keys.

    Each test's TestClient call should include a header like:
      X-Polaris-Caller: org_alpha:usr_test:owner

    Production MUST leave PG_AUTH_TRUSTED_TEST_HEADER unset.
    """
    monkeypatch.setenv("PG_AUTH_TRUSTED_TEST_HEADER", "1")
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
    except Exception as _exc:  # noqa: BLE001
        # item 2 (box2 lab harness fix): audit_ir.registry raises RegistryError (NOT ImportError) at
        # IMPORT time when an allowlisted Phase-A artifact dir is absent — which it is on box2 (only
        # SHIP_MANIFEST.md is present). The prior ``except ImportError`` did NOT catch RegistryError,
        # so this autouse fixture crashed at setup and ERRORED all 46 outline tests that never touch
        # audit_ir. Broaden the guard beyond ImportError and DISCLOSE which import failed (fail-loud
        # but continue): a test that doesn't touch audit_ir has nothing to reset.
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "conftest _reset_phase_b_singletons: audit_ir import skipped (%r) — nothing to reset.",
            _exc,
        )
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
        # M-23: also reset the review_store singleton so tests
        # that share the inspector_router module don't carry
        # state across one another.
        _ir._review_store = None
        # M-21: same for the workspace_memory_store singleton.
        _ir._workspace_memory_store = None
        _reset_runners_for_tests()

    _reset()
    yield
    _reset()
