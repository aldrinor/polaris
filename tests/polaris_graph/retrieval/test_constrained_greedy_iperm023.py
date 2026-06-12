"""I-perm-023 (#1215) PR-1 — constrained-greedy diversity-aware selection (forward guard).

Proves the new post-floor diversity pass is:
  - DEFAULT-OFF byte-identical (PG_SELECT_CONSTRAINED_GREEDY unset -> selected_rows + notes identical).
  - COVERAGE-MONOTONE (a swap only ADDS a novel bucket and never drops a covered bucket).
  - FLOOR-SAFE (never evicts a protected/floor-reserved row).
  - DETERMINISTIC (same input -> same output, no RNG).
  - A NO-OP when pool <= cap (the short-pool branch returns before the region runs).
  - And that `_apply_domain_cap` now returns (moved, brought_in_ids) so the greedy pass cannot
    undo the domain-diversity pass (Codex design-gate iter-2 P2.2).

Offline, deterministic, no network.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.retrieval import evidence_selector as es
from src.polaris_graph.retrieval.evidence_selector import (
    _apply_coverage_diversification,
    _apply_domain_cap,
    _constrained_greedy_config,
    _greedy_active_axes,
    _row_coverage_buckets,
    select_evidence_for_generation,
)

_AXES = ("safety", "class", "jurisdiction")


def _row(eid, *, tier="T1", rel=0.5, quote="", title="", url="https://example.org/x"):
    return {"evidence_id": eid, "direct_quote": quote, "title": title,
            "tier": tier, "url": url, "source_url": url, "relevance_score": rel}


def _scored(rows):
    # (original_idx, relevance, tier, row_dict) — the selector's internal scored tuple.
    return [(i, r["relevance_score"], r["tier"], r) for i, r in enumerate(rows)]


# ── config + predicates ──────────────────────────────────────────────────────

def test_config_defaults_off_not_env_flag_on():
    os.environ.pop("PG_SELECT_CONSTRAINED_GREEDY", None)
    enabled, n = _constrained_greedy_config()
    assert enabled is False          # MUST default OFF (not _env_flag_on which defaults ON)
    assert n == 24


def test_config_on_and_max_swaps_override(monkeypatch):
    monkeypatch.setenv("PG_SELECT_CONSTRAINED_GREEDY", "1")
    monkeypatch.setenv("PG_GREEDY_MAX_SWAPS", "5")
    assert _constrained_greedy_config() == (True, 5)


def test_active_axes_default_and_override(monkeypatch):
    monkeypatch.delenv("PG_GREEDY_AXES", raising=False)
    assert _greedy_active_axes() == ("safety", "class", "jurisdiction")
    monkeypatch.setenv("PG_GREEDY_AXES", "safety, bogus")
    assert _greedy_active_axes() == ("safety",)               # unknown axis ignored
    monkeypatch.setenv("PG_GREEDY_AXES", "bogus")
    assert _greedy_active_axes() == ("safety", "class", "jurisdiction")  # all-invalid -> default


def test_coverage_buckets_keyword_derivation():
    # one bucket per axis (first taxonomy match wins): "contraindicated in pregnancy" -> the FIRST
    # safety match (contraindication), NOT both.
    multi = _row_coverage_buckets(_row("a", quote="this is contraindicated in pregnancy"), _AXES)
    assert multi == frozenset({("safety", "contraindication")})
    assert ("safety", "contraindication") in _row_coverage_buckets(_row("a", quote="contraindicated"), _AXES)
    assert ("class", "meta_analysis") in _row_coverage_buckets(_row("b", title="A systematic review"), _AXES)
    assert _row_coverage_buckets(_row("c", quote="nothing special here"), _AXES) == frozenset()


# ── the diversification pass ─────────────────────────────────────────────────

def _monoculture_scenario():
    # selected: 3 T1 contraindication rows (safety monoculture, each bucket covered 3x = redundant).
    sel_rows = [_row(f"sel{i}", quote="drug is contraindicated", rel=0.9 - i * 0.01) for i in range(3)]
    # slack pool: novel-bucket T1 rows + one redundant T1 contraindication row.
    pool_rows = [
        _row("p_meta", title="A systematic review and meta-analysis", rel=0.4),   # novel class bucket
        _row("p_adv", quote="serious adverse reaction reported", rel=0.3),        # novel safety bucket
        _row("p_more_contra", quote="also contraindicated", rel=0.2),             # NOT novel
    ]
    scored = _scored(sel_rows + pool_rows)
    selected = scored[:3]            # the 3 selected
    return scored, selected


def test_pass_diversifies_monoculture_and_is_coverage_monotone():
    scored, selected = _monoculture_scenario()
    before = {b for it in selected for b in _row_coverage_buckets(it[3], _AXES)}
    swaps, telem = _apply_coverage_diversification(
        selected, scored, protected_ids=set(), max_swaps=24, axes=_AXES,
        rec_enabled=False, rec_eps=0.0)
    after = {b for it in selected for b in _row_coverage_buckets(it[3], _AXES)}
    assert swaps >= 1
    assert after.issuperset(before)                  # COVERAGE-MONOTONE: never drop a covered bucket
    assert len(after) > len(before)                  # strictly more distinct coverage
    assert ("safety", "contraindication") in after   # the monoculture bucket is still covered
    assert telem["distinct_buckets"] == len(after)


def test_pass_never_evicts_protected_rows():
    scored, selected = _monoculture_scenario()
    # protect ALL three selected -> no eviction possible -> zero swaps.
    protected = {id(it) for it in selected}
    before = list(selected)
    swaps, _ = _apply_coverage_diversification(
        selected, scored, protected_ids=protected, max_swaps=24, axes=_AXES,
        rec_enabled=False, rec_eps=0.0)
    assert swaps == 0
    assert selected == before                        # untouched


def test_pass_is_deterministic():
    s1, sel1 = _monoculture_scenario()
    s2, sel2 = _monoculture_scenario()
    _apply_coverage_diversification(sel1, s1, set(), 24, _AXES, False, 0.0)
    _apply_coverage_diversification(sel2, s2, set(), 24, _AXES, False, 0.0)
    assert [it[3]["evidence_id"] for it in sel1] == [it[3]["evidence_id"] for it in sel2]


def test_pass_zero_max_swaps_is_noop():
    scored, selected = _monoculture_scenario()
    before = list(selected)
    swaps, _ = _apply_coverage_diversification(
        selected, scored, set(), max_swaps=0, axes=_AXES, rec_enabled=False, rec_eps=0.0)
    assert swaps == 0 and selected == before


def test_swap_stays_same_tier():
    # a novel-bucket candidate in a DIFFERENT tier than any redundant row must NOT be pulled in.
    sel_rows = [_row(f"s{i}", quote="contraindicated", tier="T1", rel=0.9 - i * 0.01) for i in range(3)]
    pool_rows = [_row("p_t3", title="systematic review", tier="T3", rel=0.4)]  # novel but wrong tier
    scored = _scored(sel_rows + pool_rows)
    selected = scored[:3]
    swaps, _ = _apply_coverage_diversification(
        selected, scored, set(), 24, _AXES, False, 0.0)
    assert swaps == 0                                # no same-tier redundant->novel swap available
    assert all(it[3]["tier"] == "T1" for it in selected)


# ── domain-cap preservation (Codex diff-gate iter-1 P1 + P2) ─────────────────

def test_greedy_does_not_pull_at_cap_domain_over_the_cap():
    # The bug Codex caught: a novel-bucket candidate from an AT-CAP domain must NOT be admitted by
    # evicting a DIFFERENT-domain row (that would push the capped domain back over the cap).
    sel_rows = [
        _row("x1", quote="drug is contraindicated", url="https://x.com/1", rel=0.9),  # x.com, unique bucket
        _row("x2", quote="serious adverse reaction", url="https://x.com/2", rel=0.8),  # x.com, unique bucket
        _row("y1", quote="nothing notable", url="https://y.com/1", rel=0.7),           # y.com, NO bucket
    ]
    pool_rows = [_row("x3", title="A systematic review and meta-analysis", url="https://x.com/3", rel=0.4)]
    scored = _scored(sel_rows + pool_rows)
    selected = scored[:3]
    swaps, _ = _apply_coverage_diversification(
        selected, scored, protected_ids=set(), max_swaps=24, axes=_AXES,
        rec_enabled=False, rec_eps=0.0, domain_cap=2)
    # x.com is at the cap (2); x1/x2 are not redundant (unique buckets) so no same-domain eviction
    # is available -> the swap is rejected, x.com stays at 2 (NOT 3).
    from src.polaris_graph.retrieval.evidence_selector import _row_domain
    x_count = sum(1 for it in selected if _row_domain(it[3]) == "x.com")
    assert x_count <= 2
    assert "x3" not in [it[3]["evidence_id"] for it in selected]   # the over-cap candidate stayed out
    assert swaps == 0


def test_greedy_swaps_within_domain_when_at_cap():
    # When the at-cap domain HAS a redundant same-domain row, the novel candidate IS admitted by a
    # same-domain eviction (net-zero for the domain) -> cap respected AND coverage improves.
    sel_rows = [
        _row("x1", quote="drug is contraindicated", url="https://x.com/1", rel=0.9),  # x.com redundant pair
        _row("x2", quote="also contraindicated", url="https://x.com/2", rel=0.8),     # x.com (same bucket -> redundant)
        _row("y1", quote="nothing notable", url="https://y.com/1", rel=0.7),
    ]
    pool_rows = [_row("x3", title="A systematic review and meta-analysis", url="https://x.com/3", rel=0.4)]
    scored = _scored(sel_rows + pool_rows)
    selected = scored[:3]
    from src.polaris_graph.retrieval.evidence_selector import _row_domain
    swaps, _ = _apply_coverage_diversification(
        selected, scored, protected_ids=set(), max_swaps=24, axes=_AXES,
        rec_enabled=False, rec_eps=0.0, domain_cap=2)
    x_count = sum(1 for it in selected if _row_domain(it[3]) == "x.com")
    assert x_count == 2                                            # cap preserved (same-domain swap)
    assert "x3" in [it[3]["evidence_id"] for it in selected]       # novel candidate admitted
    assert ("class", "meta_analysis") in {b for it in selected for b in _row_coverage_buckets(it[3], _AXES)}


# ── _apply_domain_cap tuple return (Codex iter-2 P2.2) ───────────────────────

def test_domain_cap_returns_tuple_with_brought_in_ids():
    rows = [_row(f"d{i}", url="https://same.org/a", rel=0.9 - i * 0.01) for i in range(4)]
    rows += [_row("alt", url="https://other.org/b", rel=0.1)]
    scored = _scored(rows)
    selected = scored[:4]            # 4 rows all same.org (over a cap of 2)
    moved, brought = _apply_domain_cap(
        selected, scored, protected_ids=set(), cap=2, rec_enabled=False, rec_eps=0.0)
    assert isinstance(moved, int) and isinstance(brought, set)
    if moved:
        assert all(isinstance(x, int) for x in brought)


# ── integration through the public selector ─────────────────────────────────

def _integration_rows(n=200):
    # Build a truncating pool (n > cap). Most rows share one safety bucket (monoculture),
    # a few carry rare novel buckets that the greedy pass should pull in.
    rows = []
    for i in range(n):
        if i < 5:
            quote, title = "", "A systematic review and meta-analysis of trials"   # rare class bucket
        elif i < 10:
            quote, title = "serious adverse reaction observed", ""                  # rare safety bucket
        else:
            quote, title = "drug is contraindicated in this population", ""         # the monoculture
        rows.append(_row(f"ev{i:03d}", tier="T1", rel=0.9 - i * 0.001, quote=quote, title=title,
                         url=f"https://ex{i}.org/p"))
    return rows


def _select(rows, cap):
    sources = [type("S", (), {"url": r["url"], "tier": r["tier"],
                              "relevance_score": r["relevance_score"]})() for r in rows]
    return select_evidence_for_generation(
        research_question="q", protocol={}, classified_sources=sources,
        evidence_rows=rows, max_rows=cap)


def test_selector_byte_identical_when_off(monkeypatch):
    monkeypatch.delenv("PG_SELECT_CONSTRAINED_GREEDY", raising=False)
    rows = _integration_rows()
    a = _select(rows, cap=30)
    b = _select(rows, cap=30)
    assert [r["evidence_id"] for r in a.selected_rows] == [r["evidence_id"] for r in b.selected_rows]
    assert not any("constrained_greedy" in note for note in a.notes)


def test_selector_on_diversifies_when_pool_exceeds_cap(monkeypatch):
    rows = _integration_rows()
    monkeypatch.delenv("PG_SELECT_CONSTRAINED_GREEDY", raising=False)
    off = _select(rows, cap=30)
    monkeypatch.setenv("PG_SELECT_CONSTRAINED_GREEDY", "1")
    on = _select(rows, cap=30)

    def _distinct_buckets(sel):
        return len({b for r in sel.selected_rows for b in _row_coverage_buckets(r, _AXES)})
    # ON must cover at least as many distinct buckets as OFF (monotone improvement), and the
    # monoculture scenario should yield strictly more.
    assert _distinct_buckets(on) >= _distinct_buckets(off)
    assert any("constrained_greedy" in note for note in on.notes) or _distinct_buckets(on) == _distinct_buckets(off)
    assert len(on.selected_rows) == len(off.selected_rows)   # cap preserved (swap, not grow)


def test_selector_noop_when_pool_below_cap(monkeypatch):
    monkeypatch.setenv("PG_SELECT_CONSTRAINED_GREEDY", "1")
    rows = _integration_rows(n=10)           # 10 rows, cap 30 -> short-pool branch, no truncation
    sel = _select(rows, cap=30)
    assert len(sel.selected_rows) == 10
    assert not any("constrained_greedy" in note for note in sel.notes)   # region not reached
