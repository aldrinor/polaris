"""I-ready-015 (#1084) — table-cell faithfulness gate on the Trial Summary table.

Body prose goes through §9.1 strict_verify (every decimal must appear in its cited span), but the
LLM-emitted Trial Summary table cells did NOT — only the [N] citation marker was validated, not
the cell's NUMBER. So a mis-transcribed N / HR / endpoint value could survive. This gate (flag
`PG_SWEEP_TABLE_CELL_VERIFY`, default OFF) drops any row whose cell decimals are absent from the
strict_verified verified_prose (the table's sole fact source), reusing strict_verify._decimals.

Offline / cash-free: the raw table + verified_prose are inline (no LLM, no spend).
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import _extract_trial_summary_table

_HEADER = "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |"
_SEP = "|---|---|---|---|---|---|---|"

# Prose contains the decimals 200 and 42 (NOT 52).
_PROSE = "The ZORBLAX-7 trial enrolled 200 patients and showed a 42 percent reduction in the endpoint."


def _table(result_cell: str, ref: str = "[1]", n: str = "200") -> str:
    return (
        f"{_HEADER}\n{_SEP}\n"
        f"| ZORBLAX-7 | {n} | placebo | active drug | overall survival | {result_cell} | {ref} |"
    )


# ── flag-OFF: byte-identical (no gate) ──────────────────────────────────────

def test_flag_off_keeps_a_row_with_unverified_cell_number(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_TABLE_CELL_VERIFY", raising=False)
    # 52% is NOT in the prose, but with the gate OFF the row survives (today's behavior).
    out = _extract_trial_summary_table(_table("52% reduction"), {1}, verified_prose=_PROSE)
    assert "ZORBLAX-7" in out


def test_existing_two_arg_callers_unaffected(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_TABLE_CELL_VERIFY", "1")
    # No verified_prose → gate inert even when flag ON (backward-compat for existing callers/tests).
    out = _extract_trial_summary_table(_table("52% reduction"), {1})
    assert "ZORBLAX-7" in out


# ── flag-ON: the hole closes ────────────────────────────────────────────────

def test_flag_on_drops_row_with_fabricated_cell_number(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_TABLE_CELL_VERIFY", "1")
    # 52 is absent from the prose (which has 42) → the row is dropped → table suppressed.
    out = _extract_trial_summary_table(_table("52% reduction"), {1}, verified_prose=_PROSE)
    assert out == ""


def test_flag_on_keeps_row_whose_numbers_are_all_in_prose(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_TABLE_CELL_VERIFY", "1")
    # 200 (N) + 42 (Result) are both in the prose → kept.
    out = _extract_trial_summary_table(_table("42% reduction"), {1}, verified_prose=_PROSE)
    assert "ZORBLAX-7" in out
    assert "42% reduction" in out


def test_flag_on_no_decimal_row_is_unaffected(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_TABLE_CELL_VERIFY", "1")
    # A row with no numeric cells (text only) passes the numeric gate (nothing to verify).
    raw = (
        f"{_HEADER}\n{_SEP}\n"
        "| ZORBLAX-7 | many | placebo | active drug | overall survival | improved | [1] |"
    )
    out = _extract_trial_summary_table(raw, {1}, verified_prose="The ZORBLAX-7 trial improved survival.")
    assert "ZORBLAX-7" in out


def test_flag_on_citation_marker_not_treated_as_data(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_TABLE_CELL_VERIFY", "1")
    # The row cites [3]; 3 is NOT a prose decimal, but [N] markers are stripped before the numeric
    # check, so the row is kept (its DATA decimals 200 + 42 are in the prose).
    out = _extract_trial_summary_table(_table("42% reduction", ref="[3]"), {1, 3}, verified_prose=_PROSE)
    assert "ZORBLAX-7" in out


# ── reuses strict_verify._decimals (one numeric definition) ─────────────────

def test_gate_uses_strict_verify_decimals():
    import inspect
    from src.polaris_graph.generator import multi_section_generator as msg
    src = inspect.getsource(msg._extract_trial_summary_table)
    assert "from src.polaris_graph.clinical_generator.strict_verify import _decimals" in src
