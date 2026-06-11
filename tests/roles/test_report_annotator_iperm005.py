"""I-perm-005 (#1199) slice 2 — annotate_report_against_verdicts (keep + label).

The always-release sibling of the redactor: a non-VERIFIED claim is KEPT and LABELED with its
confidence marker (user judges), never DELETED. VERIFIED claims and their citation markers are
byte-identical; a genuinely-absent claim is recorded; a present-but-unlocatable claim fails closed
(never ships a non-VERIFIED claim as bare unlabeled prose).
"""

from __future__ import annotations

import pytest

from src.polaris_graph.roles.report_redactor import (
    ReportRedactionError,
    annotate_report_against_verdicts,
)

_VERIFIED_SENT = "Metformin lowered HbA1c by 0.8 percent over 24 weeks [1]."
_UNSUP_SENT = "The drug eliminated all cardiovascular events in every patient [2]."
_REPORT = f"## Findings\n\n{_VERIFIED_SENT} {_UNSUP_SENT}\n"

_AUDIT = {
    "c_ok": {"sentence": _VERIFIED_SENT, "severity": "S1"},
    "c_bad": {"sentence": _UNSUP_SENT, "severity": "S1"},
}
_MARKER = "[confidence: low — NOT confirmed by the cited source; treat as unverified]"


def test_keeps_verified_and_labels_unsupported():
    verdicts = {"c_ok": "VERIFIED", "c_bad": "UNSUPPORTED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {"c_bad": _MARKER})
    # The unsupported sentence is KEPT (not deleted) and carries the marker.
    assert _UNSUP_SENT in res.report_text
    assert _MARKER in res.report_text
    assert res.annotated_count == 1 and res.annotated[0].claim_id == "c_bad"
    # The verified sentence + its [1] marker are byte-identical (untouched).
    assert _VERIFIED_SENT in res.report_text
    assert "[1]" in res.report_text
    # No gap/redaction language was inserted.
    assert "did not survive verification" not in res.report_text


def test_marker_appended_after_the_sentence_not_replacing():
    verdicts = {"c_bad": "UNSUPPORTED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {"c_bad": _MARKER})
    # The sentence prose precedes the marker (label sits AFTER the claim).
    idx_sent = res.report_text.index("eliminated all cardiovascular events")
    idx_marker = res.report_text.index(_MARKER)
    assert idx_sent < idx_marker


def test_missing_marker_falls_back_to_low_never_unlabeled():
    verdicts = {"c_bad": "UNSUPPORTED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {})  # no marker supplied
    assert res.annotated_count == 1
    assert "[confidence: low" in res.report_text  # generic low fallback, never silently unlabeled


def test_absent_claim_recorded_not_raised():
    verdicts = {"c_gone": "UNSUPPORTED"}
    audit = {"c_gone": {"sentence": "A claim that is not present anywhere in the body [9].", "severity": "S2"}}
    res = annotate_report_against_verdicts(_REPORT, verdicts, audit, {})
    assert res.annotated_count == 0
    assert "c_gone" in res.already_absent


def test_no_audit_row_for_non_verified_fails_closed():
    with pytest.raises(ReportRedactionError):
        annotate_report_against_verdicts(_REPORT, {"c_x": "UNSUPPORTED"}, {}, {})


def test_verified_only_is_noop():
    res = annotate_report_against_verdicts(_REPORT, {"c_ok": "VERIFIED"}, _AUDIT, {})
    assert res.report_text == _REPORT
    assert res.annotated_count == 0


def test_partial_label_with_straddling_occurrence_fails_closed():
    """Codex slice-2 P0-1: a claim with one cleanly-pinnable occurrence AND one boundary-straddling
    occurrence must FAIL CLOSED — the clean hit must not suppress the raise for the unlabeled split
    occurrence (never ship a non-VERIFIED claim unlabeled)."""
    claim = "The therapy reversed organ failure in the cohort [3]."
    # Occurrence 1: clean (one sentence). Occurrence 2: split across two body lines so no single
    # rendered sentence covers it at the floor (a boundary under-split the annotator cannot pin).
    straddle_a = "The therapy reversed organ"
    straddle_b = "failure in the cohort overall across all enrolled sites and arms [4]."
    report = f"## Findings\n\n{claim}\n\n{straddle_a}\n{straddle_b}\n"
    audit = {"c": {"sentence": claim, "severity": "S1"}}
    with pytest.raises(ReportRedactionError):
        annotate_report_against_verdicts(report, {"c": "UNSUPPORTED"}, audit, {"c": _MARKER})


def test_clean_plus_same_line_straddle_tail_fails_closed():
    """Codex slice-2 iter-2 P0: a clean occurrence followed on the SAME line by a straddle-tail —
    the appended marker must not perturb segmentation so the split occurrence leaks. Must raise."""
    claim = "The therapy reversed organ failure in the cohort [3]."
    # clean occurrence, then (same line) the head of a straddle whose tail is on the next line.
    report = (
        f"## Findings\n\n{claim} The therapy reversed organ\n"
        "failure in the cohort overall across all enrolled sites [4].\n"
    )
    audit = {"c": {"sentence": claim, "severity": "S1"}}
    with pytest.raises(ReportRedactionError):
        annotate_report_against_verdicts(report, {"c": "UNSUPPORTED"}, audit, {"c": _MARKER})


def test_two_same_line_non_verified_claims_both_labeled():
    """Codex slice-2 iter-3 P0: two non-VERIFIED claims on the SAME line — each must get its OWN
    marker. The first claim's appended marker must not perturb the second's segmentation (the
    single-pass design reads spans off the original line)."""
    a = "Claim alpha asserts a strong protective effect [1]."
    b = "Claim beta asserts a separate causal mechanism [2]."
    report = f"## Findings\n\n{a} {b}\n"
    audit = {"a": {"sentence": a, "severity": "S1"}, "b": {"sentence": b, "severity": "S1"}}
    res = annotate_report_against_verdicts(
        report, {"a": "UNSUPPORTED", "b": "UNSUPPORTED"}, audit, {"a": _MARKER, "b": _MARKER}
    )
    assert res.report_text.count("[confidence:") == 2, res.report_text  # BOTH labeled
    assert res.annotated_count == 2


def test_idempotent_no_double_marker():
    verdicts = {"c_bad": "UNSUPPORTED"}
    once = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {"c_bad": _MARKER})
    twice = annotate_report_against_verdicts(once.report_text, verdicts, _AUDIT, {"c_bad": _MARKER})
    # The marker is not appended a second time (the sentence already carries it).
    assert twice.report_text.count(_MARKER) == 1


def test_idempotent_two_same_line_claims_rerun(monkeypatch):
    """Codex slice-2 iter-4 P1: re-running over already-annotated two-same-line output must NOT raise
    and must keep exactly one marker per claim (the pre-strip makes segmentation clean on re-run)."""
    a = "Claim alpha asserts a strong protective effect [1]."
    b = "Claim beta asserts a separate causal mechanism [2]."
    report = f"## Findings\n\n{a} {b}\n"
    audit = {"a": {"sentence": a, "severity": "S1"}, "b": {"sentence": b, "severity": "S1"}}
    verdicts = {"a": "UNSUPPORTED", "b": "UNSUPPORTED"}
    once = annotate_report_against_verdicts(report, verdicts, audit, {"a": _MARKER, "b": _MARKER})
    twice = annotate_report_against_verdicts(once.report_text, verdicts, audit, {"a": _MARKER, "b": _MARKER})
    assert twice.report_text.count("[confidence:") == 2  # still exactly two, no double, no raise
    assert twice.annotated_count == 2
