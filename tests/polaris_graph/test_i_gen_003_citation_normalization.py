"""I-gen-003 (GH#495) — tests for the two deterministic report-layer
fixes that replaced the inert V4 Pro regen loop:

1. `_normalize_citation_punctuation` — cosmetic citation/punctuation
   normalization applied after provenance resolution. Inserts a missing
   sentence terminator at a genuine boundary, normalizes marker spacing,
   and (critically) byte-preserves every citation marker + evidence ID.
2. PT11 scope — the `Limitations` block is POLARIS-generated meta-prose
   (corpus-skew %, contradiction-detector relative-difference telemetry,
   completeness-gap counts), not empirical claims from sources. PT11
   must NOT score it — same category as the already-excluded Methods
   block. The Analyst Synthesis, by contrast, IS generator output and
   MUST stay in PT11 scope.
"""
from __future__ import annotations

from src.polaris_graph.evaluator.external_evaluator import run_rule_checks
from src.polaris_graph.generator.multi_section_generator import (
    _normalize_citation_punctuation,
)


# ── _normalize_citation_punctuation ──────────────────────────────────


def test_normalize_inserts_missing_terminator_at_boundary():
    """`word[N] Capital` — two sentences jammed together — gets the
    missing period inserted before the marker."""
    out = _normalize_citation_punctuation(
        "insulin secretion[1] GLP-1 receptor activation enhances it.[1]"
    )
    assert out == (
        "insulin secretion.[1] GLP-1 receptor activation enhances it.[1]"
    )


def test_normalize_leaves_already_terminated_text_untouched():
    text = "secretion.[1] GLP-1 activation rises.[2]"
    assert _normalize_citation_punctuation(text) == text


def test_normalize_byte_preserves_markers_and_evidence_ids():
    """The pass must NEVER add, remove, or alter a citation marker or
    an evidence ID — it is cosmetic-only (provenance invariant §9.1)."""
    src = "binds receptors[#ev:src_A:0-10] GLP-1 enhances[2][3] Insulin rises."
    out = _normalize_citation_punctuation(src)
    assert src.count("[") == out.count("[")
    assert src.count("]") == out.count("]")
    assert "[#ev:src_A:0-10]" in out
    assert "[2][3]" in out


def test_normalize_does_not_touch_mid_sentence_decimal():
    """A decimal mid-sentence followed by a lowercase continuation is
    NOT a sentence boundary — must be left alone."""
    text = "reduced HbA1c by 2.4%[1] and body weight fell"
    assert _normalize_citation_punctuation(text) == text


def test_normalize_handles_empty_and_marker_spacing():
    assert _normalize_citation_punctuation("") == ""
    # space before the marker is normalized away at a boundary
    assert (
        _normalize_citation_punctuation("secretion [1] GLP-1 rises.[1]")
        == "secretion.[1] GLP-1 rises.[1]"
    )


# ── PT11 scope: Limitations excluded, Analyst Synthesis included ──────

_PROTOCOL = {"sha256": "deadbeef" * 8}


def _pt11(report_text: str):
    results, _, _ = run_rule_checks(
        report_text=report_text,
        protocol=_PROTOCOL,
        tier_distribution_report=None,
        contradictions=[],
        evidence_pool={},
        generator_model="deepseek/deepseek-v4-pro",
        evaluator_model="google/gemma-4-31b-it",
    )
    return next(r for r in results if r.item_id == "PT11")


def test_pt11_ignores_limitations_telemetry_decimals():
    """Uncited decimals that live ONLY in the Limitations block (the
    contradiction-detector's own relative-difference telemetry) must
    NOT fail PT11 — they are not empirical claims from sources."""
    report = (
        "# Research report\n\n"
        "### Efficacy\n"
        "Tirzepatide reduced HbA1c by 2.4 percentage points in trials.[1]\n\n"
        "### Limitations\n"
        "Limitations: sources disagree on body weight (relative difference "
        "135.7%) and on weight loss (relative difference 269.0%).\n\n"
        "## Methods\n"
        "Tier bounds 30-60%. Retrieved 2026-05-14.\n"
    )
    pt11 = _pt11(report)
    assert pt11.passed, (
        f"PT11 must pass — the only uncited decimals are Limitations "
        f"telemetry, not source claims. details={pt11.details!r}"
    )


def test_pt11_still_flags_uncited_decimals_in_body_and_synthesis():
    """Control: the SAME decimals placed in body prose / Analyst
    Synthesis (real generator output) MUST still be PT11-scored — the
    exclusion is tightly scoped to the Limitations block only."""
    report = (
        "# Research report\n\n"
        "### Efficacy\n"
        "Body weight fell by 135.7 in one arm and 269.0 in another, "
        "and a comparator dose of 2.0 mg was noted, with no citations.\n\n"
        "### Limitations\n"
        "Limitations: the corpus is skewed toward lower-tier evidence.\n\n"
        "## Methods\n"
        "Retrieved 2026-05-14.\n"
    )
    pt11 = _pt11(report)
    assert not pt11.passed, (
        "PT11 must still FAIL when uncited decimals are in body prose — "
        "the Limitations exclusion must not leak into the rest of the report."
    )
