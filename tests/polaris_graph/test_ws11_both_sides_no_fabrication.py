"""I-deepfix-001 WS-11 — two-sides SAFEGUARD: a counter-side is REFERENCED only when it truly exists,
and is NEVER fabricated when no refuting cluster was found.

Behavioral, offline, read-only against the FROZEN faithfulness engine. This test does NOT edit the engine;
it LOCKS IN the existing safeguard in ``provenance_generator._basket_for_biblio`` (~line 3329) so a future
edit that manufactures a counter-side out of nothing FAILS here.

The safeguard (per the frozen function): the bibliography projection surfaces ``refuter_cluster_ids`` ONLY
from what the upstream basket already computed — a contested basket carries its real refuting cluster ids
through, and a basket with no refuters yields an EMPTY tuple. The refuter side is a REFERENCE to the
refuting clusters (the both-sides neutral block), never derived/synthesized from the supporting members.

The function is duck-typed (reads every field via ``getattr``), so minimal ``SimpleNamespace`` stand-ins with
exactly the attributes the function reads are a faithful, dependency-free mock of a real ``ClaimBasket``.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.polaris_graph.generator.provenance_generator import _basket_for_biblio  # noqa: E402


def _member(evidence_id: str, span_verdict: str = "SUPPORTS") -> SimpleNamespace:
    """A minimal duck-typed supporting member with the attributes _basket_for_biblio reads."""
    return SimpleNamespace(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T1",
        origin_cluster_id="clu_support",
        credibility_weight=1.0,
        authority_score=0.9,
        span_verdict=span_verdict,
        member_tier="ENTAILED",
        direct_quote="the cited span text",
    )


def _basket(*, supporting_members, refuter_cluster_ids, verdict) -> SimpleNamespace:
    """A minimal duck-typed ClaimBasket stand-in.

    ``refuter_cluster_ids`` is passed EXACTLY as the caller supplies it (including the
    "attribute absent" case via the sentinel below) so we can prove the projection never
    invents a counter-side.
    """
    ns = SimpleNamespace(
        claim_cluster_id="clu_claim_1",
        claim_text="Drug X reduces event rate.",
        subject="Drug X",
        predicate="reduces event rate",
        verified_support_origin_count=len(supporting_members),
        total_clustered_origin_count=len(supporting_members),
        weight_mass=float(len(supporting_members)),
        basket_verdict=verdict,
        supporting_members=list(supporting_members),
    )
    if refuter_cluster_ids is not _ABSENT:
        ns.refuter_cluster_ids = refuter_cluster_ids
    return ns


# sentinel: "the basket object has NO refuter_cluster_ids attribute at all"
_ABSENT = object()


def test_contested_basket_references_the_real_counter_side():
    # A genuinely contested basket carries real refuting cluster ids => the projection REFERENCES them.
    basket = _basket(
        supporting_members=[_member("ev_a"), _member("ev_b")],
        refuter_cluster_ids=("clu_refute_1", "clu_refute_2"),
        verdict="contested",
    )
    out = _basket_for_biblio(basket)
    assert out["refuter_cluster_ids"] == ("clu_refute_1", "clu_refute_2"), (
        "a contested basket must carry its real refuting cluster ids through (both-sides referenced)"
    )


def test_uncontested_basket_fabricates_no_counter_side_empty_list():
    # No refuting cluster was found (empty). The projection MUST NOT invent one.
    basket = _basket(
        supporting_members=[_member("ev_a"), _member("ev_b"), _member("ev_c")],
        refuter_cluster_ids=[],  # honest "no refuters" — the WEIGHT-not-FILTER path found none
        verdict="full",
    )
    out = _basket_for_biblio(basket)
    assert out["refuter_cluster_ids"] == (), (
        "an uncontested basket must yield an EMPTY refuter set — never a fabricated counter-side"
    )


def test_absent_refuter_attribute_yields_empty_not_fabricated():
    # The basket object never even computed a refuter field => getattr default, still empty (no fabrication).
    basket = _basket(
        supporting_members=[_member("ev_a")],
        refuter_cluster_ids=_ABSENT,  # attribute genuinely absent on the object
        verdict="full",
    )
    assert not hasattr(basket, "refuter_cluster_ids")
    out = _basket_for_biblio(basket)
    assert out["refuter_cluster_ids"] == (), (
        "a basket with no refuter attribute must project to an empty counter-side, never a synthesized one"
    )


def test_none_refuter_yields_empty_not_fabricated():
    # A None refuter field (upstream sentinel) must also collapse to empty, not error, not fabricate.
    basket = _basket(
        supporting_members=[_member("ev_a")],
        refuter_cluster_ids=None,
        verdict="full",
    )
    out = _basket_for_biblio(basket)
    assert out["refuter_cluster_ids"] == ()


def test_counter_side_is_not_derived_from_supporting_members():
    # The core no-fabrication guard: many strong SUPPORTS members, zero refuters => still empty.
    # This proves the counter-side is NOT manufactured out of the support side (WEIGHT-not-FILTER: a
    # one-sided-but-well-supported claim stays one-sided, it never grows a fake opposition).
    basket = _basket(
        supporting_members=[_member(f"ev_{i}") for i in range(6)],
        refuter_cluster_ids=(),
        verdict="full",
    )
    out = _basket_for_biblio(basket)
    assert out["verified_support_origin_count"] == 6, "support side is surfaced faithfully"
    assert out["refuter_cluster_ids"] == (), (
        "six supporting origins and zero refuters must NOT synthesize any counter-side reference"
    )


def test_refuter_ids_are_stringified_faithfully_from_the_basket_only():
    # The projection stringifies the basket's OWN refuter ids verbatim (order-preserving), never invented.
    basket = _basket(
        supporting_members=[_member("ev_a")],
        refuter_cluster_ids=(7, "clu_9"),
        verdict="contested",
    )
    out = _basket_for_biblio(basket)
    assert out["refuter_cluster_ids"] == ("7", "clu_9"), (
        "refuter ids come only from the basket's own field, stringified in order"
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
