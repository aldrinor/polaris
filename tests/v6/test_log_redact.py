"""Tests for OTEL CAN_REAL log-redact module."""

from __future__ import annotations

from polaris_v6.observability.log_redact import (
    REDACT_KINDS,
    redact_attributes,
    redact_for_log,
)


def test_public_synthetic_passes_through():
    attrs = {
        "gen_ai.prompt": "What is the latest CMHC data?",
        "gen_ai.usage.input_tokens": 12,
        "polaris.run_id": "run_001",
    }
    out = redact_attributes(attrs, classification="PUBLIC_SYNTHETIC")
    assert out["gen_ai.prompt"] == "What is the latest CMHC data?"
    assert "polaris.redaction_applied" not in out


def test_can_real_redacts_prompt_and_completion():
    attrs = {
        "gen_ai.prompt": "Indigenous-resident health data: patient X was prescribed...",
        "gen_ai.completion": "Completion text containing CAN_REAL content.",
        "gen_ai.usage.input_tokens": 25,
        "gen_ai.request.model": "deepseek-v4-flash",
        "polaris.cost_usd": 0.42,
    }
    out = redact_attributes(attrs, classification="CAN_REAL")
    assert out["gen_ai.prompt"].startswith("sha256:")
    assert "len=" in out["gen_ai.prompt"]
    assert out["gen_ai.completion"].startswith("sha256:")
    # Pass-through fields stay
    assert out["gen_ai.usage.input_tokens"] == 25
    assert out["gen_ai.request.model"] == "deepseek-v4-flash"
    assert out["polaris.cost_usd"] == 0.42
    # Marker fields
    assert out["polaris.classification"] == "CAN_REAL"
    assert out["polaris.redaction_applied"] is True


def test_private_and_client_also_redact():
    attrs = {"gen_ai.prompt": "secret data"}
    for kind in ("PRIVATE", "CLIENT"):
        out = redact_attributes(attrs, classification=kind)
        assert out["gen_ai.prompt"].startswith("sha256:")


def test_unknown_classification_does_not_redact():
    attrs = {"gen_ai.prompt": "ambiguous prompt content"}
    out = redact_attributes(attrs, classification="UNKNOWN")
    assert out["gen_ai.prompt"] == "ambiguous prompt content"


def test_password_and_apikey_keys_redacted():
    attrs = {"password": "swordfish", "api_key": "sk-secret"}
    out = redact_attributes(attrs, classification="CAN_REAL")
    assert out["password"].startswith("sha256:")
    assert out["api_key"].startswith("sha256:")


def test_list_value_redacted_per_item():
    attrs = {"gen_ai.prompt": ["msg1 long enough", "msg2 long enough"]}
    out = redact_attributes(attrs, classification="CAN_REAL")
    assert all(item.startswith("sha256:") for item in out["gen_ai.prompt"])


def test_redact_for_log_passes_through_when_safe():
    assert redact_for_log("public synthetic message", "PUBLIC_SYNTHETIC") == (
        "public synthetic message"
    )


def test_redact_for_log_hashes_can_real():
    out = redact_for_log("CAN_REAL content message", "CAN_REAL")
    assert out.startswith("sha256:")
    assert "len=24" in out


def test_redact_kinds_constant():
    assert REDACT_KINDS == {"CAN_REAL", "PRIVATE", "CLIENT"}
