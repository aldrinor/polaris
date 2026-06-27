"""Deterministic offline tests for the citation/truncation normalizer.

Strings are the REAL I-extract-001 ground-truth artifacts (LAW II: no synthetic
data) drawn from the banked ``drb_72_ai_labor`` cert report and its segmented
units (``outputs/audits/iextract001/ground_truth_units.json``):

* inline orphan glue (physical render form)  : ``...world.[8].[9][10] The ...``
* bare orphan units                          : ``[9][10]`` (u008/u057/u064),
                                               ``[9][10][8]`` (u062), ``.[19][20]`` (u058)
* mid-word truncation                        : ``...aggregate statis.; bstitution ...`` (u055)
* clean controls                             : trailing multi-citation (u056),
                                               OECD few-shot positive, abbreviation ``et al.;``

Pure-deterministic; no network, no LLM, no models loaded.
"""

from __future__ import annotations

from polaris_graph.generator.citation_truncation_normalizer import (
    ACTION_FLAGGED,
    ACTION_REPAIRED,
    FLAG_ORPHAN_INLINE_COLLAPSED,
    FLAG_ORPHAN_LINE_MIGRATED,
    FLAG_ORPHAN_UNATTACHED,
    FLAG_TRUNCATION_MIDWORD,
    normalize_citations_and_truncation,
)

# --- real substrate strings -------------------------------------------------
INLINE_GLUE_LINE = (
    "The past decades have witnessed major developments in artificial "
    "intelligence (AI) technology, and AI is set to influence every aspect of "
    "our lives, including the way production is organised, with the potential to "
    "increase economic growth substantially across the world.[8].[9][10] The "
    "deployment of AI applications has triggered an intense debate.[8]"
)
TRUNCATION_UNIT = (
    "types inform the theory of labor and technological change ( 1, 18, 21, 49), "
    "standard labor data focus on aggregate statis.; bstitution between skill "
    "groups.[15]"
)
TRUNCATION_FEWSHOT = "the model predicts employ.; ment growth across all sectors.[5][6]"
CLEAN_TRAILING_MULTICITE = (
    "Research is needed to estimate how jobs may be affected[12][4][5][6][7]"
)
CLEAN_OECD = (
    "A 2020 OECD study estimates that 14% of jobs are at high risk of automation "
    "across member countries.[11]"
)
CLEAN_ABBREVIATION = "see Smith et al.; however, others disagree about the magnitude."


def _kinds(result) -> list[str]:
    return [flag.kind for flag in result.flags]


def test_inline_glue_collapses_to_same_sentence() -> None:
    """``world.[8].[9][10]`` -> ``world.[8][9][10]`` (faithful, attribution kept)."""
    result = normalize_citations_and_truncation(INLINE_GLUE_LINE)
    assert "world.[8][9][10] The deployment" in result.text
    assert ".[9][10]" not in result.text  # the spurious-period glue is gone
    assert result.inline_collapsed == 1
    assert _kinds(result) == [FLAG_ORPHAN_INLINE_COLLAPSED]
    assert result.flags[0].action == ACTION_REPAIRED


def test_bare_orphan_migrates_to_adjacent_prose() -> None:
    """A bare ``[9][10]`` line re-attaches to the immediately preceding finding."""
    text = "\n".join(
        ["- The concept of the Fourth Industrial Revolution drives Industry 4.0.[8]", "[9][10]"]
    )
    result = normalize_citations_and_truncation(text)
    out = result.text.split("\n")
    assert out[0].endswith("Industry 4.0.[8][9][10]")
    assert len(out) == 1  # orphan line collapsed away
    assert result.orphan_migrated == 1
    assert result.orphan_flagged == 0
    assert FLAG_ORPHAN_LINE_MIGRATED in _kinds(result)


def test_bare_orphan_with_extra_cluster_migrates() -> None:
    """``[9][10][8]`` (u062) carries three tokens; all migrate, none deleted."""
    text = "\n".join(["- AI adoption is uneven across regions.[1]", "[9][10][8]"])
    result = normalize_citations_and_truncation(text)
    assert result.text == "- AI adoption is uneven across regions.[1][9][10][8]"
    assert result.orphan_migrated == 1


def test_bare_orphan_after_heading_is_flagged_not_deleted() -> None:
    """No adjacent prose owner (heading) -> flag-and-preserve, never guess/delete."""
    text = "\n".join(["## Key Findings", "[9][10]"])
    result = normalize_citations_and_truncation(text)
    assert result.text == text  # untouched
    assert result.orphan_migrated == 0
    assert result.orphan_flagged == 1
    assert FLAG_ORPHAN_UNATTACHED in _kinds(result)


def test_bare_orphan_after_blank_gap_is_flagged() -> None:
    """A blank gap breaks ownership -> flag-and-preserve."""
    text = "\n".join(["- A real finding about automation.[1]", "", "[9][10]"])
    result = normalize_citations_and_truncation(text)
    assert result.text == text
    assert result.orphan_flagged == 1
    assert result.orphan_migrated == 0


def test_leading_orphan_prefix_repaired_and_migrated() -> None:
    """``.[19][20] prose`` -> prefix migrates back, prose kept clean."""
    text = "\n".join(
        ["- A prior finding on robot exposure.[8]", "- .[19][20] The study found significant effects.[3]"]
    )
    result = normalize_citations_and_truncation(text)
    out = result.text.split("\n")
    assert out[0].endswith("robot exposure.[8][19][20]")
    assert out[1] == "- The study found significant effects.[3]"
    assert result.orphan_migrated == 1


def test_truncation_unit_is_flagged_only() -> None:
    """Mid-word ``statis.; bstitution`` flagged; text never altered."""
    result = normalize_citations_and_truncation(TRUNCATION_UNIT)
    assert result.text == TRUNCATION_UNIT  # flag-only, no repair
    assert result.truncation_flagged == 1
    trunc = [f for f in result.flags if f.kind == FLAG_TRUNCATION_MIDWORD]
    assert len(trunc) == 1
    assert trunc[0].offending_span == "statis.; bstitution"
    assert trunc[0].action == ACTION_FLAGGED


def test_truncation_fewshot_flagged() -> None:
    result = normalize_citations_and_truncation(TRUNCATION_FEWSHOT)
    assert result.truncation_flagged == 1
    assert result.text == TRUNCATION_FEWSHOT


def test_clean_controls_untouched() -> None:
    """Trailing multi-citation, normal sentence, and abbreviation must not fire."""
    for clean in (CLEAN_TRAILING_MULTICITE, CLEAN_OECD, CLEAN_ABBREVIATION):
        result = normalize_citations_and_truncation(clean)
        assert result.text == clean, clean
        assert result.flags == [], clean
        assert not result.changed, clean


def test_canary_reports_real_counts() -> None:
    """Behavioral canary carries the live per-run counts."""
    text = "\n".join([INLINE_GLUE_LINE, TRUNCATION_UNIT, "## Heading", "[9][10]"])
    result = normalize_citations_and_truncation(text)
    assert result.canary == (
        "[citation_normalizer] lines=4 inline_collapsed=1 orphan_migrated=0 "
        "orphan_flagged=1 truncation_flagged=1"
    )
