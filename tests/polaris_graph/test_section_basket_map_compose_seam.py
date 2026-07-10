"""Design 4 D2 compose fast-path seam in verified_compose._section_baskets_for_compose.

Proves Design 4 acceptance 6 for the seam: PG_SECTION_BASKET_MAP OFF (or no map attached)
=> the legacy intersection runs byte-identically; ON with a precomputed map => the section's
baskets come from the map's placement. No LLM, no network. Faithfulness engine untouched.

2026-07-10 UNFREEZE Fable fix wave: Fix 6 (topical-only -> residual), Fix 9 (a corroborating
view is NOT re-composed -- the basket composes once, in its primary home).
"""

from __future__ import annotations

import os
import types

import pytest

from src.polaris_graph.generator import verified_compose as vc
from src.polaris_graph.synthesis import section_basket_map as sbm


def _member(eid):
    return types.SimpleNamespace(evidence_id=eid)


def _basket(cid, ev_ids, claim=""):
    return types.SimpleNamespace(
        claim_cluster_id=cid,
        supporting_members=[_member(e) for e in ev_ids],
        member_ev_ids=list(ev_ids),
        claim_text=claim,
        subject="",
        predicate="",
        corroboration_count=len(ev_ids),
    )


def _section(title, ev_ids):
    return types.SimpleNamespace(title=title, focus="", ev_ids=list(ev_ids), sub_query_indices=[])


def _analysis(baskets):
    return types.SimpleNamespace(baskets=baskets)


def _fixture():
    # basket_a members live in section 0; basket_b members live in section 1.
    a = _basket("cc_a", ["e1", "e2"], claim="alpha topic")
    b = _basket("cc_b", ["e3"], claim="beta topic")
    baskets = [a, b]
    sections = [_section("Sec Zero", ["e1", "e2"]), _section("Sec One", ["e3"])]
    return baskets, sections


def test_seam_off_is_legacy_intersection(monkeypatch):
    monkeypatch.delenv("PG_SECTION_BASKET_MAP", raising=False)
    monkeypatch.delenv("PG_COMPOSE_OFFTOPIC_BASKET_SCREEN", raising=False)
    baskets, sections = _fixture()
    ca = _analysis(baskets)
    # Legacy: section 0 returns only basket_a (its members intersect e1/e2).
    out = vc._section_baskets_for_compose(sections[0], ca)
    assert [b.claim_cluster_id for b in out] == ["cc_a"]
    # Attaching a map while the flag is OFF must NOT change the legacy result.
    m = sbm.build_section_basket_map(baskets, sections)
    out_off = vc._section_baskets_for_compose(
        sections[0], ca, section_basket_map=m, section_index=0
    )
    assert [b.claim_cluster_id for b in out_off] == ["cc_a"]


def test_seam_on_uses_precomputed_map(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "1")
    monkeypatch.delenv("PG_COMPOSE_OFFTOPIC_BASKET_SCREEN", raising=False)
    baskets, sections = _fixture()
    ca = _analysis(baskets)
    m = sbm.build_section_basket_map(baskets, sections)
    # Map places cc_a primary in section 0; the fast path returns it for section 0.
    out0 = vc._section_baskets_for_compose(
        sections[0], ca, section_basket_map=m, section_index=0
    )
    assert [b.claim_cluster_id for b in out0] == ["cc_a"]
    out1 = vc._section_baskets_for_compose(
        sections[1], ca, section_basket_map=m, section_index=1
    )
    assert [b.claim_cluster_id for b in out1] == ["cc_b"]


def test_seam_reads_map_off_section_attribute(monkeypatch):
    # Fix 10 wiring path: the map + index ride on the SectionPlan object (attributes), so
    # the seam resolves them via getattr when the kwargs are not passed explicitly.
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "1")
    monkeypatch.delenv("PG_COMPOSE_OFFTOPIC_BASKET_SCREEN", raising=False)
    baskets, sections = _fixture()
    ca = _analysis(baskets)
    m = sbm.build_section_basket_map(baskets, sections)
    sections[1]._section_basket_map = m
    sections[1]._section_index = 1
    out1 = vc._section_baskets_for_compose(sections[1], ca)
    assert [b.claim_cluster_id for b in out1] == ["cc_b"]


def test_seam_on_topical_only_routes_to_residual(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "1")
    monkeypatch.delenv("PG_COMPOSE_OFFTOPIC_BASKET_SCREEN", raising=False)
    # basket_c has ONLY a topical title-word home ("zeta"/"Zeta") and NO member in any
    # section's ev_ids. Fix 6: a topical-only match is NOT enough to home a real section while
    # D4 NLI is inert -> it routes to the keep-all RESIDUAL (zero drops), NOT sec1.
    a = _basket("cc_a", ["e1"], claim="alpha")
    c = _basket("cc_c", ["e9"], claim="zeta signal")
    baskets = [a, c]
    sections = [_section("Alpha Section", ["e1"]), _section("Zeta Section", ["e2"])]
    ca = _analysis(baskets)
    m = sbm.build_section_basket_map(baskets, sections)
    assert m.stranded_count == 0
    # cc_c did NOT home into real section 1 (topical-only, prov=0/subq=0).
    mapped1 = vc._section_baskets_for_compose(
        sections[1], ca, section_basket_map=m, section_index=1
    )
    assert "cc_c" not in [b.claim_cluster_id for b in mapped1]
    # It lives in the residual home instead (kept-all, never dropped).
    assert m.residual_section_index == len(sections)
    assert m.primary_section_by_cluster["cc_c"] == m.residual_section_index
    residual = vc._section_baskets_for_compose(
        sections[0], ca, section_basket_map=m, section_index=m.residual_section_index
    )
    assert "cc_c" in [b.claim_cluster_id for b in residual]


def test_seam_corroborating_view_not_recomposed(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "1")
    monkeypatch.delenv("PG_COMPOSE_OFFTOPIC_BASKET_SCREEN", raising=False)
    # cc_x is provenance-grounded in BOTH sections (e1 in sec0, e2 in sec1). Its PRIMARY home is
    # sec0 (the 'alpha' title word lifts sec0's weighted score); sec1 is a CORROBORATING facet.
    x = _basket("cc_x", ["e1", "e2"], claim="alpha finding")
    baskets = [x]
    sections = [_section("Alpha Section", ["e1"]), _section("Beta Section", ["e2"])]
    ca = _analysis(baskets)
    m = sbm.build_section_basket_map(baskets, sections)
    assert m.primary_section_by_cluster["cc_x"] == 0
    out0 = vc._section_baskets_for_compose(
        sections[0], ca, section_basket_map=m, section_index=0
    )
    assert [b.claim_cluster_id for b in out0] == ["cc_x"]
    # Fix 9: the corroborating view in sec1 does NOT re-compose the full basket (avoids the
    # repeated-composition leak) -- the basket composes once, in its primary home.
    out1 = vc._section_baskets_for_compose(
        sections[1], ca, section_basket_map=m, section_index=1
    )
    assert [b.claim_cluster_id for b in out1] == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
