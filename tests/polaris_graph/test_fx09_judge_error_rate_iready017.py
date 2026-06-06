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
    begin_run_judge_telemetry,
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


def test_per_run_scope_counts_only_this_runs_judge_invocations() -> None:
    run_tel = begin_run_judge_telemetry()
    # 245 real judge invocations; 30 errored (failed open as ENTAILED)
    for i in range(245):
        if i < 30:
            _record_judge_outcome("ENTAILED", "judge_error: timeout")
        else:
            _record_judge_outcome("ENTAILED", "ok")
    # the per-run dict starts at 0 and counts ONLY this run's judge calls
    assert run_tel["calls"] == 245
    assert run_tel["judge_error"] == 30
    calls, errors = _judge_calls_and_errors_from_telemetry(
        {"calls": 0, "judge_error": 0}, run_tel,
    )
    assert (calls, errors) == (245, 30)


def test_snapshot_is_stable_base_unaffected_by_later_ticks() -> None:
    base = get_judge_telemetry()
    _record_judge_outcome("ENTAILED", "ok")
    # base is a COPY; later ticks must not mutate it (else delta would be 0)
    assert base["calls"] == 0
    calls, _ = _judge_calls_and_errors_from_telemetry(base, get_judge_telemetry())
    assert calls == 1


def test_second_run_scope_resets_to_fresh_counter() -> None:
    # run 1 scope
    run1 = begin_run_judge_telemetry()
    for _ in range(245):
        _record_judge_outcome("ENTAILED", "ok")
    assert run1["calls"] == 245
    # a NEW run scope (NO global reset — sequential isolation): starts at 0
    run2 = begin_run_judge_telemetry()
    for _ in range(100):
        _record_judge_outcome("ENTAILED", "ok")
    assert run2["calls"] == 100, "second run scope must count ONLY its own calls"
    assert run1["calls"] == 245, "first run's dict is untouched by the second run"


def test_per_run_scope_isolates_concurrent_threads() -> None:
    """FX-09 P1 (Codex iter-1): the v6 Dramatiq worker runs asyncio.run(run_one_query)
    under --threads 2, sharing ONE process. Per-run contextvar scopes must isolate each
    thread's judge counts so a sibling run cannot dilute (or false-trip) the binding
    abort_verifier_degraded gate. With the OLD process-global snapshot/delta this test
    would see cross-contaminated counts."""
    import threading

    results: dict[str, dict] = {}
    barrier = threading.Barrier(2)

    def _worker(name: str, n_calls: int, n_errors: int) -> None:
        tel = begin_run_judge_telemetry()
        barrier.wait()  # maximize interleaving of the two threads' judge calls
        for i in range(n_calls):
            reason = "judge_error: x" if i < n_errors else "ok"
            _record_judge_outcome("ENTAILED", reason)
        results[name] = dict(tel)

    t1 = threading.Thread(target=_worker, args=("A", 245, 30))
    t2 = threading.Thread(target=_worker, args=("B", 100, 5))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert results["A"] == {"calls": 245, "judge_error": 30}, "thread A contaminated by B"
    assert results["B"] == {"calls": 100, "judge_error": 5}, "thread B contaminated by A"


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
