"""Test-level setup for tests/v6/.

Closes cycle-4 audit P1.1 (outputs/audits/continuous/97b9c1f_audit.md):
test_actors.py used to call `get_broker(use_stub=True)` at module import
time, which decorated the dramatiq actors against THAT StubBroker. The
acceptance suite then created a DIFFERENT StubBroker in its fixture,
producing `QueueNotFound: default` when calling `broker.join(...)`.

Fix: install ONE shared StubBroker at conftest IMPORT time (not via a
fixture). Module-level execution here runs BEFORE any test module is
imported by pytest collection — so when test_actors.py later imports
`polaris_v6.queue.actors`, the @dramatiq.actor decorator binds against
this StubBroker. Both test_actors.py and the acceptance suite reuse the
same broker via `dramatiq.get_broker()`.

Tested: `pytest tests/v6/` runs with deterministic broker state — no
QueueNotFound, no accidental Redis connection attempts.
"""

from __future__ import annotations

import os

import pytest

# Force StubBroker BEFORE any other test module imports `dramatiq` —
# otherwise dramatiq's `get_broker()` auto-creates a default RedisBroker.
os.environ.setdefault("POLARIS_V6_QUEUE_USE_STUB", "1")

# I-carney-004 P1: every create_app() call now invokes verify_app_startup()
# which raises RuntimeError on missing POLARIS_JWT_SECRET / static_accounts.
# Tests that mount the full app must bypass the auth substrate; individual
# auth tests opt back in by `monkeypatch.delenv("POLARIS_AUTH_DISABLED")`.
os.environ.setdefault("POLARIS_AUTH_DISABLED", "1")

try:
    from polaris_v6.queue.broker import get_broker as _get_broker

    # Eagerly install the StubBroker. Subsequent `import dramatiq` calls
    # see this broker; subsequent `@dramatiq.actor` decorations bind to it.
    _SHARED_TEST_BROKER = _get_broker(use_stub=True)
except ImportError:
    # dramatiq isn't installed — let individual tests use pytest.importorskip
    _SHARED_TEST_BROKER = None


@pytest.fixture(autouse=True)
def _isolated_run_db(tmp_path, monkeypatch):
    """Isolate the v6 run DB per test (I-rdy-013).

    `run_store` reads `POLARIS_V6_RUN_DB` on every connection, so pointing it
    at a fresh temp file per test prevents cross-test state from leaking. The
    1-concurrent-session gate makes this mandatory: a `queued` run left behind
    by an earlier test would otherwise make a later test's `POST /runs` return
    409. `monkeypatch` auto-restores the env var after each test.
    """
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "v6_runs.sqlite"))
