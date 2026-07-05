"""I-deepfix-001 rank-19 (#1344) — contradiction over-interpretation of NON-QUANTITY numbers.

The audit found both disclosed "numeric contradictions" on the cert artifact compared
NON-QUANTITY number extractions:

  * subject "aggregate" compared 64.0 (from ``ages 18-64``) vs 1.0 and the Limitations
    prose stated a "relative difference of 5000.0%";
  * subject "firm-" compared 16.0 (the volume of ``Sustainability 2024, 16, 8881``) vs
    2.0 (an author affiliation superscript) at a "relative difference of 700.0%".

None are measured quantities. The fix has two arms:

  (a) EXTRACTION SCREEN (``contradiction_detector._find_value_generic``): a UNIT-LESS
      age-range bound / journal volume-issue-article number / bracketed reference marker
      / single page number / author superscript is filtered OUT before it can become a
      claim value and be paired.

  (b) RENDER GUARD (``live_deepseek_generator._format_telemetry_block``): a WITHHELD
      (``[possible_metric_mismatch]``-marked) pairing is routed OUT of the headline
      ``contradictions_detected`` count and is NOT described as a magnitude disagreement —
      matching ``format_contradictions_for_user`` / the production render path.

RED/GREEN: an age-range / volume-number pair renders "disagree on magnitude" (the
flag-OFF pre-fix path below reproduces the exact 5000.0% / 700.0% strings) → after the
fix it is filtered / withheld and NOT rendered as a disagreement; a genuine 14% vs 41%
pair is STILL flagged as a real magnitude contradiction.

Faithfulness engine untouched (§-1.3): the fix only REDUCES false contradictions; a real
same-metric disagreement is never suppressed. All assertions go through production
functions; no internal mocking.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.live_deepseek_generator import _format_telemetry_block
from src.polaris_graph.retrieval.contradiction_detector import (
    POSSIBLE_METRIC_MISMATCH_MARKER,
    detect_contradictions,
    extract_numeric_claims,
    _find_value_generic,
)


# ──────────────────────────────────────────────────────────────────────────────
# (a) EXTRACTION SCREEN — non-quantity numbers are filtered out
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        # Age ranges (the "aggregate 64 vs 1" root) — ASCII hyphen, en-dash, "to", "years"
        "the cohort included adults ages 18-64 overall",
        "the cohort included adults ages 18–64 overall",   # en-dash
        "the sample covered adults aged 18 to 64 in scope",
        "participants 18–64 years were enrolled in the study",
        "respondents between 18 and 64 years took part",
        # Journal volume / issue / article numbers (the "firm- 16" root)
        "published in Sustainability 2024, 16, 8881 that year",
        "see Vol. 16 of the series for details",
        "the finding appears in volume 16 of the journal",
        "reported in issue 3 of the review",
        "printed as 16(3):100 in the catalogue index",
        # Bracketed reference markers
        "see the review [16] for the surrounding context",
        "as argued earlier [2] in the literature",
        # Single page numbers (ranges are handled by the bibliographic screen)
        "the argument is discussed on p. 47 of the report",
        "see page 47 for the relevant figure",
        # Author affiliation superscript (the "firm- 2" root) — digit glued to a letter
        "as reported by Smith2 in the affiliation footnote",
    ],
)
def test_non_quantity_number_is_not_extracted(text: str) -> None:
    """A UNIT-LESS non-quantity number never becomes a generic claim value (GREEN).

    Pre-fix these returned e.g. 64.0 / 16.0 / 2.0 / 47.0 (RED) and were paired into a
    fabricated magnitude contradiction."""
    assert _find_value_generic(text) is None, f"non-quantity number leaked from: {text!r}"


@pytest.mark.parametrize(
    "text, value, unit",
    [
        # A real metric CO-OCCURRING with an age range must survive (only the garbage is screened).
        ("among adults ages 18–64, the coverage rate reached 41% overall", 41.0, "percent"),
        ("the unemployment rate reached 47% in the region", 47.0, "percent"),
        ("the market grew to $13 billion last year", 13.0, "billion"),
        ("the adoption rate hit 75.5 percent among firms", 75.5, "percent"),
    ],
)
def test_real_unit_bearing_value_survives(text: str, value: float, unit: str) -> None:
    """A unit-bearing value is never screened — a genuine numeric disagreement is intact."""
    found = _find_value_generic(text)
    assert found is not None, f"real value was wrongly screened from: {text!r}"
    assert found[0] == value
    assert found[1] == unit


# ──────────────────────────────────────────────────────────────────────────────
# (a-iter3) P1a — the WHOLE superscript chain is rejected, not only the letter-glued head
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        # Superscript CHAIN — the TRAILING index leaked pre-iter-3 (Codex P1a). The letter-glued
        # head ("1"/"2") was rejected, but the comma/dash-separated trailing digit ("3"/"4"),
        # whose immediate predecessor is a comma (not a letter), was extracted as a claim value.
        "the report by Chen1,3 discusses the trend",        # 2-member comma chain
        "as noted by Smith2,4 in the review section",       # 2-member comma chain
        "the analysis Smith2,4,6 covered three cohorts",    # 3-member comma chain
        "the study Lee1-3 reported the same result",        # hyphen chain
        "the finding Wang1–4 spanned four datasets",        # en-dash chain
    ],
)
def test_superscript_chain_yields_no_numeric_claim(text: str) -> None:
    """A UNIT-LESS number that is a TRAILING member of an author/reference superscript CHAIN
    (Chen1,3 / Smith2,4,6 / Lee1-3) never becomes a claim value (iter-3 P1a widening).

    RED (pre-iter-3): the letter-glued head was rejected but the comma/dash-separated trailing
    digit leaked (e.g. "Chen1,3" -> 3.0) and could be paired into a fabricated contradiction.
    GREEN (post-fix): the whole chain is rejected."""
    assert _find_value_generic(text) is None, f"superscript-chain index leaked from: {text!r}"


def test_chen_chain_trailing_index_direct_probe() -> None:
    """The exact Codex P1a probe: ``_find_value_generic('... Chen1,3 ...')`` returns None, NOT
    (3.0, ...); a 3-member chain like ``Smith2,4`` likewise yields no numeric claim."""
    assert _find_value_generic("the cohort in Chen1,3 was analysed") is None
    assert _find_value_generic("the model Smith2,4 was fit to the data") is None


# ──────────────────────────────────────────────────────────────────────────────
# (a-iter3) P1b — the money-multiplier abbreviations bn/tn/mn survive; bare 18m does not
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, value, unit",
    [
        ("the market reached $16bn last year", 16.0, "billion"),
        ("the economy hit £4tn in output", 4.0, "trillion"),
        ("the fund grew to €7mn overall", 7.0, "million"),
    ],
)
def test_money_multiplier_abbrev_survives(text: str, value: float, unit: str) -> None:
    """The UNAMBIGUOUS money-multiplier abbreviations bn/tn/mn are recognized as real magnitude
    values (iter-3 P1b) — pre-iter-3 ``$16bn`` returned None, suppressing a genuine numeric
    disagreement. They normalize to their long form so ``$16bn`` consolidates with ``$16 billion``
    (proved by the ``unit`` assertion matching the long-form spelling)."""
    found = _find_value_generic(text)
    assert found is not None, f"money-multiplier abbrev wrongly screened from: {text!r}"
    assert found[0] == value
    assert found[1] == unit


def test_bare_meters_not_read_as_magnitude() -> None:
    """A bare ``18m`` (metres) must NOT be read as a magnitude — only the UNAMBIGUOUS bn/tn/mn
    suffixes were added, never bare m/k/b. So ``18m`` is either not extracted at all or carries
    NO magnitude unit (it is never read as 18 million/billion/etc.)."""
    found = _find_value_generic("the observation tower is 18m tall")
    assert found is None or found[1] not in ("million", "billion", "trillion", "thousand")


def test_bn_abbrev_consolidates_with_long_form() -> None:
    """``$16bn`` and ``$16 billion`` resolve to the SAME (value, unit) — the abbreviation folds
    onto its long form so corroborating sources consolidate rather than splitting into a
    ``bn`` vs ``billion`` pseudo-mismatch (§-1.3 basket faithfulness)."""
    abbrev = _find_value_generic("the market reached $16bn in revenue")
    longform = _find_value_generic("the market reached $16 billion in revenue")
    assert abbrev is not None and longform is not None
    assert abbrev[0] == longform[0] == 16.0
    assert abbrev[1] == longform[1] == "billion"


def test_garbage_only_rows_yield_no_numeric_claim() -> None:
    """The finding's exact rows (age-range row + journal-volume + superscript row) produce ZERO
    numeric claims, so no fabricated magnitude contradiction can be paired (GREEN)."""
    age_row = [{
        "evidence_id": "ev_008",
        "direct_quote": "The aggregate population covered adults ages 18–64 in the level analysis.",
        "source_url": "https://a.example", "tier": "T3",
    }]
    vol_row = [{
        "evidence_id": "ev_024",
        "direct_quote": "The firm-level figure appears in Sustainability 2024, 16, 8881 (see author Smith2).",
        "source_url": "https://b.example", "tier": "T4",
    }]
    assert extract_numeric_claims(age_row, domain="economics") == []
    assert extract_numeric_claims(vol_row, domain="economics") == []


def test_genuine_percentage_pair_still_detected_as_contradiction() -> None:
    """A genuine 14% vs 41% pair is STILL extracted and flagged as a REAL magnitude
    contradiction — the fix never suppresses a true same-metric disagreement (§-1.3)."""
    rows = [
        {"evidence_id": "c1", "direct_quote": "Semaglutide weight loss was 14% at week 68.",
         "source_url": "https://a", "tier": "T1"},
        {"evidence_id": "c2", "direct_quote": "Semaglutide weight loss was 41% at week 68.",
         "source_url": "https://b", "tier": "T1"},
    ]
    claims = extract_numeric_claims(rows, domain="clinical")
    assert {c.value for c in claims} == {14.0, 41.0}
    recs = detect_contradictions(claims, is_clinical=True)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.not_comparable is False
    assert POSSIBLE_METRIC_MISMATCH_MARKER not in rec.predicate
    assert rec.relative_difference > 1.0  # (41-14)/14 ≈ 1.93 — a real magnitude gap


# ──────────────────────────────────────────────────────────────────────────────
# (b) RENDER GUARD — a withheld pairing is not rendered as a magnitude disagreement
# ──────────────────────────────────────────────────────────────────────────────


def _finding19_records() -> list[dict[str, object]]:
    """The exact cert-artifact shape: two WITHHELD (possible_metric_mismatch) garbage pairs
    plus one GENUINE confirmed contradiction."""
    return [
        {"subject": "aggregate", "predicate": f"level {POSSIBLE_METRIC_MISMATCH_MARKER}",
         "relative_difference": 50.0, "severity": "high"},   # age-range 64-vs-1 -> "5000%"
        {"subject": "firm-", "predicate": f"level {POSSIBLE_METRIC_MISMATCH_MARKER}",
         "relative_difference": 7.0, "severity": "low"},      # volume-16-vs-superscript-2 -> "700%"
        {"subject": "semaglutide", "predicate": "weight loss",
         "relative_difference": 1.9286, "severity": "high"},  # genuine confirmed contradiction
    ]


def test_withheld_pair_not_rendered_as_magnitude_disagreement() -> None:
    """GREEN: with the fix (default), the two withheld garbage pairs are NOT counted as
    contradictions and their junk 5000% / 700% magnitudes never appear; only the genuine
    contradiction is counted; the withheld pairs are disclosed as 'possible mismatch'."""
    block = _format_telemetry_block(tier_fractions=None, contradictions=_finding19_records())
    # Only the genuine confirmed contradiction is counted.
    assert "contradictions_detected: 1" in block
    # The genuine magnitude disagreement is still surfaced.
    assert "semaglutide / weight loss: rel_diff 192.9%" in block
    # The withheld garbage magnitudes are NOT rendered as a disagreement.
    assert "5000.0%" not in block
    assert "700.0%" not in block
    # The withheld pairs are disclosed, but explicitly with no asserted magnitude.
    assert "possible_metric_mismatch: 2" in block
    assert "NO magnitude disagreement is asserted" in block
    assert "aggregate / level: possible mismatch" in block
    assert "firm- / level: possible mismatch" in block


def test_off_flag_restores_prefix_headline(monkeypatch: pytest.MonkeyPatch) -> None:
    """RED baseline / byte-identity lever: with the suppress flag OFF the withheld pairs are
    counted AND rendered as magnitude disagreements — the exact pre-fix bug this fixes."""
    monkeypatch.setenv("PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH", "0")
    block = _format_telemetry_block(tier_fractions=None, contradictions=_finding19_records())
    assert "contradictions_detected: 3" in block
    assert "5000.0%" in block   # the finding's "aggregate ... 5000.0%"
    assert "700.0%" in block    # the finding's "firm- ... 700.0%"


def test_confirmed_only_corpus_is_fully_counted() -> None:
    """A corpus with ONLY confirmed contradictions (no marker) is unaffected by the guard."""
    block = _format_telemetry_block(
        tier_fractions=None,
        contradictions=[
            {"subject": "semaglutide", "predicate": "weight loss",
             "relative_difference": 0.168, "severity": "medium"},
        ],
    )
    assert "contradictions_detected: 1" in block
    assert "16.8%" in block
    assert "possible_metric_mismatch" not in block


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
