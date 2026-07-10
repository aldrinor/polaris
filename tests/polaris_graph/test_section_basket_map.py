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


def test_weights_change_primary_home():
    fx = _load()
    # Default weights: cc_robots_reduce_employment primary = sec3 (topical breaks the prov tie).
    assert _build(fx).primary_section_by_cluster["cc_robots_reduce_employment"] == 3
    # Zero topical weight: sec0/sec3 tie on provenance -> lowest index (sec0) wins.
    flipped = _build(fx, weights={"provenance": 3, "subquery": 2, "topical": 0})
    assert flipped.primary_section_by_cluster["cc_robots_reduce_employment"] == 0


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
