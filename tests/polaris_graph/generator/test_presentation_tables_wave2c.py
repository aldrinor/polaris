"""I-deepfix-001 Wave-2c (#1344) — presentation_tables MODULE offline proof.

Pure unit test — NO real LLM, NO GPU, NO network, NO IO. Exercises the deterministic
verified-number comparison-table renderer end to end:

  1. OFF no-op — kill-switch OFF => empty/no-op even with comparable claims.
  2. ON well-formed table — >=2 comparable claims => a GFM table (header + separator + data
     rows), TABLE_MARKER, verbatim numbers, citation markers.
  3. ON <2 comparable => empty (no single-row filler), for both one-claim and different-measure
     inputs.
  4. Verbatim numbers — a value string is never reformatted/rounded; list values kept verbatim.
  5. Deterministic ordering — same input => same table; shuffled distinct-entity input => same
     table; stable sort by entity then measure.
  6. Citation markers preserved — [N] and [#ev:...] markers survive verbatim.
  7. Faithfulness-neutral — no digit sequence appears in the table that is absent from some
     input claim (module invents no number).
  8. Smoke import.
"""

from __future__ import annotations

import importlib
import re

from src.polaris_graph.generator import presentation_tables as pt
from src.polaris_graph.generator.presentation_tables import (
    TABLE_MARKER,
    VerifiedNumericClaim,
    group_comparable_claims,
    render_comparison_table,
    render_presentation_tables,
)

_FLAG = "PG_PRESENTATION_TABLES"


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
def _enable(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")


def _disable(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)


def _gold_claims():
    """Three comparable 'gold price' claims across time-points (share measure + unit)."""
    return [
        {"entity": "Gold", "measure": "spot price", "value": "1,530.00", "unit": "USD/oz",
         "time_window": "2019", "citation": "[3]"},
        {"entity": "Gold", "measure": "spot price", "value": "2,060.50", "unit": "USD/oz",
         "time_window": "2020", "citation": "[4]"},
        {"entity": "Gold", "measure": "spot price", "value": "1,800.75", "unit": "USD/oz",
         "time_window": "2021", "citation": "[5]"},
    ]


# ── 1. OFF no-op ─────────────────────────────────────────────────────────────────────────────────
def test_off_is_noop_even_with_comparable_claims(monkeypatch):
    _disable(monkeypatch)
    res = render_presentation_tables(claims=_gold_claims())
    assert res.changed is False
    assert res.text == ""
    assert res.tables == 0


def test_off_values_all_disable(monkeypatch):
    for off in ("0", "false", "off", "no", ""):
        monkeypatch.setenv(_FLAG, off)
        res = render_presentation_tables(claims=_gold_claims())
        assert res.changed is False, f"{off!r} should disable"
        assert res.text == ""


def test_off_leaves_existing_report_untouched(monkeypatch):
    _disable(monkeypatch)
    report = "# Report\n\nBody text.\n"
    res = render_presentation_tables(claims=_gold_claims(), existing_report_md=report)
    assert res.changed is False
    # OFF returns the sentinel-empty text; caller inserts nothing => byte-identical report.
    assert res.text == ""


# ── 2. ON well-formed table ──────────────────────────────────────────────────────────────────────
def test_on_renders_well_formed_table(monkeypatch):
    _enable(monkeypatch)
    res = render_presentation_tables(claims=_gold_claims())
    assert res.changed is True
    assert res.tables == 1
    assert res.rows == 3
    assert TABLE_MARKER in res.text

    lines = [ln for ln in res.text.splitlines() if ln.strip().startswith("|")]
    # header + separator + 3 data rows
    assert len(lines) == 5
    header, separator = lines[0], lines[1]
    assert "Entity" in header and "Measure" in header and "Value" in header
    assert "Unit" in header and "Citation" in header
    assert set(separator.replace("|", "").replace("-", "").split()) == set()  # only ---/pipes
    # Each data row is a 5-column GFM row.
    for row in lines[2:]:
        assert row.count("|") == 6  # 5 cells => 6 pipe delimiters


def test_on_all_values_and_citations_present(monkeypatch):
    _enable(monkeypatch)
    res = render_presentation_tables(claims=_gold_claims())
    for claim in _gold_claims():
        assert claim["value"] in res.text
        assert claim["citation"] in res.text
        assert claim["time_window"] in res.text


# ── 3. ON <2 comparable => empty (no single-row filler) ──────────────────────────────────────────
def test_on_single_claim_returns_empty(monkeypatch):
    _enable(monkeypatch)
    res = render_presentation_tables(claims=_gold_claims()[:1])
    assert res.changed is False
    assert res.text == ""
    assert res.tables == 0


def test_on_different_measures_never_group(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "US", "measure": "unemployment rate", "value": "3.5", "unit": "%",
         "citation": "[1]"},
        {"entity": "US", "measure": "inflation rate", "value": "8.0", "unit": "%",
         "citation": "[2]"},
    ]
    res = render_presentation_tables(claims=claims)
    assert res.changed is False
    assert res.text == ""


def test_on_different_units_never_group(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "Fund A", "measure": "return", "value": "12", "unit": "%", "citation": "[1]"},
        {"entity": "Fund B", "measure": "return", "value": "1,200", "unit": "USD",
         "citation": "[2]"},
    ]
    res = render_presentation_tables(claims=claims)
    assert res.changed is False
    assert res.text == ""


def test_on_only_qualifying_group_emitted(monkeypatch):
    _enable(monkeypatch)
    claims = _gold_claims() + [
        {"entity": "Silver", "measure": "lone measure", "value": "22.0", "unit": "USD/oz",
         "citation": "[9]"},
    ]
    res = render_presentation_tables(claims=claims)
    assert res.changed is True
    assert res.tables == 1  # the lone 'lone measure' claim is dropped (no filler)
    assert res.rows == 3
    assert "lone measure" not in res.text


# ── 4. Verbatim numbers (never altered / rounded) ────────────────────────────────────────────────
def test_value_rendered_verbatim_not_reformatted(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "A", "measure": "m", "value": "3,200.50", "unit": "USD", "citation": "[1]"},
        {"entity": "B", "measure": "m", "value": "3,200.50", "unit": "USD", "citation": "[2]"},
    ]
    res = render_presentation_tables(claims=claims)
    assert "3,200.50" in res.text
    # None of the reformatted / rounded variants may appear.
    for bad in ("3200.5", "3,200.5 ", "3201", "3,201"):
        assert bad not in res.text


def test_unicode_minus_and_spacing_preserved(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "Arm 1", "measure": "change", "value": "−2.04", "unit": "kg", "citation": "[1]"},
        {"entity": "Arm 2", "measure": "change", "value": "12.9 kg", "unit": "kg",
         "citation": "[2]"},
    ]
    res = render_presentation_tables(claims=claims)
    assert "−2.04" in res.text          # unicode minus, not ASCII '-2.04'
    assert "12.9 kg" in res.text        # internal spacing preserved


def test_list_value_kept_verbatim(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "A", "measure": "range", "value": ["3,100", "3,300"], "unit": "USD",
         "citation": "[1]"},
        {"entity": "B", "measure": "range", "value": ["4,000", "4,200"], "unit": "USD",
         "citation": "[2]"},
    ]
    res = render_presentation_tables(claims=claims)
    for tok in ("3,100", "3,300", "4,000", "4,200"):
        assert tok in res.text


# ── 5. Deterministic ordering ────────────────────────────────────────────────────────────────────
def test_same_input_same_table(monkeypatch):
    _enable(monkeypatch)
    a = render_presentation_tables(claims=_gold_claims())
    b = render_presentation_tables(claims=_gold_claims())
    assert a.text == b.text


def test_shuffled_distinct_entities_same_table(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "Charlie", "measure": "score", "value": "3", "unit": "pt", "citation": "[3]"},
        {"entity": "Alice", "measure": "score", "value": "1", "unit": "pt", "citation": "[1]"},
        {"entity": "Bob", "measure": "score", "value": "2", "unit": "pt", "citation": "[2]"},
    ]
    forward = render_presentation_tables(claims=claims)
    reverse = render_presentation_tables(claims=list(reversed(claims)))
    assert forward.text == reverse.text
    # Sorted by entity: Alice before Bob before Charlie.
    assert forward.text.index("Alice") < forward.text.index("Bob") < forward.text.index("Charlie")


def test_shuffled_same_entity_different_time_window_same_table(monkeypatch):
    # Flagship gold-prices shape: ONE entity, ONE measure, several time-points. Ordering must be
    # input-order-independent via the time_window/value tiebreakers (not a stable-sort fallback).
    _enable(monkeypatch)
    claims = [
        {"entity": "Gold", "measure": "spot price", "value": "3", "unit": "USD/oz",
         "time_window": "2021", "citation": "[3]"},
        {"entity": "Gold", "measure": "spot price", "value": "1", "unit": "USD/oz",
         "time_window": "2019", "citation": "[1]"},
        {"entity": "Gold", "measure": "spot price", "value": "2", "unit": "USD/oz",
         "time_window": "2020", "citation": "[2]"},
    ]
    forward = render_presentation_tables(claims=claims)
    reverse = render_presentation_tables(claims=list(reversed(claims)))
    assert forward.text == reverse.text
    # sorted by time_window: 2019 before 2020 before 2021, regardless of input order.
    assert forward.text.index("2019") < forward.text.index("2020") < forward.text.index("2021")


def test_group_key_normalizes_case_and_whitespace(monkeypatch):
    _enable(monkeypatch)
    claims = [
        VerifiedNumericClaim(entity="X", measure="Spot  Price", value="1", unit="USD",
                             citation="[1]"),
        VerifiedNumericClaim(entity="Y", measure="spot price", value="2", unit="usd",
                             citation="[2]"),
    ]
    groups = group_comparable_claims(claims)
    assert len(groups) == 1  # differing case/whitespace still group as comparable


# ── 6. Citation markers preserved ────────────────────────────────────────────────────────────────
def test_ev_token_citation_preserved(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "A", "measure": "m", "value": "5", "unit": "u", "citation": "[#ev:src9:10-20]"},
        {"entity": "B", "measure": "m", "value": "6", "unit": "u", "citation": "[7]"},
    ]
    res = render_presentation_tables(claims=claims)
    assert "[#ev:src9:10-20]" in res.text
    assert "[7]" in res.text


# ── 7. Faithfulness-neutral: no invented numbers ─────────────────────────────────────────────────
def test_no_number_in_full_block_absent_from_inputs(monkeypatch):
    _enable(monkeypatch)
    claims = _gold_claims()
    res = render_presentation_tables(claims=claims, facet_label="Precious metals")
    # EVERY digit run anywhere in the ENTIRE rendered block (title, marker, disclosure note,
    # headers, separator, rows) must originate from an input value/citation/time_window. This is
    # the widened scan (the note itself must be digit-free — no internal doc reference leaks).
    source_blob = " ".join(
        f"{c['value']} {c['citation']} {c.get('time_window', '')}" for c in claims
    )
    source_digits = set(re.findall(r"\d[\d,\.]*", source_blob))
    for token in re.findall(r"\d[\d,\.]*", res.text):
        assert token in source_digits, f"invented numeric token {token!r} in rendered block"


def test_disclosure_note_has_no_internal_doc_reference(monkeypatch):
    _enable(monkeypatch)
    res = render_presentation_tables(claims=_gold_claims())
    # No internal doc-reference chrome may reach the user-facing / judged report.
    assert "CLAUDE.md" not in res.text
    assert "§" not in res.text


def test_incomplete_claims_skipped(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "A", "measure": "m", "value": "1", "unit": "u", "citation": "[1]"},
        {"entity": "", "measure": "m", "value": "2", "unit": "u", "citation": "[2]"},   # no entity
        {"entity": "C", "measure": "", "value": "3", "unit": "u", "citation": "[3]"},   # no measure
        {"entity": "D", "measure": "m", "value": "", "unit": "u", "citation": "[4]"},   # no value
    ]
    res = render_presentation_tables(claims=claims)
    # Only the single complete claim survives => <2 comparable => empty.
    assert res.changed is False
    assert res.text == ""


def test_missing_unit_and_citation_render_gap(monkeypatch):
    _enable(monkeypatch)
    claims = [
        {"entity": "A", "measure": "m", "value": "1"},
        {"entity": "B", "measure": "m", "value": "2"},
    ]
    res = render_presentation_tables(claims=claims)
    assert res.changed is True
    assert pt.GAP_CELL in res.text  # empty unit/citation => disclosed gap


# ── existing-report append + idempotency ─────────────────────────────────────────────────────────
def test_append_to_existing_report_and_idempotent(monkeypatch):
    _enable(monkeypatch)
    report = "# Report\n\nBody.\n"
    first = render_presentation_tables(claims=_gold_claims(), existing_report_md=report)
    assert first.changed is True
    assert first.text.startswith("# Report")
    assert TABLE_MARKER in first.text
    # A re-finalize over the already-marked report is a no-op (resume-safe).
    second = render_presentation_tables(claims=_gold_claims(), existing_report_md=first.text)
    assert second.changed is False
    assert second.text == first.text


# ── pure building block ──────────────────────────────────────────────────────────────────────────
def test_render_comparison_table_is_pure_and_flag_independent(monkeypatch):
    # The low-level renderer is NOT flag-gated (directly testable); it never touches the env.
    _disable(monkeypatch)
    rows = [_c for _c in (pt._coerce_claim(x) for x in _gold_claims()) if _c is not None]
    md = render_comparison_table(rows)
    assert TABLE_MARKER in md
    assert "1,530.00" in md and "2,060.50" in md and "1,800.75" in md


def test_render_comparison_table_empty_returns_empty():
    # Exported building block: an empty group must not IndexError on rows[0].
    assert render_comparison_table([]) == ""


# ── 8. smoke import ──────────────────────────────────────────────────────────────────────────────
def test_smoke_import():
    mod = importlib.import_module("src.polaris_graph.generator.presentation_tables")
    assert hasattr(mod, "render_presentation_tables")
    assert mod.presentation_tables_enabled.__module__.endswith("presentation_tables")
