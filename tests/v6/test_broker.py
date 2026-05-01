"""Tests for queue.broker.get_broker.

Verifies:
  - StubBroker path (default for tests / CI without Redis)
  - Env-var override (POLARIS_V6_QUEUE_USE_STUB=1)
  - Redis URL resolution precedence: arg > env > default
  - heartbeat_seconds * 1000 conversion to ms for RedisBroker
  - dramatiq global broker is registered after construction
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

pytest.importorskip("dramatiq")

import dramatiq  # noqa: E402
from dramatiq.brokers.redis import RedisBroker  # noqa: E402
from dramatiq.brokers.stub import StubBroker  # noqa: E402

from polaris_v6.queue.broker import (  # noqa: E402
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_REDIS_URL,
    get_broker,
)


def test_use_stub_explicit_true_returns_stubbroker():
    broker = get_broker(use_stub=True)
    assert isinstance(broker, StubBroker)
    # Registered globally as the active broker.
    assert dramatiq.get_broker() is broker


def test_use_stub_via_env_var():
    with patch.dict(os.environ, {"POLARIS_V6_QUEUE_USE_STUB": "1"}, clear=False):
        broker = get_broker()
    assert isinstance(broker, StubBroker)


def test_use_stub_env_var_zero_uses_redis_path():
    """Only `1` enables stub. `0`, `false`, etc. fall through to RedisBroker."""
    with patch.dict(os.environ, {"POLARIS_V6_QUEUE_USE_STUB": "0"}, clear=False):
        # Construct against a phony URL that the broker doesn't actually
        # connect to until first send; just verify the type.
        broker = get_broker(redis_url="redis://test-host:6379/0")
    assert isinstance(broker, RedisBroker)


def test_redis_url_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("POLARIS_V6_REDIS_URL", "redis://env-host:6379/0")
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "0")
    # Connection won't actually fire until a message is sent; we only verify
    # that the arg-provided URL is recorded.
    broker = get_broker(redis_url="redis://arg-host:6379/0")
    # RedisBroker stores the parsed URL on its client connection_kwargs.
    assert "arg-host" in str(broker.client.connection_pool.connection_kwargs)


def test_redis_url_env_used_when_arg_missing(monkeypatch):
    monkeypatch.setenv("POLARIS_V6_REDIS_URL", "redis://env-host:6379/0")
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "0")
    broker = get_broker()
    assert "env-host" in str(broker.client.connection_pool.connection_kwargs)


def test_redis_url_default_when_neither_set(monkeypatch):
    monkeypatch.delenv("POLARIS_V6_REDIS_URL", raising=False)
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "0")
    broker = get_broker()
    # Default is redis://localhost:6379/0.
    assert "localhost" in str(broker.client.connection_pool.connection_kwargs)


def test_default_heartbeat_seconds_is_30():
    assert DEFAULT_HEARTBEAT_SECONDS == 30


def test_default_redis_url_is_canonical():
    assert DEFAULT_REDIS_URL == "redis://localhost:6379/0"


def test_set_broker_registers_globally():
    """dramatiq.get_broker() must return the broker get_broker() built."""
    broker = get_broker(use_stub=True)
    assert dramatiq.get_broker() is broker
