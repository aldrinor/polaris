"""
Regression tests for Fix-1 contradiction-detector tuning (2026-04-18 live run).

Live cycle spot-check surfaced a spurious 'contradiction' grouping:
  ev_008 (Nature STEP 5 abstract): 5.0%  — achievement threshold, not claim
  ev_006 (PR Newswire release):    6.5%  — mentioned in passing, not claim
  ev_013 (STEP UP 7.2 mg dose):   20.7%  — different dose than our query

With Fix-1 in place:
  - 5.0 / 6.5 should be filtered by the value-phrase-verb requirement
    AND the placebo/threshold reject patterns.
  - 20.7 is a 7.2 mg result — if extracted at all, it should be
    grouped into its own (dose=7.2 mg) bucket, NOT with 2.4 mg claims.

These tests pin the Fix-1 behavior.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.contradiction_detector import (
    _extract_dose,
    _find_value_in_context,
    detect_contradictions,
    extract_numeric_claims,
)


def _ev(ev_id: str, quote: str, url: str | None = None) -> dict:
    # A17 same-source guard: distinct source_url per evidence_id by default so a genuine
    # cross-source contradiction (two trials disagree) is detected; pass an explicit shared `url=`
    # to exercise the same-source (not_comparable) path. The old shared placeholder was unrealistic.
    return {"evidence_id": ev_id, "direct_quote": quote, "tier": "T1",
            "source_url": url if url is not None else f"https://example.com/{ev_id}"}


# ─────────────────────────────────────────────────────────────────────────────
# Filter behaviors
# ─────────────────────────────────────────────────────────────────────────────


def test_fix1_placebo_arm_number_not_extracted() -> None:
    """Placebo-arm values should be filtered out."""
    quote = (
        "Mean weight loss was 14.9% with semaglutide 2.4 mg versus 2.4% "
        "with placebo."
    )
    result = _find_value_in_context(quote, "weight loss")
    # Should pick 14.9 (treatment arm), NOT 2.4 (placebo arm)
    assert result is not None
    # R-5 Fix B: _find_value_in_context now returns a 4-tuple
    # (value, unit, ctx_window, anchor_position). Unpack with *_.
    value, unit, *_ = result
    assert value == 14.9


def test_fix1_achievement_threshold_not_extracted_as_claim() -> None:
    """'achieved at least 5%' is an achievement threshold, not a claim value."""
    quote = (
        "More than 77.1% of participants achieved at least 5% weight loss."
    )
    result = _find_value_in_context(quote, "weight loss")
    # Should pick 77.1 (the actual value), NOT 5 (threshold)
    assert result is not None
    value, *_ = result
    assert value == 77.1


def test_fix1_trial_acronym_integer_not_extracted() -> None:
    """'STEP 5' is a trial-program ID, not a claim value."""
    quote = (
        "In STEP 5, semaglutide produced a mean weight loss of 15.2% "
        "at week 104."
    )
    result = _find_value_in_context(quote, "weight loss")
    assert result is not None
    value, *_ = result
    assert value == 15.2


def test_fix1_dose_extraction() -> None:
    quote = "Semaglutide 2.4 mg achieved 14.9% weight loss."
    assert _extract_dose(quote) == "2.4 mg"
    quote2 = "STEP UP evaluated semaglutide 7.2 mg with 20.7% weight loss."
    assert _extract_dose(quote2) == "7.2 mg"


def test_fix1_value_without_verb_rejected() -> None:
    """A bare decimal without a value-phrase verb should NOT be extracted
    as a weight-loss claim (prevents random noise)."""
    quote = "The study enrolled 77.1% of eligible participants."
    # "enrolled" is not a value-phrase verb for weight loss
    result = _find_value_in_context(quote, "weight loss")
    # With the value-phrase gate, 77.1 should NOT be picked up here
    # (no "achieved", "reduced", "loss of" etc.)
    assert result is None or result[0] != 77.1


# ─────────────────────────────────────────────────────────────────────────────
# Grouping by dose
# ─────────────────────────────────────────────────────────────────────────────


def test_fix1_different_doses_not_grouped() -> None:
    """2.4 mg and 7.2 mg results must not be grouped as contradictions."""
    evidence = [
        _ev("ev_24", "Semaglutide 2.4 mg achieved 14.9% weight loss at week 68."),
        _ev("ev_72", "Semaglutide 7.2 mg achieved 20.7% weight loss at week 72."),
    ]
    claims = extract_numeric_claims(evidence)
    assert len(claims) == 2
    # Doses should be captured
    doses = sorted(c.dose for c in claims)
    assert doses == ["2.4 mg", "7.2 mg"]
    # Different doses => different grouping keys => no contradiction
    records = detect_contradictions(claims)
    assert records == []


def test_fix1_same_dose_different_values_still_flagged() -> None:
    """Same dose, different values → still a contradiction."""
    evidence = [
        _ev("ev_a", "Semaglutide 2.4 mg achieved 14.9% weight loss at week 68."),
        _ev("ev_b", "Semaglutide 2.4 mg achieved 17.4% weight loss at week 104."),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    assert len(records) == 1
    r = records[0]
    assert r.predicate == "weight loss (2.4 mg)"


def test_fix1_live_run_noise_not_flagged() -> None:
    """The exact 3-value grouping that fired falsely in the live run
    (ev_008 5.0, ev_006 6.5, ev_013 20.7) must NOT fire under Fix-1."""
    evidence = [
        _ev("ev_008",
            "The STEP 5 trial assessed the efficacy and safety of once-"
            "weekly subcutaneous semaglutide 2.4 mg versus placebo (both "
            "plus behavioral intervention). More than 5% of participants "
            "achieved early weight loss. At week 5 of treatment..."),
        _ev("ev_006",
            "PR NEWSWIRE: Results of a phase 3a trial showed investigational "
            "semaglutide 2.4 mg once-weekly. Approximately 6.5% of "
            "participants reported nausea in the early visit schedule."),
        _ev("ev_013",
            "STEP UP trial evaluating investigational semaglutide 7.2 mg "
            "in adults with obesity achieved 20.7% weight loss at week 72."),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    # The live-run false positive was "weight loss" grouping of
    # 5.0 / 6.5 / 20.7. After Fix-1:
    #   - 5.0 is an achievement threshold (filtered) OR week number (filtered)
    #   - 6.5 is nausea rate, not weight loss (different predicate)
    #   - 20.7 is 7.2 mg dose (different grouping key)
    # So we expect NO spurious "weight loss" contradiction.
    weight_loss_records = [r for r in records if "weight loss" in r.predicate]
    assert len(weight_loss_records) == 0, \
        f"Fix-1 regression: spurious weight-loss contradiction fired: {weight_loss_records}"


def test_fix1_endpoint_phrase_captured() -> None:
    evidence = [
        _ev("ev_a", "Semaglutide 2.4 mg achieved 14.9% weight loss at week 68."),
    ]
    claims = extract_numeric_claims(evidence)
    assert len(claims) == 1
    assert "week 68" in claims[0].endpoint_phrase
