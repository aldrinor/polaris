"""Codex+Fable gate-fix P1-3 — ``verified_compose._basket_confirmed_offtopic`` missing-member bug.

Pure Python. The prior impl looked ONLY at the RESOLVED subset of members, so a basket with one
resolved-off-topic member PLUS other members that are MISSING from the pool was wrongly WITHHELD.
Precision-first contract: ANY unresolved / missing / id-less / unjudged / relevant / escalated member
PROTECTS the whole basket; withhold ONLY when EVERY member resolves in the pool AND every one is
``_is_confirmed_offtopic``. (The positive-relevance override inside ``_is_confirmed_offtopic`` is kept.)
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

vc = importlib.import_module("src.polaris_graph.generator.verified_compose")


def _member(eid):
    return SimpleNamespace(evidence_id=eid)


def _basket(*eids):
    return SimpleNamespace(supporting_members=[_member(e) for e in eids])


def _pool():
    return {
        "on": {"content_relevance_label": "relevant"},
        "off1": {"topic_offtopic_demoted": True, "content_relevance_label": "demoted"},
        "off2": {"topic_offtopic_demoted": True, "content_relevance_label": "demoted"},
        "prot": {"topic_offtopic_demoted": True, "content_relevance_label": "escalated_relevant"},
        "unjudged": {},
    }


# ── THE FIX: a missing/unresolved member protects a basket with an off-topic member ──────────────
def test_missing_member_protects_basket():
    """[off1 (resolved off-topic), absent (NOT in pool)] => KEEP (False). The prior impl returned
    True (withheld) because it ignored the unresolved member."""
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket("off1", "absent_from_pool"), pool) is False


def test_idless_member_protects_basket():
    """[off1 (resolved off-topic), '' (id-less)] => KEEP (False)."""
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket("off1", ""), pool) is False


# ── preserved behaviour (existing contract still holds) ──────────────────────────────────────────
def test_all_members_resolved_and_offtopic_withholds():
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket("off1", "off2"), pool) is True
    assert vc._basket_confirmed_offtopic(_basket("off1"), pool) is True


def test_mixed_basket_kept():
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket("off1", "on"), pool) is False


def test_protected_override_kept():
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket("prot"), pool) is False
    # even mixed with a confirmed-off member, the override protects the basket
    assert vc._basket_confirmed_offtopic(_basket("off1", "prot"), pool) is False


def test_unjudged_member_protects():
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket("off1", "unjudged"), pool) is False


def test_empty_and_missing_pool_keep():
    pool = _pool()
    assert vc._basket_confirmed_offtopic(_basket(), pool) is False        # no members => keep
    assert vc._basket_confirmed_offtopic(_basket("absent"), pool) is False  # single missing => keep


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
