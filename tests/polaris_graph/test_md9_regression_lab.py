"""M-D9 phase 1 (bootstrap) regression-lab tests."""

from __future__ import annotations

import pytest

from src.polaris_graph.audit_ir.model_pin import ModelPin, capture_pin
from src.polaris_graph.audit_ir.regression_lab import (
    InductionMetric,
    ManifestDrift,
    PinDriftField,
    RegressionInputs,
    RegressionLabError,
    RegressionVerdict,
    diff_regression,
    pins_replay_equivalent,
    report_to_exit_code,
)
from src.polaris_graph.auto_induction.precision_metrics import (
    PrecisionMetrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metrics(
    *,
    precision: float = 0.85,
    silent_disagreement_rate: float = 0.02,
    abstain_recall: float = 0.95,
    abstain_precision: float = 0.90,
    operator_review_load: float = 0.20,
) -> PrecisionMetrics:
    """Construct a PrecisionMetrics with raw counts that yield
    the requested derived values. Uses N=10000 cases so small
    deltas (e.g. 1pp) survive integer rounding without
    collisions."""
    in_scope_total = 5000
    abstain_should = 5000
    in_scope_accepted = 4000  # 1000 abstained out of 5000 in-scope
    in_scope_match = int(round(in_scope_accepted * precision))
    in_scope_silent = int(round(in_scope_total * silent_disagreement_rate))
    abstain_correct = int(round(abstain_should * abstain_recall))
    if abstain_precision > 0:
        abstain_total = int(round(abstain_correct / abstain_precision))
    else:
        abstain_total = abstain_correct
    total_cases = (
        int(round(abstain_total / operator_review_load))
        if operator_review_load > 0
        else 10000
    )
    return PrecisionMetrics(
        total_cases=total_cases,
        in_scope_total=in_scope_total,
        in_scope_accepted=in_scope_accepted,
        in_scope_match_at_tau=in_scope_match,
        in_scope_silent_disagreements=in_scope_silent,
        abstain_should_abstain_total=abstain_should,
        abstain_correct=abstain_correct,
        abstain_total=abstain_total,
    )


def _pin(
    *,
    run_id: str = "r",
    model: str = "z-ai/glm-5.1",
    inductor: str = "KeywordInductor",
    inductor_profile: str = "anchor: tirzepatide",
    env: dict[str, str | None] | None = None,
) -> ModelPin:
    return capture_pin(
        run_id=run_id,
        llm_models={"generator": model},
        inductor_type=inductor,
        inductor_profile_text=inductor_profile,
        env_snapshot=env or {},
    )


def _inputs(
    *,
    pin: ModelPin | None = None,
    metrics: PrecisionMetrics | None = None,
    manifest: dict[str, object] | None = None,
) -> RegressionInputs:
    return RegressionInputs(
        pin=pin if pin is not None else _pin(),
        induction_metrics=metrics if metrics is not None else _metrics(),
        manifest=manifest,
    )


# ---------------------------------------------------------------------------
# GREEN cases (no drift)
# ---------------------------------------------------------------------------


def test_identical_pin_and_metrics_green() -> None:
    base = _inputs()
    curr = _inputs()
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.GREEN
    assert report.pin_drift == ()
    assert report.induction_drift == ()
    assert report.manifest_drift == ()


def test_metric_drift_within_tolerance_is_green() -> None:
    base = _inputs(metrics=_metrics(precision=0.85))
    # 0.86 vs 0.85: well within default 0.02 tolerance.
    curr = _inputs(metrics=_metrics(precision=0.86))
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.GREEN


def test_green_exit_code_is_zero() -> None:
    base = _inputs()
    curr = _inputs()
    report = diff_regression(base, curr)
    assert report_to_exit_code(report) == 0


# ---------------------------------------------------------------------------
# RED cases (regression detected)
# ---------------------------------------------------------------------------


def test_precision_drop_beyond_tolerance_is_red() -> None:
    base = _inputs(metrics=_metrics(precision=0.90))
    curr = _inputs(metrics=_metrics(precision=0.80))  # -10pp
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED
    assert any(
        d.metric is InductionMetric.PRECISION and d.is_regression
        for d in report.induction_drift
    )


def test_silent_disagreement_rise_is_red() -> None:
    base = _inputs(metrics=_metrics(silent_disagreement_rate=0.02))
    curr = _inputs(metrics=_metrics(silent_disagreement_rate=0.10))
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_abstain_recall_drop_is_red() -> None:
    base = _inputs(metrics=_metrics(abstain_recall=0.96))
    curr = _inputs(metrics=_metrics(abstain_recall=0.80))
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_operator_review_load_rise_is_red() -> None:
    base = _inputs(metrics=_metrics(operator_review_load=0.20))
    # +20pp rise in operator review (UX regression).
    curr = _inputs(metrics=_metrics(operator_review_load=0.40))
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_status_success_to_abort_is_red() -> None:
    """Live manifest schema: top-level `status` (unified
    taxonomy: success / partial_* / abort_* / error_*).
    success -> abort_* is regression."""
    base = _inputs(manifest={"status": "success"})
    curr = _inputs(manifest={"status": "abort_no_verified_sections"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED
    assert any(
        d.field is ManifestDrift.STATUS and d.is_regression
        for d in report.manifest_drift
    )


def test_manifest_status_success_to_partial_is_red() -> None:
    """success -> partial_* is regression: report produced but
    degraded signal. Codex round-1 explicit example."""
    base = _inputs(manifest={"status": "success"})
    curr = _inputs(manifest={"status": "partial_thin_corpus"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_status_partial_to_abort_is_red() -> None:
    """Within-taxonomy degradation: partial -> abort regresses."""
    base = _inputs(manifest={"status": "partial_thin_corpus"})
    curr = _inputs(manifest={"status": "abort_corpus_inadequate"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_status_within_partial_tier_is_yellow() -> None:
    """Within-tier partial flip is drift but not regression
    (report still produced, just a different degradation type)."""
    base = _inputs(manifest={"status": "partial_thin_corpus"})
    curr = _inputs(manifest={"status": "partial_outline_fallback"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.YELLOW


def test_manifest_release_allowed_flip_is_red() -> None:
    base = _inputs(manifest={"release_allowed": True})
    curr = _inputs(manifest={"release_allowed": False})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_adequacy_proceed_to_expand_is_red() -> None:
    """Live schema: nested `adequacy.decision`.
    proceed -> expand is regression (Codex round-1 explicit)."""
    base = _inputs(manifest={"adequacy": {"decision": "proceed"}})
    curr = _inputs(manifest={"adequacy": {"decision": "expand"}})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED
    assert any(
        d.field is ManifestDrift.ADEQUACY_DECISION and d.is_regression
        for d in report.manifest_drift
    )


def test_manifest_adequacy_expand_to_proceed_is_yellow() -> None:
    """Improvement, not regression."""
    base = _inputs(manifest={"adequacy": {"decision": "expand"}})
    curr = _inputs(manifest={"adequacy": {"decision": "proceed"}})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.YELLOW


def test_manifest_sentences_verified_dropped_to_zero_is_red() -> None:
    """Live schema: nested `generator.sentences_verified`."""
    base = _inputs(
        manifest={
            "status": "success",
            "generator": {"sentences_verified": 5},
        }
    )
    curr = _inputs(
        manifest={
            "status": "success",
            "generator": {"sentences_verified": 0},
        }
    )
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_unknown_status_fails_closed() -> None:
    """An unknown status taxonomy value should fail closed
    (treat as regression rather than miss it)."""
    base = _inputs(manifest={"status": "success"})
    curr = _inputs(manifest={"status": "some_unknown_label"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_unknown_partial_typo_fails_closed() -> None:
    """Round-2 fix: a typo'd partial_* value (NOT in
    UNIFIED_STATUS_VALUES) must fail closed, not bucket as
    'partial' via prefix match."""
    base = _inputs(manifest={"status": "partial_thin_corpus"})
    curr = _inputs(manifest={"status": "partial_typo"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_manifest_unknown_abort_typo_fails_closed() -> None:
    """Round-2 fix: same for abort_* typos."""
    base = _inputs(manifest={"status": "abort_no_sources"})
    curr = _inputs(manifest={"status": "abort_typo"})
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_known_status_values_match_live_runner() -> None:
    """Taxonomy-drift guard. The runner's UNIFIED_STATUS_VALUES
    is the source of truth; regression_lab's KNOWN_STATUS_VALUES
    must mirror it exactly. Adding a new status to the runner
    without updating regression_lab will fail this test."""
    from src.polaris_graph.audit_ir.regression_lab import (
        KNOWN_STATUS_VALUES,
    )

    # Import the live taxonomy from the runner. (The runner is
    # a script, so this is a one-way dependency at test time.)
    import importlib
    runner = importlib.import_module("scripts.run_honest_sweep_r3")
    live = runner.UNIFIED_STATUS_VALUES

    assert KNOWN_STATUS_VALUES == live, (
        f"taxonomy drift: regression_lab has "
        f"{KNOWN_STATUS_VALUES - live} not in runner; "
        f"runner has {live - KNOWN_STATUS_VALUES} not in regression_lab"
    )


def test_pin_schema_version_change_is_red() -> None:
    """Schema version change is always RED (cross-version pins
    are not safely comparable for replay)."""
    from dataclasses import replace

    base_pin = _pin()
    curr_pin = replace(base_pin, pin_schema_version="v99")
    base = _inputs(pin=base_pin)
    curr = _inputs(pin=curr_pin)
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_red_exit_code_is_one() -> None:
    base = _inputs(metrics=_metrics(precision=0.90))
    curr = _inputs(metrics=_metrics(precision=0.70))
    report = diff_regression(base, curr)
    assert report_to_exit_code(report) == 1


# ---------------------------------------------------------------------------
# YELLOW cases (drift but no regression)
# ---------------------------------------------------------------------------


def test_model_change_alone_is_yellow() -> None:
    """Operator changed model but precision held — YELLOW (review,
    don't block)."""
    base = _inputs(pin=_pin(model="z-ai/glm-5.1"))
    curr = _inputs(pin=_pin(model="qwen/qwen3.5-plus"))
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.YELLOW
    assert any(d.field_name == "llm_models" for d in report.pin_drift)


def test_env_change_alone_is_yellow() -> None:
    base = _inputs(pin=_pin(env={"OPENROUTER_PROVIDER_ORDER": "a,b"}))
    curr = _inputs(pin=_pin(env={"OPENROUTER_PROVIDER_ORDER": "b,a"}))
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.YELLOW


def test_inductor_profile_change_alone_is_yellow() -> None:
    base = _inputs(pin=_pin(inductor_profile="anchor: tirzepatide"))
    curr = _inputs(
        pin=_pin(inductor_profile="anchor: tirzepatide; support: t2dm")
    )
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.YELLOW
    assert any(
        d.field_name == "inductor_version_hash" for d in report.pin_drift
    )


def test_yellow_exit_code_is_zero() -> None:
    """YELLOW doesn't block CI — exit 0."""
    base = _inputs(pin=_pin(model="z-ai/glm-5.1"))
    curr = _inputs(pin=_pin(model="qwen/qwen3.5-plus"))
    report = diff_regression(base, curr)
    assert report_to_exit_code(report) == 0


def test_metric_improvement_is_yellow_not_red() -> None:
    """Precision improvement is config drift (something changed)
    but not a regression."""
    base = _inputs(metrics=_metrics(precision=0.80))
    curr = _inputs(metrics=_metrics(precision=0.95))  # +15pp
    report = diff_regression(base, curr)
    # Movement detected, but is_regression=False on the precision
    # metric since it improved.
    assert report.verdict is RegressionVerdict.YELLOW
    assert any(
        d.metric is InductionMetric.PRECISION and not d.is_regression
        for d in report.induction_drift
    )


# ---------------------------------------------------------------------------
# Pin per-key env diff
# ---------------------------------------------------------------------------


def test_env_diff_emits_per_key_drift() -> None:
    """Two env vars change: report shows two PinDriftField
    entries, not one big dict diff."""
    base = _inputs(pin=_pin(env={"A": "1", "B": "2", "C": "3"}))
    curr = _inputs(pin=_pin(env={"A": "1", "B": "9", "C": "8"}))
    report = diff_regression(base, curr)
    env_drifts = [d for d in report.pin_drift if "env_snapshot" in d.field_name]
    assert len(env_drifts) == 2
    keys = {d.field_name for d in env_drifts}
    assert "env_snapshot[B]" in keys
    assert "env_snapshot[C]" in keys


def test_env_diff_unset_vs_empty_treated_as_drift() -> None:
    """v4 None-vs-"" distinction propagates to env drift."""
    base = _inputs(pin=_pin(env={"PG_NLI_CONTEXT_WINDOW": None}))
    curr = _inputs(pin=_pin(env={"PG_NLI_CONTEXT_WINDOW": ""}))
    report = diff_regression(base, curr)
    assert any(
        d.field_name == "env_snapshot[PG_NLI_CONTEXT_WINDOW]"
        for d in report.pin_drift
    )


# ---------------------------------------------------------------------------
# Manifest diff
# ---------------------------------------------------------------------------


def test_manifest_none_skips_check() -> None:
    """Either side missing manifest → no manifest drift checked."""
    base = _inputs(manifest=None)
    curr = _inputs(manifest={"status": "abort_corpus_inadequate"})
    report = diff_regression(base, curr)
    assert report.manifest_drift == ()


def test_manifest_failure_to_success_not_regression() -> None:
    """Going from failure → success is improvement, not regression."""
    base = _inputs(manifest={"status": "abort_no_verified_sections"})
    curr = _inputs(manifest={"status": "success"})
    report = diff_regression(base, curr)
    flips = [
        d for d in report.manifest_drift
        if d.field is ManifestDrift.STATUS
    ]
    assert len(flips) == 1
    assert flips[0].is_regression is False
    assert report.verdict is RegressionVerdict.YELLOW


# ---------------------------------------------------------------------------
# validation_set_hash drift fails closed (Codex round-1 fix)
# ---------------------------------------------------------------------------


def test_validation_set_hash_change_is_red() -> None:
    """validation_set_hash is the IDENTITY of the benchmark
    dataset. Once it changes, induction metrics are no longer
    apples-to-apples — CI must fail closed."""
    from src.polaris_graph.audit_ir.model_pin import capture_pin

    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        inductor_type="KW",
        inductor_profile_text="anchor: foo",
    )
    # Synthesize a new pin with a different validation_set_hash
    # by re-capturing with a different validation_set_path.
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(
        suffix=".yaml", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write("in_scope: [{case_id: a, query: q}]\n")
        path = Path(f.name)
    try:
        pin_b = capture_pin(
            run_id="b",
            llm_models={"generator": "m"},
            inductor_type="KW",
            inductor_profile_text="anchor: foo",
            validation_set_path=path,
        )
    finally:
        path.unlink(missing_ok=True)
    assert pin_a.validation_set_hash != pin_b.validation_set_hash

    base = _inputs(pin=pin_a)
    curr = _inputs(pin=pin_b)
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED
    # The drift entry should be tagged as schema-severity.
    vs_drifts = [
        d for d in report.pin_drift
        if d.field_name == "validation_set_hash"
    ]
    assert len(vs_drifts) == 1
    assert vs_drifts[0].severity == "schema"


# ---------------------------------------------------------------------------
# Tolerance overrides (LAW VI)
# ---------------------------------------------------------------------------


def test_precision_tolerance_env_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tightening tolerance to 0.005 catches a 1pp drop that
    would otherwise be GREEN."""
    monkeypatch.setenv("PG_REGRESSION_PRECISION_TOLERANCE", "0.005")
    base = _inputs(metrics=_metrics(precision=0.90))
    curr = _inputs(metrics=_metrics(precision=0.89))  # -1pp
    report = diff_regression(base, curr)
    assert report.verdict is RegressionVerdict.RED


def test_invalid_tolerance_raises() -> None:
    import os

    os.environ["PG_REGRESSION_PRECISION_TOLERANCE"] = "not-a-float"
    try:
        with pytest.raises(RegressionLabError, match="float"):
            diff_regression(_inputs(), _inputs())
    finally:
        del os.environ["PG_REGRESSION_PRECISION_TOLERANCE"]


def test_negative_tolerance_raises() -> None:
    import os

    os.environ["PG_REGRESSION_PRECISION_TOLERANCE"] = "-0.1"
    try:
        with pytest.raises(RegressionLabError, match=">=0"):
            diff_regression(_inputs(), _inputs())
    finally:
        del os.environ["PG_REGRESSION_PRECISION_TOLERANCE"]


# ---------------------------------------------------------------------------
# Replay-equivalence shortcut
# ---------------------------------------------------------------------------


def test_pins_replay_equivalent_re_exports_pin_helper() -> None:
    pin_a = _pin(model="m1")
    pin_b = _pin(run_id="b", model="m1")  # same config, different run_id
    pin_c = _pin(model="m2")
    assert pins_replay_equivalent(pin_a, pin_b) is True
    assert pins_replay_equivalent(pin_a, pin_c) is False
