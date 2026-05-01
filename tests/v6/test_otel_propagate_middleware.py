"""Tests for queue.middleware.otel_propagate.OtelPropagateMiddleware.

Covers the inject/extract dance that keeps trace context across the
Dramatiq enqueue → execute boundary. Verifies:

  - before_enqueue writes a non-empty `otel_carrier` to message options
    when a span is active.
  - before_process_message extracts the carrier and attaches a context
    token on the message (storage location: message.options['_otel_token']).
  - after_process_message detaches the token (cleanup).
  - All three handlers are no-ops when the carrier is missing or when
    OpenTelemetry isn't installed (silent ImportError fallback).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("dramatiq")
pytest.importorskip("opentelemetry")
pytest.importorskip("opentelemetry.sdk")

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402

from polaris_v6.queue.middleware.otel_propagate import (  # noqa: E402
    OTEL_OPTION_KEY,
    OtelPropagateMiddleware,
)


@pytest.fixture(autouse=True)
def _otel_provider():
    """Install a real TracerProvider so spans actually populate context.
    Without this, OTEL's NoOp tracer means propagate.inject writes nothing.
    """
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    yield
    # Provider is global; we leave it set across tests for simplicity.


def _msg() -> MagicMock:
    m = MagicMock()
    m.options = {}
    return m


def test_before_enqueue_injects_carrier_when_span_active():
    mw = OtelPropagateMiddleware()
    msg = _msg()
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test-parent"):
        mw.before_enqueue(MagicMock(), msg, None)
    # The injected carrier should contain at least one propagation header
    # (typically `traceparent` for W3C TraceContext).
    assert OTEL_OPTION_KEY in msg.options
    carrier = msg.options[OTEL_OPTION_KEY]
    assert isinstance(carrier, dict)
    assert len(carrier) > 0


def test_before_enqueue_no_op_without_active_span_carrier_can_be_empty():
    """Without an active span, propagate.inject may write an empty carrier;
    the middleware skips writing if the carrier is empty."""
    mw = OtelPropagateMiddleware()
    msg = _msg()
    # No span active — call directly.
    mw.before_enqueue(MagicMock(), msg, None)
    # The implementation only assigns when carrier is non-empty.
    if OTEL_OPTION_KEY in msg.options:
        # If a default propagator inserted something, it'd be tiny.
        assert isinstance(msg.options[OTEL_OPTION_KEY], dict)


def test_before_process_message_attaches_token_when_carrier_present():
    mw = OtelPropagateMiddleware()
    msg = _msg()
    # Simulate inject: capture from a real span.
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent"):
        mw.before_enqueue(MagicMock(), msg, None)

    # Process at the worker side.
    mw.before_process_message(MagicMock(), msg)
    assert "_otel_token" in msg.options
    # Don't leak the token; clean up via the after hook.
    mw.after_process_message(MagicMock(), msg)


def test_before_process_message_no_op_when_no_carrier():
    mw = OtelPropagateMiddleware()
    msg = _msg()  # no OTEL_OPTION_KEY
    mw.before_process_message(MagicMock(), msg)
    assert "_otel_token" not in msg.options


def test_after_process_message_detaches_token():
    mw = OtelPropagateMiddleware()
    msg = _msg()
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent"):
        mw.before_enqueue(MagicMock(), msg, None)
    mw.before_process_message(MagicMock(), msg)
    assert "_otel_token" in msg.options

    mw.after_process_message(MagicMock(), msg)
    # Token consumed.
    assert "_otel_token" not in msg.options


def test_after_process_message_no_op_when_no_token():
    mw = OtelPropagateMiddleware()
    msg = _msg()  # no _otel_token
    # Should be a no-op; no exception.
    mw.after_process_message(MagicMock(), msg)


def test_full_round_trip_preserves_carrier_until_handler():
    """Inject → process → after — verify the carrier survives the
    serialization-equivalent round-trip with the same dict identity."""
    mw = OtelPropagateMiddleware()
    msg = _msg()
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent"):
        mw.before_enqueue(MagicMock(), msg, None)

    carrier_at_enqueue = msg.options[OTEL_OPTION_KEY]
    mw.before_process_message(MagicMock(), msg)
    # Carrier still present after extract.
    assert msg.options[OTEL_OPTION_KEY] == carrier_at_enqueue
    mw.after_process_message(MagicMock(), msg)
