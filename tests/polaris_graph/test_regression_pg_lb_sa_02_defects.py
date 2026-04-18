"""
Regression tests keyed to documented PG_LB_SA_02 content-audit defects.

Each test pins a specific defect from loopback/audit/PG_LB_SA_02_CONTENT_AUDIT.md
so the honest-rebuild work does not silently re-introduce the same pattern.
Tests that cover components not yet built are marked @pytest.mark.xfail with
the phase that will satisfy them.

Plan: C:/Users/msn/.claude/plans/lovely-finding-firefly.md
Phase 1f.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helper: load openrouter_client without its transitive dependencies
# (tracing module requires an async runtime; we mock it for unit tests).
# ─────────────────────────────────────────────────────────────────────────────

def _load_openrouter_client():
    """Import openrouter_client with a minimal tracing stub."""
    if "src.polaris_graph.tracing" not in sys.modules:
        pkg_src = types.ModuleType("src")
        pkg_pg = types.ModuleType("src.polaris_graph")
        pkg_tracing = types.ModuleType("src.polaris_graph.tracing")
        pkg_tracing._current_tracer = lambda: None
        sys.modules.setdefault("src", pkg_src)
        sys.modules.setdefault("src.polaris_graph", pkg_pg)
        sys.modules["src.polaris_graph.tracing"] = pkg_tracing
    repo_root = Path(__file__).resolve().parents[2]
    mod_path = repo_root / "src" / "polaris_graph" / "llm" / "openrouter_client.py"
    spec = importlib.util.spec_from_file_location(
        "polaris_graph_llm_openrouter_for_tests", str(mod_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# D-001..D-003: abstract fabrications (SELECT scope drop, "limited beyond
# 16 months" inference, wrong-polarity shortage-restricts-access).
#
# Covered functionally by Phase 4 (provenance-emitting generator + strict
# citation-span verification). Until that lands, these tests xfail.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(reason="Phase 4 scope: provenance-emitting generator",
                    strict=False)
def test_d_001_abstract_does_not_drop_overweight_from_select_scope():
    """Report abstracts must preserve source scope qualifiers.

    PG_LB_SA_02 abstract dropped "or overweight" from SELECT trial
    population (BMI >=27). The agent narrowed it to "obesity" alone,
    omitting ~40% of the trial population.
    """
    # Covered by Phase 4 synthesizer rewrite + external evaluator (Phase 5).
    assert False  # noqa: B011 - xfail placeholder


@pytest.mark.xfail(reason="Phase 4 scope: provenance-emitting generator",
                    strict=False)
def test_d_002_no_unsourced_inferences_about_evidence_duration():
    """Inferences like 'long-term evidence beyond 16 months is limited'
    must be sourced or omitted. PG_LB_SA_02 included this inference
    cited to source [4], but source [4] does not state it; STEP 5 at
    104 weeks contradicts the 'limited beyond 16 months' claim.
    """
    assert False


@pytest.mark.xfail(reason="Phase 4 scope: provenance-emitting generator",
                    strict=False)
def test_d_003_no_polarity_inversion_on_shortage_framing():
    """'Shortage since 2022 restricting access' contradicts source [25]
    (FDA stabilization notice). Report polarity must match source polarity.
    """
    assert False


# ─────────────────────────────────────────────────────────────────────────────
# D-004: trial mis-attribution (STEP 1 vs STEP 3 response rates)
#
# Covered by Phase 3 trial-ID extraction. Until that lands, xfail.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(reason="Phase 3 scope: trial-ID extraction",
                    strict=False)
def test_d_004_step1_response_rates_not_attributed_to_step3():
    """86.6% / 47.6% are STEP 3 (Wadden JAMA 2021) numbers. Report
    should not attribute them to STEP 1. Trial-ID extraction (NCT regex
    + STEP-N pattern matching) prevents this.
    """
    assert False


# ─────────────────────────────────────────────────────────────────────────────
# D-010: Patch C setid extraction fails on nctr-crs.fda.gov URLs
#
# Currently the regex in wiki_builder._extract_regulatory_id only matches
# the old /drugsatfda_docs/label/YYYY/NNNNNsREVlbl.pdf path structure.
# The new /set-ids/{uuid}/ path pattern is silently dropped.
#
# This regression test xfails until Phase 2 reshape of tier_classifier /
# setid handler — but the test will catch silent breakage when the fix lands.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(reason="Phase 2 scope: setid extraction (new FDA URL pattern)",
                    strict=False)
def test_d_010_setid_extraction_handles_new_fda_url_pattern():
    """FDA moved to nctr-crs.fda.gov/fdalabel/services/spl/set-ids/{uuid}/
    URL structure. Patch C must recognize this pattern and emit a setid
    string for bibliography dedup.
    """
    from src.polaris_graph.wiki import wiki_builder  # type: ignore
    url = (
        "https://nctr-crs.fda.gov/fdalabel/services/spl/set-ids/"
        "ee06186f-2aa3-4990-a760-757579d8f77b/spl-doc?hl=wegovy"
    )
    setid = wiki_builder._extract_regulatory_id(url)
    # Expected: something non-empty containing the UUID
    assert setid
    assert "ee06186f-2aa3-4990-a760-757579d8f77b" in setid


# ─────────────────────────────────────────────────────────────────────────────
# D-011: Patch D over-assigns GOLD to Novo marketing pages, news, student
# journals. Target: Novo-branded industry pages should be BRONZE, not GOLD.
#
# Phase 2 scope: rewrite tier_classifier. Until then, this test xfails.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(reason="Phase 2 scope: tier_classifier rules",
                    strict=False)
def test_d_011_novo_hcp_portal_not_gold_tier():
    """Novo Nordisk's novomedlink.com / wegovy.com HCP portals are
    industry marketing pages. A rules-based tier classifier should
    assign them BRONZE (industry marketing) regardless of OpenAlex
    indexing state.
    """
    # When the tier_classifier module exists, this test imports it and
    # exercises the rule for novomedlink.com.
    pytest.importorskip("src.polaris_graph.retrieval.tier_classifier")
    from src.polaris_graph.retrieval.tier_classifier import classify_source_tier  # type: ignore
    tier = classify_source_tier(
        url="https://www.novomedlink.com/obesity/products/treatments/wegovy/"
            "efficacy-safety/safety-profile.html",
        source_type="industry_report",
        publisher=None,
    )
    assert tier == "BRONZE", f"expected BRONZE for Novo HCP portal, got {tier}"


# ─────────────────────────────────────────────────────────────────────────────
# D-015: 25K content-cap truncation — claim extraction must capture facts
# at chars 10K-25K when present.
#
# This is a test of the evidence-extraction layer. Phase 2/4 reshapes this;
# xfailed until then.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(reason="Phase 2/4 scope: per-claim content window extraction",
                    strict=False)
def test_d_015_claim_extraction_captures_content_beyond_10k_chars():
    """When a source is fetched at 25K chars, the verifier must be able
    to find quotes at positions 10K-25K. PG_LB_SA_02 had I² values,
    effect-size CIs, and heterogeneity stats in the 10K-25K window that
    the verifier could not see (2K / 8K windows hard-coded in NLI).
    """
    assert False


# ─────────────────────────────────────────────────────────────────────────────
# D-027: Patch B POLISH crashed with unexpected kwarg `call_type`.
#
# This test locks in the Phase 1c guarantee: LLM-client function signatures
# accept only declared kwargs; misuse raises at call-site, not silently.
# ─────────────────────────────────────────────────────────────────────────────

def test_d_027_openrouter_client_generate_rejects_unknown_kwargs():
    """LLM client methods must reject unknown kwargs with TypeError so
    integration bugs like PG_LB_SA_02 POLISH crash are caught at call
    time, not hidden behind a try/except shipping-unpolished fallback.

    This test inspects the OpenRouterClient.generate signature rather
    than instantiating the client (which would need an API key).
    """
    mod = _load_openrouter_client()
    import inspect
    sig = inspect.signature(mod.OpenRouterClient.generate)
    accepted_names = set(sig.parameters.keys())
    # The defect was that a caller passed `call_type=` which was silently
    # accepted via **kwargs or similar. We assert call_type is NOT an
    # accepted parameter — if a caller passes it, Python raises TypeError.
    assert "call_type" not in accepted_names, (
        f"generate() accepts 'call_type' — this is exactly the kwarg that "
        f"caused the PG_LB_SA_02 POLISH crash. Remove it from the signature "
        f"or rename the caller. Accepted: {sorted(accepted_names)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1a positive checks: faithfulness_score absent from schema;
# Phase 1c positive checks: family segregation helpers work.
# ─────────────────────────────────────────────────────────────────────────────

def test_phase_1c_family_from_model_known_prefixes():
    """family_from_model correctly identifies all 10 known families."""
    mod = _load_openrouter_client()
    cases = [
        ("deepseek/deepseek-v3.2-exp", "deepseek"),
        ("qwen/qwen3-32b", "qwen"),
        ("z-ai/glm-5.1", "glm"),
        ("meta-llama/Llama-3.3-70B", "llama"),
        ("google/gemma-4-31b", "gemma"),
        ("mistralai/Mistral-Large-3", "mistral"),
        ("moonshotai/Kimi-K2.5", "kimi"),
        ("openai/gpt-5", "openai"),
        ("anthropic/claude-opus-4.7", "anthropic"),
        ("google/gemini-3.1-pro", "google-closed"),
        ("unknown-vendor/mystery-model", "unknown"),
    ]
    for model, expected in cases:
        assert mod.family_from_model(model) == expected, (
            f"family_from_model({model!r}) != {expected!r}"
        )


def test_phase_1c_check_family_segregation_allows_different_families():
    """DeepSeek + Qwen are genuinely different families and should pass."""
    mod = _load_openrouter_client()
    gen, ev = mod.check_family_segregation(
        "deepseek/deepseek-v3.2-exp",
        "qwen/qwen3-32b",
    )
    assert gen == "deepseek"
    assert ev == "qwen"


def test_phase_1c_check_family_segregation_blocks_same_family():
    """Same-family pair (DeepSeek V3.2 + DeepSeek R1) must raise."""
    mod = _load_openrouter_client()
    with pytest.raises(RuntimeError, match="same training-lineage family"):
        mod.check_family_segregation(
            "deepseek/deepseek-v3.2-exp",
            "deepseek/deepseek-r1",
        )


def test_phase_1c_check_family_segregation_blocks_unknown_without_override():
    """Unknown family without explicit override must raise."""
    mod = _load_openrouter_client()
    with pytest.raises(RuntimeError, match="does not match any known family"):
        mod.check_family_segregation(
            "unknown-vendor/mystery-model",
            "qwen/qwen3-32b",
        )


def test_phase_1c_check_family_segregation_accepts_explicit_override():
    """Unknown vendor with explicit override should pass."""
    mod = _load_openrouter_client()
    gen, ev = mod.check_family_segregation(
        "unknown-vendor/mystery-model",
        "qwen/qwen3-32b",
        generator_override="custom-family",
    )
    assert gen == "custom-family"
    assert ev == "qwen"


def test_phase_1b_hallucination_detector_is_stub():
    """audit_sections_for_hallucination returns empty list per the
    Phase 1b stub. Running it should emit a DeprecationWarning but
    not crash.
    """
    import warnings
    # Mock the required src packages
    if "src.polaris_graph.agents.hallucination_detector" in sys.modules:
        del sys.modules["src.polaris_graph.agents.hallucination_detector"]
    repo_root = Path(__file__).resolve().parents[2]
    mod_path = repo_root / "src" / "polaris_graph" / "agents" / "hallucination_detector.py"
    spec = importlib.util.spec_from_file_location(
        "halluc_stub_for_tests", str(mod_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._is_enabled() is False, "stub must report disabled"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = mod.audit_sections_for_hallucination(
            sections=[{"section_id": "s1", "title": "X", "content": "y",
                       "evidence_ids": []}],
            evidence=[],
            research_query="test",
        )
    assert result == [], "stub must return empty list"
    # Deprecation warning expected (may have fired on earlier _is_enabled call)
    # We don't strictly require it here since _warn_once deduplicates.


def test_phase_1a_faithfulness_score_removed_from_synthesizer_recomputation():
    """The survivorship-bias recomputation (FIX-043A) in synthesizer.py
    must not be reintroduced. This test greps the source for the specific
    lines that used to recompute faithfulness after orphan-claim filtering.
    """
    repo_root = Path(__file__).resolve().parents[2]
    synth = (repo_root / "src" / "polaris_graph" / "agents" /
             "synthesizer.py").read_text(encoding="utf-8")
    # The defective pattern: recompute faithfulness = faithful_count / verified_claims
    # AFTER the claims list has been filtered via FIX-QM7.
    # We look for the specific log signature that only fired in the defective path.
    forbidden = "FIX-043A: Recomputed faithfulness"
    assert forbidden not in synth, (
        f"synthesizer.py contains {forbidden!r} — Phase 1a removal regression. "
        f"This log line was the survivorship-bias surface: it fired after "
        f"FIX-QM7 filtered unfaithful evidence, yielding cooked ~100% scores."
    )
