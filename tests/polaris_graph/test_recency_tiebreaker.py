"""Tests for the #955 within-tier recency tiebreaker in evidence_selector. NO network / NO spend.

Asserts recency is a SOFT tiebreaker: within the same tier AND same relevance band a newer row sorts
first, but recency NEVER crosses a higher relevance band (a more-relevant older row always wins), NEVER
hard-drops a row (undated rows stay eligible), and the kill-switch restores byte-identical prior ordering.
"""

from __future__ import annotations

import pytest

import src.polaris_graph.retrieval.evidence_selector as es
from src.polaris_graph.retrieval.evidence_selector import (
    _recency_epsilon,
    _relevance_band,
    _relevance_recency_key,
    _row_year,
    _year_sort_value,
    select_evidence_for_generation,
)

_Q = "tirzepatide reduction outcome glucose"


def _row(stmt, *, tier="T2", year=None, meta_year=None, ev_id, url=None):
    r = {"statement": stmt, "direct_quote": stmt, "tier": tier,
         "evidence_id": ev_id, "source_url": url or f"https://x/{ev_id}"}
    if year is not None:
        r["year"] = year
    if meta_year is not None:
        r["metadata"] = {"year": meta_year}
    return r


# ── helpers ────────────────────────────────────────────────────────────────
def test_row_year_sources_and_bounds():
    assert _row_year({"year": 2024}) == 2024
    assert _row_year({"metadata": {"year": 2019}}) == 2019
    assert _row_year({"year": "2021"}) == 2021          # coercible
    assert _row_year({"year": None}) is None
    assert _row_year({}) is None
    assert _row_year({"year": "n/a"}) is None            # non-numeric
    assert _row_year({"year": 1700}) is None             # out of range
    assert _row_year({"year": 3000}) is None


def test_relevance_band_monotonic_and_exact_mode():
    # higher score -> higher (or equal) band
    assert _relevance_band(0.9, 0.05) >= _relevance_band(0.1, 0.05)
    # within one epsilon -> same band (near-tie)
    assert _relevance_band(0.50, 0.05) == _relevance_band(0.52, 0.05)
    # epsilon<=0 -> exact score (only exact ties share a band)
    assert _relevance_band(0.5, 0.0) == 0.5
    assert _relevance_band(0.5, 0.0) != _relevance_band(0.51, 0.0)


def test_year_sort_value_newer_first_missing_last():
    assert _year_sort_value({"year": 2024}) < _year_sort_value({"year": 2014})  # newer sorts first
    assert _year_sort_value({"year": 2014}) < _year_sort_value({})              # dated before undated


def test_relevance_recency_key_disabled_is_pure_score():
    item = (3, 0.7, "T2", {"year": 2024})
    assert _relevance_recency_key(item, False, 0.05) == (-0.7,)


def test_default_epsilon_is_005():
    assert _recency_epsilon() == 0.05


# ── integration: ordering ────────────────────────────────────────────────────
def test_same_band_newer_row_sorts_first(monkeypatch):
    monkeypatch.delenv("PG_SELECT_RECENCY_TIEBREAK", raising=False)
    rows = [_row(_Q, year=2014, ev_id="old"), _row(_Q, year=2024, ev_id="new")]
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=10,
    )
    order = [r["evidence_id"] for r in sel.selected_rows]
    assert order.index("new") < order.index("old")  # newer first within the same band


def test_relevance_gap_beats_recency(monkeypatch):
    monkeypatch.delenv("PG_SELECT_RECENCY_TIEBREAK", raising=False)
    high = _row(_Q, year=2010, ev_id="high")                         # all 4 anchors -> high band
    low = _row("tirzepatide commentary", year=2025, ev_id="low")     # 1 anchor -> low band, newer
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=[low, high], max_rows=10,
    )
    order = [r["evidence_id"] for r in sel.selected_rows]
    assert order.index("high") < order.index("low")  # higher relevance band wins despite older


def test_missing_year_not_dropped(monkeypatch):
    monkeypatch.delenv("PG_SELECT_RECENCY_TIEBREAK", raising=False)
    rows = [_row(_Q, year=2024, ev_id="dated"), _row(_Q, ev_id="undated")]
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=10,
    )
    ids = {r["evidence_id"] for r in sel.selected_rows}
    assert ids == {"dated", "undated"}  # undated row is never hard-dropped


def test_truncation_slot_goes_to_newer_in_same_band(monkeypatch):
    """Codex P2: in the truncating path, a same-band newer row may take the quota slot."""
    monkeypatch.delenv("PG_SELECT_RECENCY_TIEBREAK", raising=False)
    rows = [_row(_Q, year=2014, ev_id="old"), _row(_Q, year=2024, ev_id="new")]
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=1,  # only one slot -> truncation path
    )
    assert [r["evidence_id"] for r in sel.selected_rows] == ["new"]


# ── kill-switch ──────────────────────────────────────────────────────────────
def test_killswitch_off_restores_index_order(monkeypatch):
    monkeypatch.setenv("PG_SELECT_RECENCY_TIEBREAK", "0")
    rows = [_row(_Q, year=2014, ev_id="old"), _row(_Q, year=2024, ev_id="new")]
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=10,
    )
    order = [r["evidence_id"] for r in sel.selected_rows]
    assert order.index("old") < order.index("new")  # same score -> original index order
    assert not any("recency_tiebreak" in n for n in sel.notes)  # telemetry suppressed when OFF


def test_killswitch_on_emits_telemetry(monkeypatch):
    monkeypatch.delenv("PG_SELECT_RECENCY_TIEBREAK", raising=False)
    rows = [_row(_Q, year=2024, ev_id="a"), _row(_Q, year=2014, ev_id="b")]
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=10,
    )
    assert any("recency_tiebreak enabled" in n for n in sel.notes)


# ── floors intact ────────────────────────────────────────────────────────────
def test_primary_floor_still_reserved_with_recency(monkeypatch):
    monkeypatch.delenv("PG_SELECT_RECENCY_TIEBREAK", raising=False)
    primary = {"statement": "SURPASS-2 tirzepatide reduction outcome glucose",
               "direct_quote": "primary results", "tier": "T1", "evidence_id": "surpass2",
               "source_url": "https://nejm.org/10.1056/nejmoa2107519", "year": 2021}
    filler = [_row(_Q, tier="T1", year=2024, ev_id=f"f{i}") for i in range(8)]
    sel = select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=[*filler, primary], max_rows=3,
        primary_trial_anchors=["SURPASS-2"],
    )
    ids = {r["evidence_id"] for r in sel.selected_rows}
    assert "surpass2" in ids  # named-trial primary reserved despite newer fillers
