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
