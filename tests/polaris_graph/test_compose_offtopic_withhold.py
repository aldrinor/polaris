"""N6-FIX-A + N6-FIX-B (I-deepfix-001 wave-2) — off-topic WITHHOLD on the compose seam + the legacy
outline strip.

Pure Python, no GPU / LLM / network. Per the UNIFIED_BUILD_PLAN ruling, N1-FIX-1 and N6-FIX-A are the
SAME change under the ONE flag ``PG_COMPOSE_OFFTOPIC_BASKET_SCREEN`` (the second flag name
``PG_COMPOSE_BASKET_OFFTOPIC_WITHHOLD`` from the raw N6 spec is intentionally NOT created — a single
flag gates the single behaviour). This test file exercises N6's asserts against that one impl, plus
the N6-FIX-B outline ev_id strip under the EXISTING ``PG_ASPECT_OFFTOPIC_SLOT_GUARD``.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

vc = importlib.import_module("src.polaris_graph.generator.verified_compose")
bc = importlib.import_module("src.polaris_graph.generator.boundary_conditions")
_msg = importlib.import_module("src.polaris_graph.generator.multi_section_generator")

_SCREEN_ENV = "PG_COMPOSE_OFFTOPIC_BASKET_SCREEN"
_SLOT_GUARD_ENV = "PG_ASPECT_OFFTOPIC_SLOT_GUARD"
# Codex+Fable gate-fix P1-2: the legacy-outline strip now rides its OWN default-OFF flag, NOT the
# existing default-ON PG_ASPECT_OFFTOPIC_SLOT_GUARD.
_STRIP_ENV = "PG_LEGACY_OUTLINE_OFFTOPIC_STRIP"


def _member(eid, quote=""):
    return SimpleNamespace(
        evidence_id=eid, direct_quote=quote, span_verdict="SUPPORTS",
        source_url="https://example.org/x", source_tier="T5",
    )


def _basket(ccid, claim_text, subject, weight, *members):
    return SimpleNamespace(
        claim_cluster_id=ccid, claim_text=claim_text, subject=subject, predicate="",
        weight_mass=weight, refuter_cluster_ids=(),
        supporting_members=list(members),
    )


def _pool():
    return {
        "A": {"content_relevance_label": "relevant"},                       # on-topic
        "B": {"topic_offtopic_demoted": True, "content_relevance_label": "demoted"},        # off-topic
        "C": {"topic_offtopic_demoted": True, "content_relevance_label": "relevant"},       # override
    }


def _fixture_baskets():
    # b1 headline (on-topic, high weight); b2 off-topic-only (lower weight, boundary marker + overlap);
    # b3 mixed [A,B]; b4 protected [C]. b3/b4 are higher weight so they never qualify as a boundary.
    b1 = _basket("b1", "automation displaces workers in warehouses", "automation warehouses", 9.0,
                 _member("A", "Automation displaced warehouse workers."))
    b2 = _basket("b2", "automation displaces workers however only seasonally", "seasonal", 2.0,
                 _member("B", "However, automation displaced workers only seasonally."))
    b3 = _basket("b3", "mixed basket claim", "mixed", 12.0,
                 _member("A", "on-topic member text"), _member("B", "off-topic member text"))
    b4 = _basket("b4", "protected basket claim", "protected", 12.0,
                 _member("C", "protected member text"))
    return b1, b2, b3, b4


def _section():
    return SimpleNamespace(ev_ids=["A", "B", "C"])


def _cred(baskets):
    return SimpleNamespace(baskets=list(baskets))


def test_flag_on_withholds_offtopic_only_keeps_mixed_and_override(monkeypatch):
    """(1) flag ON + pool passed: returns b1, b3 (mixed => consolidation preserved), b4 (override
    honored) and NOT b2 (off-topic only)."""
    monkeypatch.setenv(_SCREEN_ENV, "1")
    b1, b2, b3, b4 = _fixture_baskets()
    out = vc._section_baskets_for_compose(_section(), _cred((b1, b2, b3, b4)), evidence_pool=_pool())
    assert out == [b1, b3, b4]
    assert b2 not in out


def test_flag_off_returns_all_byte_identical(monkeypatch):
    """(2) flag OFF (the ONE screen flag unset): all four baskets returned — byte-identical."""
    monkeypatch.delenv(_SCREEN_ENV, raising=False)
    b1, b2, b3, b4 = _fixture_baskets()
    out = vc._section_baskets_for_compose(_section(), _cred((b1, b2, b3, b4)), evidence_pool=_pool())
    assert out == [b1, b2, b3, b4]


def test_pool_not_passed_returns_all_byte_identical(monkeypatch):
    """(3) evidence_pool NOT passed (legacy caller signature): all four returned — byte-identical
    even with the flag ON."""
    monkeypatch.setenv(_SCREEN_ENV, "1")
    b1, b2, b3, b4 = _fixture_baskets()
    out = vc._section_baskets_for_compose(_section(), _cred((b1, b2, b3, b4)))
    assert out == [b1, b2, b3, b4]


def test_boundary_line_no_longer_selects_screened_offtopic_basket(monkeypatch):
    """(4) B2 regression (the transcribeanywhere class): against the UNSCREENED list the off-topic
    lower-weight b2 IS selected as the boundary qualifier (RED baseline); against the FIX-1-screened
    list b2 is gone, so no qualifier remains and the boundary line is empty. Fix 1 (P0-1): selection is
    pure; the line never quotes a raw member span regardless."""
    monkeypatch.setenv(_SCREEN_ENV, "1")
    b1, b2, b3, b4 = _fixture_baskets()
    # RED baseline: unscreened, b2 is the selected boundary qualifier.
    sel = bc.select_boundary_qualifier([b1], [b1, b2, b3, b4])
    assert sel is not None and sel[1].claim_cluster_id == "b2"
    # GREEN: the FIX-1 screen removes b2 from the compose set; no qualifier remains.
    screened = vc._section_baskets_for_compose(_section(), _cred((b1, b2, b3, b4)), evidence_pool=_pool())
    assert b2 not in screened
    assert bc.select_boundary_qualifier([b1], screened) is None
    assert bc.synthesize_boundary_line([b1], screened) == ""


def test_outline_strip_removes_offtopic_ev_ids_under_new_flag(monkeypatch):
    """(5) outline strip (P1-2): a plan with ev_ids=[A,B,C] under the NEW default-OFF
    PG_LEGACY_OUTLINE_OFFTOPIC_STRIP flag ON yields [A,C] (B stripped, C protected by the override)."""
    monkeypatch.setenv(_STRIP_ENV, "1")
    plan = _msg.SectionPlan(title="Sec", focus="f", ev_ids=["A", "B", "C"], archetype="")
    out = _msg._strip_offtopic_ev_ids_from_plans([plan], _pool())
    assert out[0].ev_ids == ["A", "C"]


def test_outline_strip_flag_off_byte_identical(monkeypatch):
    """(P1-2 byte-identical) the NEW flag OFF (default) => NO strip, even though the existing
    default-ON PG_ASPECT_OFFTOPIC_SLOT_GUARD is ON. Plans keep every ev_id unchanged."""
    monkeypatch.delenv(_STRIP_ENV, raising=False)            # NEW flag OFF (default)
    monkeypatch.delenv(_SLOT_GUARD_ENV, raising=False)       # existing guard default ON
    plan = _msg.SectionPlan(title="Sec", focus="f", ev_ids=["A", "B", "C"], archetype="")
    out = _msg._strip_offtopic_ev_ids_from_plans([plan], _pool())
    assert out[0].ev_ids == ["A", "B", "C"]  # no strip => byte-identical

    # Explicitly ON existing guard but NEW flag still OFF => still no strip (does not ride the old flag).
    monkeypatch.setenv(_SLOT_GUARD_ENV, "1")
    plan2 = _msg.SectionPlan(title="Sec", focus="f", ev_ids=["A", "B", "C"], archetype="")
    out2 = _msg._strip_offtopic_ev_ids_from_plans([plan2], _pool())
    assert out2[0].ev_ids == ["A", "B", "C"]


def test_outline_strip_emptied_plan_still_ships(monkeypatch):
    """(5) a plan reduced to [] still ships (the plan object survives with empty ev_ids — the
    downstream no_evidence gap-stub path handles it, this helper never drops a plan)."""
    monkeypatch.setenv(_STRIP_ENV, "1")
    plan = _msg.SectionPlan(title="OffOnly", focus="f", ev_ids=["B"], archetype="")
    out = _msg._strip_offtopic_ev_ids_from_plans([plan], _pool())
    assert len(out) == 1
    assert out[0].ev_ids == []


def test_outline_strip_accepts_row_list(monkeypatch):
    """The strip helper accepts a list of row dicts (the production caller passes `evidence`),
    not only a pool dict."""
    monkeypatch.setenv(_STRIP_ENV, "1")
    rows = [
        {"evidence_id": "A", "content_relevance_label": "relevant"},
        {"evidence_id": "B", "topic_offtopic_demoted": True, "content_relevance_label": "demoted"},
        {"evidence_id": "C", "topic_offtopic_demoted": True, "content_relevance_label": "relevant"},
    ]
    plan = _msg.SectionPlan(title="Sec", focus="f", ev_ids=["A", "B", "C"], archetype="")
    out = _msg._strip_offtopic_ev_ids_from_plans([plan], rows)
    assert out[0].ev_ids == ["A", "C"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
