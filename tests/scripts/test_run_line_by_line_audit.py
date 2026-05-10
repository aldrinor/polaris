"""Tests for I-bakeoff-A-001 — line-by-line audit harness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_line_by_line_audit import (  # noqa: E402
    audit_sentence,
    run_line_by_line_audit,
)


def _pool(direct_quote: str, ev_id: str = "ev_x") -> dict:
    return {ev_id: {"evidence_id": ev_id, "direct_quote": direct_quote}}


def test_unsupported_when_no_token():
    s = "Tirzepatide reduced HbA1c by 1.5%."
    r = audit_sentence(s, _pool("ignored"))
    assert r["verdict"] == "UNSUPPORTED"
    assert r["reason"] == "no_provenance_token"


def test_unreachable_on_unknown_source():
    s = "Tirzepatide reduced HbA1c by 1.5% [#ev:nonexistent:0-50]."
    r = audit_sentence(s, _pool("ignored"))
    assert r["verdict"] == "UNREACHABLE"
    assert "unknown_evidence_id" in r["reason"]


def test_unreachable_on_span_out_of_range():
    span_text = "short"
    pool = _pool(span_text, "ev_x")
    s = f"Claim [#ev:ev_x:0-9999]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "UNREACHABLE"
    assert "span_out_of_range" in r["reason"]


def test_verified_when_decimals_match_and_overlap_ok():
    span_text = "Tirzepatide reduced HbA1c by 1.5% in adult patients with T2DM."
    pool = _pool(span_text, "ev_a")
    s = f"Tirzepatide reduced HbA1c by 1.5% in adult patients [#ev:ev_a:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "VERIFIED"
    assert r["decimals_match"] is True


def test_fabricated_when_numeric_mismatch_and_low_overlap():
    span_text = "GLP-1 RAs commonly studied in T2DM."
    pool = _pool(span_text, "ev_b")
    # Sentence asserts a number not in span, with minimal lexical overlap
    s = f"Tirzepatide cut weight by 22.5% in obese adults [#ev:ev_b:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "FABRICATED"
    assert "numeric_mismatch_AND_low_overlap" in r["reason"]


def test_partial_when_numeric_match_but_low_overlap():
    """Span contains only the matching decimal; sentence has the
    same decimal but additional content words not in the span.
    decimals_match=True, overlap=0 (span has no content words) → PARTIAL.
    """
    span_text = "1.5"  # just the number; no content words in span
    pool = _pool(span_text, "ev_c")
    # Sentence uses ONLY the matching decimal "1.5", no other numbers
    s = f"Tirzepatide reduction was 1.5 percent in patients [#ev:ev_c:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "PARTIAL", f"expected PARTIAL, got {r}"
    assert "low_content_overlap" in r["reason"]


def test_partial_when_overlap_ok_but_numeric_mismatch():
    span_text = "Tirzepatide reduced HbA1c in adult patients with T2DM."
    pool = _pool(span_text, "ev_d")
    # Sentence adds a decimal not in span
    s = f"Tirzepatide reduced HbA1c by 1.5% in adult patients [#ev:ev_d:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "PARTIAL"
    assert "numeric_mismatch" in r["reason"]


def test_run_audit_aggregates_summary():
    span_a = "Drug A reduced X by 1.5%."
    span_b = "Drug B reduced Y by 2.3%."
    pool = {
        "a": {"evidence_id": "a", "direct_quote": span_a},
        "b": {"evidence_id": "b", "direct_quote": span_b},
    }
    report = (
        f"Drug A reduced X by 1.5% [#ev:a:0-{len(span_a)}]. "
        f"Drug B reduced Y by 2.3% [#ev:b:0-{len(span_b)}]. "
        "Drug C cured everything."  # no token → UNSUPPORTED
    )
    result = run_line_by_line_audit(report, pool)
    s = result["summary"]
    assert s["total_sentences"] == 3
    assert s["verdict_counts"]["VERIFIED"] == 2
    assert s["verdict_counts"]["UNSUPPORTED"] == 1
    assert s["verified_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert s["alert"] is False  # no FABRICATED, no UNREACHABLE


def test_alert_fires_on_fabricated():
    span = "Drug A studied"
    pool = _pool(span, "a")
    report = f"Drug X cured 99.9% of patients [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    assert result["summary"]["verdict_counts"]["FABRICATED"] == 1
    assert result["summary"]["alert"] is True


def test_alert_fires_on_unreachable():
    pool = {}
    report = "Drug X did the thing [#ev:missing:0-5]."
    result = run_line_by_line_audit(report, pool)
    assert result["summary"]["verdict_counts"]["UNREACHABLE"] == 1
    assert result["summary"]["alert"] is True


def test_audit_md_render_includes_per_claim_table():
    """The {model}/audit.md format contains per-claim verdict rows
    + summary + recommendation per acceptance criterion.
    """
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A reduced X by 1.5%."
    pool = _pool(span, "a")
    report = f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    assert "# Line-by-line audit" in md
    assert "## Summary" in md
    assert "## Per-claim verdicts" in md
    assert "## Recommendation" in md
    assert "VERIFIED" in md


def test_audit_md_recommends_reject_on_fabricated():
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A studied"
    pool = _pool(span, "a")
    report = f"Drug X cured 99.9% of patients [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    assert "REJECT" in md.upper()


def test_audit_md_recommends_accept_on_high_verified():
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A reduced X by 1.5%"
    pool = _pool(span, "a")
    # 4 VERIFIED sentences → 100%
    report = "\n".join(
        f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]." for _ in range(4)
    )
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    assert "ACCEPT" in md.upper()


def test_canonical_evidencepool_source_id_schema():
    """I-bakeoff-A-001 iter-1 diff P1 fix: pool loader normalizes
    canonical retrieval2.EvidencePool schema (source_id + full_text)
    in addition to legacy {evidence_id + direct_quote}.
    """
    from scripts.run_line_by_line_audit import _normalize_pool

    canonical = {
        "sources": [
            {
                "source_id": "src-1",
                "full_text": "Drug A reduced X by 1.5%",
                "snippet": "fallback snippet",
            },
        ],
    }
    normalized = _normalize_pool(canonical)
    assert "src-1" in normalized
    assert normalized["src-1"]["direct_quote"] == "Drug A reduced X by 1.5%"

    # An audit on canonical-format pool should NOT produce UNREACHABLE
    span = "Drug A reduced X by 1.5%"
    sentence = f"Drug A reduced X by 1.5% [#ev:src-1:0-{len(span)}]."
    r = audit_sentence(sentence, normalized)
    assert r["verdict"] == "VERIFIED", (
        f"canonical schema not normalized correctly; got {r}"
    )


def test_canonical_verified_sentence_field_normalization():
    """I-bakeoff-A-001 iter-1 diff P1 fix: sentence loader accepts
    canonical VerifiedSentence schema (sentence_text field) in
    addition to {sentence: ...}.
    """
    from scripts.run_line_by_line_audit import _normalize_sentence

    assert _normalize_sentence({"sentence": "S1"}) == "S1"
    assert _normalize_sentence({"sentence_text": "S2"}) == "S2"
    assert _normalize_sentence("S3 raw") == "S3 raw"
    assert _normalize_sentence({}) == ""
    assert _normalize_sentence({"unrelated": "x"}) == ""


def test_audit_md_includes_cited_span_quote():
    """I-bakeoff-A-001 iter-1 diff P2 fix: per CLAUDE.md §-1.1 the audit
    table includes the cited span quote that supports each verdict.
    """
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A reduced X by 1.5%"
    pool = _pool(span, "a")
    report = f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    # The cited span must appear in the rendered markdown
    assert "Drug A reduced X by 1.5%" in md
    assert "Cited span quote" in md  # column header


def test_per_sentence_output_truncates_long_sentences():
    """The per-sentence dump caps sentence preview at 200 chars to
    keep the audit manifest readable.
    """
    long_sentence = "a " * 200
    span = "a a a a a"
    pool = _pool(span, "a")
    s = f"{long_sentence}[#ev:a:0-{len(span)}]."
    r = audit_sentence(s, pool)
    assert len(r["sentence"]) <= 200
