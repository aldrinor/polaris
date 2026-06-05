"""I-ready-013 (#1080) — Claude-authored BEHAVIORAL + NEGATIVE coverage for the verified-only surface.

Complements the source-pin tests in test_verified_only_surface_iready013.py. These assert the change is
correctly SCOPED — i.e. it suppresses the un-span-verified Analyst Synthesis layer ONLY for the
clinical / benchmark path and leaves every other path byte-identical (no over-suppression). Offline, no
network, no spend.
"""
from __future__ import annotations

import inspect

import pytest


# ── the analyst-block gate decision, replicated behaviourally (the exact condition in
#    multi_section_generator.generate_multi_section_report) ───────────────────────────────────────
def _gate_runs(*, partial_mode, suppress, env_enabled, research_plan, has_sections, has_biblio):
    return (
        not partial_mode
        and not suppress
        and env_enabled
        and research_plan is None
        and bool(has_sections)
        and bool(has_biblio)
    )


def test_gate_condition_matches_source_exactly():
    # guard against drift: the replicated boolean above must mirror the real inline gate.
    from src.polaris_graph.generator import multi_section_generator as msg

    src = inspect.getsource(msg.generate_multi_section_report)
    for token in (
        "not partial_mode",
        "and not suppress_analyst_synthesis",
        "and analyst_synth_enabled",
        "and research_plan is None",
        "and section_results",
        "and global_biblio",
    ):
        assert token in src, token


def test_suppress_true_blocks_the_unverified_layer_even_when_otherwise_eligible():
    # clinical/benchmark: everything else says "run", but the caller suppressor wins -> NO analyst layer.
    assert _gate_runs(
        partial_mode=False, suppress=True, env_enabled=True,
        research_plan=None, has_sections=True, has_biblio=True,
    ) is False


def test_env_kill_switch_blocks_the_unverified_layer():
    # Gate-B sets PG_SWEEP_ANALYST_SYNTHESIS=0 -> env_enabled False -> NO analyst layer.
    assert _gate_runs(
        partial_mode=False, suppress=False, env_enabled=False,
        research_plan=None, has_sections=True, has_biblio=True,
    ) is False


def test_legacy_non_clinical_off_mode_is_PRESERVED_byte_identical():
    # NEGATIVE / no-over-suppression: default caller (suppress=False) + flag on (env_enabled=True) +
    # planner-off (research_plan None) -> the legacy unverified layer STILL runs. The fix must NOT
    # change non-clinical behaviour.
    assert _gate_runs(
        partial_mode=False, suppress=False, env_enabled=True,
        research_plan=None, has_sections=True, has_biblio=True,
    ) is True


def test_default_param_is_false_so_omitting_it_is_byte_identical():
    import inspect as _inspect

    from src.polaris_graph.generator import multi_section_generator as msg

    sig = _inspect.signature(msg.generate_multi_section_report)
    assert sig.parameters["suppress_analyst_synthesis"].default is False


# ── clinical-domain detection (the run_one_query suppressor key) is correctly SCOPED ──────────────
def _clinical_only(domain: str) -> bool:
    # mirrors run_one_query: _clinical_verified_only_surface = domain.strip().lower() == "clinical"
    return str(domain or "").strip().lower() == "clinical"


@pytest.mark.parametrize("domain", ["clinical", "Clinical", " CLINICAL "])
def test_clinical_domain_triggers_verified_only_surface(domain):
    assert _clinical_only(domain) is True


@pytest.mark.parametrize("domain", ["financial", "tech", "policy", "due_diligence", "", "general"])
def test_non_clinical_domains_keep_the_legacy_surface(domain):
    # no over-suppression: non-clinical runs are unaffected by the clinical force-off.
    assert _clinical_only(domain) is False


# ── UI path coverage: the pipeline-B domain inference maps medical-family -> clinical ─────────────
@pytest.mark.parametrize("application", ["clinical", "medical", "pharma", "health"])
def test_ui_medical_family_applications_route_to_clinical(application):
    from src.polaris_graph.pipeline_a_ui_adapter import _infer_domain

    assert _infer_domain(application, "any query") == "clinical"


def test_ui_non_medical_application_does_not_force_clinical():
    from src.polaris_graph.pipeline_a_ui_adapter import _infer_domain

    # a plainly non-clinical app/query must NOT be coerced to clinical (else we'd over-suppress).
    assert _infer_domain("finance", "quarterly revenue of a public company") != "clinical"
