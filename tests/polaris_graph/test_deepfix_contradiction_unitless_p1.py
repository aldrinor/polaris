"""I-deepfix-001 (#1344) — Codex preflight iter-1 P1 regression.

The contradiction scale-guard (FIX #4) must NOT suppress a genuine UNIT-LESS SAME-METRIC
contradiction (hazard ratio / odds ratio / risk ratio / index) merely because the spread
exceeds 1000%. Relabeling `not_comparable` now REQUIRES positive count-scale evidence — at
least one operand at/above PG_CONTRADICTION_RAW_COUNT_FLOOR (a raw count / sample size /
identifier lifted as a value). Unit-less alone is NOT incomparability. Suppressing a real
contradiction is the §-1.1-lethal "mislabel a real finding" class, so this is locked by a test.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.contradiction_detector import (
    ExtractedNumericClaim,
    detect_contradictions,
)


def _hr(ev_id: str, value: float, url: str) -> ExtractedNumericClaim:
    """A unit-less hazard-ratio claim — the bucket the iter-1 P1 over-suppressed."""
    return ExtractedNumericClaim(
        evidence_id=ev_id,
        subject="drug_x",
        predicate="hazard ratio for all-cause mortality",
        value=value,
        unit="",  # hazard ratio carries no unit token
        context_snippet=f"hazard ratio {value}",
        source_url=url,
    )


def test_unitless_same_metric_high_spread_still_flagged():
    # Hazard ratio 0.5 (protective) vs 8.0 (harmful): rel = 1500% (>1000% spurious threshold),
    # NEITHER operand >= 100 (no count-scale evidence). A REAL clinical contradiction that MUST
    # survive — the iter-1 P1 was the spurious-magnitude arm suppressing exactly this.
    claims = [
        _hr("ev_a", 0.5, "https://example.com/trial_a"),
        _hr("ev_b", 8.0, "https://example.com/cohort_b"),
    ]
    records = detect_contradictions(
        claims, rel_threshold=0.5, abs_threshold=1.0, is_clinical=True
    )
    assert len(records) == 1, "a unit-less same-metric >1000% contradiction must still be detected"
    r = records[0]
    assert r.not_comparable is False, "must NOT be relabeled not_comparable (no count-scale operand)"
    assert "[not_comparable]" not in r.predicate
    assert r.relative_difference > 10.0  # the real ~1500% spread is preserved, not nulled to 0.0


def test_unitless_ratio_vs_raw_count_is_not_comparable():
    # The drb_72 forensic case: a 0-1 ratio (0.62) bucketed with a raw count / sample size (3682)
    # under a missing unit. has_ratio AND has_count -> genuine scale mismatch -> not_comparable
    # (magnitude nulled, kept out of the headline count, both sources still disclosed — §-1.3).
    claims = [
        ExtractedNumericClaim(
            evidence_id="ev_ratio", subject="study", predicate="complementarity index",
            value=0.62, unit="", context_snippet="index 0.62",
            source_url="https://example.com/s1",
        ),
        ExtractedNumericClaim(
            evidence_id="ev_count", subject="study", predicate="complementarity index",
            value=3682.0, unit="", context_snippet="n = 3682",
            source_url="https://example.com/s2",
        ),
    ]
    records = detect_contradictions(
        claims, rel_threshold=0.5, abs_threshold=1.0, is_clinical=True
    )
    assert len(records) == 1
    r = records[0]
    assert r.not_comparable is True, "0-1 ratio vs raw count 3682 is a genuine scale mismatch"
    assert "[not_comparable]" in r.predicate
    assert r.relative_difference == 0.0 and r.absolute_difference == 0.0  # junk magnitude nulled
    assert {c.evidence_id for c in r.claims} == {"ev_ratio", "ev_count"}  # both still disclosed
