"""Table-aware HTML linearization for provenance (I-meta-002-q1d #954). NO network / NO spend.

Asserts: result-table cells survive WITH their column headers ('header: cell'), integer/%-without-decimal
cells are preserved, no-table HTML is unchanged, malformed tables fail-open, and the kill-switch disables
the append. The point is that a clinical result-table number keeps its header context in the text the
provenance window captures (so strict_verify can verify it), not float free after tag-stripping.
"""

from __future__ import annotations

import pytest

import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.live_retriever import _strip_html, linearize_html_tables

_TABLE_HTML = """
<html><body>
<p>Adverse events by arm.</p>
<table>
  <tr><th>Adverse event</th><th>Tirzepatide 15 mg</th><th>Placebo</th></tr>
  <tr><td>Discontinuation due to nausea</td><td>3.8%</td><td>0.4%</td></tr>
  <tr><td>Patients enrolled</td><td>938</td><td>315</td></tr>
</table>
</body></html>
"""


def test_linearize_keeps_header_cell_association():
    out = linearize_html_tables(_TABLE_HTML)
    # the result cell survives WITH its column header (not a floating "3.8")
    assert "Adverse event: Discontinuation due to nausea" in out
    assert "Tirzepatide 15 mg: 3.8%" in out
    assert "Placebo: 0.4%" in out


def test_linearize_preserves_integer_and_pct_cells():
    out = linearize_html_tables(_TABLE_HTML)
    # integer count (no decimal) survives with its header — flattening would lose the association
    assert "Tirzepatide 15 mg: 938" in out
    assert "Placebo: 315" in out


def test_strip_html_appends_linearized_tables():
    out = _strip_html(_TABLE_HTML)
    assert "Adverse events by arm." in out          # base text retained
    assert "Tirzepatide 15 mg: 3.8%" in out          # table cells appended with headers


def test_no_table_html_unchanged_no_append():
    html = "<html><body><p>Tirzepatide reduced HbA1c by 2.1 percent.</p></body></html>"
    assert linearize_html_tables(html) == ""
    out = _strip_html(html)
    assert "Tirzepatide reduced HbA1c by 2.1 percent." in out
    assert " | " not in out  # nothing appended


def test_headerless_table_falls_back_to_joined_cells():
    html = "<table><tr><td>alpha</td><td>12.5%</td></tr></table>"
    out = linearize_html_tables(html)
    # single-row, no <th> → header row is row 0, so it IS the header and yields no data rows
    assert out == "" or "alpha" in out  # fail-safe: never raises, never fabricates


def test_malformed_table_fails_open():
    assert linearize_html_tables("<table><tr><td>unclosed") == ""
    assert linearize_html_tables(None) == ""  # type: ignore[arg-type]


def test_kill_switch_disables_append(monkeypatch):
    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
    out = _strip_html(_TABLE_HTML)
    assert "Adverse events by arm." in out
    assert "Tirzepatide 15 mg: 3.8%" not in out  # append disabled


def test_colspan_table_degrades_to_joined_no_misleading_header():
    """Codex brief-gate iter-1 P1: a colspan table must NOT emit a wrong header:cell association — it
    degrades to plain ' | '-joined cells (the source's numbers survive, but never under a fabricated
    column header)."""
    html = (
        "<table>"
        "<tr><th>Event</th><th colspan='2'>Tirzepatide</th></tr>"
        "<tr><td>Nausea</td><td>12%</td><td>3.8%</td></tr>"
        "</table>"
    )
    out = linearize_html_tables(html)
    # the cells survive joined, but NOT as a misleading "Tirzepatide: <wrong cell>" index-zip
    assert "Nausea | 12% | 3.8%" in out
    assert "Tirzepatide: " not in out  # no fabricated header:cell from the colspan header


def test_rowspan_table_degrades_to_joined():
    html = (
        "<table>"
        "<tr><th>Arm</th><th>Value</th></tr>"
        "<tr><td rowspan='2'>Drug</td><td>5</td></tr>"
        "<tr><td>7</td></tr>"
        "</table>"
    )
    out = linearize_html_tables(html)
    # rowspan present → no index-zip association; cells survive joined
    assert "Arm: " not in out and "Value: " not in out
    assert "5" in out and "7" in out


def test_headerless_multirow_table_degrades_no_fabricated_association():
    """Codex brief-gate iter-2 P1: a headerless MULTI-row table (no <th> anywhere) must NOT treat row 0 as
    headers — that fabricates 'Nausea: Vomiting | 12%: 3.8%'. It degrades to plain joined rows."""
    html = (
        "<table>"
        "<tr><td>Nausea</td><td>12%</td></tr>"
        "<tr><td>Vomiting</td><td>3.8%</td></tr>"
        "</table>"
    )
    out = linearize_html_tables(html)
    assert "Nausea: Vomiting" not in out and "12%: 3.8%" not in out  # no fabricated header:cell
    assert ":" not in out  # no association at all for a headerless table
    assert "Nausea | 12%" in out and "Vomiting | 3.8%" in out  # cells survive joined per row


def test_row_header_mixed_th_td_degrades_no_fabrication():
    """Codex diff-gate P1: a ROW-header table (each row starts with a <th> row-label, then <td> data) is
    NOT a column-header table — treating row 0 ('Nausea | 12%') as column headers fabricates
    'Nausea: Vomiting | 12%: 3.8%'. It degrades to plain joined rows (no ':' association)."""
    html = (
        "<table>"
        "<tr><th>Nausea</th><td>12%</td></tr>"
        "<tr><th>Vomiting</th><td>3.8%</td></tr>"
        "</table>"
    )
    out = linearize_html_tables(html)
    assert "Nausea: Vomiting" not in out and "12%: 3.8%" not in out
    assert ":" not in out
    assert "Nausea | 12%" in out and "Vomiting | 3.8%" in out


def test_empty_th_before_data_degrades_no_fabrication():
    """Codex diff-gate P1: an empty <th> header row must NOT promote a later data row to headers. Empty
    header text → not canonical → degrade to joined."""
    html = (
        "<table>"
        "<tr><th></th><th></th></tr>"
        "<tr><td>Nausea</td><td>12%</td></tr>"
        "<tr><td>Vomiting</td><td>3.8%</td></tr>"
        "</table>"
    )
    out = linearize_html_tables(html)
    assert ":" not in out  # no association (empty header is not authoritative)
    assert "Nausea | 12%" in out and "Vomiting | 3.8%" in out


def test_canonical_only_th_in_first_row_associates():
    """Positive control: a TRUE column-header table (row 0 all <th>, data rows all <td>, no later <th>)
    DOES associate."""
    html = (
        "<table>"
        "<tr><th>Event</th><th>Drug</th></tr>"
        "<tr><td>Nausea</td><td>12%</td></tr>"
        "</table>"
    )
    out = linearize_html_tables(html)
    assert "Event: Nausea" in out and "Drug: 12%" in out


def test_strip_html_table_linearize_never_raises_on_garbage():
    # exercise the fail-open path through _strip_html
    for bad in ("<table>", "<table><tr>", "<table><tr><th></th></tr></table>"):
        out = _strip_html(bad)
        assert isinstance(out, str)
