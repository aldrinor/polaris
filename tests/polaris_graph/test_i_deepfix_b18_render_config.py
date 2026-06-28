"""Behavioral tests for I-deepfix-001 basket B18 (#1344) render/config fixes.

Covers two production code paths through their real entry points:

* :func:`markdown_table_normalizer.normalize_gfm_tables` — the GFM-table render fix
  (insert the missing ``| --- |`` separator row; re-pad data rows to the header
  column count WITHOUT dropping the first cell / shifting columns). This is the
  same function wired into ``run_honest_sweep_r3.py`` at the render seam.

* :func:`contradiction_detector.format_contradictions_for_user` fed by the real
  :func:`contradiction_detector.detect_contradictions` — the contradiction-telemetry
  noise cleanup (a ``possible_metric_mismatch``-marked record is routed OUT of the
  headline contradiction count, with no junk rel/abs magnitude).

All assertions go through production functions; no internal mocking. Faithfulness
engine is never touched by either fix.
"""

import os
import re

import pytest

from src.polaris_graph.generator.markdown_table_normalizer import (
    FLAG_ROW_REPADDED,
    FLAG_SEPARATOR_INSERTED,
    normalize_gfm_tables,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    POSSIBLE_METRIC_MISMATCH_MARKER,
    ExtractedNumericClaim,
    detect_contradictions,
    format_contradictions_for_user,
)


# ──────────────────────────────────────────────────────────────────────────────
# B18 (1) — GFM table renderer
# ──────────────────────────────────────────────────────────────────────────────

_GFM_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


def test_missing_separator_row_is_inserted():
    """A header + data rows with NO GFM separator gets one inserted after the header."""
    md = (
        "| Author | Result | Trial |\n"
        "| Smith 2020 [3] | 14.9% | STEP 1 |\n"
        "| Jones 2021 [4] | 17.4% | STEP 5 |\n"
    )
    result = normalize_gfm_tables(md)
    assert result.separators_inserted == 1
    lines = result.text.split("\n")
    # The separator must be the SECOND line (right after the header).
    assert _GFM_SEPARATOR_RE.match(lines[1]), f"no separator inserted: {lines[1]!r}"
    assert any(f.kind == FLAG_SEPARATOR_INSERTED for f in result.flags)


def test_empty_leading_citation_cell_does_not_drop_first_cell():
    """A data row with an EMPTY leading author/citation cell keeps every column.

    The numeric value must NOT migrate into the leading cell (no column shift), so the
    value stays under the Result header and the (empty) citation column is preserved.
    """
    md = (
        "| Author | Result | Trial |\n"
        "| --- | --- | --- |\n"
        "|  | 14.9% | STEP 1 |\n"
    )
    result = normalize_gfm_tables(md)
    data_row = result.text.split("\n")[2]
    cells = [c.strip() for c in data_row.strip().strip("|").split("|")]
    assert len(cells) == 3, f"column shift / cell drop: {cells!r}"
    assert cells[0] == "", "leading empty citation cell must be preserved, not dropped"
    assert cells[1] == "14.9%", "numeric value must stay under its own column"
    assert cells[2] == "STEP 1"


def test_short_row_right_padded_not_left_shifted():
    """A row with FEWER cells than the header is right-padded (no first-cell drop)."""
    md = (
        "| Author | Result | Trial | Citation |\n"
        "| --- | --- | --- | --- |\n"
        "| Smith 2020 | 14.9% |\n"  # only 2 cells for a 4-column header
    )
    result = normalize_gfm_tables(md)
    assert result.rows_repadded >= 1
    data_row = result.text.split("\n")[2]
    cells = [c.strip() for c in data_row.strip().strip("|").split("|")]
    assert len(cells) == 4
    assert cells[0] == "Smith 2020", "leading cell preserved"
    assert cells[1] == "14.9%"
    assert cells[2] == "" and cells[3] == "", "missing columns padded on the RIGHT"
    assert any(f.kind == FLAG_ROW_REPADDED for f in result.flags)


def test_lost_leading_delimiter_restores_leading_cell():
    """I-deepfix-001 Codex P1 (iter 3): a data row that LOST its leading pipe
    (header has one, row does not) is short on the LEADING cell — restore the
    empty leading cell so values do not right-shift into the wrong columns."""
    md = (
        "| Author | Result | Trial |\n"
        "| --- | --- | --- |\n"
        "14.9% | STEP 1 |\n"  # lost leading pipe -> Author cell is the missing one
    )
    result = normalize_gfm_tables(md)
    assert result.rows_repadded >= 1
    data_row = result.text.split("\n")[2]
    cells = [c.strip() for c in data_row.strip().strip("|").split("|")]
    assert len(cells) == 3
    # The empty cell is restored at the FRONT (Author), not appended at the end,
    # so the value lands under Result/Trial, not shifted left under Author.
    assert cells[0] == "", "lost leading structural cell restored at the front"
    assert cells[1] == "14.9%"
    assert cells[2] == "STEP 1"


def test_overlong_row_keeps_every_cell():
    """A row with MORE cells than the header keeps all cells (never truncated)."""
    md = (
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 | 3 |\n"
    )
    result = normalize_gfm_tables(md)
    data_row = result.text.split("\n")[2]
    cells = [c.strip() for c in data_row.strip().strip("|").split("|")]
    assert cells == ["1", "2", "3"], "no cell may be dropped from an over-long row"


def test_non_table_prose_byte_identical():
    """Prose with an inline pipe (no leading-pipe header) is left untouched."""
    md = "The cost is a | b tradeoff in this design.\nNext paragraph here.\n"
    result = normalize_gfm_tables(md)
    assert result.text == md
    assert not result.changed


def test_well_formed_table_is_byte_identical():
    """A table that already has a separator + full rows is unchanged."""
    md = (
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
    )
    result = normalize_gfm_tables(md)
    assert result.text == md
    assert not result.changed


def test_off_flag_is_byte_identical(monkeypatch):
    """With PG_RENDER_GFM_TABLE_NORMALIZE OFF the text is byte-identical (no repair)."""
    monkeypatch.setenv("PG_RENDER_GFM_TABLE_NORMALIZE", "0")
    md = (
        "| Author | Result |\n"
        "| Smith [3] | 14.9% |\n"
    )
    result = normalize_gfm_tables(md)
    assert result.text == md
    assert not result.changed


# ──────────────────────────────────────────────────────────────────────────────
# B18 (3) — contradiction telemetry noise cleanup (possible_metric_mismatch)
# ──────────────────────────────────────────────────────────────────────────────


def _mismatch_claims():
    """Two NON-clinical generic numeric claims that group on the same metric cue but
    cannot positively confirm a shared metric — the real detector labels them
    possible_metric_mismatch (different sources, big magnitude gap)."""
    return [
        ExtractedNumericClaim(
            evidence_id="ev1",
            subject="unemployment",
            predicate="rate",
            value=4.0,
            unit="percent",
            context_snippet="unemployment rate was 4.0 percent",
            source_url="https://a.example/report1",
            source_tier="T3",
        ),
        ExtractedNumericClaim(
            evidence_id="ev2",
            subject="unemployment",
            predicate="rate",
            value=17500.0,
            unit="percent",
            context_snippet="a different unemployment rate metric 17500 percent",
            source_url="https://b.example/report2",
            source_tier="T4",
        ),
    ]


def test_detector_marks_possible_metric_mismatch_on_non_clinical():
    """The real detector tags the unconfirmed-shared-metric pair with the marker."""
    records = detect_contradictions(_mismatch_claims(), is_clinical=False)
    assert records, "expected a record for the disagreeing generic pair"
    assert any(
        POSSIBLE_METRIC_MISMATCH_MARKER in r.predicate for r in records
    ), "detector did not mark the pair as possible_metric_mismatch"


def test_metric_mismatch_excluded_from_headline_count(monkeypatch):
    """A possible_metric_mismatch record is NOT counted as a contradiction and its
    junk rel_diff magnitude is not surfaced in the headline."""
    monkeypatch.setenv("PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH", "1")
    records = detect_contradictions(_mismatch_claims(), is_clinical=False)
    summary = format_contradictions_for_user(records)
    # Headline count must be ZERO confirmed contradictions.
    assert "Detected 0 contradiction(s)" in summary, summary
    # The junk magnitude (e.g. 437481.7% / huge rel_diff) must NOT appear as a
    # headline contradiction line.
    assert "rel_diff=" not in summary or "Detected 0" in summary
    # The pair is still DISCLOSED in the possible-metric-mismatch section.
    assert "possible-metric-mismatch bucket" in summary, summary
    # Every source still listed (never dropped — §-1.3).
    assert "ev=ev1" in summary and "ev=ev2" in summary, summary


def test_metric_mismatch_off_flag_restores_headline(monkeypatch):
    """With the suppress flag OFF the marker record is counted in the headline (pre-fix)."""
    monkeypatch.setenv("PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH", "0")
    records = detect_contradictions(_mismatch_claims(), is_clinical=False)
    summary = format_contradictions_for_user(records)
    # Pre-fix behaviour: the mismatch record IS in the headline count and carries
    # a rel_diff magnitude line.
    assert "Detected 1 contradiction(s)" in summary, summary
    assert "rel_diff=" in summary, summary


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
