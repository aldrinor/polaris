"""Tests for I-bug-110 — synthesis [N] scrub telemetry counters.

When `_scrub_invalid_n_markers` strips an out-of-range or malformed
[N] marker from synthesis output, two process-lifetime counters
record the event:
  - n_scrub_count: total markers scrubbed (cumulative)
  - n_scrub_runs: number of synthesis calls that needed any scrub

These mirror the entailment-judge telemetry pattern.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.analyst_synthesis import (
    _scrub_invalid_n_markers,
    _SYNTHESIS_TELEMETRY,
    get_synthesis_telemetry,
    reset_synthesis_telemetry,
)


@pytest.fixture(autouse=True)
def _reset_synthesis_counters():
    reset_synthesis_telemetry()
    yield
    reset_synthesis_telemetry()


def test_clean_text_does_not_increment_counters():
    text = "Result [1] and [2] and [3]."
    _scrub_invalid_n_markers(text, biblio_size=5)
    snap = get_synthesis_telemetry()
    assert snap["synthesis_n_scrub_count"] == 0
    assert snap["synthesis_n_scrub_runs"] == 0


def test_one_invalid_marker_increments_count_and_runs():
    text = "Result [1] and [99]."
    _scrub_invalid_n_markers(text, biblio_size=5)
    snap = get_synthesis_telemetry()
    assert snap["synthesis_n_scrub_count"] == 1
    assert snap["synthesis_n_scrub_runs"] == 1


def test_multiple_invalid_markers_in_one_call_increment_count_once_per_marker():
    text = "Result [99] and [-1] and [0] and [3]."
    _scrub_invalid_n_markers(text, biblio_size=5)
    snap = get_synthesis_telemetry()
    # 3 invalid: [99], [-1], [0]
    assert snap["synthesis_n_scrub_count"] == 3
    # but only 1 RUN had a scrub
    assert snap["synthesis_n_scrub_runs"] == 1


def test_two_calls_with_scrubs_increment_runs_twice():
    _scrub_invalid_n_markers("Result [99].", biblio_size=5)
    _scrub_invalid_n_markers("Other [99] [98].", biblio_size=5)
    snap = get_synthesis_telemetry()
    assert snap["synthesis_n_scrub_count"] == 3  # 1 + 2
    assert snap["synthesis_n_scrub_runs"] == 2


def test_two_calls_one_clean_one_scrubbed_increments_runs_once():
    _scrub_invalid_n_markers("Result [1].", biblio_size=5)  # clean
    _scrub_invalid_n_markers("Result [99].", biblio_size=5)  # scrubbed
    snap = get_synthesis_telemetry()
    assert snap["synthesis_n_scrub_count"] == 1
    assert snap["synthesis_n_scrub_runs"] == 1


def test_get_telemetry_returns_snapshot_not_live():
    """Mutating the snapshot must NOT affect the live counters."""
    _scrub_invalid_n_markers("Result [99].", biblio_size=5)
    snap = get_synthesis_telemetry()
    snap["synthesis_n_scrub_count"] = 1000
    live = get_synthesis_telemetry()
    assert live["synthesis_n_scrub_count"] == 1, "snapshot mutation leaked to live counter"


def test_reset_zeroes_counters():
    _scrub_invalid_n_markers("Result [99].", biblio_size=5)
    assert get_synthesis_telemetry()["synthesis_n_scrub_count"] == 1
    reset_synthesis_telemetry()
    snap = get_synthesis_telemetry()
    assert snap["synthesis_n_scrub_count"] == 0
    assert snap["synthesis_n_scrub_runs"] == 0


def test_reset_in_place_preserves_dict_identity():
    """reset_synthesis_telemetry mutates in place — anyone holding a
    reference to _SYNTHESIS_TELEMETRY sees the reset.
    """
    ref = _SYNTHESIS_TELEMETRY
    _scrub_invalid_n_markers("Result [99].", biblio_size=5)
    assert ref["synthesis_n_scrub_count"] == 1
    reset_synthesis_telemetry()
    assert ref["synthesis_n_scrub_count"] == 0  # same dict object zeroed in place
