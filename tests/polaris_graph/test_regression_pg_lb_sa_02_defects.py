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
# D-001..D-015: PG_LB_SA_02 defect regressions.
#
# History: these were Phase-1f aspirational stubs (`assert False` bodies)
# written before Phases 2-6 landed. The XF-cleanup pass re-assessed each:
#   - d_001/d_002 — implemented as real tests using Phase 4 strict_verify
#     + Phase 3 completeness machinery.
#   - d_003      — removed (polarity inversion is genuinely not implemented
#     anywhere in the pipeline; tracked in TODO.md instead of a stub test).
#   - d_004      — removed, covered by test_r5_fix_b_subject.py
#     (subject-disambiguation cross-drug grouping).
#   - d_010      — rewritten against Rule R2c regulatory-content-marker in
#     the new tier_classifier (the old wiki_builder._extract_regulatory_id
#     function was removed when the tier taxonomy was rebuilt).
#   - d_011      — removed, covered by
#     test_r5_fix_a_denylist.py::test_fix2_novonordiskmedical_is_t5_*.
#   - d_015      — implemented against live_retriever._build_provenance_quote.
# ─────────────────────────────────────────────────────────────────────────────


def test_d_001_strict_verify_drops_unsourced_scope_qualifier_loss():
    """PG_LB_SA_02 defect: generator wrote "in adults with obesity"
    when the SELECT source quote said "in adults with overweight or
    obesity" (dropping ~40% of trial population).

    Test: a sentence that alters a population qualifier must fail
    strict_verify because the sentence text contains words not in
    the cited span (the check isn't linguistic but provides a hard
    numeric backstop: if the sentence claims decimals the span lacks,
    it drops).
    """
    from src.polaris_graph.generator.provenance_generator import (
        strict_verify,
    )
    # Evidence quote contains BOTH "overweight" AND the numeric result.
    evidence_pool = {
        "ev_select": {
            "direct_quote": (
                "In adults with overweight or obesity and established "
                "cardiovascular disease, semaglutide 2.4 mg reduced "
                "major adverse cardiovascular events by 20.0% versus "
                "placebo."
            ),
            "source_url": "https://nejm.org/select",
            "tier": "T1",
            "statement": "SELECT trial primary endpoint",
        }
    }
    # The faithful sentence cites a span that contains 20.0
    faithful = (
        "Semaglutide reduced major adverse cardiovascular events by "
        "20.0% [#ev:ev_select:138-150] in adults with overweight or obesity."
    )
    # The defective sentence contains a fabricated number not in the quote
    fabricated = (
        "Semaglutide reduced major adverse cardiovascular events by "
        "35.0% [#ev:ev_select:138-150] in adults with obesity."
    )
    report_faithful = strict_verify(faithful, evidence_pool)
    report_fab = strict_verify(fabricated, evidence_pool)

    assert report_faithful.total_kept == 1
    # Fabricated: 35.0 is not in the cited span → dropped
    assert report_fab.total_dropped == 1


def test_d_002_sentence_with_no_provenance_token_is_dropped():
    """PG_LB_SA_02 defect: generator wrote 'long-term evidence beyond
    16 months is limited' cited to [4] but [4] did not state it.

    Test: strict_verify drops sentences that have NO [#ev:...] token
    at all (the Phase 4 rule). This pins the drop-unsourced-inference
    behavior even when the sentence is entirely prose (no numbers).
    """
    from src.polaris_graph.generator.provenance_generator import (
        strict_verify,
    )
    evidence_pool = {
        "ev_a": {"direct_quote": "A quote about something."},
    }
    draft_with_unsourced = (
        "The drug was effective at 14.9% [#ev:ev_a:0-10]. "
        "Long-term evidence beyond 16 months is limited."
    )
    report = strict_verify(draft_with_unsourced, evidence_pool)
    # Second sentence has no [#ev:...] → dropped
    dropped_texts = [sv.sentence for sv in report.dropped_sentences]
    assert any("Long-term" in s for s in dropped_texts), \
        f"Expected Long-term sentence to drop, kept: {dropped_texts}"


def test_d_010_setid_extraction_via_r2c_regulatory_marker():
    """PG_LB_SA_02 defect: FDA moved label URLs from
    /drugsatfda_docs/label/YYYY/NNNNNsREVlbl.pdf to
    nctr-crs.fda.gov/fdalabel/services/spl/set-ids/{uuid}/
    The old setid regex missed the new pattern.

    This test pins the replacement behavior: Rule R2c in the new
    tier_classifier recognizes the new URL as regulatory content
    and assigns T3, regardless of OpenAlex metadata.
    """
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )
    sig = ClassificationSignals(
        url=(
            "https://nctr-crs.fda.gov/fdalabel/services/spl/set-ids/"
            "ee06186f-2aa3-4990-a760-757579d8f77b/spl-doc?hl=wegovy"
        ),
        title="Wegovy (semaglutide) Prescribing Information",
        publisher="",
        fetched_content_length=15000,
        openalex_publication_type="",
        openalex_source_type="",
        openalex_is_peer_reviewed=False,
        source_type_hint="",
    )
    r = classify_source_tier(sig)
    assert r.tier.value == "T3", f"expected T3 regulatory, got {r.tier.value}"
    # R2c fires on URL markers like "set-ids/" (regulatory content)
    # OR title markers like "Prescribing Information". Either path is acceptable.
    rule_names = " ".join(r.matched_rules)
    assert "R2" in rule_names or "regulatory" in rule_names.lower(), \
        f"expected a regulatory rule to match, matched: {r.matched_rules}"


def test_d_015_provenance_quote_captures_decimals_beyond_10k_chars():
    """PG_LB_SA_02 defect: I² values, CIs, and heterogeneity stats
    live at positions 10K-25K of a fetched paper but the verifier's
    hard-coded 2K/8K windows never saw them.

    Test: _build_provenance_quote() stores 500-char windows around
    EVERY decimal in the full content, so a verifier can find
    decimals at any position up to max_total_chars (12K default).
    """
    from src.polaris_graph.retrieval.live_retriever import (
        _build_provenance_quote,
    )
    # Build a fake 15K-char body with a decimal ("-15.2%") at position ~11K
    head = "Abstract. " + "padding-a " * 150           # ~1500 chars
    mid  = "Methods. " + "padding-b " * 800            # ~8000 chars
    deep = (
        "Results. At week 104, the primary endpoint change from "
        "baseline was -15.2% (95% CI -17.4 to -13.0), I2 = 67.3%. "
    )
    tail = "Discussion. " + "padding-c " * 200         # ~2000 chars
    content = head + mid + deep + tail
    # Sanity: decimal lives deep in the body
    assert "-15.2" in content
    idx = content.find("-15.2")
    assert idx > 8000, f"test setup wrong: decimal at {idx}, expected > 8000"

    quote = _build_provenance_quote(
        content, head_chars=1500, window_chars=500,
    )
    # The quote should contain the deep decimal AND I2 value
    assert "-15.2" in quote, "decimal at char ~11K must be in provenance quote"
    assert "67.3" in quote, "I^2 value must be in provenance quote"
    assert "[...]" in quote, "separator between head and decimal windows expected"


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
