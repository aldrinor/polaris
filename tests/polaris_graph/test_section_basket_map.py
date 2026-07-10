"""Offline unit contract for synthesis/section_basket_map.py (Design 4 D1 / MASTER S5).

Proves the offline-provable subset of Design 4 §7b: acceptance 1 (coverage / stranded==0),
2 (exactly one primary home per basket), 4 (determinism across repeated builds AND input
permutation), 6 (OFF gate + verified_compose fast-path byte-identity). Acceptance 3/5/7/8
need a rendered report / the NLI cross-encoder and are the VM hamster's job (deferred).

Fixture is real drb_72 evidence_ids (tests/fixtures/section_basket_map/drb72_mini.json).
No LLM, no network. Faithfulness engine untouched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.polaris_graph.synthesis import section_basket_map as sbm

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "section_basket_map"
    / "drb72_mini.json"
)


def _load():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _build(fx, *, weights=None):
    return sbm.build_section_basket_map(
        fx["baskets"],
        fx["section_plans"],
        evidence_pool=fx.get("evidence_rows"),
        sub_queries=fx.get("sub_queries"),
        weights=weights,
    )


# ── Acceptance 1 — coverage: zero stranded, every basket in >=1 section ──────────────────────────

def test_a1_no_stranded_baskets():
    fx = _load()
    m = _build(fx)
    assert m.stranded_count == 0
    n_baskets = len(fx["baskets"])
    all_cids = {v.claim_cluster_id for views in m.views_by_section.values() for v in views}
    assert len(all_cids) == n_baskets
    # Every basket's cluster id has a home in the primary map.
    for b in fx["baskets"]:
        assert b["claim_cluster_id"] in m.primary_section_by_cluster


def test_a1_orphan_routes_to_residual_home():
    fx = _load()
    m = _build(fx)
    # cc_unclassified_residual matches no section by any signal -> residual home.
    assert m.residual_section_index == len(fx["section_plans"])
    assert m.primary_section_by_cluster["cc_unclassified_residual"] == m.residual_section_index
    assert m.residual_title == "Additional Corroborated Findings"
    residual_views = m.views_by_section[m.residual_section_index]
    assert [v.claim_cluster_id for v in residual_views] == ["cc_unclassified_residual"]
    assert residual_views[0].role == "primary"


# ── Acceptance 2 — uniqueness: exactly one primary home per basket ────────────────────────────────

def test_a2_one_primary_home_per_basket():
    fx = _load()
    m = _build(fx)
    assert len(m.primary_section_by_cluster) == len(fx["baskets"])
    primary_count: dict[str, int] = {}
    for views in m.views_by_section.values():
        for v in views:
            if v.role == "primary":
                primary_count[v.claim_cluster_id] = primary_count.get(v.claim_cluster_id, 0) + 1
    # Each basket appears as a primary view exactly once, run-wide.
    assert primary_count == {b["claim_cluster_id"]: 1 for b in fx["baskets"]}


def test_a2_corroborating_facet_is_section_matched_subset():
    fx = _load()
    m = _build(fx)
    # cc_robots_reduce_employment: acemoglu_restrepo_robots_jobs (sec0) + ev_028 (sec3).
    # Primary sec3 (higher topical); corroborating sec0 carries ONLY the sec0-matched facet.
    assert m.primary_section_by_cluster["cc_robots_reduce_employment"] == 3
    sec0_views = {v.claim_cluster_id: v for v in m.views_by_section[0]}
    corro = sec0_views["cc_robots_reduce_employment"]
    assert corro.role == "corroborating"
    assert corro.section_member_ev_ids == ["acemoglu_restrepo_robots_jobs"]
    # The full member set is never split: ev_028 stays the sec3 primary facet.
    sec3_views = {v.claim_cluster_id: v for v in m.views_by_section[3]}
    assert "ev_028" in sec3_views["cc_robots_reduce_employment"].section_member_ev_ids


def test_tie_break_goes_to_lowest_section_index():
    fx = _load()
    m = _build(fx)
    # cc_estimates_vary: frey (sec0) + ev_037 (sec1), equal weighted score, zero topical.
    # Deterministic keep-first tie -> lowest index (sec0) is primary, sec1 corroborates.
    assert m.primary_section_by_cluster["cc_estimates_vary"] == 0
    sec1 = {v.claim_cluster_id: v for v in m.views_by_section[1]}
    assert sec1["cc_estimates_vary"].role == "corroborating"


def test_subquery_lineage_signal_fires():
    fx = _load()
    m = _build(fx)
    # cc_subquery_only: ev_027 not in any section's ev_ids, but its retrieval_subquery maps
    # to sub_query index 4 -> only section 4 (sub_query_indices [4]) becomes a candidate.
    assert m.primary_section_by_cluster["cc_subquery_only"] == 4
    row = next(r for r in m.assignment_table if r["claim_cluster_id"] == "cc_subquery_only")
    assert row["signals"]["subquery"] == 1
    assert row["signals"]["provenance"] == 0


# ── Acceptance 4 — determinism ───────────────────────────────────────────────────────────────────

def test_a4_repeated_builds_byte_identical():
    fx = _load()
    a = sbm.dumps_map(_build(fx))
    b = sbm.dumps_map(_build(fx))
    c = sbm.dumps_map(_build(fx))
    assert a == b == c


def test_a4_input_permutation_byte_identical():
    fx = _load()
    canonical = sbm.dumps_map(_build(fx))
    # Reversed basket order.
    fx_rev = dict(fx)
    fx_rev["baskets"] = list(reversed(fx["baskets"]))
    assert sbm.dumps_map(_build(fx_rev)) == canonical
    # A rotated permutation.
    fx_rot = dict(fx)
    fx_rot["baskets"] = fx["baskets"][5:] + fx["baskets"][:5]
    assert sbm.dumps_map(_build(fx_rot)) == canonical


# ── LAW VI — knobs read through env ──────────────────────────────────────────────────────────────

def test_weights_resolve_from_env(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_W_PROVENANCE", "7")
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_W_SUBQUERY", "5")
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_W_TOPICAL", "0")
    w = sbm.resolve_weights()
    assert w == {"provenance": 7, "subquery": 5, "topical": 0}


def test_primary_selection_is_tiered_not_weighted():
    """Fix 5(c): primary selection is TIERED-LEXICOGRAPHIC (provenance, then sub-query, then
    discriminative topical, then lowest index) — NOT a flat weighted sum. A real provenance/
    sub-query assignment can never be outvoted by an accumulation of weak lexical matches, and
    the env weights no longer flip a placement. This is the fix for the 84%-single-word leak."""
    fx = _load()
    # cc_robots_reduce_employment: sec0 and sec3 both carry provenance=1; the discriminative
    # topical tier breaks the tie -> sec3 (more discriminative shared words).
    assert _build(fx).primary_section_by_cluster["cc_robots_reduce_employment"] == 3
    # Zeroing the topical WEIGHT must NOT change the outcome — tiers, not weights, decide.
    flipped = _build(fx, weights={"provenance": 3, "subquery": 2, "topical": 0})
    assert flipped.primary_section_by_cluster["cc_robots_reduce_employment"] == 3


def test_provenance_tier_dominates_topical_regardless_of_weights():
    """A basket with ONE real provenance match in section A but a LARGE topical overlap with
    section B lands in A — provenance is a higher tier than topical, so no topical weight (even
    a huge one) can move it. This is the structural guarantee fix 5(c) adds; it holds for any
    question because it reads only the runtime signals, never a hardcoded section/word."""
    baskets = [{
        "claim_cluster_id": "cc_prov_wins",
        "claim_text": "beta gamma delta epsilon zeta",  # heavy lexical overlap with section B
        "subject": "", "predicate": "",
        "member_ev_ids": ["e_prov"],  # provenance match with section A only
    }]
    sections = [
        {"title": "Alpha", "focus": "", "ev_ids": ["e_prov"], "sub_query_indices": []},
        {"title": "beta gamma", "focus": "delta epsilon zeta", "ev_ids": ["e_other"],
         "sub_query_indices": []},
    ]
    for w in ({"provenance": 3, "subquery": 2, "topical": 1},
              {"provenance": 1, "subquery": 1, "topical": 999}):
        m = sbm.build_section_basket_map(baskets, sections, weights=w)
        assert m.primary_section_by_cluster["cc_prov_wins"] == 0


def test_residual_title_env_override(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_RESIDUAL_TITLE", "Uncategorized Corroboration")
    m = _build(_load())
    assert m.residual_title == "Uncategorized Corroboration"


# ── Acceptance 6 (module half) — master flag gate ────────────────────────────────────────────────

def test_a6_master_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SECTION_BASKET_MAP", raising=False)
    assert sbm.section_basket_map_enabled() is False
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "1")
    assert sbm.section_basket_map_enabled() is True
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "off")
    assert sbm.section_basket_map_enabled() is False


# ── Fix 3 — the map serializes AND deserializes (the checkpoint round-trip) ──────────────────────

def test_fix3_load_map_round_trip_is_byte_identical():
    fx = _load()
    m = _build(fx)
    raw = sbm.dumps_map(m)
    rehydrated = sbm.load_map(raw)
    # A JSON-rehydrated map must be byte-for-byte equal to the in-memory one (int-normalized keys,
    # rebuilt view objects) — the seam that consumed a rehydrated map used to see ZERO views.
    assert sbm.dumps_map(rehydrated) == raw
    # Section keys rehydrate as ints, and views rehydrate as SectionBasketView objects.
    assert all(isinstance(k, int) for k in rehydrated.views_by_section)
    any_view = next(iter(next(iter(rehydrated.views_by_section.values()))))
    assert isinstance(any_view, sbm.SectionBasketView)


# ── Fix 4 — no silent basket loss: duplicate + empty cids are counted, never collapsed ───────────

def test_fix4_duplicate_cid_baskets_do_not_collapse():
    # Two DISTINCT baskets share a cluster id; the old build overwrote one (stranded read 0).
    baskets = [
        {"claim_cluster_id": "dup", "claim_text": "alpha", "member_ev_ids": ["e1"]},
        {"claim_cluster_id": "dup", "claim_text": "beta", "member_ev_ids": ["e2"]},
        {"claim_cluster_id": "solo", "claim_text": "gamma", "member_ev_ids": ["e3"]},
    ]
    sections = [{"title": "S", "focus": "", "ev_ids": ["e1", "e2", "e3"], "sub_query_indices": []}]
    m = sbm.build_section_basket_map(baskets, sections)
    # Every INPUT basket produces a map entry — none collapse, none vanish.
    assert len(m.primary_section_by_cluster) == 3
    assert m.stranded_count == 0


def test_fix4_empty_cid_basket_is_not_dropped():
    baskets = [
        {"claim_cluster_id": "", "claim_text": "orphan", "member_ev_ids": ["e9"]},
        {"claim_cluster_id": "real", "claim_text": "kept", "member_ev_ids": ["e1"]},
    ]
    sections = [{"title": "S", "focus": "", "ev_ids": ["e1"], "sub_query_indices": []}]
    m = sbm.build_section_basket_map(baskets, sections)
    # The empty-cid basket gets a deterministic synthetic id and is counted, not silently skipped.
    assert len(m.primary_section_by_cluster) == 2
    assert m.stranded_count == 0
    assert any(k.startswith("__nocid__#") for k in m.primary_section_by_cluster)


# ── Fix 6 — a non-Latin question yields content words (topical signal survives) ──────────────────

def test_fix6_unicode_tokenizer_yields_content_words():
    # Cyrillic content words; the ASCII-only tokenizer produced an empty set (all-residual).
    words = sbm._content_words("автоматизация вытесняет рабочие места")
    assert words  # non-empty: the topical signal can fire for a non-English question
    assert "автоматизация" in words


# ── Fix 7a — a dead signal is visible in the serialized stats, never a hidden zero ───────────────

def test_fix7a_signal_availability_surfaced():
    fx = _load()
    m = _build(fx)
    assert set(m.signals_available) == {"provenance", "subquery", "topical"}
    assert m.signals_available["subquery"] is True  # fixture wires ev_027 -> sub_query 4
    # No sub_queries passed => the sub-query signal is structurally unavailable and SAID so.
    m_nosq = sbm.build_section_basket_map(fx["baskets"], fx["section_plans"])
    assert m_nosq.signals_available["subquery"] is False
    assert "subquery" in m_nosq.signal_totals


# ── Fix 9 — a topical-only primary carries the FULL member list (uniform with residual) ──────────

def test_fix9_topical_only_primary_carries_full_member_facet():
    # basket matches section 0 by TITLE word only; no member ev_id is in the section's ev_ids.
    baskets = [{
        "claim_cluster_id": "cc_top", "claim_text": "zeta signal",
        "subject": "", "predicate": "", "member_ev_ids": ["e_x", "e_y"],
    }]
    sections = [{"title": "Zeta Section", "focus": "", "ev_ids": ["e_other"], "sub_query_indices": []}]
    m = sbm.build_section_basket_map(baskets, sections)
    assert m.primary_section_by_cluster["cc_top"] == 0
    view = m.views_by_section[0][0]
    assert view.role == "primary"
    # Uniform with the residual branch: the full member set is the facet, never empty.
    assert view.section_member_ev_ids == ["e_x", "e_y"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
