"""I-ready-006 (#1082) — query-complexity router (offline, no model, no spend).

A deterministic, FAIL-OPEN classifier right-sizes confidently-simple factual queries (lower fetch cap
+ a relaxed full adequacy profile) while a clinical / comparison / mechanism query is NEVER
under-served. Default OFF (PG_COMPLEXITY_ROUTING) → byte-identical. These tests lock the classifier
labels (incl. the multi-entity "Telus and Bell" case + compare/causal fail-open per Codex brief P2-4),
the full simple-adequacy profile (P2-1), the right-sizing behaviour, and the OFF-mode gating (P2-2).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes.complexity_router import (
    ComplexityDecision,
    classify_complexity,
)


# ── classifier: SIMPLE (right-sizeable factual lookups) ────────────────────────
@pytest.mark.parametrize("q", [
    "Telus and Bell stock price over the past 20 years",   # multi-entity factual (Codex P2-4)
    "What is the population of Canada?",
    "What was the GDP of Germany in 2023?",
    "Apple stock price since 2010",
    "What is the capital of France?",
])
def test_simple_factual_queries_classify_simple(q):
    d = classify_complexity(q)
    assert isinstance(d, ComplexityDecision)
    assert d.complexity == "simple", (q, d.reasons)
    assert d.confidence >= 0.70


@pytest.mark.parametrize("q", [
    "What is the capital of France?",
    "What is the population of Canada?",
])
def test_civic_queries_with_trailing_punctuation_reach_the_routing_gate(q):
    # Codex diff-gate iter-4 P2: a trailing "?" must not strip the entity below the 0.80 gate.
    d = classify_complexity(q)
    assert d.complexity == "simple"
    assert d.confidence >= 0.80


def test_telus_bell_is_high_confidence_simple():
    d = classify_complexity("Telus and Bell stock price over the past 20 years")
    assert d.complexity == "simple"
    assert d.confidence >= 0.80   # passes the default PG_COMPLEXITY_MIN_CONFIDENCE=0.80 gate
    assert "safe_factual_cue+named_entity" in d.reasons


# ── classifier: COMPLEX / fail-open (NEVER under-serve) ────────────────────────
@pytest.mark.parametrize("q", [
    "Compare the efficacy of tirzepatide versus semaglutide for type 2 diabetes",
    "Why does metformin reduce cardiovascular events?",
    "What is the mechanism of SGLT2 inhibitors?",
    "Systematic review of statins for primary prevention",
    "What is the recommended dose of warfarin in renal impairment?",
    "Tell me about diabetes",                 # ambiguous → fail open
    "Discuss the trade-offs of carbon pricing policy",
])
def test_complex_or_ambiguous_queries_fail_open_to_complex(q):
    d = classify_complexity(q)
    assert d.complexity == "complex", (q, d.reasons)


# ── clinical-safety guard: clinical/outcome/safety queries are NEVER simple (Codex diff-gate P1-1) ──
@pytest.mark.parametrize("q", [
    "What is the mortality rate of Semaglutide in diabetes?",          # Codex P1-1 probe
    "What is the incidence rate of Guillain-Barre after Shingrix?",    # Codex P1-1 probe
    "What is the 5-year survival rate of pancreatic cancer?",
    "How common are adverse events with tirzepatide?",
    "What is the prevalence of hypertension in adults?",
    "What is the case fatality rate of measles?",
    "What is the readmission rate after CABG?",
    # Codex diff-gate iter-2 reprobes — the denylist missed these; the safe-factual ALLOWLIST catches
    # them (no financial/civic cue ⇒ never simple), regardless of the disease name.
    "What is the death rate from COVID-19?",
    "What is the rate of GBS after Shingrix?",
    "What is the rate of Guillain-Barre after Shingrix?",
    "What is the fatality rate of Ebola?",
    # Codex diff-gate iter-3 reprobes — epidemiology / drug-utilization disguised as "population".
    "What is the population with long COVID in Canada?",
    "What is the population with obesity in Canada?",
    "What is the population taking statins in Canada?",
    "What is the population using Ozempic in Canada?",
    "What is the population of diabetics in the US?",
    # Codex diff-gate iter-4 reprobes — cohort-prevalence "population of <cohort> with <disease>"
    # (structural pattern; no disease name enumeration).
    "What is the population of children with asthma in the United States?",
    "What is the population of adults with COPD in the US?",
    "What is the population of people with migraine in the United Kingdom?",
    "What is the number of people taking statins in Canada?",
])
def test_clinical_outcome_safety_queries_are_complex(q):
    # A factual-RATE clinical/outcome/safety question must route complex — it must NEVER be right-sized
    # to the 1-source simple adequacy profile (lethal-class under-serving per §-1.1).
    d = classify_complexity(q)
    assert d.complexity == "complex", (q, d.reasons)


# ── due-diligence / analytical queries are NOT simple (Codex diff-gate iter-3 P1-2) ──────────────
@pytest.mark.parametrize("q", [
    "What are Apple revenue drivers and competitive risks for next 5 years",
    "What is Microsoft revenue exposure to OpenAI",
    "What is Apple profit risk from China tariffs",
    "What is the outlook for Tesla revenue going forward",
    # Codex diff-gate iter-4 reprobes — investment JUDGMENT, not a factual lookup.
    "Is Tesla stock overvalued?",
    "Is Tesla stock a buy?",
    "Should I buy Apple stock?",
])
def test_due_diligence_analytical_queries_are_complex(q):
    # revenue/profit are safe cues, but driver/risk/exposure/competitive/outlook/tariff intent makes
    # these multi-hop analysis, not a one-line factual lookup.
    assert classify_complexity(q).complexity == "complex", (q, classify_complexity(q).reasons)


def test_empty_question_fails_open():
    assert classify_complexity("").complexity == "complex"
    assert classify_complexity("   ").complexity == "complex"
    # a non-str input must NOT raise — fail open.
    assert classify_complexity(None).complexity == "complex"  # type: ignore[arg-type]


# ── CAP-ONLY (Codex diff-gate iter-5 §-1.2 rule 6): the adequacy gate is NOT relaxed ───────────
def test_router_does_not_relax_the_corpus_adequacy_gate():
    # A keyword classifier could not reliably exclude clinical cohort queries, so #1082 ships CAP-ONLY:
    # it never passes a relaxed adequacy override. A mis-classified clinical query therefore still hits
    # the FULL clinical adequacy bar -> aborts SAFELY instead of shipping a thin answer. The
    # adequacy-relaxation half is deferred to a follow-up. Lock that the override is NOT wired.
    import inspect

    import scripts.run_honest_sweep_r3 as sweep

    src = inspect.getsource(sweep)
    assert "_SIMPLE_ADEQUACY_THRESHOLDS" not in src   # the relaxed-profile constant is removed
    assert "override=(_SIMPLE_ADEQUACY" not in src    # no adequacy override is passed anywhere


# ── byte-identical OFF: the routing + manifest field are gated (Codex brief P2-2) ──────────────
def test_routing_and_manifest_field_are_gated_off_by_default():
    import inspect

    import scripts.run_honest_sweep_r3 as sweep

    src = inspect.getsource(sweep.run_one_query)
    # the router only runs when PG_COMPLEXITY_ROUTING is truthy.
    assert 'os.getenv("PG_COMPLEXITY_ROUTING", "0")' in src
    assert "if _complexity_routing_on:" in src
    # the manifest field is added ONLY when routing is on (no field when OFF → byte-identical).
    assert 'if _complexity_routing_on and _routing_decision is not None:' in src
    assert '"complexity_routing"' in src
    # the simple fetch cap only applies when simple_routed (cap-only right-sizing).
    assert 'PG_SIMPLE_FETCH_CAP' in src
    # FAIL-OPEN (Codex diff-gate iter-1 P2-1): the classifier + the env parses are inside a try/except
    # so a bad PG_COMPLEXITY_MIN_CONFIDENCE / PG_SIMPLE_FETCH_CAP value never aborts the run — it falls
    # back to the full path. Structural check that the guarded block has a fail-open except.
    routing_idx = src.find("if _complexity_routing_on:")
    cap_idx = src.find("# I-meta-005 Phase 1", routing_idx)   # the next block after the router
    block = src[routing_idx:cap_idx] if cap_idx > routing_idx else src[routing_idx:routing_idx + 2000]
    assert "try:" in block and "FAIL OPEN" in block.upper()
