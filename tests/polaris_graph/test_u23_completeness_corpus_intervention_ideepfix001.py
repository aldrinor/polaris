"""U23 (I-deepfix-001) — completeness corpus-fallback intervention recognition.

THE BUG (autopsy U23, drb_75 metal-ions/CVD run): the completeness gate marked
EVERY drug/intervention topic non-applicable and reported a vacuous "1/1 = 100%
complete". The question named a CONDITION ("metal ions and cardiovascular
disease") but no specific intervention, so the BUG-7 question-only recognizer
"found no known intervention" — even though the retrieved CORPUS contained an
EDTA chelation-therapy RCT and a magnesium meta-analysis. Two defects combined:

  1. "chelation" was not a recognised intervention term at all.
  2. the recognizer consulted the QUESTION only, never the corpus.

Result: the efficacy / safety / regulatory / interaction slots for the corpus
intervention were NEVER MEASURED, and the gate passed vacuously.

THE FIX (two parts):
  (a) config: `chelation` / `chelation therapy` added to the scope-gate
      recognizer's `device_procedure_terms`.
  (b) completeness_checker: when the QUESTION yields a CONFIDENT negative,
      `_topic_applies` falls back to the SAME recognizer on the CORPUS. A corpus
      hit makes NON-critical drug topics applicable (measured, gaps surfaced). The
      CRITICAL contraindications topic stays on the disclose path for a corpus-only
      hit — no spurious `abort_critical_topic_uncovered` HOLD is reintroduced.

FAITHFULNESS: this only refines the completeness DENOMINATOR (applicability
precision). It never touches strict_verify / NLI / the 4-role D8 audit /
span-grounding, never drops a verified claim, adds no cap/floor, and adds NO new
hold path. Measuring MORE topics (surfacing gaps that were silently vacuous)
STRENGTHENS the gate.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes import completeness_checker as cc
from src.polaris_graph.nodes.completeness_checker import check_completeness
from src.polaris_graph.nodes.scope_gate import (
    _intervention_present,
    _reset_intervention_cache,
)

# The real drb_75 research question: names a condition + generic "interventions"
# / "supplementation" but NO specific drug/intervention token.
_METAL_ION_QUESTION = (
    "Could therapeutic interventions aimed at modulating plasma metal ion "
    "concentrations represent effective preventive or therapeutic strategies "
    "against cardiovascular diseases? What types of interventions such as "
    "supplementation have been proposed, and is there clinical evidence "
    "supporting their feasibility and efficacy?"
)

# Corpus that names the intervention (chelation) only in the evidence, mirroring
# the real drb_75 corpus (a chelation RCT + a magnesium meta-analysis).
_CHELATION_CORPUS = [
    {"direct_quote": "The TACT randomized controlled trial evaluated EDTA "
                     "chelation therapy in patients with prior myocardial "
                     "infarction and reported a reduction in cardiovascular "
                     "events.", "statement": "chelation rct"},
    {"direct_quote": "A meta-analysis of magnesium supplementation trials "
                     "assessed effects on blood pressure and mortality.",
     "statement": "magnesium meta-analysis"},
]

# BUG-7 regression control: a genuinely non-intervention question whose evidence
# names NO recognised intervention. The corpus fallback must find nothing here so
# the drug topics stay non-applicable (no BUG-7 regression).
_MICROBIOTA_QUESTION = (
    "How does the gut microbiota influence host metabolism in healthy adults?"
)
_MICROBIOTA_EVIDENCE = [
    {"direct_quote": "Gut microbiota produce short-chain fatty acids that "
                     "modulate the glycemic response and weight regulation.",
     "statement": "microbiome metabolism"},
]

_DRUG_TOPICS = (
    "efficacy_primary", "safety_adverse_events", "contraindications",
    "class_specific_risks_glp1", "regulatory_status", "drug_interactions",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Default-ON behaviour for both gates; reset the recognizer cache so the
    config edit (chelation) is picked up and env edits never leak across tests."""
    monkeypatch.delenv("PG_COMPLETENESS_DRUG_DETECTOR", raising=False)
    monkeypatch.delenv("PG_COMPLETENESS_CORPUS_INTERVENTION", raising=False)
    _reset_intervention_cache()
    yield
    _reset_intervention_cache()


def _applicable_ids(report) -> list[str]:
    return [tc.topic.id for tc in report.topics if tc.applies]


# ──────────────────────────────────────────────────────────────────────────────
# (a) config: chelation is now a recognised intervention token
# ──────────────────────────────────────────────────────────────────────────────

def test_chelation_is_recognised_as_an_intervention():
    """The recognizer must now return a token for chelation / chelation therapy —
    before the config edit it returned None (part 1 of the U23 root cause)."""
    assert _intervention_present("EDTA chelation therapy for cardiovascular disease")
    assert _intervention_present("chelation reduced metal ion burden")


# ──────────────────────────────────────────────────────────────────────────────
# (b) corpus fallback: the U23 case is no longer all-non-applicable (RED->GREEN)
# ──────────────────────────────────────────────────────────────────────────────

def test_corpus_intervention_makes_drug_topics_applicable():
    """The core U23 fix: with the intervention named only in the CORPUS, the
    non-critical drug topics become APPLICABLE (measured), so the report is no
    longer a vacuous all-non-applicable 100% pass. RED before the fix (only
    population_subgroups applied), GREEN after."""
    report = check_completeness(
        domain="clinical",
        research_question=_METAL_ION_QUESTION,
        evidence_rows=_CHELATION_CORPUS,
    )
    applicable = _applicable_ids(report)
    # These become applicable ONLY via the corpus fallback (no applies_if; the
    # question names no intervention).
    assert "efficacy_primary" in applicable
    assert "safety_adverse_events" in applicable
    assert "regulatory_status" in applicable
    # More than the single non-drug topic is now evaluated (was 1/7).
    drug_applicable = [t for t in applicable if t in _DRUG_TOPICS]
    assert len(drug_applicable) >= 3, applicable


def test_glp1_class_topic_stays_off_for_corpus_without_class_anchor():
    """The GLP-1 class-specific topic must NOT flip on: its applies_if class
    anchors (glp-1/incretin/...) appear in neither the question nor the chelation
    corpus, so its class restriction still holds even under the corpus fallback."""
    report = check_completeness(
        domain="clinical",
        research_question=_METAL_ION_QUESTION,
        evidence_rows=_CHELATION_CORPUS,
    )
    assert "class_specific_risks_glp1" not in _applicable_ids(report)


def test_critical_contraindications_disclosed_not_held_on_corpus_only():
    """Clinical-safety guard: a corpus-ONLY intervention must NOT force the
    CRITICAL contraindications topic applicable (that would reintroduce a spurious
    abort_critical_topic_uncovered HOLD). It stays non-applicable AND is DISCLOSED
    for manual review."""
    report = check_completeness(
        domain="clinical",
        research_question=_METAL_ION_QUESTION,
        evidence_rows=_CHELATION_CORPUS,
    )
    assert "contraindications" not in _applicable_ids(report)
    # No new hold path.
    assert report.uncovered_critical_topic_ids() == []
    # The corpus intervention is surfaced, not silently dropped.
    joined = " ".join(report.notes).lower()
    assert "corpus" in joined and "chelation" in joined


# ──────────────────────────────────────────────────────────────────────────────
# Regression: BUG-7 non-drug question with no corpus intervention stays clean
# ──────────────────────────────────────────────────────────────────────────────

def test_non_drug_question_no_corpus_intervention_stays_non_applicable():
    """A genuinely non-intervention question whose corpus names NO recognised
    intervention must keep ALL drug topics non-applicable — the corpus fallback
    finds nothing, so the BUG-7 guarantee is preserved (no false positives)."""
    report = check_completeness(
        domain="clinical",
        research_question=_MICROBIOTA_QUESTION,
        evidence_rows=_MICROBIOTA_EVIDENCE,
    )
    applicable = _applicable_ids(report)
    for drug_topic in _DRUG_TOPICS:
        assert drug_topic not in applicable, (drug_topic, applicable)
    assert report.uncovered_critical_topic_ids() == []


# ──────────────────────────────────────────────────────────────────────────────
# Kill-switch OFF reverts to the pre-U23 question-only behaviour (byte-identical)
# ──────────────────────────────────────────────────────────────────────────────

def test_kill_switch_off_reverts_to_question_only(monkeypatch):
    """With PG_COMPLETENESS_CORPUS_INTERVENTION=0 the corpus fallback is disabled:
    the U23 case returns to the pre-fix all-non-applicable behaviour (only the
    non-drug population_subgroups topic applies), documenting the escape hatch."""
    monkeypatch.setenv("PG_COMPLETENESS_CORPUS_INTERVENTION", "0")
    report = check_completeness(
        domain="clinical",
        research_question=_METAL_ION_QUESTION,
        evidence_rows=_CHELATION_CORPUS,
    )
    applicable = _applicable_ids(report)
    for drug_topic in _DRUG_TOPICS:
        assert drug_topic not in applicable, (drug_topic, applicable)
