"""Regression coverage for diagnostic lever-state recording."""

from scripts.compose_agentic_report_s3gear329 import _resolved_or_env


def test_resolved_or_env_captures_registered_env_and_unset_sources(monkeypatch):
    registered_key = "PG_RENDER_BLOCKS"
    unregistered_key = "PG_STRICT_VERIFY_ENTAILMENT"
    unset_key = "PG_UNREGISTERED_RECORDER_TEST_KEY"

    monkeypatch.setenv(registered_key, "registered-value")
    monkeypatch.setenv(unregistered_key, "off")
    monkeypatch.delenv(unset_key, raising=False)

    assert _resolved_or_env(registered_key) == {
        "value": "registered-value",
        "source": "resolve",
    }
    assert _resolved_or_env(unregistered_key) == {"value": "off", "source": "env"}
    assert _resolved_or_env(unset_key) == {"value": None, "source": "unset"}
