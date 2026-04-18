"""
R-5 Fix B regression tests: contradiction subject disambiguation.
Cross-drug comparison quotes must attribute the number to the drug
NEAREST the value, not the first drug in the quote.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.contradiction_detector import (
    _normalize_subject,
    _subject_near_position,
    detect_contradictions,
    extract_numeric_claims,
)


def test_r5_legacy_normalize_returns_first_drug() -> None:
    """Back-compat: _normalize_subject returns the first drug."""
    text = "retatrutide achieved 28.7% in one trial; zepbound achieved 25.5% in another."
    assert _normalize_subject(text) == "retatrutide"


def test_r5_subject_near_position_picks_closest_drug() -> None:
    text = (
        "Early data on retatrutide suggested efficacy. "
        "Eli Lilly's Zepbound achieving an average weight loss of 25.5% "
        "compared to CagriSema at 23%."
    )
    # Find position of "25.5"
    pos = text.find("25.5")
    assert pos > 0
    # The drug nearest the 25.5 value is Zepbound (not in our regex,
    # but tirzepatide would be if we had it). Since Zepbound isn't in
    # the drug regex, nearest match in window should be... actually
    # let me check. This test uses drugs that ARE in the regex.
    text2 = (
        "Early data on retatrutide looked promising. "
        "In a head-to-head, tirzepatide achieved 25.5% weight loss "
        "while CagriSema achieved 23%."
    )
    pos2 = text2.find("25.5")
    subj = _subject_near_position(text2, pos2)
    assert subj == "tirzepatide", f"Expected tirzepatide, got {subj}"


def test_r5_subject_near_position_fallback_to_first() -> None:
    """If no drug is within the window, fall back to first-in-text."""
    text = "retatrutide early data. " + "noise " * 80 + "achieved 25.5% reduction."
    pos = text.find("25.5")
    # Window of ±150 around 25.5 should NOT contain retatrutide (100+ chars away)
    subj = _subject_near_position(text, pos, window=150)
    # Falls back to first-in-text search
    assert subj == "retatrutide"


def test_r5_cross_drug_contradiction_not_false_grouped() -> None:
    """The live-run bug: two evidence rows, each citing a DIFFERENT drug
    near its value, must NOT be grouped as a contradiction of one drug."""
    evidence = [
        {"evidence_id": "ev_a",
         "direct_quote": (
             "Retatrutide from Eli Lilly achieved 28.7% weight loss in "
             "phase 3. Meanwhile, in the SURMOUNT-5 trial, tirzepatide "
             "achieved a mean weight loss of 25.5% at week 72."
         ),
         "tier": "T1", "source_url": "https://a/"},
        {"evidence_id": "ev_b",
         "direct_quote": (
             "Retatrutide data suggest best-in-class efficacy. "
             "tirzepatide achieved mean weight loss of 20.2% at week 72."
         ),
         "tier": "T1", "source_url": "https://b/"},
    ]
    claims = extract_numeric_claims(evidence)
    # The 25.5% is near 'tirzepatide' (within ~30 chars), and 20.2% is
    # near 'tirzepatide' (within ~30 chars). Both should be attributed
    # to tirzepatide, NOT retatrutide. So they WOULD be a contradiction
    # on tirzepatide (25.5% vs 20.2%).
    subjects = sorted({c.subject for c in claims})
    assert "tirzepatide" in subjects, f"Expected tirzepatide, got {subjects}"
    # Verify the claims attribute correctly
    for c in claims:
        if c.value == 25.5:
            assert c.subject == "tirzepatide", \
                f"25.5% should be tirzepatide, got {c.subject}"
        if c.value == 20.2:
            assert c.subject == "tirzepatide", \
                f"20.2% should be tirzepatide, got {c.subject}"


def test_r5_no_false_cross_drug_grouping() -> None:
    """retatrutide 28.7% AND tirzepatide 25.5% in two different
    evidence rows should NOT be flagged as a single contradiction."""
    evidence = [
        {"evidence_id": "ev_ret",
         "direct_quote": "In a phase 3 trial, retatrutide achieved mean weight loss of 28.7%.",
         "tier": "T1", "source_url": "https://r/"},
        {"evidence_id": "ev_tir",
         "direct_quote": "SURMOUNT-5 showed tirzepatide achieved 25.5% weight loss at week 72.",
         "tier": "T1", "source_url": "https://t/"},
    ]
    claims = extract_numeric_claims(evidence)
    subjects = sorted({c.subject for c in claims})
    assert "retatrutide" in subjects
    assert "tirzepatide" in subjects
    records = detect_contradictions(claims)
    # Different drugs → different grouping key → no contradiction
    assert len(records) == 0, f"Unexpected contradiction: {records}"
