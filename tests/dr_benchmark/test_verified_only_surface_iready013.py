"""I-ready-013 (#1080): clinical/Gate-B reports omit unverified Analyst Synthesis.

Offline, no network/spend. Pins the exact control surfaces:
  - Gate-B force-disables PG_SWEEP_ANALYST_SYNTHESIS and preflights it off.
  - run_one_query passes a clinical verified-only suppressor to the generator.
  - the generator boundary checks both the env kill switch and caller suppressor
    before importing/calling the analyst synthesis writer.
  - pipeline-B UI clinical inference reaches the same run_one_query domain path.
"""

from __future__ import annotations

import inspect
import os

import pytest

from scripts.dr_benchmark import run_gate_b as gate_b


def _set_min_passing_gate_b_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "PG_SWEEP_FETCH_CAP": "1000",
        "PG_SWEEP_MAX_SERPER": "100",
        "PG_SWEEP_MAX_S2": "100",
        "PG_STORM_ENABLED_IN_BENCHMARK": "1",
        "PG_SWEEP_EVIDENCE_DEEPENER": "1",
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1",
        "PG_AGENTIC_SEARCH_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1",
        # I-ready-016b (#1097): the 3 readiness faithfulness flags are now preflight-required.
        "PG_USE_SAFETY_REFUSAL": "1", "PG_SWEEP_NLI_CONFLICT": "1", "PG_SWEEP_TABLE_CELL_VERIFY": "1",
        "PG_ENABLE_TOOL_TRACKER": "1",
        "PG_USE_FINDING_DEDUP": "1",
        "PG_CAPPED_FINDING_DEDUP": "1",
        "PG_STRICT_VERIFY_ENTAILMENT": "enforce",
        "PG_MOST_MAX_EVIDENCE": "800",
        "PG_LIVE_MAX_EV_TO_GEN": "1500",
        "PG_RELEVANCE_FLOOR": "0.30",
        "PG_SWEEP_ANALYST_SYNTHESIS": "0",
    }.items():
        monkeypatch.setenv(key, value)

    from src.polaris_graph.llm.openrouter_client import set_max_cost_per_run

    set_max_cost_per_run(25.0)


def test_gate_b_slate_force_disables_unverified_analyst_synthesis(monkeypatch):
    from src.polaris_graph.llm.openrouter_client import (
        get_max_cost_per_run,
        set_max_cost_per_run,
    )

    old_cap = get_max_cost_per_run()
    try:
        monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
        gate_b.apply_full_capability_benchmark_slate()
        assert os.environ["PG_SWEEP_ANALYST_SYNTHESIS"] == "0"
        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_SWEEP_ANALYST_SYNTHESIS"] == "0"
        assert "PG_SWEEP_ANALYST_SYNTHESIS" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
        assert "PG_SWEEP_ANALYST_SYNTHESIS" in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
    finally:
        set_max_cost_per_run(old_cap)


def test_gate_b_preflight_fails_if_analyst_synthesis_enabled(monkeypatch):
    from src.polaris_graph.llm.openrouter_client import (
        get_max_cost_per_run,
        set_max_cost_per_run,
    )

    old_cap = get_max_cost_per_run()
    try:
        _set_min_passing_gate_b_env(monkeypatch)
        gate_b.preflight_full_capability()

        monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
        with pytest.raises(RuntimeError, match="Analyst Synthesis"):
            gate_b.preflight_full_capability()
    finally:
        set_max_cost_per_run(old_cap)


def test_generator_boundary_checks_kill_switch_and_suppressor_before_writer_import():
    from src.polaris_graph.generator import multi_section_generator as msg

    source = inspect.getsource(msg.generate_multi_section_report)
    assert "suppress_analyst_synthesis: bool = False" in source
    assert 'os.getenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")' in source
    assert "and not suppress_analyst_synthesis" in source
    assert "and analyst_synth_enabled" in source

    suppress_idx = source.index("and not suppress_analyst_synthesis")
    env_idx = source.index("and analyst_synth_enabled")
    import_idx = source.index("from src.polaris_graph.generator.analyst_synthesis import")
    assert suppress_idx < import_idx
    assert env_idx < import_idx


def test_run_one_query_forces_clinical_verified_only_surface():
    from scripts import run_honest_sweep_r3 as sweep

    source = inspect.getsource(sweep.run_one_query)
    assert "_clinical_verified_only_surface" in source
    assert 'str(q.get("domain", "")).strip().lower() == "clinical"' in source
    assert "suppress_analyst_synthesis=_clinical_verified_only_surface" in source


def test_pipeline_b_ui_clinical_queries_reach_clinical_run_one_query_path():
    from src.polaris_graph.pipeline_a_ui_adapter import _infer_domain

    assert _infer_domain("medical", "any query") == "clinical"
    assert _infer_domain("", "clinical trial evidence for anticoagulation") == "clinical"
