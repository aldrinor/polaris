"""Standalone tests for the render-only repetition dedup (I-deepfix-001 #1344).

These prove the fix does NOT over-reach: it is a purely cosmetic pass on the
final report.md markdown TEXT, downstream of the faithfulness engine. The
negative controls are the anti-over-reach evidence.
"""
import copy

from src.polaris_graph.generator.render_repetition_dedup import (
    dedup_rendered_report_markdown,
)


def test_forced_positive_duplicate_body_sentence_dropped():
    """A verbatim claim sentence repeated across two body sections keeps the
    first occurrence and drops the later one."""
    claim = "Tirzepatide reduced HbA1c by 2.1 percentage points versus placebo [12]."
    report = (
        "# Report\n\n"
        "## Efficacy\n\n"
        f"{claim} It was well tolerated overall [13].\n\n"
        "## Discussion\n\n"
        f"{claim} Further trials are warranted [14].\n"
    )
    out = dedup_rendered_report_markdown(report)
    # Kept exactly once.
    assert out.count(claim) == 1
    # The first (Efficacy) occurrence survived; the unique surrounding sentences stay.
    assert "It was well tolerated overall [13]." in out
    assert "Further trials are warranted [14]." in out
    # Headings untouched.
    assert "## Efficacy" in out and "## Discussion" in out


def test_negative_control_different_sentences_both_kept():
    """Two sentences with DIFFERENT text -> both kept."""
    report = (
        "## Body\n\n"
        "Semaglutide lowered body weight by 14.9 percent over 68 weeks [1]. "
        "Liraglutide lowered body weight by 8.0 percent over 56 weeks [2].\n"
    )
    out = dedup_rendered_report_markdown(report)
    assert "Semaglutide lowered body weight by 14.9 percent over 68 weeks [1]." in out
    assert "Liraglutide lowered body weight by 8.0 percent over 56 weeks [2]." in out


def test_negative_control_duplicate_with_additional_citation_merged():
    """A duplicate carrying an ADDITIONAL [N] -> kept copy GAINS the [N]; no source lost."""
    sentence_a = "Metformin remained first-line therapy across all six guidelines [3]."
    sentence_b = "Metformin remained first-line therapy across all six guidelines [7]."
    report = (
        "## Overview Body\n\n"
        f"{sentence_a}\n\n"
        "## Guidelines\n\n"
        f"{sentence_b}\n"
    )
    out = dedup_rendered_report_markdown(report)
    # Later duplicate dropped.
    assert sentence_b not in out
    # Kept copy now carries BOTH citation ids — no source lost.
    assert "[3]" in out
    assert "[7]" in out
    # Exactly one rendered copy of the claim text remains.
    assert out.count("Metformin remained first-line therapy across all six guidelines") == 1


def test_negative_control_headings_and_structure_untouched():
    """### slot headings, tables, and non-duplicate content are byte-identical."""
    report = (
        "# Title\n\n"
        "## Methods\n\n"
        "### Data Sources\n\n"
        "We searched three databases for eligible randomized trials [4].\n\n"
        "| Drug | Dose |\n"
        "| --- | --- |\n"
        "| A | 10mg |\n\n"
        "### Analysis Plan\n\n"
        "Random-effects meta-analysis pooled the standardized mean differences [5].\n"
    )
    out = dedup_rendered_report_markdown(report)
    # No duplicates present -> byte-for-byte identical (round-trip invariant).
    assert out == report
    # Explicit heading + table survival.
    for marker in ("### Data Sources", "### Analysis Plan", "| Drug | Dose |", "| --- | --- |"):
        assert marker in out


def test_front_key_findings_not_gutted_from_body():
    """The front Key Findings block extracts a body sentence verbatim; the body
    copy MUST survive (front summary is exempt, never registered as the kept
    first occurrence)."""
    headline = "The pooled hazard ratio for cardiovascular death was 0.82 [9]."
    report = (
        "## Key Findings\n\n"
        f"- {headline}\n\n"
        "## Cardiovascular Outcomes\n\n"
        f"{headline} This effect was consistent across subgroups [10].\n"
    )
    out = dedup_rendered_report_markdown(report)
    # BOTH the front bullet and the body sentence remain (no gutting).
    assert out.count(headline) == 2
    assert "This effect was consistent across subgroups [10]." in out


def test_section_never_emptied_by_dedup():
    """If every eligible sentence in a section is a duplicate, the section keeps
    its first sentence rather than becoming an empty heading."""
    claim = "Adverse events were balanced between the treatment arms in the trial [6]."
    report = (
        "## Safety\n\n"
        f"{claim}\n\n"
        "## Tolerability\n\n"
        f"{claim}\n"
    )
    out = dedup_rendered_report_markdown(report)
    # First occurrence kept; the second section is not emptied (restored).
    assert out.count(claim) == 2
    assert "## Tolerability" in out


def test_faithfulness_inputs_are_byte_identical_after_pass():
    """The pass is str->str and touches NOTHING the faithfulness engine reads.
    A representative D8 / verification-input structure passed ALONGSIDE the call
    is unchanged — the function has no access to it."""
    d8_inputs = {
        "kept_sentences_pre_resolve": [
            {"sv": "abc123", "text": "Sentence one [1]."},
            {"sv": "def456", "text": "Sentence two [2]."},
        ],
        "verification": {"tokens": ["[#ev:1:0-10]", "[#ev:2:5-20]"]},
        "evidence_pool": {"1": "span one", "2": "span two"},
    }
    frozen = copy.deepcopy(d8_inputs)
    report = (
        "## Body\n\n"
        "Sentence one [1]. Sentence one [1]. Sentence two here is unique [2].\n"
    )
    _ = dedup_rendered_report_markdown(report)
    # D8/verification inputs are byte-identical before vs after (never passed in).
    assert d8_inputs == frozen


def test_short_fragments_not_deduped():
    """Fail-open precision guard: short repeated fragments are never collapsed."""
    report = "## Body\n\nNot applicable. Not applicable. See table one below now [1].\n"
    out = dedup_rendered_report_markdown(report)
    assert out.count("Not applicable.") == 2


def test_idempotent():
    """Running the pass twice is stable (no residual duplicates re-processed)."""
    claim = "Empagliflozin reduced hospitalization for heart failure by 35 percent [8]."
    report = f"## A\n\n{claim}\n\n## B\n\n{claim} Extra unique framing sentence here [9].\n"
    once = dedup_rendered_report_markdown(report)
    twice = dedup_rendered_report_markdown(once)
    assert once == twice


def test_empty_and_non_string_inputs_fail_open():
    assert dedup_rendered_report_markdown("") == ""
    assert dedup_rendered_report_markdown(None) is None
