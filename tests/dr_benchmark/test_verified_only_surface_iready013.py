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
    # _set_min_passing_gate_b_env applies the production slate, which mutates os.environ DIRECTLY (not via
    # monkeypatch). Snapshot + restore the whole environment so the winners-only baseline (e.g. the W4
    # PG_CLINICAL_PDF_EXTRACTOR=mineru25 pin) does not leak into sibling dr_benchmark tests in the same
    # process — the env-leak class this suite is otherwise prone to.
    env_snapshot = dict(os.environ)
    try:
        _set_min_passing_gate_b_env(monkeypatch)
        # offline=True: this is a no-GPU / no-spend unit test, so skip ONLY the WINNER-FIRES GPU
        # host-capability probes (W4 mineru25 torch.cuda, W5 reranker device) that would false-fail on a
        # CPU host. The NO-LOSER gate + the killed-loser REQUIRED_OFF check (which is what protects the
        # analyst-synthesis suppression) stay UNCONDITIONAL, so the perturbation below still binds.
        gate_b.preflight_full_capability(offline=True)

        # I-deepfix-001 (#1344): the legacy Analyst Synthesis layer is a killed un-span-verified loser —
        # PG_SWEEP_ANALYST_SYNTHESIS is in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS, so re-arming it trips
        # the generic NO-LOSER/REQUIRED_OFF gate. The message names the flag (the dedicated "Analyst
        # Synthesis" phrasing was consolidated into the generic killed-loser gate), so match the flag id.
        monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
        with pytest.raises(RuntimeError, match="PG_SWEEP_ANALYST_SYNTHESIS"):
            gate_b.preflight_full_capability(offline=True)
    finally:
        set_max_cost_per_run(old_cap)
        # I-deepfix-001 (#1344) Codex P1: undo monkeypatch FIRST — _set_min_passing_gate_b_env recorded
        # POST-slate env values via monkeypatch, and pytest's monkeypatch teardown runs AFTER this finally;
        # without undo() it would re-inject them, defeating the snapshot restore. The snapshot restore then
        # handles the slate's DIRECT os.environ mutations (untracked by monkeypatch). Both are required.
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
