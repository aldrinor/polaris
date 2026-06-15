"""BUG-7 (I-arch-006, #1262) — drug/intervention completeness applicability.

THE BUG (clinical-safety-critical): the GLP-1 / drug-pharmacology completeness
checklist (HbA1c / pancreatitis / thyroid / gallbladder efficacy + safety, and
the ``critical: true`` ``contraindications`` topic) was applied to NON-drug
clinical questions (gut-microbiota, Parkinson's, metal-ions) purely because they
route ``domain="clinical"``. ``completeness_checker._topic_applies`` only did a
STATIC substring match of a topic's ``applies_if`` terms against the question OR
the evidence blob, and a topic with no ``applies_if`` (the CRITICAL
``contraindications`` topic) applied to EVERY clinical question. Result: a false
"covered" inflation AND a spurious ``abort_critical_topic_uncovered`` hold (or, if
incidental evidence mentioned a drug word, a falsely-covered critical topic) on
questions with no drug at all. A false-negative on applicability for a CRITICAL
topic silently disables a real safety abort — that is the lethal failure mode.

THE FIX: a checklist topic flagged ``requires_drug_intervention: true`` becomes
applicable only when the QUESTION is actually about a drug/intervention, decided
by the SAME robust config-driven recognizer the scope gate uses
(``scope_gate._intervention_present`` = canonical drug names + WHO/USAN INN-stem
recognition) OR one of the topic's own ``applies_if`` CLASS anchors in the
question. On recognizer-unavailability a CRITICAL topic FAILS CLOSED (stays
applicable + discloses) so a real safety abort is never silently disabled.

FAITHFULNESS: applicability only refines the completeness DENOMINATOR (an
applicability-precision / input-hygiene change). It never touches strict_verify /
NLI / the 4-role D8 audit / span-grounding, never drops a verified claim, and on
ambiguity errs toward keeping a critical safety topic active. Removing a FALSE
applicability is not a weakening — the GLP-1 drug checklist genuinely does not
apply to a gut-microbiota question.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes import completeness_checker as cc
from src.polaris_graph.nodes.completeness_checker import (
    ChecklistTopic,
    check_completeness,
    load_checklist,
)
from src.polaris_graph.nodes.scope_gate import _reset_intervention_cache


# A GLP-1 drug question whose evidence has efficacy/safety but NO contraindication
# coverage (so the critical topic is APPLICABLE and UNCOVERED).
_GLP1_DRUG_QUESTION = (
    "What is the efficacy and safety of semaglutide for weight loss in adults "
    "with obesity?"
)
_GLP1_EVIDENCE = [
    {"direct_quote": "Semaglutide 2.4 mg reduced body weight by 14.9% versus "
                     "placebo over 68 weeks.", "statement": "efficacy"},
    {"direct_quote": "Nausea and vomiting were the most common adverse events "
                     "leading to discontinuation.", "statement": "safety"},
]

# Two NON-drug clinical questions. Their evidence even MENTIONS drug-ish words
# (glycemic, therapy) to prove the fix anchors on the QUESTION, not incidental
# evidence text.
_MICROBIOTA_QUESTION = (
    "How does the gut microbiota influence host metabolism in healthy adults?"
)
_MICROBIOTA_EVIDENCE = [
    {"direct_quote": "Gut microbiota produce short-chain fatty acids that "
                     "modulate the glycemic response and weight regulation.",
     "statement": "microbiome metabolism"},
]
_PARKINSON_QUESTION = (
    "What is the role of alpha-synuclein aggregation in Parkinson disease "
    "progression?"
)
_PARKINSON_EVIDENCE = [
    {"direct_quote": "Alpha-synuclein aggregates impair mitochondrial function "
                     "in dopaminergic neurons; non-pharmacological therapy is "
                     "under study.", "statement": "pd pathology"},
]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Drop the kill-switch (default-ON behaviour) and reset the recognizer
    cache around each test so env edits never leak across tests."""
    monkeypatch.delenv("PG_COMPLETENESS_DRUG_DETECTOR", raising=False)
    _reset_intervention_cache()
    yield
    _reset_intervention_cache()


def _applicable_ids(report) -> list[str]:
    return [tc.topic.id for tc in report.topics if tc.applies]


def _critical_applicable_ids(report) -> list[str]:
    return [
        tc.topic.id for tc in report.topics
        if tc.applies and getattr(tc.topic, "critical", False)
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Checklist metadata wiring
# ──────────────────────────────────────────────────────────────────────────────

def test_yaml_marks_drug_topics_requires_intervention():
    """The clinical checklist marks the drug-pharmacology topics — including the
    CRITICAL contraindications topic — with requires_drug_intervention=true, and
    leaves the general population-subgroups topic UNmarked (so it still applies
    to non-drug clinical questions; adequacy elsewhere unchanged)."""
    topics = {t.id: t for t in load_checklist("clinical")}
    assert topics["contraindications"].requires_drug_intervention is True
    assert topics["contraindications"].critical is True
    for tid in (
        "efficacy_primary", "safety_adverse_events", "class_specific_risks_glp1",
        "regulatory_status", "drug_interactions",
    ):
        assert topics[tid].requires_drug_intervention is True, tid
    # General clinical topic NOT gated -> still applies to non-drug questions.
    assert topics["population_subgroups"].requires_drug_intervention is False


def test_requires_drug_intervention_defaults_false():
    """An un-marked topic is byte-identical (flag defaults False)."""
    t = ChecklistTopic(id="x", label="X")
    assert t.requires_drug_intervention is False


# ──────────────────────────────────────────────────────────────────────────────
# POSITIVE: a real GLP-1 drug question — critical + GLP-1 class topics APPLY
# ──────────────────────────────────────────────────────────────────────────────

def test_glp1_drug_question_applies_critical_and_class_topics():
    report = check_completeness(
        domain="clinical",
        research_question=_GLP1_DRUG_QUESTION,
        evidence_rows=_GLP1_EVIDENCE,
    )
    applicable = _applicable_ids(report)
    # The critical contraindications topic MUST apply for a real drug question.
    assert "contraindications" in applicable
    # The GLP-1 class-specific-risks topic MUST apply for a GLP-1 drug.
    assert "class_specific_risks_glp1" in applicable
    # And the critical safety abort can still fire (uncovered contraindications).
    assert report.uncovered_critical_topic_ids() == ["contraindications"]


def test_non_glp1_drug_keeps_class_topic_off_but_critical_on():
    """A non-GLP-1 drug (metformin) keeps the GLP-1 class restriction (topic does
    NOT apply) yet the generic critical contraindications topic DOES apply —
    proving the fix is not GLP-1-only and the class restriction is preserved."""
    report = check_completeness(
        domain="clinical",
        research_question="What is the efficacy of metformin for type 2 diabetes?",
        evidence_rows=[{"direct_quote": "Metformin 500 mg reduced HbA1c by 1.2 "
                                        "percentage points.", "statement": ""}],
    )
    applicable = _applicable_ids(report)
    assert "contraindications" in applicable          # generic critical -> applies
    assert "class_specific_risks_glp1" not in applicable  # GLP-1 restriction held


# ──────────────────────────────────────────────────────────────────────────────
# REGRESSION (mandatory): non-drug clinical questions must NOT spuriously apply
# the drug checklist — the OLD bug is gone.
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "question, evidence",
    [
        (_MICROBIOTA_QUESTION, _MICROBIOTA_EVIDENCE),
        (_PARKINSON_QUESTION, _PARKINSON_EVIDENCE),
    ],
)
def test_non_drug_clinical_does_not_apply_drug_topics(question, evidence):
    report = check_completeness(
        domain="clinical",
        research_question=question,
        evidence_rows=evidence,
    )
    applicable = _applicable_ids(report)
    # None of the drug-pharmacology topics may apply to a non-drug question.
    for drug_topic in (
        "contraindications", "efficacy_primary", "safety_adverse_events",
        "class_specific_risks_glp1", "regulatory_status", "drug_interactions",
    ):
        assert drug_topic not in applicable, (drug_topic, applicable)


@pytest.mark.parametrize(
    "question, evidence",
    [
        (_MICROBIOTA_QUESTION, _MICROBIOTA_EVIDENCE),
        (_PARKINSON_QUESTION, _PARKINSON_EVIDENCE),
    ],
)
def test_non_drug_clinical_no_spurious_critical_hold(question, evidence):
    """The lethal symptom: the CRITICAL contraindications topic must NOT apply to
    a non-drug clinical question, so it can neither inflate "covered" nor gate a
    spurious abort_critical_topic_uncovered."""
    report = check_completeness(
        domain="clinical",
        research_question=question,
        evidence_rows=evidence,
    )
    assert _critical_applicable_ids(report) == []
    assert report.uncovered_critical_topic_ids() == []


def test_old_bug_evidence_substring_no_longer_triggers_drug_topic():
    """Direct regression on the root cause: a non-drug question whose EVIDENCE
    incidentally contains the class substring "glp-1" must NOT flip the GLP-1
    class topic on (the prior substring-on-evidence false-positive path)."""
    report = check_completeness(
        domain="clinical",
        research_question=_MICROBIOTA_QUESTION,
        evidence_rows=[{"direct_quote": "Some commentary mentioned glp-1 and "
                                        "therapy in passing.", "statement": ""}],
    )
    assert "class_specific_risks_glp1" not in _applicable_ids(report)
    assert "drug_interactions" not in _applicable_ids(report)


# ──────────────────────────────────────────────────────────────────────────────
# FAIL-CLOSED / DISCLOSE on AMBIGUITY (mandatory): recognizer unavailable must
# NOT silently disable the critical safety topic.
# ──────────────────────────────────────────────────────────────────────────────

def test_recognizer_unavailable_fail_closed_keeps_critical_applicable(monkeypatch):
    """When the intervention recognizer cannot be consulted (genuine ambiguity),
    a CRITICAL requires_drug_intervention topic stays APPLICABLE (fail-closed) and
    a disclosure note is emitted — never silently marked non-applicable."""
    monkeypatch.setattr(
        cc, "_intervention_detected_or_ambiguous",
        lambda _q: (False, True),  # detected=False, ambiguous=True
    )
    report = check_completeness(
        domain="clinical",
        research_question=_MICROBIOTA_QUESTION,
        evidence_rows=_MICROBIOTA_EVIDENCE,
    )
    # Critical contraindications stays applicable under ambiguity.
    assert "contraindications" in _critical_applicable_ids(report)
    # And the decision is DISCLOSED, not silent.
    joined = " ".join(report.notes).lower()
    assert "contraindications" in joined
    assert "fail-closed" in joined or "could not be determined" in joined


def test_clean_negative_is_not_ambiguity(monkeypatch):
    """A clean None from the recognizer (it ran, found no drug) is a CONFIDENT
    negative — the critical topic correctly drops out, with NO fail-closed
    disclosure (that path is reserved for genuine recognizer-unavailability)."""
    monkeypatch.setattr(
        cc, "_intervention_detected_or_ambiguous",
        lambda _q: (False, False),  # detected=False, ambiguous=False
    )
    report = check_completeness(
        domain="clinical",
        research_question=_MICROBIOTA_QUESTION,
        evidence_rows=_MICROBIOTA_EVIDENCE,
    )
    assert _critical_applicable_ids(report) == []
    joined = " ".join(report.notes).lower()
    assert "fail-closed" not in joined


# ──────────────────────────────────────────────────────────────────────────────
# Kill-switch OFF reverts to the legacy substring behaviour (byte-identical path)
# ──────────────────────────────────────────────────────────────────────────────

def test_kill_switch_off_reverts_to_legacy_substring(monkeypatch):
    """With PG_COMPLETENESS_DRUG_DETECTOR=0 the flag is ignored and the legacy
    substring applies_if behaviour returns — contraindications (no applies_if)
    again applies to every clinical question. This documents the pre-BUG-7 path
    is intact behind the escape hatch."""
    monkeypatch.setenv("PG_COMPLETENESS_DRUG_DETECTOR", "0")
    report = check_completeness(
        domain="clinical",
        research_question=_MICROBIOTA_QUESTION,
        evidence_rows=_MICROBIOTA_EVIDENCE,
    )
    # Legacy: contraindications has no applies_if -> always applies.
    assert "contraindications" in _critical_applicable_ids(report)
