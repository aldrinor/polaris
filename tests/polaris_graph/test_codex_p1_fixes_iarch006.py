"""Codex gate P1 fixes for I-arch-006 (#1262) — two faithfulness/clinical-safety holes.

P1-1 (BUG-19): the boilerplate pre-gate filter must NOT silently drop a real NEGATIVE
clinical finding ("Metastases were not found") as if it were a 404 stub. Bare "not found"
was removed from the substring error tokens; only a literal whole-unit "not found" body
(a bare 404) is still excluded.

P1-2 (BUG-7): a CRITICAL drug-contraindications topic must never be SILENTLY marked
non-applicable on a drug-recognizer MISS (brand/trade names it does not cover) — that
would disable abort_critical_topic_uncovered. On a confident-negative for a critical
topic we now FAIL-CLOSED + disclose when the question carries generic drug signal, and
otherwise keep non-applicable but DISCLOSE the decision (never silent). A genuine
non-drug question is never spuriously held.

Offline, deterministic, no network/spend.
"""

from __future__ import annotations

import pytest

from src.tools.access_bypass import is_boilerplate_or_nonassertional
from src.polaris_graph.nodes import completeness_checker as cc
from src.polaris_graph.nodes.completeness_checker import (
    ChecklistTopic,
    _generic_drug_signal,
    _topic_applies,
)


# ── P1-1: BUG-19 negative-finding safety ──────────────────────────────────────

@pytest.mark.parametrize("sentence", [
    "Metastases were not found.",
    "No distant metastases were not found on the PET-CT.",
    "The mutation was not found in any of the 42 patients.",
    "Residual disease was not found at the 12-month follow-up.",
])
def test_real_negative_clinical_finding_is_not_dropped(sentence):
    assert is_boilerplate_or_nonassertional(sentence) is False, (
        "Codex P1: a real NEGATIVE clinical finding must reach the gate, not be "
        "silently excluded as a 404 stub"
    )


@pytest.mark.parametrize("stub", [
    "Page not found",
    "404 Not Found",
    "Not Found",
    "not found.",
    "404 - Not Found",
])
def test_literal_error_page_stub_is_still_dropped(stub):
    assert is_boilerplate_or_nonassertional(stub) is True


# ── P1-2: BUG-7 critical-topic fail-closed / disclose ─────────────────────────

def test_generic_drug_signal_ignores_non_drug_questions():
    assert _generic_drug_signal("Does gut microbiota affect colorectal cancer?") is False
    assert _generic_drug_signal("Deep brain stimulation vs best medical therapy in Parkinson") is False
    assert _generic_drug_signal("Do metal ions in water raise cardiovascular risk?") is False


@pytest.mark.parametrize("non_drug", [
    # Codex iter-2 P1: broad route/dosing terms must NOT trip the drug signal.
    "Validity of a self-administered questionnaire for symptom screening",
    "Does subcutaneous fat thickness predict cardiovascular risk?",
    "Optimal radiation dosing schedule in early-stage breast cancer",
    "Intramuscular EMG recording during gait in Parkinson disease",
    "How is the dosage of radiation calculated in CT imaging?",
])
def test_generic_drug_signal_not_tripped_by_broad_nondrug_terms(non_drug):
    assert _generic_drug_signal(non_drug) is False, (
        "Codex iter-2 P1: a non-drug question must not fail-closed a critical drug topic"
    )


def test_generic_drug_signal_fires_on_real_drug_questions():
    assert _generic_drug_signal("contraindications of tirzepatide 15 mg") is True
    assert _generic_drug_signal("a novel DPP-4 inhibitor administered orally") is True
    assert _generic_drug_signal("chemotherapy dosing in advanced NSCLC") is True


def _critical_topic() -> ChecklistTopic:
    return ChecklistTopic(
        id="contraindications", label="Contraindications",
        keywords=["contraindication"], applies_if=["glp-1", "incretin"],
        critical=True, requires_drug_intervention=True,
    )


def test_critical_topic_failclosed_on_recognizer_miss_with_drug_signal(monkeypatch):
    """Recognizer MISSES the brand (returns None) but the question carries drug
    signal -> the critical topic must FAIL-CLOSED (applies=True) + disclose."""
    monkeypatch.setenv("PG_COMPLETENESS_DRUG_DETECTOR", "1")
    monkeypatch.setattr(
        "src.polaris_graph.nodes.scope_gate._intervention_present",
        lambda q: None,  # confident negative: recognizer ran, found nothing
        raising=False,
    )
    applies, disclosure = _topic_applies(
        _critical_topic(),
        "What are the contraindications of fictbrandxyz 15 mg in adults?",
        "",
    )
    assert applies is True, "critical topic must fail-closed on a brand-name miss with drug signal"
    assert disclosure and "FAIL-CLOSED" in disclosure


def test_critical_topic_nonapplicable_but_disclosed_on_genuine_non_drug(monkeypatch):
    """Genuine non-drug question (no drug signal) -> non-applicable so a non-drug
    report is never spuriously held, but the decision is DISCLOSED, never silent."""
    monkeypatch.setenv("PG_COMPLETENESS_DRUG_DETECTOR", "1")
    monkeypatch.setattr(
        "src.polaris_graph.nodes.scope_gate._intervention_present",
        lambda q: None,
        raising=False,
    )
    applies, disclosure = _topic_applies(
        _critical_topic(),
        "Does gut microbiota composition influence colorectal cancer risk?",
        "",
    )
    assert applies is False, "a genuine non-drug question must not spuriously hold a non-drug report"
    assert disclosure != "", "the non-applicable decision for a CRITICAL topic must be disclosed, not silent"
