"""I-wire-013 (#1327) — CONTRADICTION HARDEN behavioral tests.

Two pure (no-model) checks, one per fix point:

  1. Extraction hardening (``contradiction_detector._find_value_generic``): a UNIT-LESS number that
     sits inside a DOI suffix / arXiv id / ISSN / page range is a citation artifact, NOT a measured
     metric value. It must NOT be lifted as a generic metric value, so a (DOI-suffix, page-number)
     pair never surfaces as a fabricated ``possible_metric_mismatch`` contradiction. A genuine
     unit-bearing percentage IS still extracted (faithfulness unchanged).

  2. Render gate (``run_honest_sweep_r3._render_contradicts_block``): a contradiction record whose
     predicate carries the ``[possible_metric_mismatch]`` marker is the detector declaring it could
     NOT confirm a shared metric, so it is SKIPPED from the headline "Contradictions (both sides)"
     block, while a CONFIRMED shared-metric disagreement (47% vs 32% unemployment) STILL renders.
     Every claim of a skipped record stays disclosed in the contradictions.json sidecar (never
     dropped — §-1.3); only the misleading headline framing is suppressed.

Faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is untouched.
"""

from __future__ import annotations

import json

from scripts.run_honest_sweep_r3 import (
    _is_unconfirmed_metric_mismatch,
    _render_contradicts_block,
)
from src.polaris_graph.evaluator.external_evaluator import run_rule_checks
from src.polaris_graph.retrieval.contradiction_detector import (
    POSSIBLE_METRIC_MISMATCH_MARKER,
    detect_contradictions,
    extract_numeric_claims,
    _BIBLIOGRAPHIC_ID_RE,
    _find_value_generic,
)


def test_page_range_dash_class_matches_ranges_not_doi_suffix():
    """iter-2 (Codex P2-2): the page-range dash class is normalized to explicit codepoint escapes
    ``[\\-\\u2012\\u2013\\u2014\\u2015]`` (encoding-agnostic). It still matches a real page range with an
    ASCII hyphen AND an en-dash, and a bare DOI suffix's internal hyphens (no ``pp.``/``pages`` cue) are
    not mistaken for a page range — behaviour byte-for-byte equal to the prior literal class."""
    assert _BIBLIOGRAPHIC_ID_RE.search("pp. 12-19") is not None        # ASCII hyphen U+002D
    assert _BIBLIOGRAPHIC_ID_RE.search("pp. 12–19") is not None    # en dash U+2013
    assert _BIBLIOGRAPHIC_ID_RE.search("pages 412-419") is not None     # ASCII hyphen, 'pages' cue
    # a DOI suffix's internal hyphens are NOT a page range (no pp./pages cue, no '10.xxxx/' DOI prefix)
    assert _BIBLIOGRAPHIC_ID_RE.search("s41586-024-07123") is None


def test_bibliographic_numbers_not_extracted_as_metric_values():
    """A DOI suffix / arXiv id / ISSN / page-range number is never a generic metric value."""
    assert _find_value_generic("see DOI 10.1038/s41586-024-07123 for the dataset") is None
    assert _find_value_generic("preprint arXiv:2401.12345 reports the method") is None
    assert _find_value_generic("published under ISSN 0028-0836 last year") is None
    assert _find_value_generic("the result is discussed on pp. 412-419 of the volume") is None
    assert _find_value_generic("pages 412-419 cover the topic") is None
    # A genuine unit-bearing percentage IS still extracted (the conservative rule: only UNIT-LESS
    # numbers are screened; a value with a real unit is always a metric).
    found = _find_value_generic("the unemployment rate reached 47% in the region")
    assert found is not None
    assert found[0] == 47.0
    assert found[1] == "percent"


def test_doi_and_page_number_pair_not_emitted_as_metric_mismatch():
    """Two non-clinical rows whose only numbers are a DOI suffix and a page range share a generic
    metric cue ("rate") but carry NO real metric value, so NO possible_metric_mismatch is emitted."""
    evidence = [
        {
            "evidence_id": "a",
            "direct_quote": "The coverage rate study, DOI 10.1038/s41586-024-07123, examines policy.",
            "source_url": "http://example.org/a",
            "tier": "T5",
        },
        {
            "evidence_id": "b",
            "direct_quote": "The coverage rate review appears on pp. 412-419 here.",
            "source_url": "http://example.org/b",
            "tier": "T5",
        },
    ]
    claims = extract_numeric_claims(evidence, domain="economics")
    records = detect_contradictions(
        claims, rel_threshold=0.0001, abs_threshold=1.0, is_clinical=False
    )
    assert claims == []
    assert records == []
    assert not any(
        POSSIBLE_METRIC_MISMATCH_MARKER in (r.predicate or "") for r in records
    )


def test_render_skips_mismatch_keeps_confirmed_disagreement(tmp_path):
    """The render block skips a ``[possible_metric_mismatch]`` record but renders a confirmed
    shared-metric disagreement (47% vs 32% unemployment)."""
    records = [
        {
            "subject": "unemployment",
            "predicate": "rate " + POSSIBLE_METRIC_MISMATCH_MARKER,
            "relative_difference": 0.20,
            "claims": [
                {"evidence_id": "ev_a", "value": 5, "unit": "", "source_tier": "T5"},
                {"evidence_id": "ev_b", "value": 412, "unit": "", "source_tier": "T5"},
            ],
        },
        {
            "subject": "unemployment",
            "predicate": "unemployment rate",
            "relative_difference": 0.319,
            "claims": [
                {"evidence_id": "ev_c", "value": 47, "unit": "%", "source_tier": "T1"},
                {"evidence_id": "ev_d", "value": 32, "unit": "%", "source_tier": "T2"},
            ],
        },
    ]
    path = tmp_path / "contradictions.json"
    path.write_text(json.dumps(records), encoding="utf-8")

    out = _render_contradicts_block(str(path))

    # The mismatch record is skipped: neither the marker nor its distinctive page-number 412 appears.
    assert POSSIBLE_METRIC_MISMATCH_MARKER not in out
    assert "412" not in out
    # The confirmed disagreement STILL renders, with both opposing sides.
    assert "CONTRADICTS" in out
    assert "47" in out
    assert "32" in out


def test_leading_dash_year_not_extracted_as_metric_value():
    """iter-3b: a YEAR captured with a leading dash (e.g. "-2010" lifted from a "2009-2010" range)
    is recognised as a year, never a measured metric value — so a row whose only numbers are two
    years yields NO generic metric value (no fabricated possible_metric_mismatch)."""
    # "2009" is followed by "-", so only "-2010" is captured by the value regex; the abs-magnitude
    # year screen must still reject it. No real metric remains -> None.
    assert _find_value_generic("the coverage rate spanned 2009-2010 in scope") is None
    # A genuine unit-bearing percentage in the SAME row is still extracted (faithfulness unchanged).
    found = _find_value_generic("the rate over 2009-2010 reached 47% overall")
    assert found is not None
    assert found[0] == 47.0
    assert found[1] == "percent"


def test_doi_suffix_and_year_pair_not_emitted_as_metric_mismatch():
    """iter-3b: two non-clinical rows sharing a metric cue ("rate") whose only numbers are a DOI
    suffix and a (dash-captured) YEAR carry NO real metric value, so NO possible_metric_mismatch is
    emitted — the DOI-suffix/year render-noise class is killed at the detector."""
    evidence = [
        {
            "evidence_id": "a",
            "direct_quote": "The coverage rate dataset, DOI 10.1038/s41586-024-07123, is open.",
            "source_url": "http://example.org/a",
            "tier": "T7",
        },
        {
            "evidence_id": "b",
            "direct_quote": "The coverage rate figures spanned 2009-2010 in that review.",
            "source_url": "http://example.org/b",
            "tier": "T7",
        },
    ]
    claims = extract_numeric_claims(evidence, domain="economics")
    records = detect_contradictions(
        claims, rel_threshold=0.0001, abs_threshold=1.0, is_clinical=False
    )
    assert claims == []
    assert records == []


def test_is_unconfirmed_metric_mismatch_helper_record_and_dict():
    """iter-3b: the shared disclosure/PT08 filter flags a [possible_metric_mismatch] predicate on
    BOTH a record-like object and a serialized dict, and clears a confirmed disagreement."""
    class _Rec:
        def __init__(self, predicate):
            self.predicate = predicate

    assert _is_unconfirmed_metric_mismatch(_Rec("rate " + POSSIBLE_METRIC_MISMATCH_MARKER)) is True
    assert _is_unconfirmed_metric_mismatch({"predicate": "rate " + POSSIBLE_METRIC_MISMATCH_MARKER})
    assert _is_unconfirmed_metric_mismatch(_Rec("unemployment rate")) is False
    assert _is_unconfirmed_metric_mismatch({"predicate": "unemployment rate"}) is False
    assert _is_unconfirmed_metric_mismatch({}) is False


def test_pt08_passes_when_mismatch_withheld_but_disclosed_subset_intact():
    """iter-3b lock-step proof: PT08 (contradiction disclosure) MUST NOT abort when a
    possible_metric_mismatch record is deliberately withheld from the report, AS LONG AS the same
    record is excluded from the PT08 payload (the co-change). The UNFILTERED payload would falsely
    fail PT08; the FILTERED payload — exactly what run_one_query now passes — passes, while the
    confirmed disagreement still gates."""
    confirmed = {"subject": "unemployment", "predicate": "unemployment rate"}
    mismatch = {"subject": "technological", "predicate": "change " + POSSIBLE_METRIC_MISMATCH_MARKER}
    # The report discloses ONLY the confirmed disagreement (mirrors the printer skip).
    report_text = (
        "## Contradiction disclosures\n"
        "- unemployment / unemployment rate: cited values range 47 to 32 % (source tiers: T1).\n"
    )
    common = dict(
        report_text=report_text,
        protocol={},
        tier_distribution_report=None,
        evidence_pool={},
        generator_model="gen-model",
        evaluator_model="eval-model",
    )

    def _pt08(results):
        return next(r for r in results if r.item_id == "PT08")

    # UNFILTERED: the undisclosed mismatch trips PT08 (proves the filter is load-bearing).
    results_unfiltered, _, _ = run_rule_checks(contradictions=[confirmed, mismatch], **common)
    assert _pt08(results_unfiltered).passed is False

    # FILTERED (the run_one_query co-change): only the disclosed confirmed record gates -> PT08 OK.
    filtered = [c for c in [confirmed, mismatch] if not _is_unconfirmed_metric_mismatch(c)]
    results_filtered, _, _ = run_rule_checks(contradictions=filtered, **common)
    assert _pt08(results_filtered).passed is True
