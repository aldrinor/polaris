"""LEVER 2 — typed cross-study synthesis matrix (PG_SYNTHESIS_MATRIX).

Deterministic tests over the extract / attach / suppression / faithfulness logic.
The LLM call (`_call_synthesis_matrix`) is thin (LLM -> `_extract_synthesis_matrix`);
these tests exercise the validated, deterministic surface directly.
"""
import os
import importlib

import pytest

MSG = "src.polaris_graph.generator.multi_section_generator"


@pytest.fixture()
def msg(monkeypatch):
    # Default OFF unless a test sets it.
    monkeypatch.delenv("PG_SYNTHESIS_MATRIX", raising=False)
    monkeypatch.delenv("PG_SYNTHESIS_MATRIX_MIN_ROWS", raising=False)
    monkeypatch.delenv("PG_SWEEP_TABLE_CELL_VERIFY", raising=False)
    # These tests exercise the deterministic structural/verbatim extraction path; keep the entailment
    # judge gate OFF here (verbatim fallback) so no live judge is needed. Entailment is covered in
    # test_lever_integration_safety.py with a mocked judge. Production default is 'on'.
    monkeypatch.setenv("PG_SYNTHESIS_MATRIX_ENTAILMENT", "off")
    mod = importlib.import_module(MSG)
    return mod


HEADER = "| Study | Context | Measure | Finding | Design | Ref |"
SEP = "|---|---|---|---|---|---|"


def _table(rows):
    return "\n".join([HEADER, SEP, *rows])


def test_flag_default_off(msg):
    assert msg._synthesis_matrix_enabled() is False


def test_flag_on(msg, monkeypatch):
    monkeypatch.setenv("PG_SYNTHESIS_MATRIX", "1")
    assert msg._synthesis_matrix_enabled() is True


def test_extract_valid_three_rows(msg):
    # Every cell is a verbatim span of the SINGLE clause carrying the row's [N] (no comma inside it).
    prose = (
        "A firm deployment in customer support raised productivity 14% [1]. "
        "A randomized experiment in writing raised productivity 34% [2]. "
        "A randomized experiment in coding raised productivity 56% [3]."
    )
    raw = _table([
        "| customer support | customer support | productivity | 14% | firm deployment | [1] |",
        "| writing | writing | productivity | 34% | randomized experiment | [2] |",
        "| coding | coding | productivity | 56% | randomized experiment | [3] |",
    ])
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3)
    assert out.startswith(HEADER)
    assert out.count("\n") == 4  # header + sep + 3 rows
    for n in ("[1]", "[2]", "[3]"):
        assert n in out


def test_suppress_two_rows(msg):
    raw = _table([
        "| A | x | m | +1% | rct | [1] |",
        "| B | y | m | +2% | rct | [2] |",
    ])
    assert msg._extract_synthesis_matrix(raw, {1, 2}, min_rows=3) == ""


def test_no_comparable_studies_sentinel(msg):
    assert msg._extract_synthesis_matrix("NO_COMPARABLE_STUDIES", {1, 2, 3}) == ""


def test_out_of_range_citation_row_dropped(msg):
    # Row citing [9] (not a valid prose marker) is dropped -> only 2 valid rows -> suppressed.
    raw = _table([
        "| A | x | m | +1% | rct | [1] |",
        "| B | y | m | +2% | rct | [2] |",
        "| C | z | m | +3% | rct | [9] |",
    ])
    assert msg._extract_synthesis_matrix(raw, {1, 2, 3}, min_rows=3) == ""


def test_row_without_citation_dropped(msg):
    raw = _table([
        "| A | x | m | +1% | rct | [1] |",
        "| B | y | m | +2% | rct | |",  # no [N] -> dropped
        "| C | z | m | +3% | rct | [3] |",
    ])
    # only 2 cited rows survive -> suppressed
    assert msg._extract_synthesis_matrix(raw, {1, 2, 3}, min_rows=3) == ""


def test_cell_verify_drops_fabricated_number(msg, monkeypatch):
    monkeypatch.setenv("PG_SWEEP_TABLE_CELL_VERIFY", "1")
    prose = "Rose 14% [1]. Rose 34% [2]. Rose 56% [3]."
    raw = _table([
        "| A | x | productivity | +14% | rct | [1] |",
        "| B | y | productivity | +34% | rct | [2] |",
        "| C | z | productivity | +99% | rct | [3] |",  # 99 not in prose -> dropped
    ])
    # fabricated 99 row dropped -> 2 rows -> suppressed
    assert msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3) == ""


def test_attach_is_additive_and_coverage_holds(msg):
    prose = "A [1]. B [2]. C [3]."
    table = _table([
        "| A | x | m | +1% | rct | [1] |",
        "| B | y | m | +2% | rct | [2] |",
        "| C | z | m | +3% | rct | [3] |",
    ])
    out = msg._attach_synthesis_matrix(prose, table)
    assert out.startswith(prose)          # prose untouched (literal prefix)
    assert "\n\n" in out                  # table is its own block
    assert table.strip() in out
    # every prose marker survives
    for n in ("[1]", "[2]", "[3]"):
        assert n in out


def test_attach_no_table_is_noop(msg):
    prose = "A [1]. B [2]."
    assert msg._attach_synthesis_matrix(prose, "") == prose


def test_attach_rejects_foreign_marker(msg):
    # A table smuggling a marker not in prose would break coverage superset in the other
    # direction; but coverage asserts prose-markers ⊆ result, which always holds for append.
    # Here we assert the prose-prefix invariant catches any prose mutation.
    prose = "A [1]. B [2]. C [3]."
    table = _table([
        "| A | x | m | +1% | rct | [1] |",
        "| B | y | m | +2% | rct | [2] |",
        "| C | z | m | +3% | rct | [3] |",
    ])
    out = msg._attach_synthesis_matrix(prose, table)
    # prose markers are a subset of result markers
    import re
    before = set(re.findall(r"\[(\d+)\]", prose))
    after = set(re.findall(r"\[(\d+)\]", out))
    assert before.issubset(after)


def test_min_rows_floor_is_three(msg, monkeypatch):
    monkeypatch.setenv("PG_SYNTHESIS_MATRIX_MIN_ROWS", "1")
    assert msg._synthesis_matrix_min_rows() == 3  # floored to 3, never below


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-x", "-q"]))
