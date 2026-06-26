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

from scripts.run_honest_sweep_r3 import _render_contradicts_block
from src.polaris_graph.retrieval.contradiction_detector import (
    POSSIBLE_METRIC_MISMATCH_MARKER,
    detect_contradictions,
    extract_numeric_claims,
    _find_value_generic,
)


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
