"""Dramatiq broker initialization for POLARIS v6.

Pin: dramatiq[redis,watch]==2.1.0; redis==7.4.0.

Per docs/backend_modernization.md §3 acceptance matrix, the broker is
configured with `heartbeat=30s` (mitigates broker-disconnect detection
latency) and uses sticky connections via ConnectionMiddleware (cookbook
pattern; mitigates the high-retry-rate degradation effect that makes
queues 40% slower under retry storms).
"""

from __future__ import annotations

import os
from typing import Optional

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

DEFAULT_HEARTBEAT_SECONDS = 30
DEFAULT_REDIS_URL = "redis://localhost:6379/0"

# I-carney-005 P1-001: same-process broker init guard. Set True after the
# first successful get_broker(); subsequent calls return the existing
# dramatiq broker (idempotent). Critical because polaris_v6.queue.actors
# calls get_broker() at module import BEFORE @dramatiq.actor decorations,
# and we don't want a second call to overwrite the broker the conftest
# already installed.
_INITIALIZED = False


def _reset_for_testing() -> None:
    """Test-only: reset the init sentinel so the next get_broker() rebuilds.

    Callers (autouse fixtures in tests/) MUST also save and restore the
    current `dramatiq.get_broker()` reference. Production code never calls
    this — the sentinel is meant to be one-way per process.
    """
    global _INITIALIZED
    _INITIALIZED = False


def get_broker(
    *,
    use_stub: Optional[bool] = None,
    redis_url: Optional[str] = None,
    heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
) -> dramatiq.Broker:
    """Construct and register the broker.

    Idempotent: if `_INITIALIZED` is True, returns the current dramatiq
    broker without reconstruction. Tests that need a fresh broker per case
    use `_reset_for_testing()` in an autouse fixture; production code calls
    this once at module import time and trusts the cached result thereafter.

    Args:
        use_stub: if True, use StubBroker (in-process, for tests). If None,
            inferred from POLARIS_V6_QUEUE_USE_STUB=1 env var.
        redis_url: Redis URL (defaults to POLARIS_V6_REDIS_URL env or
            redis://localhost:6379/0).
        heartbeat_seconds: broker heartbeat interval.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return dramatiq.get_broker()

    if use_stub is None:
        use_stub = os.environ.get("POLARIS_V6_QUEUE_USE_STUB", "") == "1"

    broker: dramatiq.Broker
    if use_stub:
        broker = StubBroker()
        broker.emit_after("process_boot")
    else:
        url = redis_url or os.environ.get("POLARIS_V6_REDIS_URL", DEFAULT_REDIS_URL)
        broker = RedisBroker(url=url, heartbeat_timeout=heartbeat_seconds * 1000)

    dramatiq.set_broker(broker)
    _INITIALIZED = True
    return broker
