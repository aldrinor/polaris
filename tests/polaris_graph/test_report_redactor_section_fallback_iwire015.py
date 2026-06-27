"""I-wire-015 #1337 R5: TIER-4 section-level redaction fallback regression tests.

The post-gate redactor (``reconcile_report_against_verdicts``) used to ABORT the WHOLE report
(raise ``ReportRedactionError`` -> ``released_with_disclosed_gaps``, ~empty report) whenever ONE
un-VERIFIED claim could not be bounded to a span (TIER-1) or a body line / line-run (TIER-2). The
#1337 reconfirm3 failure: a single un-boundable chrome fragment collapsed an otherwise-good 25K-word
report to 363 words. TIER-4 narrows the blast radius to the markdown SECTION containing the claim:
the unsupported claim is STILL fully removed (faithfulness preserved — never ships), only that one
section's coverage is lost, every other section survives. Faithfulness is identical to the old abort;
only the blast radius changes.

These tests exercise the advisor's discriminating cases: section-withhold-not-whole-report,
flag-off-reverts-to-raise, normal-bounded-claim-unaffected, unsupported-never-ships, multi-occurrence
termination, and the section-straddle last-resort raise (no infinite loop).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.roles.report_redactor import (
    ReportRedactionError,
    reconcile_report_against_verdicts,
)

_FLAG = "PG_REDACT_SECTION_LEVEL_FALLBACK"


def _unbounded_within_section_report() -> tuple[str, dict, dict, str]:
    """A report whose un-VERIFIED claim is rendered SPLIT across two redactable body lines that a
    BLANK line separates (non-contiguous) within ONE section — so TIER-1 (per-line) and TIER-2
    (contiguous line-run) both fail, but the section body-join bounds it (TIER-4)."""
    claim = (
        "First half of the unsupported chrome claim sits on this line "
        "second half of the unsupported chrome claim ends here."
    )
    report = (
        "## Findings\n"
        "A verified statement that should survive intact.[1]\n"
        "\n"
        "## Risk Notes\n"
        "First half of the unsupported chrome claim sits on this line\n"
        "\n"
        "second half of the unsupported chrome claim ends here.[2]\n"
    )
    final_verdicts = {"05-001": "UNSUPPORTED"}
    audit_map = {"05-001": {"sentence": claim, "severity": "S3"}}
    return report, final_verdicts, audit_map, claim


def test_tier4_section_withhold_not_whole_report(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    report, verdicts, audit, claim = _unbounded_within_section_report()
    result = reconcile_report_against_verdicts(report, verdicts, audit)

    # The OTHER section survives intact (NOT a whole-report abort).
    assert "A verified statement that should survive intact." in result.report_text
    # The unsupported claim's prose is GONE (faithfulness: never ships).
    assert "First half of the unsupported chrome claim" not in result.report_text
    assert "second half of the unsupported chrome claim" not in result.report_text
    # Recorded as a SECTION-scope redaction (transparent in gaps.json).
    assert result.redacted_count == 1
    assert result.redacted[0].redaction_scope == "section"
    note = result.gaps_json()[0]["note"]
    assert "SECTION withheld" in note


def test_tier4_disabled_reverts_to_whole_report_raise(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    report, verdicts, audit, _claim = _unbounded_within_section_report()
    with pytest.raises(ReportRedactionError):
        reconcile_report_against_verdicts(report, verdicts, audit)


def test_normal_bounded_claim_unaffected(monkeypatch):
    """A normal single-line unsupported claim is still removed at CLAIM scope (TIER-1); the VERIFIED
    neighbour on the same line — and its citation marker — survive byte-for-byte. The TIER-4 fix
    must not change the normal redaction path."""
    monkeypatch.setenv(_FLAG, "1")
    report = (
        "## Findings\n"
        "A verified statement that should survive intact.[1] "
        "An unsupported claim on the same line should be removed cleanly.[2]\n"
    )
    verdicts = {"05-002": "UNSUPPORTED"}
    audit = {"05-002": {"sentence": "An unsupported claim on the same line should be removed cleanly.", "severity": "S2"}}
    result = reconcile_report_against_verdicts(report, verdicts, audit)

    assert "A verified statement that should survive intact." in result.report_text
    assert "[1]" in result.report_text  # VERIFIED neighbour keeps its citation
    assert "An unsupported claim on the same line" not in result.report_text
    assert result.redacted_count == 1
    assert result.redacted[0].redaction_scope == "claim"  # NOT a section withhold


def test_multi_occurrence_two_sections_terminates(monkeypatch):
    """The same un-boundable stem present in TWO sections withholds BOTH and terminates (no spin)."""
    monkeypatch.setenv(_FLAG, "1")
    claim = (
        "Leading clause of the unbounded duplicate claim "
        "trailing clause of the unbounded duplicate claim ends."
    )
    report = (
        "## Section A\n"
        "Leading clause of the unbounded duplicate claim\n"
        "\n"
        "trailing clause of the unbounded duplicate claim ends.[1]\n"
        "## Section B\n"
        "An unrelated verified statement survives here.[2]\n"
        "## Section C\n"
        "Leading clause of the unbounded duplicate claim\n"
        "\n"
        "trailing clause of the unbounded duplicate claim ends.[3]\n"
    )
    verdicts = {"05-003": "UNSUPPORTED"}
    audit = {"05-003": {"sentence": claim, "severity": "S3"}}
    result = reconcile_report_against_verdicts(report, verdicts, audit)

    assert "Leading clause of the unbounded duplicate claim" not in result.report_text
    assert "trailing clause of the unbounded duplicate claim" not in result.report_text
    assert "An unrelated verified statement survives here." in result.report_text  # Section B kept


def test_section_straddle_still_raises_last_resort(monkeypatch):
    """A claim that straddles a SECTION BOUNDARY (a heading between its halves) cannot be bounded to
    any single section -> TIER-4 returns False -> the true last-resort fail-closed raise fires (and
    the loop does NOT spin)."""
    monkeypatch.setenv(_FLAG, "1")
    claim = (
        "First half of the straddling unsupported claim is here "
        "second half of the straddling unsupported claim ends."
    )
    report = (
        "## Section A\n"
        "First half of the straddling unsupported claim is here\n"
        "## Section B\n"
        "second half of the straddling unsupported claim ends.[1]\n"
    )
    verdicts = {"05-004": "UNSUPPORTED"}
    audit = {"05-004": {"sentence": claim, "severity": "S3"}}
    with pytest.raises(ReportRedactionError):
        reconcile_report_against_verdicts(report, verdicts, audit)


def test_wrapped_citation_body_line_is_redactable(monkeypatch):
    """ROOT CAUSE of the #1337 reconfirm3 whole-report collapse: a body line that BEGINS with the
    WRAPPED trailing citations of the prior sentence ("[71][5][7][6] ...") was mis-classified as a
    non-redactable bibliography row, so an unsupported claim rendered on it could not be bounded by
    ANY tier -> whole-report abort. 2+ consecutive leading markers mark a redactable body line; the
    unsupported claim must be redacted precisely (CLAIM scope), the verified neighbour survives, and
    the report does NOT collapse."""
    monkeypatch.setenv(_FLAG, "1")
    claim = "Further unsupported research describes a fabricated metric of automation certainty."
    report = (
        "## Findings\n"
        "A verified statement that should survive intact.[1]\n"
        "## Evidence\n"
        f"[71][5][7][6] {claim} The verified neighbour stays put here.[2]\n"
    )
    verdicts = {"05-041": "UNSUPPORTED"}
    audit = {"05-041": {"sentence": claim, "severity": "S3"}}
    result = reconcile_report_against_verdicts(report, verdicts, audit)  # must NOT raise
    assert "A verified statement that should survive intact." in result.report_text
    assert "The verified neighbour stays put here." in result.report_text
    assert "fabricated metric of automation certainty" not in result.report_text
    assert result.redacted_count == 1
    assert result.redacted[0].redaction_scope == "claim"  # precise, NOT a collapse / section withhold


def test_single_marker_bibliography_line_protected(monkeypatch):
    """A genuine bibliography reference row ("[12] Autor, D. (2015). Title. Journal.") starts with a
    SINGLE citation marker and stays NON-redactable, so a coincidental stem match never rewrites a
    reference. (Paired with the wrapped-body test: single marker = protected, 2+ markers = body.)"""
    from src.polaris_graph.roles.report_redactor import _is_redactable_body_line
    assert _is_redactable_body_line("[12] Autor, D. (2015). The polarization of work. Journal of Econ.") is False
    assert _is_redactable_body_line("[71][5][7][6] Further research is needed on automation.") is True
    assert _is_redactable_body_line("A normal body sentence with a trailing citation.[3]") is True
    assert _is_redactable_body_line("## Heading") is False
    assert _is_redactable_body_line("") is False


def test_verified_claim_never_redacted(monkeypatch):
    """A VERIFIED claim is never touched, at any severity (regression guard)."""
    monkeypatch.setenv(_FLAG, "1")
    report = "## Findings\nA solidly verified claim about robots and wages.[1]\n"
    verdicts = {"05-005": "VERIFIED"}
    audit = {"05-005": {"sentence": "A solidly verified claim about robots and wages.", "severity": "S3"}}
    result = reconcile_report_against_verdicts(report, verdicts, audit)
    assert "A solidly verified claim about robots and wages." in result.report_text
    assert result.redacted_count == 0
