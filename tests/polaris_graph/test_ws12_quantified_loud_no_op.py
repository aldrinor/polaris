"""I-deepfix-001 WS-12 — a quantified-analysis NO-OP is LOUDLY disclosed, never silent.

Behavioral, offline. Guards the existing (already-wired) machinery so a future regression that lets a
quantified no-op ship SILENTLY fails here. `quantified_degradation_disclosure` is called + appended to the
report (run_honest_sweep_r3.py:13346); the telemetry inits enabled=True / verified_sentences=0 before every
no-op return (quantified_analysis.py:450), so each no-op firing_status (spec_validation_rejected /
execution_failed / no_verified_sentences) renders a reader-facing '## Capability disclosures' block that
NAMES the reason.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.run_honest_sweep_r3 import quantified_degradation_disclosure  # noqa: E402


def test_spec_validation_rejected_is_loudly_disclosed():
    telem = {
        "enabled": True,
        "verified_sentences": 0,
        "firing_status": "spec_validation_rejected",
        "sourced_numbers_extracted": 7,
    }
    out = quantified_degradation_disclosure(telem)
    assert "## Capability disclosures" in out, "a quantified no-op must render a loud disclosure block"
    assert "spec_validation_rejected" in out, "the disclosure must NAME the firing_status reason"
    assert "7 sourced numbers" in out, "the disclosure discloses how many sourced numbers went unmodeled"


def test_execution_failed_is_loudly_disclosed():
    out = quantified_degradation_disclosure(
        {"enabled": True, "verified_sentences": 0, "firing_status": "execution_failed"}
    )
    assert "## Capability disclosures" in out and "execution_failed" in out


def test_no_verified_sentences_is_loudly_disclosed():
    out = quantified_degradation_disclosure(
        {"enabled": True, "verified_sentences": 0, "firing_status": "no_verified_sentences"}
    )
    assert "## Capability disclosures" in out and "no_verified_sentences" in out


def test_verified_output_produces_no_disclosure():
    # Quantified genuinely fired (verified_sentences > 0) => no degradation disclosure (the prose IS
    # the output). This is the "renders verified quantified prose" branch of the WS-12 requirement.
    out = quantified_degradation_disclosure(
        {"enabled": True, "verified_sentences": 4, "firing_status": "fired"}
    )
    assert out == "", "when quantified verified prose shipped, no degradation block is rendered"


def test_disabled_quantified_produces_no_disclosure():
    # Quantified never enabled => nothing to disclose (byte-identical legacy).
    assert quantified_degradation_disclosure({"enabled": False, "verified_sentences": 0}) == ""
    assert quantified_degradation_disclosure(None) == ""


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
