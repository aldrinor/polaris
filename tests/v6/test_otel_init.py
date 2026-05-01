"""Tests for the fail-loudly OTEL init contract.

Per CLAUDE.md LAW II + docs/opentelemetry_genai.md Errata E-2:
- Required env value: `gen_ai_latest_experimental`
- The legacy `gen_ai_dev` from earlier draft plans MUST be rejected.
"""

import pytest


def test_init_otel_raises_when_env_missing(monkeypatch):
    monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)
    pytest.importorskip("opentelemetry")
    from polaris_v6.observability.otel_init import init_otel

    with pytest.raises(RuntimeError, match="gen_ai_latest_experimental"):
        init_otel()


def test_init_otel_rejects_legacy_gen_ai_dev(monkeypatch):
    monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_dev")
    pytest.importorskip("opentelemetry")
    from polaris_v6.observability.otel_init import init_otel

    with pytest.raises(RuntimeError, match="gen_ai_latest_experimental"):
        init_otel()


def test_init_otel_accepts_correct_value(monkeypatch):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    pytest.importorskip("opentelemetry")
    from polaris_v6.observability.otel_init import init_otel

    provider = init_otel()
    assert provider is not None


def test_init_otel_accepts_in_csv_list(monkeypatch):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN",
        "http_dup,gen_ai_latest_experimental,messaging_dup",
    )
    pytest.importorskip("opentelemetry")
    from polaris_v6.observability.otel_init import init_otel

    provider = init_otel()
    assert provider is not None
