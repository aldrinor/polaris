"""B13 (I-arch-011) — domain-general contradiction subject + confidence-interval guard.

LANE CONTRA. Two surgical fixes, both ADVISORY-surface only (label, never
drop/hold a report — faithfulness gates untouched):

1. SUBJECT EXTRACTION IS DOMAIN-GENERAL.
   ``contradiction_detector._normalize_subject`` was a DRUG-NAME-ONLY finder. The
   qualitative present-vs-absent detector (``qualitative_conflict_detector``)
   calls it for the assertion subject; on a NON-drug clinical corpus
   (Parkinson / deep-brain-stimulation device + procedure safety) it returned
   ``""`` for EVERY flag, so:
     * Pass A (hard conflict) skips empty-subject assertions entirely, and
     * Pass B collapses every unrelated flag into one ``("", concept_type)``
       bucket — real T1 safety signals diluted into indistinguishable noise.
   The fix adds an OPT-IN ``general_fallback`` (default False, so every
   pre-existing caller — incl. the clinical numeric path — is byte-identical) and
   wires it only into the two qualitative call sites. Drug-name precedence is
   preserved (a named drug still wins). Result on a DBS corpus: a NON-EMPTY
   entity subject is extracted and the present-vs-absent pair is FLAGGED.

2. A CONFIDENCE-INTERVAL BOUND IS NOT A METRIC VALUE.
   The numeric extractor misparsed the "95%" in "Mortality reduction (95% CI
   2-9)" as a 95% mortality value, manufacturing fake numeric contradictions
   against the real single-digit figure. The fix rejects a number that is the
   confidence LEVEL directly before a CI / confidence-interval cue — anchored on
   that number's own position, so a real point estimate ("8%" in "reduced to 8%
   (95% CI 5-12)") and a legitimate "95% of patients" value are unaffected.

NO network / NO model / NO spend — pure rule-cue. These tests assert the
BEHAVIOR (extracted subject non-empty; pair flagged; CI level not emitted), not
that a flag/env is set.
"""

from __future__ import annotations

import pytest

import src.polaris_graph.retrieval.contradiction_detector as cd
from src.polaris_graph.retrieval.contradiction_detector import (
    detect_contradictions,
    extract_numeric_claims,
    _find_value_generic,
    _find_value_in_context,
    _normalize_predicate,
    _normalize_subject,
)
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    detect_qualitative_conflicts,
    extract_qualitative_assertions,
)


def _ev(eid: str, quote: str, url: str, tier: str = "T1") -> dict:
    return {"evidence_id": eid, "direct_quote": quote, "source_url": url, "tier": tier}


# ── FIX 1: domain-general subject on a NON-DRUG (DBS) clinical corpus ─────────────────────────────
def test_non_drug_dbs_subject_is_non_empty_and_pair_is_flagged():
    """The lane bug: a Parkinson/DBS corpus resolved EVERY qualitative subject to ""
    (drug-name-only extractor), so every safety flag diluted into one ("",concept)
    bucket. Post-fix the device/procedure subject is EXTRACTED (non-empty) and the
    contraindicated-vs-safe pair is surfaced (severity not pinned — Pass A 'high' or
    Pass B 'review' both count as flagged)."""
    ev = [
        _ev("ev_000", "DBS is contraindicated in patients with dementia.", "https://a", "T1"),
        _ev("ev_001", "DBS is safe in patients with dementia.", "https://b", "T2"),
    ]
    assertions = extract_qualitative_assertions(ev)
    # (a) both sides extract — and the subject is the NON-DRUG device entity, NOT "".
    assert len(assertions) >= 2, "both the contraindicated and the safe side must extract"
    subjects = {a.subject for a in assertions}
    assert "" not in subjects, (
        "pre-fix bug: a non-drug DBS subject resolved to '' for every flag — the dilution "
        f"failure this lane fixes. Got subjects={subjects!r}"
    )
    assert subjects == {"dbs"}, (
        "the same device named the same way on both sides must resolve to the SAME non-empty "
        f"subject token so the two assertions group/conflict. Got {subjects!r}"
    )
    # (b) the present-vs-absent disagreement is FLAGGED (advisory surface), keyed on the
    # real entity — NOT silently dropped, NOT buried under an empty subject.
    records = detect_qualitative_conflicts(assertions)
    flagged = [r for r in records if r.subject == "dbs" and "contraindication" in r.predicate]
    assert flagged, (
        "the contraindicated-vs-safe DBS disagreement must surface under the real entity "
        f"subject. Got records={[(r.severity, r.subject, r.predicate) for r in records]!r}"
    )


def test_normalize_subject_default_is_drug_only_byte_identical():
    """The opt-in is OFF by default: every pre-existing caller (incl. the clinical numeric
    path) keeps the drug-name-only behaviour and its fallback — byte-identical."""
    # Non-drug text with general_fallback OFF -> the unchanged fallback, never a noun.
    assert _normalize_subject("DBS is contraindicated in dementia.", fallback="") == ""
    assert _normalize_subject("DBS is contraindicated in dementia.", fallback="unknown") == "unknown"
    # general_fallback ON -> the domain-general noun subject.
    assert _normalize_subject(
        "DBS is contraindicated in dementia.", fallback="", general_fallback=True) == "dbs"


def test_drug_name_still_wins_over_general_noun():
    """Drug-name precedence preserved: a named drug is still the subject even with the
    general fallback enabled (the clinical golden behaviour, e.g. test_qualitative's
    'semaglutide' assertions, is unchanged)."""
    assert _normalize_subject(
        "Semaglutide is contraindicated in pregnancy.",
        fallback="", general_fallback=True) == "semaglutide"


# ── FIX 2: a 95% CI bound/level is NOT emitted as a numeric contradiction value ──────────────────
@pytest.mark.parametrize(
    "quote",
    [
        "Mortality reduction was demonstrated (95% CI 2-9).",
        "Mortality was reduced, with a 95% confidence interval reported.",
    ],
)
def test_confidence_interval_level_not_emitted_as_metric_value(quote):
    """The 95% in '(95% CI ...)' is the statistical confidence LEVEL, not a mortality
    value. Pre-fix the clinical extractor returned (95.0, '%') here (a fabricated 95%
    mortality figure that manufactured fake contradictions); post-fix it is rejected."""
    pred = _normalize_predicate(quote, domain="clinical")
    clinical = _find_value_in_context(quote, pred) if pred else None
    if clinical is not None:
        value, _unit, _ctx, _pos = clinical
        assert value != 95.0, (
            f"the confidence LEVEL 95.0 must not be emitted as the metric value for {quote!r}; "
            f"got {clinical!r}"
        )
    # The generic (non-clinical) path must likewise not surface 95.0 as the value.
    generic = _find_value_generic(quote)
    if generic is not None:
        gvalue, _gu, _gc, _gp = generic
        assert gvalue != 95.0, (
            f"generic path must not emit the confidence LEVEL 95.0 as the value for {quote!r}; "
            f"got {generic!r}"
        )


def test_confidence_interval_bound_not_emitted_as_value():
    """A CI-only row ('(95% CI 2-9)' with NO point estimate) must emit NEITHER the
    confidence level (95) NOR an interval BOUND (2 / 9 / -9) as the metric value — the
    whole parenthetical is interval statistics, not a measured outcome. Pre-fix the
    generic path returned (-9.0, '') (a CI bound surfaced as a value)."""
    quote = "Mortality reduction was demonstrated (95% CI 2-9)."
    generic = _find_value_generic(quote)
    assert generic is None, (
        "a CI-only row must yield NO generic metric value (neither the 95 level nor the "
        f"2/9 bounds); got {generic!r}"
    )
    pred = _normalize_predicate(quote, domain="clinical")
    clinical = _find_value_in_context(quote, pred) if pred else None
    assert clinical is None, (
        f"the clinical path must yield NO value for a CI-only row; got {clinical!r}"
    )


def test_confidence_interval_bound_does_not_become_a_contradiction_record():
    """End-to-end (§-1.4 — assert the effect in real output): two NON-clinical sources
    whose only numbers are CI bounds must NOT manufacture a numeric contradiction record.
    Pre-fix the bound (-9 vs another bound) surfaced as a value and a fake contradiction
    could form; post-fix no numeric claim is extracted from a CI-only row."""
    evidence = [
        _ev("ev_000", "Labor productivity growth was reported (95% CI 2-9).", "https://a"),
        _ev("ev_001", "Labor productivity growth was reported (95% CI 11-18).", "https://b"),
    ]
    claims = extract_numeric_claims(evidence)  # non-clinical -> generic path
    # No CI-bound number may become a claim value.
    bad = [c for c in claims if c.value in (-9.0, 2.0, 9.0, 11.0, 18.0)]
    assert not bad, f"CI bounds must not become numeric claims; got {[(c.value, c.unit) for c in bad]!r}"
    records = detect_contradictions(claims, is_clinical=False)
    assert records == [], (
        "two CI-only rows must not produce a numeric contradiction record; "
        f"got {[(r.subject, r.predicate, r.relative_difference) for r in records]!r}"
    )


def test_legitimate_95_percent_value_still_extracted():
    """A real '95% of patients' value (no CI cue) must STILL be extracted — the guard is
    anchored on a CI cue, not a blanket '95% is always a confidence level' rule (that would
    suppress a real value — a faithfulness loss)."""
    quote = "95% of patients achieved the primary endpoint of weight loss."
    pred = _normalize_predicate(quote, domain="clinical")
    clinical = _find_value_in_context(quote, pred) if pred else None
    assert clinical is not None and clinical[0] == 95.0, (
        f"a legitimate 95% value (no CI cue) must survive the guard; got {clinical!r}"
    )
    generic = _find_value_generic(quote)
    assert generic is not None and generic[0] == 95.0, (
        f"generic path must keep a legitimate 95% value; got {generic!r}"
    )
