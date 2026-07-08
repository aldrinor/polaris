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
    # I-deepfix-001 (#1344) WINNERS-ONLY PURITY (STALE-BASELINE fix): preflight_full_capability now
    # enforces the FULL winners-only contract — the NO-LOSER gate (every killed loser force-OFF; an UNSET
    # loser like PG_SWEEP_QUERY_DECOMPOSE defaults ON and trips it), the WINNER_EXACT_VALUE assertions
    # (mineru25 / qwen3 embedder+reranker / glm-5.2 evaluator+entailment), the complete REQUIRED-flag
    # contract, and the faithfulness slate. A hand-rolled "min env" can no longer satisfy all of that, so
    # reproduce the EXACT production state the run sees just before preflight: the full-capability slate
    # PLUS the programmatic env-forces run_gate_b_query applies before it calls preflight (the entry-scoped
    # flags that are NOT in the slate dict), PLUS the complete REQUIRED / REQUIRED-OFF flag sets so the
    # caller's single perturbation (PG_SWEEP_ANALYST_SYNTHESIS=1) is what trips the gate — not some other
    # unset required flag. This mirrors the proven test_purity_preflight_gates._apply_clean_winners_only_slate.
    # Clear any loser env an operator .env might carry, so the slate's force-EXACT "0" is the only value.
    for _k in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_STORM_INGEST_WEB_RESULTS", "PG_STORM_ENABLED",
        "PG_STORM_OUTLINE_SECTIONS", "PG_STORM_MIN_EFFECTIVE_QUERIES",
        "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_SWEEP_EVIDENCE_DEEPENER", "PG_SWEEP_QUERY_DECOMPOSE",
        "PG_QGEN_ITERRESEARCH", "PG_USE_RESEARCH_PLANNER",
        "PG_EMBED_MODEL", "PG_ENTAILMENT_MODEL", "PG_EVALUATOR_MODEL",
    ):
        monkeypatch.delenv(_k, raising=False)

    gate_b.apply_full_capability_benchmark_slate()

    # Mirror the programmatic env-forces run_gate_b_query sets BEFORE preflight that are NOT in the slate
    # dict but ARE pre-required by the pre-existing preflight checks (the entry-scoped flags).
    for _name, _value in {
        "PG_AGENTIC_SEARCH_IN_BENCHMARK": "0",      # loser, force-off (run_gate_b_query)
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1",
        "PG_USE_SAFETY_REFUSAL": "1",
        "PG_SWEEP_NLI_CONFLICT": "1",
        "PG_BENCHMARK_STRICT_GATES": "1",
        "PG_SWEEP_TABLE_CELL_VERIFY": "1",
        "PG_SECTION_DISTILL": "1",
        "PG_RELEVANCE_SCORER": "semantic_v2",
        "PG_TRAFILATURA_SUBPROCESS": "1",
        "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY": "1",
    }.items():
        monkeypatch.setenv(_name, _value)
    # Satisfy the COMPLETE required-flag contract so the analyst-synthesis perturbation isolates the gate
    # under test (every required flag ON, every killed loser provably OFF, the binding verifier enforcing).
    for _flag in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        monkeypatch.setenv(_flag, "1")
    for _flag in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS:
        monkeypatch.setenv(_flag, "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")

    from src.polaris_graph.llm.openrouter_client import set_max_cost_per_run

    set_max_cost_per_run(25.0)


def test_gate_b_slate_enables_gated_analyst_synthesis(monkeypatch):
    """I-deepfix-001 (#1369): the analyst-synthesis layer is RE-ENABLED under the GATED D3 PROMOTE
    (drop-if-ungrounded) posture — operator-authorized, dual-gated (Codex+Fable). The slate now forces
    the layer ON with BOTH gate flags ON; the three flags are conscious WINNERS (allowlist + FORCE_EXACT)
    and are NO LONGER in REQUIRED_OFF. This supersedes the old I-ready-013 hard-ban assertion."""
    from src.polaris_graph.llm.openrouter_client import (
        get_max_cost_per_run,
        set_max_cost_per_run,
    )

    old_cap = get_max_cost_per_run()
    try:
        gate_b.apply_full_capability_benchmark_slate()
        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_SWEEP_ANALYST_SYNTHESIS"] == "1"
        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED"] == "1"
        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_ANALYST_SYNTHESIS_DEVIATION_CHECK"] == "1"
        assert os.environ["PG_SWEEP_ANALYST_SYNTHESIS"] == "1"
        for _f in (
            "PG_SWEEP_ANALYST_SYNTHESIS",
            "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED",
            "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK",
        ):
            assert _f in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
            assert _f in gate_b._WINNER_FLAG_ALLOWLIST
            assert _f not in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
    finally:
        set_max_cost_per_run(old_cap)


def test_gate_b_preflight_refuses_ungated_analyst_synthesis(monkeypatch):
    """I-deepfix-001 (#1369): the layer may ONLY ship under the D3 fail-closed PROMOTE gate. A run with
    PG_SWEEP_ANALYST_SYNTHESIS ON while PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED resolves falsey is the exact
    ungated posture that was banned, so the preflight REFUSES it fail-closed."""
    from src.polaris_graph.llm.openrouter_client import (
        get_max_cost_per_run,
        set_max_cost_per_run,
    )

    old_cap = get_max_cost_per_run()
    # _set_min_passing_gate_b_env mutates os.environ DIRECTLY; snapshot + restore so the winners-only
    # baseline does not leak into sibling dr_benchmark tests in the same process.
    env_snapshot = dict(os.environ)
    try:
        _set_min_passing_gate_b_env(monkeypatch)
        # ungated posture: layer ON, D3 PROMOTE gate OFF => REFUSED fail-closed by the :4693 preflight assert.
        monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
        monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "0")
        with pytest.raises(RuntimeError, match="PROMOTE"):
            gate_b.preflight_full_capability(offline=True)
    finally:
        set_max_cost_per_run(old_cap)
        monkeypatch.undo()
        os.environ.clear()
        os.environ.update(env_snapshot)


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
