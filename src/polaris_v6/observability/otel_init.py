"""OpenTelemetry SDK initialization with mandatory GenAI semconv opt-in check.

Per CLAUDE.md LAW II (No Silent Fallbacks): if OTEL is misconfigured, POLARIS
aborts at startup rather than ship a build with broken telemetry.

Per docs/opentelemetry_genai.md (Errata E-2): the only correct env value is
`gen_ai_latest_experimental`. Any other value (including the legacy `gen_ai_dev`
that appeared in earlier draft plans) raises RuntimeError.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

REQUIRED_OPT_IN = "gen_ai_latest_experimental"
ENV_VAR = "OTEL_SEMCONV_STABILITY_OPT_IN"


def init_otel() -> trace.TracerProvider:
    """Initialize OpenTelemetry with mandatory GenAI semconv opt-in.

    Raises:
        RuntimeError: if OTEL_SEMCONV_STABILITY_OPT_IN does not include
            `gen_ai_latest_experimental` in its comma-separated list.
    """
    actual = os.environ.get(ENV_VAR, "")
    tokens = [token.strip() for token in actual.split(",") if token.strip()]
    if REQUIRED_OPT_IN not in tokens:
        raise RuntimeError(
            f"POLARIS v6 requires {ENV_VAR} to include "
            f"'{REQUIRED_OPT_IN}'. Got: '{actual}'. "
            f"See docs/opentelemetry_genai.md for the rationale."
        )

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider
