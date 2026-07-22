"""Integration safety tests reproducing the two SAFETY BLOCKS Sol's integrated gate found, then
proving them fixed:
  FIX 1 — L2 synthesis-matrix cells must be grounded in their OWN cited sentence (no fabrication).
  FIX 2 — L5 cross-section consolidation can never destroy an L2 table block.
  FIX 3 — L6 reader-register Limitations is deterministic (no LLM fabrication surface).
"""
import importlib
import os

import pytest

MSG = "src.polaris_graph.generator.multi_section_generator"
GUARD = "src.polaris_graph.generator.cross_section_repetition_guard"

HEADER = "| Study | Context | Measure | Finding | Design | Ref |"
SEP = "|---|---|---|---|---|---|"


@pytest.fixture()
def msg(monkeypatch):
    monkeypatch.delenv("PG_SYNTHESIS_MATRIX", raising=False)
    monkeypatch.delenv("PG_SWEEP_TABLE_CELL_VERIFY", raising=False)
    return importlib.import_module(MSG)


def _table(rows):
    return "\n".join([HEADER, SEP, *rows])


# ---------------------------------------------------------------- FIX 1: L2 fabrication fail-closed
def test_fabricated_cell_drops_row(msg):
    # The cited sentence for [1] says nothing about "Stanford" or a "meta-analysis": invented cells.
    prose = (
        "Productivity rose 14% in one setting [1]. Output rose 34% elsewhere [2]. "
        "A further gain of 56% was reported [3]."
    )
    raw = _table([
        "| Stanford lab | biotech | throughput | 14% | meta-analysis | [1] |",
        "| B | y | m | 34% | rct | [2] |",
        "| C | z | m | 56% | rct | [3] |",
    ])
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3)
    # Row 1 ungrounded -> dropped -> < 3 rows -> whole table suppressed (fail-closed).
    assert out == ""


def test_number_on_wrong_citation_drops_row(msg):
    # The row cites [1] but asserts 99% — a value that appears only in the [2] sentence.
    prose = "Effect was 14% [1]. A different effect was 99% [2]. And another was 56% [3]."
    raw = _table([
        "| a | c | m | 99% | rct | [1] |",
        "| b | c | m | 14% | rct | [2] |",
        "| d | c | m | 56% | rct | [3] |",
    ])
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3)
    # Row 1's 99% is not in the [1] sentence -> dropped; row 2's 14% is not in the [2] sentence ->
    # dropped. Only row 3 grounded -> < 3 -> suppressed.
    assert out == ""


def test_grounded_table_survives(msg):
    prose = (
        "In a randomized trial on writing, output rose 34% [1]. "
        "In a randomized trial on coding, output rose 56% [2]. "
        "In a randomized trial on support, output rose 14% [3]."
    )
    raw = _table([
        "| writing | writing | output | 34% | randomized trial | [1] |",
        "| coding | coding | output | 56% | randomized trial | [2] |",
        "| support | support | output | 14% | randomized trial | [3] |",
    ])
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3)
    assert out.startswith(HEADER)
    assert out.count("\n") == 4


# ---------------------------------------------------------------- FIX 2: L5 never destroys a table
def test_guard_skips_table_units(monkeypatch):
    guard = importlib.import_module(GUARD)
    # A unit that absorbed a table row (contains a pipe) is never eligible for consolidation.
    assert guard._contains_table("Some prose [1]. | writing | x | m | 34% | rct | [1] |") is True
    assert guard._contains_table("Plain prose sentence with a citation [1].") is False


def test_consolidation_preserves_table_block(monkeypatch):
    guard = importlib.import_module(GUARD)
    monkeypatch.setenv("PG_CROSS_SECTION_REPETITION_GUARD", "1")

    class SR:
        def __init__(self, title, text):
            self.title = title
            self.verified_text = text
            self.dropped_due_to_failure = False
            self.is_gap_stub = False

    # Same duplicated finding in two sections + a table block appended in section 2. The duplicate
    # should consolidate, but the table block must survive byte-for-byte.
    dup = "Employment fell by 5 percentage points in exposed occupations [1]."
    table = "\n\n" + "\n".join([HEADER, SEP, "| a | b | c | 5% | rct | [1] |"])
    s1 = SR("Section One", dup + " More context here [2].")
    s2 = SR("Section Two", dup + " Extra detail [3]." + table)
    guard.consolidate_cross_section_repetition([s1, s2])
    # The table header + its row are still present verbatim in section 2 (never consumed/replaced).
    assert HEADER in s2.verified_text
    assert "| a | b | c | 5% | rct | [1] |" in s2.verified_text


# ---------------------------------------------------------------- FIX 3: L6 deterministic register
def test_reader_limitations_deterministic_no_fabrication(msg):
    text = msg._deterministic_reader_limitations(
        {"T1": 0.04, "T2": 0.01}, None, {"start": 2015, "end": 2025}, ["policy design"]
    )
    assert text.startswith("Limitations:")
    # 4% + 1% peer-reviewed => "5%" stated verbatim; no internal vocabulary leaks.
    assert "5%" in text
    for banned in ("telemetry", "pipeline", "T1", "T6", "tier"):
        assert banned not in text
    assert "2015-2025" in text
    assert "policy design" in text


def test_reader_limitations_stable(msg):
    a = msg._deterministic_reader_limitations({"T1": 0.1, "T2": 0.0}, None, None, None)
    b = msg._deterministic_reader_limitations({"T1": 0.1, "T2": 0.0}, None, None, None)
    assert a == b  # deterministic: same telemetry -> identical text
    assert "10%" in a
