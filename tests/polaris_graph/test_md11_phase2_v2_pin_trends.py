"""M-D11 phase 2 v2 — pin trend analysis tests.

Pins:
  - analyze_pin_trends pure derivation contract
  - PinTrendVerdict thresholds (env-overridable per LAW VI)
  - Drift event accuracy across all dimension classes
  - Single-pin window edge case
  - Out-of-order pins fail loudly
  - Dimension union: keys appearing/disappearing across pins
  - Threshold relationship validation (unstable <= stable)
  - report_to_exit_code mapping
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.audit_ir.model_pin import ModelPin
from src.polaris_graph.audit_ir.pin_trends import (
    DEFAULT_STABLE_THRESHOLD,
    DEFAULT_UNSTABLE_THRESHOLD,
    DimensionTrendStat,
    PinDriftEvent,
    PinTrendError,
    PinTrendReport,
    PinTrendVerdict,
    analyze_pin_trends,
    report_to_exit_code,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pin(
    *,
    run_id: str = "r1",
    captured_at: float = 1000.0,
    schema: str = "v4",
    models: dict[str, str] | None = None,
    providers: dict[str, str] | None = None,
    prompts: dict[str, str] | None = None,
    sources: dict[str, str] | None = None,
    inductor_type: str | None = "keyword_v5",
    inductor_hash: str | None = "abc123",
    validation_hash: str | None = "vhash_001",
    env: dict[str, str | None] | None = None,
) -> ModelPin:
    return ModelPin(
        run_id=run_id,
        captured_at=captured_at,
        pin_schema_version=schema,
        llm_models=models or {"generator": "glm-5.1", "evaluator": "qwen-3.5-plus"},
        llm_providers=providers or {"generator": "openrouter"},
        prompt_version_hashes=prompts or {"system": "h_sys_001"},
        retrieval_source_versions=sources or {"serper": "1.0"},
        inductor_type=inductor_type,
        inductor_version_hash=inductor_hash,
        validation_set_hash=validation_hash,
        env_snapshot=env or {"PG_NLI_ENABLED": "1"},
        notes="",
    )


# ---------------------------------------------------------------------------
# Empty / single-pin edge cases
# ---------------------------------------------------------------------------


def test_empty_pin_sequence_raises() -> None:
    with pytest.raises(PinTrendError, match="empty"):
        analyze_pin_trends([])


def test_single_pin_window_is_trivially_stable() -> None:
    report = analyze_pin_trends([_pin()])
    assert report.pin_count == 1
    assert report.verdict == PinTrendVerdict.STABLE
    assert report.drift_events == ()
    assert report.dimension_stats == ()
    assert report.window_start == report.window_end == 1000.0


def test_non_sequence_input_raises() -> None:
    with pytest.raises(PinTrendError, match="must be a sequence"):
        analyze_pin_trends("not a sequence")  # type: ignore[arg-type]


def test_non_modelpin_element_raises() -> None:
    with pytest.raises(PinTrendError, match="not a ModelPin"):
        analyze_pin_trends([_pin(), {"run_id": "r2"}])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Chronological ordering
# ---------------------------------------------------------------------------


def test_out_of_order_pins_fail_loudly() -> None:
    """Per LAW II — fail loudly. Silent sorting would mask
    operator-side bugs in the pin store query."""
    pins = [
        _pin(captured_at=2000.0, run_id="r2"),
        _pin(captured_at=1000.0, run_id="r1"),
    ]
    with pytest.raises(PinTrendError, match="chronologically ordered"):
        analyze_pin_trends(pins)


def test_equal_timestamps_are_allowed() -> None:
    """Two pins captured at the same instant (e.g. concurrent
    workers writing a batch) are valid. No strict-monotonic
    requirement."""
    pins = [
        _pin(captured_at=1000.0, run_id="r1"),
        _pin(captured_at=1000.0, run_id="r2"),
    ]
    report = analyze_pin_trends(pins)
    assert report.pin_count == 2
    assert report.verdict == PinTrendVerdict.STABLE


# ---------------------------------------------------------------------------
# All-stable window
# ---------------------------------------------------------------------------


def test_two_identical_pins_are_stable() -> None:
    pins = [
        _pin(captured_at=1000.0, run_id="r1"),
        _pin(captured_at=2000.0, run_id="r2"),
    ]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.STABLE
    assert report.drift_events == ()
    # Every dimension has stability 1.0
    assert all(s.stability_score == 1.0 for s in report.dimension_stats)
    assert all(s.change_count == 0 for s in report.dimension_stats)
    assert all(s.total_transitions == 1 for s in report.dimension_stats)


def test_window_start_and_end_track_first_and_last_pin() -> None:
    pins = [
        _pin(captured_at=1000.0, run_id="r1"),
        _pin(captured_at=1500.0, run_id="r2"),
        _pin(captured_at=2000.0, run_id="r3"),
    ]
    report = analyze_pin_trends(pins)
    assert report.window_start == 1000.0
    assert report.window_end == 2000.0
    assert report.pin_count == 3


# ---------------------------------------------------------------------------
# Drift event detection per dimension class
# ---------------------------------------------------------------------------


def test_model_drift_emits_event_with_before_after() -> None:
    pins = [
        _pin(captured_at=1000.0, models={"generator": "glm-5.1"}),
        _pin(captured_at=2000.0, models={"generator": "glm-5.2"}),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events if e.dimension == "llm_models.generator"]
    assert len(events) == 1
    assert events[0].before == "glm-5.1"
    assert events[0].after == "glm-5.2"
    assert events[0].pin_index == 1
    assert events[0].captured_at == 2000.0


def test_prompt_hash_drift_emitted() -> None:
    pins = [
        _pin(captured_at=1000.0, prompts={"system": "h_001"}),
        _pin(captured_at=2000.0, prompts={"system": "h_002"}),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "prompt_version_hashes.system"]
    assert len(events) == 1
    assert events[0].before == "h_001"
    assert events[0].after == "h_002"


def test_validation_hash_drift_emitted() -> None:
    pins = [
        _pin(captured_at=1000.0, validation_hash="vhash_001"),
        _pin(captured_at=2000.0, validation_hash="vhash_002"),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "validation_set_hash"]
    assert len(events) == 1
    assert events[0].before == "vhash_001"
    assert events[0].after == "vhash_002"


def test_env_snapshot_drift_per_var() -> None:
    pins = [
        _pin(captured_at=1000.0,
             env={"PG_NLI_ENABLED": "1", "PG_MAX_COST_PER_RUN": "5.00"}),
        _pin(captured_at=2000.0,
             env={"PG_NLI_ENABLED": "0", "PG_MAX_COST_PER_RUN": "5.00"}),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "env_snapshot.PG_NLI_ENABLED"]
    assert len(events) == 1
    assert events[0].before == "1"
    assert events[0].after == "0"
    # Other env var was stable
    assert not any(e.dimension == "env_snapshot.PG_MAX_COST_PER_RUN"
                   for e in report.drift_events)


def test_env_var_appearing_emits_event_with_none_before() -> None:
    """A var present in pin[1] but absent in pin[0] is a
    transition from None → value. Surface explicitly."""
    pins = [
        _pin(captured_at=1000.0, env={"PG_NLI_ENABLED": "1"}),
        _pin(captured_at=2000.0,
             env={"PG_NLI_ENABLED": "1", "NEW_VAR": "added"}),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "env_snapshot.NEW_VAR"]
    assert len(events) == 1
    assert events[0].before is None
    assert events[0].after == "added"


def test_env_var_disappearing_emits_event_with_none_after() -> None:
    pins = [
        _pin(captured_at=1000.0,
             env={"PG_NLI_ENABLED": "1", "OLD_VAR": "removed_next"}),
        _pin(captured_at=2000.0, env={"PG_NLI_ENABLED": "1"}),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "env_snapshot.OLD_VAR"]
    assert len(events) == 1
    assert events[0].before == "removed_next"
    assert events[0].after is None


def test_env_var_unset_vs_empty_string_are_distinct() -> None:
    """ModelPin.env_snapshot uses None for unset, '' for set-
    empty. Trend analysis must respect that distinction —
    going from None → '' IS a transition."""
    pins = [
        _pin(captured_at=1000.0, env={"VAR": None}),
        _pin(captured_at=2000.0, env={"VAR": ""}),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "env_snapshot.VAR"]
    assert len(events) == 1
    assert events[0].before is None
    assert events[0].after == ""


def test_inductor_type_drift_emitted() -> None:
    pins = [
        _pin(captured_at=1000.0, inductor_type="keyword_v5"),
        _pin(captured_at=2000.0, inductor_type="llm_augmented_v5"),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "inductor_type"]
    assert len(events) == 1
    assert events[0].before == "keyword_v5"
    assert events[0].after == "llm_augmented_v5"


def test_schema_version_drift_emitted() -> None:
    pins = [
        _pin(captured_at=1000.0, schema="v4"),
        _pin(captured_at=2000.0, schema="v5"),
    ]
    report = analyze_pin_trends(pins)
    events = [e for e in report.drift_events
              if e.dimension == "pin_schema_version"]
    assert len(events) == 1
    assert events[0].before == "v4"
    assert events[0].after == "v5"


# ---------------------------------------------------------------------------
# Stability score calculation
# ---------------------------------------------------------------------------


def test_stability_score_one_change_in_three_transitions() -> None:
    """4 pins = 3 transitions. One change = stability 2/3."""
    pins = [
        _pin(captured_at=1000.0, models={"generator": "glm-5.1"}),
        _pin(captured_at=2000.0, models={"generator": "glm-5.1"}),
        _pin(captured_at=3000.0, models={"generator": "glm-5.2"}),
        _pin(captured_at=4000.0, models={"generator": "glm-5.2"}),
    ]
    report = analyze_pin_trends(pins)
    gen_stat = next(s for s in report.dimension_stats
                    if s.dimension == "llm_models.generator")
    assert gen_stat.change_count == 1
    assert gen_stat.total_transitions == 3
    assert gen_stat.stability_score == pytest.approx(2 / 3)


def test_stability_score_change_every_step_is_zero() -> None:
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "b"}),
        _pin(captured_at=3000.0, models={"generator": "c"}),
    ]
    report = analyze_pin_trends(pins)
    gen_stat = next(s for s in report.dimension_stats
                    if s.dimension == "llm_models.generator")
    assert gen_stat.stability_score == 0.0
    assert gen_stat.change_count == 2
    assert gen_stat.total_transitions == 2


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------


def test_all_stable_dimensions_yield_stable_verdict() -> None:
    pins = [_pin(captured_at=1000.0), _pin(captured_at=2000.0)]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.STABLE


def test_one_drifting_dimension_yields_drifting() -> None:
    """4 pins, 3 transitions, 1 change on generator = 2/3 ≈
    0.667 stability. Default thresholds: stable=0.95,
    unstable=0.5. So 0.667 → DRIFTING."""
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "a"}),
        _pin(captured_at=3000.0, models={"generator": "b"}),
        _pin(captured_at=4000.0, models={"generator": "b"}),
    ]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.DRIFTING


def test_one_unstable_dimension_yields_unstable() -> None:
    """3 pins, 2 transitions, 2 changes on generator = 0.0
    stability < unstable threshold 0.5 → UNSTABLE."""
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "b"}),
        _pin(captured_at=3000.0, models={"generator": "c"}),
    ]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.UNSTABLE


def test_unstable_overrides_drifting_in_verdict() -> None:
    """If two dimensions: one DRIFTING (0.67), one UNSTABLE
    (0.0), verdict is UNSTABLE (worst-dimension wins)."""
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}, prompts={"sys": "h1"}),
        _pin(captured_at=2000.0, models={"generator": "b"}, prompts={"sys": "h1"}),
        _pin(captured_at=3000.0, models={"generator": "c"}, prompts={"sys": "h2"}),
    ]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.UNSTABLE


# ---------------------------------------------------------------------------
# Threshold env overrides + validation
# ---------------------------------------------------------------------------


def test_stable_threshold_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_PIN_TREND_STABLE_THRESHOLD", "0.50")
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "a"}),
        _pin(captured_at=3000.0, models={"generator": "b"}),
        _pin(captured_at=4000.0, models={"generator": "b"}),
    ]
    # 0.667 stability >= 0.50 stable threshold → STABLE
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.STABLE


def test_unstable_threshold_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_PIN_TREND_UNSTABLE_THRESHOLD", "0.10")
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "b"}),
        _pin(captured_at=3000.0, models={"generator": "c"}),
    ]
    # 0.0 stability < 0.10 unstable threshold → UNSTABLE
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.UNSTABLE


def test_explicit_threshold_arg_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_PIN_TREND_STABLE_THRESHOLD", "0.50")
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "a"}),
        _pin(captured_at=3000.0, models={"generator": "b"}),
        _pin(captured_at=4000.0, models={"generator": "b"}),
    ]
    # Explicit 0.99 stable threshold overrides env's 0.50
    # 0.667 < 0.99 → DRIFTING
    report = analyze_pin_trends(pins, stable_threshold=0.99)
    assert report.verdict == PinTrendVerdict.DRIFTING


def test_invalid_threshold_relationship_raises() -> None:
    pins = [_pin(captured_at=1000.0), _pin(captured_at=2000.0)]
    with pytest.raises(PinTrendError, match="thresholds must satisfy"):
        analyze_pin_trends(
            pins, stable_threshold=0.3, unstable_threshold=0.7,
        )


def test_explicit_threshold_kwargs_clamped_to_unit_interval() -> None:
    """Codex round-1 MEDIUM fix (v2): explicit threshold kwargs
    are clamped to [0.0, 1.0] just like env overrides. v1
    raised on out-of-range values, contradicting the docstring
    contract that thresholds are clamped."""
    pins = [_pin(captured_at=1000.0), _pin(captured_at=2000.0)]
    # 1.5 clamps to 1.0; -0.2 clamps to 0.0 — should not raise
    report = analyze_pin_trends(
        pins, stable_threshold=1.5, unstable_threshold=-0.2,
    )
    assert report.verdict == PinTrendVerdict.STABLE


def test_drift_events_ordering_deterministic() -> None:
    """Codex round-1 MEDIUM fix (v2): drift events are emitted
    in dimension-sorted order within each transition. v1
    iterated `seen_dims` (a set), so order depended on Python's
    hash seed — same input could yield different drift_events
    tuples across processes, violating pure-derivation contract.
    """
    # Two pins with multiple dimension changes in one transition.
    pins = [
        _pin(
            captured_at=1000.0,
            models={"generator": "a", "evaluator": "x"},
            prompts={"sys": "h1", "user": "h2"},
        ),
        _pin(
            captured_at=2000.0,
            models={"generator": "b", "evaluator": "y"},
            prompts={"sys": "h3", "user": "h4"},
        ),
    ]
    # Run twice, collect drift_events both times — must match
    # exactly across runs (with same Python process the hash
    # seed is fixed, but the ASSERT is that they're SORTED).
    report = analyze_pin_trends(pins)
    dims_in_event_order = [e.dimension for e in report.drift_events
                           if e.pin_index == 1]
    assert dims_in_event_order == sorted(dims_in_event_order), (
        f"drift_events not in sorted order: {dims_in_event_order}"
    )


def test_threshold_clamped_to_unit_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_PIN_TREND_STABLE_THRESHOLD", "1.5")
    monkeypatch.setenv("PG_PIN_TREND_UNSTABLE_THRESHOLD", "-0.3")
    pins = [_pin(captured_at=1000.0), _pin(captured_at=2000.0)]
    # Should clamp to 1.0 and 0.0 — analyze should not raise.
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.STABLE


def test_invalid_threshold_string_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_PIN_TREND_STABLE_THRESHOLD", "not a number")
    pins = [_pin(captured_at=1000.0), _pin(captured_at=2000.0)]
    # Invalid env value → falls back to DEFAULT_STABLE_THRESHOLD
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.STABLE


# ---------------------------------------------------------------------------
# Report → exit code
# ---------------------------------------------------------------------------


def test_report_to_exit_code_unstable_blocks() -> None:
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "b"}),
        _pin(captured_at=3000.0, models={"generator": "c"}),
    ]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.UNSTABLE
    assert report_to_exit_code(report) == 1


def test_report_to_exit_code_drifting_passes() -> None:
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "a"}),
        _pin(captured_at=3000.0, models={"generator": "b"}),
        _pin(captured_at=4000.0, models={"generator": "b"}),
    ]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.DRIFTING
    assert report_to_exit_code(report) == 0


def test_report_to_exit_code_stable_passes() -> None:
    pins = [_pin(captured_at=1000.0), _pin(captured_at=2000.0)]
    report = analyze_pin_trends(pins)
    assert report.verdict == PinTrendVerdict.STABLE
    assert report_to_exit_code(report) == 0


# ---------------------------------------------------------------------------
# Drift event ordering
# ---------------------------------------------------------------------------


def test_drift_events_chronologically_ordered_by_pin_index() -> None:
    """Events emitted in pin-index order (and within a pin
    transition, in insertion order — but tests should not
    depend on intra-pin ordering)."""
    pins = [
        _pin(captured_at=1000.0, models={"generator": "a"}),
        _pin(captured_at=2000.0, models={"generator": "b"}),  # change at i=1
        _pin(captured_at=3000.0, models={"generator": "b"}),
        _pin(captured_at=4000.0, models={"generator": "c"}),  # change at i=3
    ]
    report = analyze_pin_trends(pins)
    pin_indices = [e.pin_index for e in report.drift_events]
    assert pin_indices == sorted(pin_indices)
    # Specifically: changes at i=1 and i=3
    gen_indices = [e.pin_index for e in report.drift_events
                   if e.dimension == "llm_models.generator"]
    assert gen_indices == [1, 3]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_default_thresholds_are_sensible() -> None:
    assert 0.0 < DEFAULT_UNSTABLE_THRESHOLD < DEFAULT_STABLE_THRESHOLD < 1.0
