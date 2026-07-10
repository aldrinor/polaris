"""Design 4 D2 compose fast-path seam in verified_compose._section_baskets_for_compose.

Proves Design 4 acceptance 6 for the seam: PG_SECTION_BASKET_MAP OFF (or no map attached)
=> the legacy intersection runs byte-identically; ON with a precomputed map => the section's
baskets come from the map's placement. No LLM, no network. Faithfulness engine untouched.
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


def test_seam_on_recovers_a_stranded_basket(monkeypatch):
    monkeypatch.setenv("PG_SECTION_BASKET_MAP", "1")
    monkeypatch.delenv("PG_COMPOSE_OFFTOPIC_BASKET_SCREEN", raising=False)
    # basket_c has a topical home (title word match) but NO member in any section's ev_ids:
    # the legacy intersection strands it; the map gives it a primary home.
    a = _basket("cc_a", ["e1"], claim="alpha")
    c = _basket("cc_c", ["e9"], claim="zeta signal")
    baskets = [a, c]
    sections = [_section("Alpha Section", ["e1"]), _section("Zeta Section", ["e2"])]
    ca = _analysis(baskets)
    # Legacy section 1 strands cc_c (e9 not in e2).
    legacy = vc._section_baskets_for_compose(sections[1], ca)
    assert [b.claim_cluster_id for b in legacy] == []
    # Map routes cc_c to section 1 by topical overlap ("zeta"/"Zeta").
    m = sbm.build_section_basket_map(baskets, sections)
    assert m.stranded_count == 0
    mapped = vc._section_baskets_for_compose(
        sections[1], ca, section_basket_map=m, section_index=1
    )
    assert "cc_c" in [b.claim_cluster_id for b in mapped]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
