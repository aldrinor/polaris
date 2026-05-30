"""Tests for the #956 source-diversity passes in evidence_selector. NO network / NO spend.

Asserts both passes are SOFT same-tier swaps on post-floor slack: a sub-query origin present in a tier's
pool reaches the selection (round-robin reservation), one domain cannot dominate beyond the soft cap, floors
are never evicted, tier minimums (per-tier counts) are preserved, and the kill-switches restore the prior
non-diverse selection exactly.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    _row_domain,
    _row_query_origin,
    select_evidence_for_generation,
)

_Q = "alpha beta gamma delta"


def _row(ev_id, *, tier="T2", origin="A", host="x.com", stmt=_Q):
    return {
        "evidence_id": ev_id,
        "source_url": f"https://{host}/{ev_id}",
        "statement": stmt,
        "direct_quote": stmt,
        "tier": tier,
        "query_origin": origin,
    }


def _off(monkeypatch):
    monkeypatch.setenv("PG_SELECT_SUBQUERY_RESERVE", "0")
    monkeypatch.setenv("PG_SELECT_DOMAIN_CAP", "0")


def _on(monkeypatch):
    monkeypatch.delenv("PG_SELECT_SUBQUERY_RESERVE", raising=False)
    monkeypatch.delenv("PG_SELECT_DOMAIN_CAP", raising=False)


def _select(rows, max_rows, anchors=None):
    return select_evidence_for_generation(
        research_question=_Q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=max_rows, primary_trial_anchors=anchors,
    )


# ── helpers ──────────────────────────────────────────────────────────────
def test_row_query_origin_and_domain():
    assert _row_query_origin({"query_origin": "X"}) == "X"
    assert _row_query_origin({}) == "_unlabeled"
    assert _row_domain({"source_url": "https://www.fda.gov/drugs"}) == "fda.gov"
    assert _row_domain({}) == ""


# ── sub-query reservation ──────────────────────────────────────────────────
def test_underrepresented_subquery_reaches_selection(monkeypatch):
    _on(monkeypatch)
    # 4 origin-A rows + 1 origin-B row, all T2 same relevance; only 3 slots.
    rows = [_row(f"a{i}", origin="A") for i in range(4)] + [_row("b0", origin="B")]
    sel = _select(rows, max_rows=3)
    origins = {_row_query_origin(r) for r in sel.selected_rows}
    assert "B" in origins  # the lone sub-topic is not starved


def test_killswitch_off_lets_one_origin_dominate(monkeypatch):
    _off(monkeypatch)
    rows = [_row(f"a{i}", origin="A") for i in range(4)] + [_row("b0", origin="B")]
    sel = _select(rows, max_rows=3)
    origins = [_row_query_origin(r) for r in sel.selected_rows]
    assert origins == ["A", "A", "A"]  # prior non-diverse behavior (by index)
    assert not any("subquery_reservation" in n for n in sel.notes)


# ── per-domain soft cap ─────────────────────────────────────────────────────
def test_domain_soft_cap_limits_dominance(monkeypatch):
    _on(monkeypatch)
    # 4 rows on x.com + 2 on y.com, all T2 same origin/relevance; 4 slots, cap=ceil(0.5*4)=2.
    rows = [_row(f"x{i}", host="x.com") for i in range(4)] + [_row(f"y{i}", host="y.com") for i in range(2)]
    sel = _select(rows, max_rows=4)
    doms = [_row_domain(r) for r in sel.selected_rows]
    assert doms.count("x.com") <= 2  # capped
    assert "y.com" in doms          # under-represented domain pulled in
    assert len(sel.selected_rows) == 4  # no slot left empty


def test_killswitch_off_lets_one_domain_dominate(monkeypatch):
    _off(monkeypatch)
    rows = [_row(f"x{i}", host="x.com") for i in range(4)] + [_row(f"y{i}", host="y.com") for i in range(2)]
    sel = _select(rows, max_rows=4)
    doms = [_row_domain(r) for r in sel.selected_rows]
    assert doms.count("x.com") == 4  # prior behavior (by index, no cap)
    assert not any("domain_soft_cap" in n for n in sel.notes)


# ── invariants: tier minimums + floors ──────────────────────────────────────
def test_tier_minimums_preserved(monkeypatch):
    # mixed-tier pool: diversity must not change per-tier counts (same-tier swaps).
    rows = (
        [_row(f"t1_{i}", tier="T1", origin="A") for i in range(3)]
        + [_row(f"t2_{i}", tier="T2", origin="A") for i in range(3)]
        + [_row("t2_b", tier="T2", origin="B")]
    )
    _off(monkeypatch)
    base = _select(rows, max_rows=4).selected_counts
    _on(monkeypatch)
    div = _select(rows, max_rows=4).selected_counts
    assert base == div  # per-tier counts identical → no tier dropped below quota


def test_floor_primary_not_evicted_by_diversity(monkeypatch):
    _on(monkeypatch)
    primary = {
        "evidence_id": "surpass2", "tier": "T1",
        "source_url": "https://nejm.org/10.1056/nejmoa2107519",
        "statement": "SURPASS-2 alpha beta gamma delta", "direct_quote": "primary",
        "query_origin": "A",
    }
    # many same-origin/same-domain T1 fillers that the diversity passes would otherwise churn
    fillers = [_row(f"f{i}", tier="T1", origin="A", host="x.com") for i in range(8)]
    sel = _select([*fillers, primary], max_rows=3, anchors=["SURPASS-2"])
    ids = {r["evidence_id"] for r in sel.selected_rows}
    assert "surpass2" in ids  # named-trial primary floor survives diversity


def test_domain_cap_yields_when_no_same_tier_replacement(monkeypatch):
    _on(monkeypatch)
    # all rows same domain + same tier → cap cannot swap (no other-domain same-tier row); must yield, not crash
    rows = [_row(f"x{i}", host="x.com", origin="A") for i in range(6)]
    sel = _select(rows, max_rows=4)
    assert len(sel.selected_rows) == 4  # full, no empty slot
    assert all(_row_domain(r) == "x.com" for r in sel.selected_rows)  # yielded


def test_short_pool_path_unaffected(monkeypatch):
    _on(monkeypatch)
    # pool <= max_rows → short-pool path keeps everything; diversity is moot there.
    rows = [_row(f"a{i}", origin="A") for i in range(2)] + [_row("b0", origin="B")]
    sel = _select(rows, max_rows=10)
    assert len(sel.selected_rows) == 3  # all kept, no churn
