"""OpenTelemetry trace-id propagation middleware for Dramatiq.

`opentelemetry-instrumentation-dramatiq` does not exist on PyPI (verified
2026-05-01). POLARIS provides its own middleware that injects the active
trace context onto outgoing message options and re-extracts it inside
the worker before invoking the actor.

Per docs/backend_modernization.md §3 acceptance scenario 6: trace-id
present in actor span; parent-child relationship preserved across
enqueue → execute → child-actor invocation.
"""

from __future__ import annotations

from typing import Any

import dramatiq

OTEL_OPTION_KEY = "otel_carrier"


class OtelPropagateMiddleware(dramatiq.Middleware):
    """Inject + re-extract OpenTelemetry context across queue boundary."""

    def before_enqueue(self, broker: dramatiq.Broker, message: dramatiq.Message, delay: int | None) -> None:
        """Inject the active OTel context onto the outgoing message options.

        Writes a carrier under ``OTEL_OPTION_KEY`` only if propagation produced
        one. No-op if OpenTelemetry is not installed.
        """
        try:
            from opentelemetry import propagate

            carrier: dict[str, Any] = {}
            propagate.inject(carrier)
            if carrier:
                message.options[OTEL_OPTION_KEY] = carrier
        except ImportError:
            return

    def before_process_message(self, broker: dramatiq.Broker, message: dramatiq.Message) -> None:
        """Re-extract and attach the message's OTel context before the actor runs.

        Stashes the detach token under ``_otel_token`` for teardown. No-op if
        the message carries no carrier or OpenTelemetry is not installed.
        """
        carrier = message.options.get(OTEL_OPTION_KEY)
        if not carrier:
            return
        try:
            from opentelemetry import context, propagate

            ctx = propagate.extract(carrier)
            token = context.attach(ctx)
            message.options.setdefault("_otel_token", token)
        except ImportError:
            return

    def after_process_message(
        self,
        broker: dramatiq.Broker,
        message: dramatiq.Message,
        *,
        result: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        """Detach the OTel context attached in ``before_process_message``.

        Pops and detaches the ``_otel_token``. No-op if none was set or
        OpenTelemetry is not installed.
        """
        token = message.options.pop("_otel_token", None)
        if token is None:
            return
        try:
            from opentelemetry import context as otel_context

            otel_context.detach(token)
        except ImportError:
            return
