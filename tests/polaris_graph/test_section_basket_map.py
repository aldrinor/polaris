"""Offline unit contract for synthesis/section_basket_map.py (Design 4 D1 / MASTER S5).

Proves the offline-provable subset of Design 4 §7b: acceptance 1 (coverage / stranded==0),
2 (exactly one primary home per basket), 4 (determinism across repeated builds AND input
permutation), 6 (OFF gate + verified_compose fast-path byte-identity). Acceptance 3/5/7/8
need a rendered report / the NLI cross-encoder and are the VM hamster's job (deferred).

Fixture is real drb_72 evidence_ids (tests/fixtures/section_basket_map/drb72_mini.json).
No LLM, no network. Faithfulness engine untouched.

2026-07-10 UNFREEZE Fable fix wave: Fix 6 (a real-section PRIMARY needs a GROUNDED signal
-- provenance ev_id OR sub-query origin; a topical-only match routes to the keep-all
residual while D4 NLI is inert) and Fix 14 (neutral deterministic tie-break, NOT lowest
section index) change the placement contract; the assertions below assert the NEW contract.
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
    assert m.residual_section_index == len(fx["section_plans"])
    assert m.residual_title == "Additional Corroborated Findings"
    # cc_unclassified_residual matches no section by any signal -> residual home.
    assert m.primary_section_by_cluster["cc_unclassified_residual"] == m.residual_section_index
    # Fix 6: cc_fourth_revolution is TOPICAL-ONLY (one generic shared word, prov=0/subq=0),
    # so it ALSO routes to the keep-all residual (NOT a real section) while D4 NLI is inert
    # -- it was a real-section primary under the pre-fix topical-primary behavior.
    assert m.primary_section_by_cluster["cc_fourth_revolution"] == m.residual_section_index
    residual_views = m.views_by_section[m.residual_section_index]
    assert sorted(v.claim_cluster_id for v in residual_views) == [
        "cc_fourth_revolution",
        "cc_unclassified_residual",
    ]
    assert all(v.role == "primary" for v in residual_views)


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
    # cc_robots_reduce_employment: acemoglu_restrepo_robots_jobs (sec0, prov) + ev_028 (sec3, prov).
    # BOTH sections are provenance-grounded; sec3 wins on higher topical overlap (Fix 6 leaves this
    # unchanged -- both are grounded). Corroborating sec0 carries ONLY the sec0-matched facet.
    assert m.primary_section_by_cluster["cc_robots_reduce_employment"] == 3
    sec0_views = {v.claim_cluster_id: v for v in m.views_by_section[0]}
    corro = sec0_views["cc_robots_reduce_employment"]
    assert corro.role == "corroborating"
    assert corro.section_member_ev_ids == ["acemoglu_restrepo_robots_jobs"]
    # The full member set is never split: ev_028 stays the sec3 primary facet.
    sec3_views = {v.claim_cluster_id: v for v in m.views_by_section[3]}
    assert "ev_028" in sec3_views["cc_robots_reduce_employment"].section_member_ev_ids


def test_tie_break_is_neutral_deterministic():
    fx = _load()
    m = _build(fx)
    # cc_estimates_vary: frey (sec0, prov) + ev_037 (sec1, prov), equal weighted score, zero
    # topical. Fix 14: the tie-break is a NEUTRAL deterministic hash (NOT lowest section index),
    # so the primary is whichever of {0,1} has the smaller stable_tiebreak -- computed here, not
    # assumed to be sec0.
    tied = [0, 1]
    expected = min(tied, key=lambda i: sbm._stable_tiebreak("cc_estimates_vary", i))
    other = 1 if expected == 0 else 0
    assert m.primary_section_by_cluster["cc_estimates_vary"] == expected
    sec_other = {v.claim_cluster_id: v for v in m.views_by_section[other]}
    assert sec_other["cc_estimates_vary"].role == "corroborating"


def test_subquery_lineage_signal_fires():
    fx = _load()
    m = _build(fx)
    # cc_subquery_only: ev_027 not in any section's ev_ids, but its retrieval_subquery maps
    # to sub_query index 4 -> section 4 (sub_query_indices [4]) is its ONLY grounded candidate.
    # Sub-query IS a grounded signal (Fix 6), so it stays a real-section primary.
    assert m.primary_section_by_cluster["cc_subquery_only"] == 4
    row = next(r for r in m.assignment_table if r["claim_cluster_id"] == "cc_subquery_only")
    assert row["signals"]["subquery"] == 1
    assert row["signals"]["provenance"] == 0
    # Fix 7/17: the sub-query signal is DISCLOSED as live in stats (evidence_pool + sub_queries
    # threaded AND plans carry sub_query_indices).
    assert m.stats["signals_available"]["subquery"] is True


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


def test_a8_resume_round_trip_restores_int_keys_and_views():
    # Fix 8: a JSON-serialized map reloads to INT section keys + SectionBasketView objects, so
    # the compose seam finds the section's baskets on resume (not zero from string keys).
    fx = _load()
    m = _build(fx)
    reloaded = sbm.load_map(sbm.dumps_map(m))
    assert reloaded.to_json_dict() == m.to_json_dict()
    assert all(isinstance(k, int) for k in reloaded.views_by_section)
    for views in reloaded.views_by_section.values():
        assert all(isinstance(v, sbm.SectionBasketView) for v in views)


# ── LAW VI — knobs read through env ──────────────────────────────────────────────────────────────

def test_weights_resolve_from_env(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_W_PROVENANCE", "7")
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_W_SUBQUERY", "5")
    monkeypatch.setenv("PG_SECTION_BASKET_MAP_W_TOPICAL", "0")
    w = sbm.resolve_weights()
    assert w == {"provenance": 7, "subquery": 5, "topical": 0}


def test_weights_change_primary_home():
    fx = _load()
    # Default weights: cc_robots_reduce_employment primary = sec3 (topical breaks the prov tie).
    assert _build(fx).primary_section_by_cluster["cc_robots_reduce_employment"] == 3
    # Zero topical weight: sec0/sec3 tie on provenance -> Fix 14 neutral hash tie-break decides.
    flipped = _build(fx, weights={"provenance": 3, "subquery": 2, "topical": 0})
    expected = min([0, 3], key=lambda i: sbm._stable_tiebreak("cc_robots_reduce_employment", i))
    assert flipped.primary_section_by_cluster["cc_robots_reduce_employment"] == expected


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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
