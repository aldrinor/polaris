"""Tests for I-bug-111 — synthesis [N] scrub alert threshold.

When `_scrub_invalid_n_markers` strips MORE than
`SYNTHESIS_SCRUB_ALERT_THRESHOLD` (default: 5) markers in a single
call, a sticky alert flag is set. Operator-facing: sweep manifest
writers surface this as `manifest.synthesis_n_scrub_alert: bool`.

The flag is sticky across calls (true if ANY single call tripped it)
so a transient spike in one call is still surfaced after subsequent
clean calls.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.analyst_synthesis import (
    SYNTHESIS_SCRUB_ALERT_THRESHOLD,
    _scrub_invalid_n_markers,
    reset_synthesis_scrub_alert,
    reset_synthesis_telemetry,
    synthesis_scrub_alert_state,
)


@pytest.fixture(autouse=True)
def _reset_alert_state():
    reset_synthesis_scrub_alert()
    reset_synthesis_telemetry()
    yield
    reset_synthesis_scrub_alert()
    reset_synthesis_telemetry()


def test_alert_threshold_value():
    """Per acceptance: alert threshold = 5 (matches issue body 'scrub > 5')."""
    assert SYNTHESIS_SCRUB_ALERT_THRESHOLD == 5


def test_no_alert_on_clean_synthesis():
    text = "Result [1] [2] [3]."
    _scrub_invalid_n_markers(text, biblio_size=5)
    assert synthesis_scrub_alert_state() is False


def test_no_alert_when_scrub_at_threshold():
    """Threshold 5 means STRICTLY GREATER than 5 fires. Exactly 5 does NOT."""
    # 5 invalid markers
    text = "[99] [98] [97] [96] [95] and [1] survives."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert n == 5
    assert synthesis_scrub_alert_state() is False, (
        "exactly threshold (5) should NOT fire alert"
    )


def test_alert_when_scrub_exceeds_threshold():
    """6 markers scrubbed in ONE call > threshold 5 → alert fires."""
    text = "[99] [98] [97] [96] [95] [94] and [1]."
    cleaned, n = _scrub_invalid_n_markers(text, biblio_size=5)
    assert n == 6
    assert synthesis_scrub_alert_state() is True


def test_alert_is_sticky_across_calls():
    """Once tripped, alert stays True even after subsequent clean calls."""
    # First call trips it
    _scrub_invalid_n_markers("[99] [98] [97] [96] [95] [94].", biblio_size=5)
    assert synthesis_scrub_alert_state() is True
    # Second call is clean — alert MUST remain True (sticky)
    _scrub_invalid_n_markers("[1] [2] [3].", biblio_size=5)
    assert synthesis_scrub_alert_state() is True


def test_reset_clears_alert():
    _scrub_invalid_n_markers("[99] [98] [97] [96] [95] [94].", biblio_size=5)
    assert synthesis_scrub_alert_state() is True
    reset_synthesis_scrub_alert()
    assert synthesis_scrub_alert_state() is False


def test_alert_log_message_includes_count_and_threshold(caplog):
    """The WARN log line surfaces both the scrubbed count and threshold,
    so operators have actionable info without checking source code.
    """
    text = "[99] [98] [97] [96] [95] [94] [93]."
    with caplog.at_level("WARNING"):
        _scrub_invalid_n_markers(text, biblio_size=5)
    alert_lines = [
        r for r in caplog.records
        if "synthesis_n_scrub_alert" in r.message
    ]
    assert len(alert_lines) == 1
    msg = alert_lines[0].message
    assert "7" in msg, "scrubbed count must appear in alert log"
    assert "5" in msg, "threshold must appear in alert log"


def test_manifest_field_picks_up_alert_state():
    """I-bug-111 iter-1 P1 regression: scripts/run_honest_sweep_r3.py
    surfaces the alert as `manifest['synthesis_n_scrub_alert']`. This
    test simulates that wiring: scrub > threshold → alert fires →
    manifest field reflects True.
    """
    text = "[99] [98] [97] [96] [95] [94] [93]."  # 7 invalid markers
    _scrub_invalid_n_markers(text, biblio_size=5)
    manifest_field_value = synthesis_scrub_alert_state()
    # This is the exact expression the sweep's manifest writer uses
    manifest = {"synthesis_n_scrub_alert": manifest_field_value}
    assert manifest["synthesis_n_scrub_alert"] is True


def test_manifest_field_false_on_clean_run():
    """No scrub events → manifest field is False (not absent / not None)."""
    _scrub_invalid_n_markers("[1] [2] [3].", biblio_size=5)
    manifest = {"synthesis_n_scrub_alert": synthesis_scrub_alert_state()}
    assert manifest["synthesis_n_scrub_alert"] is False


def test_two_sequential_runs_alert_resets_between_them():
    """I-bug-111 iter-1 diff P1 fix: sweep calls run_one_query in a
    loop within a single process. The sticky alert MUST be reset at
    the START of each run so a high-scrub query 1 does not poison
    the manifest of clean query 2.

    This test simulates the per-run reset that
    `scripts/run_honest_sweep_r3.py:run_one_query` does at line 1009
    (next to `reset_run_cost`).
    """
    # Run 1: high-scrub. Alert fires.
    text_high = "[99] [98] [97] [96] [95] [94]."  # 6 invalid markers
    _scrub_invalid_n_markers(text_high, biblio_size=5)
    run1_alert = synthesis_scrub_alert_state()
    assert run1_alert is True

    # Run 2 boundary: simulate run_one_query's start-of-run reset.
    reset_synthesis_scrub_alert()
    reset_synthesis_telemetry()

    # Run 2: clean synthesis. Alert MUST be False.
    _scrub_invalid_n_markers("[1] [2] [3].", biblio_size=5)
    run2_alert = synthesis_scrub_alert_state()
    assert run2_alert is False, (
        "alert from run 1 leaked into run 2 — start-of-run reset broken"
    )


def test_alert_does_not_fire_for_low_volume_scrubs():
    """Multiple separate calls each scrubbing a few markers: cumulative
    count exceeds threshold, but no SINGLE call does → no alert.
    """
    # 3 calls, 2 scrubs each = 6 total. None individually > 5.
    for _ in range(3):
        _scrub_invalid_n_markers("[99] [98] and [1].", biblio_size=5)
    # No single call exceeded threshold
    assert synthesis_scrub_alert_state() is False
