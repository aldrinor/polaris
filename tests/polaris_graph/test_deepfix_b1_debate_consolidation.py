"""B1 (I-deepfix-001 #1344) — debate-class con-basket consolidation behavioral tests.

FAIL-LOUD: proves the con-basket is CONSOLIDATED into the section compose set BEFORE strict_verify
(the real ``_section_baskets_for_compose`` selection path), instead of being funnel-dropped. RED
before src/polaris_graph/generator/debate_consolidation.py + the verified_compose wiring existed.
Offline, $0.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

import pytest

vc = importlib.import_module("src.polaris_graph.generator.verified_compose")
dc = importlib.import_module("src.polaris_graph.generator.debate_consolidation")


@dataclass
class _Member:
    evidence_id: str
    span_verdict: str = "SUPPORTS"


@dataclass
class _Basket:
    claim_cluster_id: str
    supporting_members: list
    refuter_cluster_ids: tuple = ()


@dataclass
class _Section:
    ev_ids: list = field(default_factory=list)


@dataclass
class _Cred:
    baskets: list = field(default_factory=list)


def _make_case():
    pro = _Basket(
        claim_cluster_id="pro",
        supporting_members=[_Member("ev_pro")],
        refuter_cluster_ids=("con",),
    )
    con = _Basket(
        claim_cluster_id="con",
        supporting_members=[_Member("ev_con")],  # NOT assigned to the section
        refuter_cluster_ids=(),
    )
    section = _Section(ev_ids=["ev_pro"])  # only the pro evidence is assigned here
    cred = _Cred(baskets=[pro, con])
    return pro, con, section, cred


def test_con_basket_funnel_dropped_when_disabled(monkeypatch):
    """RED baseline: with B1 OFF the legacy selection returns only the pro-basket — the con side is
    funnel-dropped because its evidence was not assigned to the section."""
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "0")
    _pro, _con, section, cred = _make_case()
    selected = vc._section_baskets_for_compose(section, cred)
    ccids = [b.claim_cluster_id for b in selected]
    assert ccids == ["pro"], "expected the legacy funnel to drop the con-basket"


def test_con_basket_consolidated_before_verify_when_enabled(monkeypatch):
    """GREEN: with B1 ON (default) the referenced con-basket is CONSOLIDATED into the section compose
    set alongside the pro-basket, so both sides flow into compose BEFORE strict_verify."""
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "1")
    _pro, _con, section, cred = _make_case()
    selected = vc._section_baskets_for_compose(section, cred)
    ccids = {b.claim_cluster_id for b in selected}
    assert "pro" in ccids and "con" in ccids, f"con side must be consolidated, got {ccids}"


def test_default_on_consolidates(monkeypatch):
    """The kill-switch defaults ON (no env set)."""
    monkeypatch.delenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", raising=False)
    _pro, _con, section, cred = _make_case()
    selected = vc._section_baskets_for_compose(section, cred)
    assert {b.claim_cluster_id for b in selected} == {"pro", "con"}


def test_augment_never_mutates_input_and_dedups():
    pro, con, _section, _cred = _make_case()
    selected_in = [pro]
    out = dc.augment_with_con_baskets(selected_in, [pro, con])
    assert selected_in == [pro], "input list must not be mutated"
    assert [b.claim_cluster_id for b in out] == ["pro", "con"]
    # already-present con-basket is not duplicated
    out2 = dc.augment_with_con_baskets([pro, con], [pro, con])
    assert [b.claim_cluster_id for b in out2] == ["pro", "con"]


def test_no_refuter_is_byte_identical():
    plain = _Basket(claim_cluster_id="x", supporting_members=[_Member("e")], refuter_cluster_ids=())
    out = dc.augment_with_con_baskets([plain], [plain])
    assert out == [plain]


def test_should_hedge_confidence_only_when_both_sides_present():
    pro, con, _section, _cred = _make_case()
    assert dc.should_hedge_confidence([pro, con]) is True
    # pro alone: the con cluster it refutes is not present -> not two-sided in the compose set
    assert dc.should_hedge_confidence([pro]) is False
    plain = _Basket(claim_cluster_id="x", supporting_members=[], refuter_cluster_ids=())
    assert dc.should_hedge_confidence([plain]) is False


def test_faithfulness_neutral_con_basket_keeps_its_own_members(monkeypatch):
    """Consolidation ADDS the con-basket unchanged — its members (and their own span verdicts) are
    the exact objects from the corpus; nothing is fabricated or re-verdicted here."""
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "1")
    _pro, con, section, cred = _make_case()
    selected = vc._section_baskets_for_compose(section, cred)
    con_out = next(b for b in selected if b.claim_cluster_id == "con")
    assert con_out is con, "the consolidated con-basket must be the same object, unmodified"
    assert con_out.supporting_members[0].span_verdict == "SUPPORTS"
