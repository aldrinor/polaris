"""FX-09 (I-ready-017): judge_error_rate denominator = ACTUAL judge invocations.

The judge only runs on sentences that pass every mechanical check first, so the old
denominator (all kept+dropped sentences) diluted the #1071 binding
abort_verifier_degraded gate ~2.87x. The fix derives the rate from the
process-lifetime entailment-judge telemetry delta (snapshot at run boundary).

No network, no spend: drives the real telemetry counters via _record_judge_outcome
and the pure helper run_honest_sweep_r3._judge_calls_and_errors_from_telemetry.
"""
from __future__ import annotations

import pytest

from scripts.run_honest_sweep_r3 import _judge_calls_and_errors_from_telemetry
from src.polaris_graph.llm.entailment_judge import (
    _record_judge_outcome,
    get_judge_telemetry,
    reset_judge_telemetry,
)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    reset_judge_telemetry()
    try:
        yield
    finally:
        reset_judge_telemetry()


def test_helper_denominator_is_judge_calls_not_all_sentences() -> None:
    """281 no_provenance + 155 no_overlap drops NEVER reach the judge; 245 do, N error.
    rate must be N/245, NOT N/702."""
    base = {"calls": 0, "judge_error": 0}
    # only the 245 that reached the judge tick the counter; 30 of them errored
    now = {"calls": 245, "judge_error": 30}
    calls, errors = _judge_calls_and_errors_from_telemetry(base, now)
    assert calls == 245
    assert errors == 30
    rate = errors / calls
    assert abs(rate - 30 / 245) < 1e-9
    assert abs(rate - 30 / 702) > 0.05  # NOT the diluted denominator


def test_real_telemetry_delta_counts_only_judge_invocations() -> None:
    base = get_judge_telemetry()
    # 245 real judge invocations; 30 errored (failed open as ENTAILED)
    for i in range(245):
        if i < 30:
            _record_judge_outcome("ENTAILED", "judge_error: timeout")
        else:
            _record_judge_outcome("ENTAILED", "ok")
    calls, errors = _judge_calls_and_errors_from_telemetry(base, get_judge_telemetry())
    assert calls == 245
    assert errors == 30


def test_snapshot_is_stable_base_unaffected_by_later_ticks() -> None:
    base = get_judge_telemetry()
    _record_judge_outcome("ENTAILED", "ok")
    # base is a COPY; later ticks must not mutate it (else delta would be 0)
    assert base["calls"] == 0
    calls, _ = _judge_calls_and_errors_from_telemetry(base, get_judge_telemetry())
    assert calls == 1


def test_process_lifetime_second_run_uses_only_its_delta() -> None:
    # run 1
    base1 = get_judge_telemetry()
    for _ in range(245):
        _record_judge_outcome("ENTAILED", "ok")
    calls1, _ = _judge_calls_and_errors_from_telemetry(base1, get_judge_telemetry())
    assert calls1 == 245
    # run 2 (NO reset — process-lifetime counters): snapshot a fresh base
    base2 = get_judge_telemetry()
    for _ in range(100):
        _record_judge_outcome("ENTAILED", "ok")
    calls2, _ = _judge_calls_and_errors_from_telemetry(base2, get_judge_telemetry())
    assert calls2 == 100, "second run must use ONLY its own delta, not the lifetime total"


def test_degraded_trip_fires_on_correct_denominator() -> None:
    cap = 0.10
    base = {"calls": 0, "judge_error": 0}
    now = {"calls": 245, "judge_error": 30}
    calls, errors = _judge_calls_and_errors_from_telemetry(base, now)
    rate_new = errors / calls
    rate_old_diluted = errors / 702
    assert rate_new > cap, "30/245 must trip the degraded gate"
    assert rate_old_diluted < cap, "30/702 would have MASKED the degraded judge (the bug)"


def test_zero_judge_calls_rate_is_zero_not_div_by_zero() -> None:
    base = {"calls": 5, "judge_error": 0}
    now = {"calls": 5, "judge_error": 0}
    calls, errors = _judge_calls_and_errors_from_telemetry(base, now)
    assert calls == 0
    rate = (errors / calls) if calls else 0.0
    assert rate == 0.0
