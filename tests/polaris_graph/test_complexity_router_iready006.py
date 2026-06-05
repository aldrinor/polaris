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


def test_telus_bell_is_high_confidence_simple():
    d = classify_complexity("Telus and Bell stock price over the past 20 years")
    assert d.complexity == "simple"
    assert d.confidence >= 0.80   # passes the default PG_COMPLEXITY_MIN_CONFIDENCE=0.80 gate
    assert "factual_cue+named_entity" in d.reasons


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
])
def test_clinical_outcome_safety_queries_are_complex(q):
    # A factual-RATE clinical/outcome/safety question must route complex — it must NEVER be right-sized
    # to the 1-source simple adequacy profile (lethal-class under-serving per §-1.1).
    d = classify_complexity(q)
    assert d.complexity == "complex", (q, d.reasons)


def test_empty_question_fails_open():
    assert classify_complexity("").complexity == "complex"
    assert classify_complexity("   ").complexity == "complex"
    # a non-str input must NOT raise — fail open.
    assert classify_complexity(None).complexity == "complex"  # type: ignore[arg-type]


# ── simple adequacy profile: FULL profile (Codex brief P2-1) ───────────────────
def test_simple_adequacy_is_a_full_profile():
    from scripts.run_honest_sweep_r3 import _SIMPLE_ADEQUACY_THRESHOLDS as s

    # every threshold is relaxed (not just min_total_sources/min_t1_count) so a single authoritative
    # T5/T6 factual source is enough — no clinical 8-source / 2-T1 / low-industry-fraction demand.
    assert s.min_total_sources == 1
    assert s.min_t1_count == 0
    assert s.min_t1_plus_t2 == 0
    assert s.min_t1_plus_t2_plus_t3 == 0
    assert s.min_t3_plus_t4_plus_t6 == 0
    assert s.min_evidence_rows == 1
    assert s.max_t5_plus_t6_fraction == 1.0    # T5/T6 industry/financial sources are fine for a fact
    assert s.max_t7_fraction == 0.50           # the stub guard is kept


# ── right-sizing behaviour: a 1-source factual corpus is ADEQUATE under the simple profile ─────
def test_simple_profile_makes_a_thin_factual_corpus_adequate():
    from src.polaris_graph.nodes.corpus_adequacy_gate import assess_corpus_adequacy
    from scripts.run_honest_sweep_r3 import _SIMPLE_ADEQUACY_THRESHOLDS

    # AdequacyDecision is a Literal["proceed","expand","abort"] (string), not an Enum.
    # one authoritative financial/data source (T5), one evidence row — a stock-price fact.
    tier_counts = {"T5": 1}
    # clinical default thresholds → NOT a proceed (8 sources / 2 T1 demanded).
    clinical = assess_corpus_adequacy(
        tier_counts=tier_counts, evidence_row_count=1, domain="clinical", protocol=None,
    )
    assert clinical.decision != "proceed"
    # the simple override → proceed on the same thin corpus (right-sized).
    simple = assess_corpus_adequacy(
        tier_counts=tier_counts, evidence_row_count=1, domain="clinical", protocol=None,
        override=_SIMPLE_ADEQUACY_THRESHOLDS,
    )
    assert simple.decision == "proceed"


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
    # the adequacy override is gated on the confident-simple decision (never the full path).
    assert "override=(_SIMPLE_ADEQUACY_THRESHOLDS if _simple_routed else None)" in src
    # the simple fetch cap only applies when simple_routed.
    assert 'PG_SIMPLE_FETCH_CAP' in src
    # FAIL-OPEN (Codex diff-gate iter-1 P2-1): the classifier + the env parses are inside a try/except
    # so a bad PG_COMPLEXITY_MIN_CONFIDENCE / PG_SIMPLE_FETCH_CAP value never aborts the run — it falls
    # back to the full path. Structural check that the guarded block has a fail-open except.
    routing_idx = src.find("if _complexity_routing_on:")
    cap_idx = src.find("# I-meta-005 Phase 1", routing_idx)   # the next block after the router
    block = src[routing_idx:cap_idx] if cap_idx > routing_idx else src[routing_idx:routing_idx + 2000]
    assert "try:" in block and "FAIL OPEN" in block.upper()
