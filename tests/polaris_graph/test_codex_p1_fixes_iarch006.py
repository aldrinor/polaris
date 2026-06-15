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


# ── P1-2: BUG-7 critical-topic — pure DISCLOSE (never silent, never spuriously held) ──
#
# Codex iter-1..3 converged: a keyword "drug signal" heuristic to auto-FAIL-CLOSED a
# critical topic on a recognizer confident-negative is a false-positive minefield
# (negation "non-pharmacological"/"medication-free"; polysemy "capsule endoscopy"/
# "monoclonal gammopathy"). Per Codex's "fail-closed OR DISCLOSE" guidance + the
# operator's disclose-don't-hold directive, the critical confident-negative path is now
# PURE DISCLOSE: applies=False (a non-drug report is NEVER spuriously held) + a
# disclosure note ALWAYS (auditable, NEVER silent).

def _critical_topic() -> ChecklistTopic:
    return ChecklistTopic(
        id="contraindications", label="Contraindications",
        keywords=["contraindication"], applies_if=["glp-1", "incretin"],
        critical=True, requires_drug_intervention=True,
    )


@pytest.mark.parametrize("question", [
    # the 3 golden non-drug questions ...
    "Does gut microbiota composition influence colorectal cancer risk?",
    "Deep brain stimulation versus best medical therapy in Parkinson disease",
    "Do metal ions in drinking water increase cardiovascular disease risk?",
    # ... the iter-2/iter-3 false-positive TRAPS that must NEVER cause a spurious hold ...
    "Validity of a self-administered questionnaire for symptom screening",
    "Does subcutaneous fat thickness predict cardiovascular risk?",
    "Optimal radiation dosing in early-stage breast cancer",
    "Capsule endoscopy findings in small-bowel Crohn disease",
    "Diagnostic criteria for monoclonal gammopathy of undetermined significance",
    "Non-pharmacological management of chronic low back pain",
    # ... and a drug-ish question whose specific brand the recognizer misses ...
    "What are the contraindications of fictbrandxyz 15 mg in adults?",
])
def test_critical_topic_confident_negative_is_nonapplicable_but_disclosed(monkeypatch, question):
    """On a recognizer confident-negative, a CRITICAL topic is NON-applicable (so no
    report is ever spuriously held by abort_critical_topic_uncovered) AND the decision
    is DISCLOSED (never silent) — for EVERY question, drug-ish or not, with NO keyword
    false positives."""
    monkeypatch.setenv("PG_COMPLETENESS_DRUG_DETECTOR", "1")
    monkeypatch.setattr(
        "src.polaris_graph.nodes.scope_gate._intervention_present",
        lambda q: None,  # confident negative: recognizer ran, found nothing
        raising=False,
    )
    applies, disclosure = _topic_applies(_critical_topic(), question, "")
    assert applies is False, "a critical confident-negative must NEVER spuriously hold a report"
    assert disclosure != "", "the skipped critical safety topic must be DISCLOSED, never silent"
